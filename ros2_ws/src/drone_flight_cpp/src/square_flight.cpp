// C++ port of drone_localization/square_flight.py.
//
// Same OFFBOARD profile as Python: stream OffboardControlMode +
// TrajectorySetpoint at 20 Hz, engage OFFBOARD, arm, climb via the first
// waypoint (0, 0, -altitude), fly the 10 m square (optional cruise_speed / yaw_spin_rate), land, then Hold.
// Optional ROS params (defaults preserve baseline): cruise_speed (m/s), yaw_spin_rate (rad/s).
// Env helpers in scripts/run-vio-stress.sh: SQUARE_SPEED, SQUARE_YAW_SPIN.
// Velocity FF tapers and yaw-spin pauses inside a settle zone so corners
// remain reachable (faster_motion previously timed out on wp1).
//
// Why not ModeExecutor + TrajectorySetpointType for the climb:
// PX4 only sets vehicle_constraints.want_takeoff from a position/velocity
// setpoint when flag_control_offboard_enabled is true (classic OFFBOARD).
// External modes never set that flag, so arm → scheduleMode stays on the
// ground until COM_DISARM_PRFLT (10 s). PX4's built-in takeoff clears the
// timer but inserts a different climb than Python and failed the RMSE gate.
// Matching Python's OFFBOARD climb is the smallest fix that both leaves the
// ground and keeps the climb samples in the same envelope as the baseline.
#include <px4_msgs/msg/offboard_control_mode.hpp>
#include <px4_msgs/msg/trajectory_setpoint.hpp>
#include <px4_msgs/msg/vehicle_command.hpp>
#include <px4_msgs/msg/vehicle_local_position.hpp>
#include <px4_msgs/msg/vehicle_status.hpp>
#include <rclcpp/rclcpp.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <optional>
#include <stdexcept>
#include <limits>
#include <string>
#include <vector>

using namespace std::chrono_literals;  // NOLINT

class SquareFlightNode : public rclcpp::Node
{
public:
  SquareFlightNode()
  : Node("square_flight_cpp")
  {
    square_side_ = declare_parameter("square_side", 10.0);
    altitude_ = declare_parameter("altitude", 5.0);
    max_altitude_ = declare_parameter("max_altitude", 6.0);
    corner_hold_time_ = declare_parameter("corner_hold_time", 3.0);
    mission_timeout_ = declare_parameter("mission_timeout", 180.0);
    waypoint_tolerance_ = declare_parameter("waypoint_tolerance", 0.5);
    // 0 = position-only (PX4 MPC cruise). >0 fills velocity toward the waypoint.
    cruise_speed_ = declare_parameter("cruise_speed", 0.0);
    // Continuous yaw rate (rad/s) while Flying; 0 keeps yaw=0 (baseline).
    yaw_spin_rate_ = declare_parameter("yaw_spin_rate", 0.0);

    if (altitude_ > max_altitude_) {
      throw std::runtime_error("Target altitude exceeds safety limit");
    }

    const float z = static_cast<float>(-altitude_);
    const float side = static_cast<float>(square_side_);
    waypoints_ = {
      {0.f, 0.f, z},
      {side, 0.f, z},
      {side, side, z},
      {0.f, side, z},
      {0.f, 0.f, z},
    };

    // PX4 v1.17 + px4_msgs release/1.17: BEST_EFFORT + TRANSIENT_LOCAL
    rclcpp::QoS qos_px4(10);
    qos_px4.best_effort();
    qos_px4.transient_local();

    offboard_control_mode_pub_ =
      create_publisher<px4_msgs::msg::OffboardControlMode>("/fmu/in/offboard_control_mode", qos_px4);
    trajectory_setpoint_pub_ =
      create_publisher<px4_msgs::msg::TrajectorySetpoint>("/fmu/in/trajectory_setpoint", qos_px4);
    vehicle_command_pub_ =
      create_publisher<px4_msgs::msg::VehicleCommand>("/fmu/in/vehicle_command", qos_px4);

    status_sub_ = create_subscription<px4_msgs::msg::VehicleStatus>(
      "/fmu/out/vehicle_status_v1", qos_px4,
      [this](px4_msgs::msg::VehicleStatus::SharedPtr msg) {vehicle_status_ = msg;});
    position_sub_ = create_subscription<px4_msgs::msg::VehicleLocalPosition>(
      "/fmu/out/vehicle_local_position_v1", qos_px4,
      [this](px4_msgs::msg::VehicleLocalPosition::SharedPtr msg) {vehicle_local_position_ = msg;});

    timer_ = create_wall_timer(50ms, std::bind(&SquareFlightNode::controlLoop, this));

    RCLCPP_INFO(
      get_logger(),
      "Square flight (C++ OFFBOARD): side=%.1fm, alt=%.1fm, hold=%.1fs, timeout=%.0fs, "
      "cruise_speed=%.1fm/s, yaw_spin=%.2f rad/s",
      square_side_, altitude_, corner_hold_time_, mission_timeout_, cruise_speed_,
      yaw_spin_rate_);
  }

private:
  enum class State { Init, Preflight, Arming, Flying, Landing, Complete };

  uint64_t nowUs() const
  {
    return static_cast<uint64_t>(get_clock()->now().nanoseconds() / 1000);
  }

  void publishOffboardControlMode()
  {
    px4_msgs::msg::OffboardControlMode msg{};
    msg.timestamp = nowUs();
    msg.position = true;
    msg.velocity = cruise_speed_ > 0.0;
    msg.acceleration = false;
    msg.attitude = false;
    msg.body_rate = false;
    offboard_control_mode_pub_->publish(msg);
  }

  void publishTrajectorySetpoint(
    float x, float y, float z, float yaw,
    float vx = std::numeric_limits<float>::quiet_NaN(),
    float vy = std::numeric_limits<float>::quiet_NaN(),
    float vz = std::numeric_limits<float>::quiet_NaN(),
    float yawspeed = std::numeric_limits<float>::quiet_NaN())
  {
    px4_msgs::msg::TrajectorySetpoint msg{};
    msg.timestamp = nowUs();
    msg.position = {x, y, z};
    msg.yaw = yaw;
    const float nan = std::numeric_limits<float>::quiet_NaN();
    msg.velocity = {vx, vy, vz};
    msg.acceleration = {nan, nan, nan};
    msg.jerk = {nan, nan, nan};
    msg.yawspeed = yawspeed;
    trajectory_setpoint_pub_->publish(msg);
  }

  void publishWaypointSetpoint(const std::array<float, 3> & wp)
  {
    // Settle zone: position-only (no vel FF, no yaw spin) so we can enter the
    // waypoint ball. Full cruise_speed all the way in caused endless overshoot
    // on faster_motion (never reached wp1 within 0.5 m before mission timeout).
    const float settle_m = std::max(1.5f, static_cast<float>(2.0 * waypoint_tolerance_));
    float dist = std::numeric_limits<float>::infinity();
    float dx = 0.f, dy = 0.f, dz = 0.f;
    if (vehicle_local_position_) {
      dx = wp[0] - vehicle_local_position_->x;
      dy = wp[1] - vehicle_local_position_->y;
      dz = wp[2] - vehicle_local_position_->z;
      dist = std::sqrt(dx * dx + dy * dy + dz * dz);
    }
    const bool settling = dist < settle_m;

    float yaw = 0.f;
    float yawspeed = std::numeric_limits<float>::quiet_NaN();
    if (yaw_spin_rate_ != 0.0) {
      const auto now = std::chrono::steady_clock::now();
      if (!spin_yaw_) {
        spin_yaw_ = 0.f;
        spin_last_ = now;
      }
      if (!settling) {
        const double dt = std::chrono::duration<double>(now - *spin_last_).count();
        spin_yaw_ = static_cast<float>(*spin_yaw_ + yaw_spin_rate_ * dt);
        spin_last_ = now;
        yaw = *spin_yaw_;
        yawspeed = static_cast<float>(yaw_spin_rate_);
      } else {
        yaw = *spin_yaw_;
        yawspeed = 0.f;
        spin_last_ = now;
      }
    }

    float vx = std::numeric_limits<float>::quiet_NaN();
    float vy = std::numeric_limits<float>::quiet_NaN();
    float vz = std::numeric_limits<float>::quiet_NaN();
    if (cruise_speed_ > 0.0 && vehicle_local_position_) {
      if (settling || dist < 1e-3f) {
        vx = 0.f;
        vy = 0.f;
        vz = 0.f;
      } else {
        const float speed = std::min(
          static_cast<float>(cruise_speed_), std::max(0.5f, dist));
        const float scale = speed / dist;
        vx = dx * scale;
        vy = dy * scale;
        vz = dz * scale;
      }
    }
    publishTrajectorySetpoint(wp[0], wp[1], wp[2], yaw, vx, vy, vz, yawspeed);
  }

  void publishVehicleCommand(uint32_t command, float p1 = 0.f, float p2 = 0.f, float p3 = 0.f)
  {
    px4_msgs::msg::VehicleCommand msg{};
    msg.timestamp = nowUs();
    msg.command = command;
    msg.param1 = p1;
    msg.param2 = p2;
    msg.param3 = p3;
    msg.target_system = 1;
    msg.target_component = 1;
    msg.source_system = 1;
    msg.source_component = 1;
    msg.from_external = true;
    vehicle_command_pub_->publish(msg);
  }

  void engageOffboardMode()
  {
    publishVehicleCommand(px4_msgs::msg::VehicleCommand::VEHICLE_CMD_DO_SET_MODE, 1.f, 6.f);
  }

  void engageHoldMode()
  {
    // AUTO_LOITER (Hold): armable after an offboard landing.
    publishVehicleCommand(
      px4_msgs::msg::VehicleCommand::VEHICLE_CMD_DO_SET_MODE, 1.f, 4.f, 3.f);
  }

  void arm()
  {
    publishVehicleCommand(px4_msgs::msg::VehicleCommand::VEHICLE_CMD_COMPONENT_ARM_DISARM, 1.f);
  }

  void land()
  {
    publishVehicleCommand(px4_msgs::msg::VehicleCommand::VEHICLE_CMD_NAV_LAND);
  }

  float distanceToWaypoint(const std::array<float, 3> & wp) const
  {
    if (!vehicle_local_position_) {
      return std::numeric_limits<float>::infinity();
    }
    const float dx = vehicle_local_position_->x - wp[0];
    const float dy = vehicle_local_position_->y - wp[1];
    const float dz = vehicle_local_position_->z - wp[2];
    return std::sqrt(dx * dx + dy * dy + dz * dz);
  }

  void controlLoop()
  {
    if (!vehicle_status_ || !vehicle_local_position_) {
      return;
    }

    const auto now = std::chrono::steady_clock::now();

    if (mission_start_ && state_ != State::Landing && state_ != State::Complete) {
      const double elapsed =
        std::chrono::duration<double>(now - *mission_start_).count();
      if (elapsed > mission_timeout_) {
        RCLCPP_ERROR(get_logger(), "Mission timeout (%.0fs), landing", mission_timeout_);
        land();
        offboard_setpoint_counter_ = 0;
        state_ = State::Landing;
        return;
      }
    }

    if (state_ == State::Flying &&
      vehicle_local_position_->z < static_cast<float>(-max_altitude_ - 0.5))
    {
      RCLCPP_ERROR(
        get_logger(), "Altitude %.1fm exceeds max %.1fm, landing",
        -vehicle_local_position_->z, max_altitude_);
      land();
      offboard_setpoint_counter_ = 0;
      state_ = State::Landing;
      return;
    }

    switch (state_) {
      case State::Init:
        if (vehicle_local_position_->z_valid && vehicle_local_position_->xy_valid) {
          if (vehicle_status_->pre_flight_checks_pass) {
            RCLCPP_INFO(get_logger(), "Preflight checks passed, starting mission");
            mission_start_ = now;
            state_ = State::Preflight;
            offboard_setpoint_counter_ = 0;
          } else {
            if (!preflight_fail_logged_) {
              RCLCPP_WARN(get_logger(), "Waiting for preflight checks to pass...");
              preflight_fail_logged_ = true;
            }
            // Left in OFFBOARD by a previous run while disarmed: switch to Hold.
            if (vehicle_status_->nav_state == 14 && vehicle_status_->arming_state != 2) {
              if ((++hold_requests_ % 20) == 1) {
                RCLCPP_INFO(get_logger(), "Disarmed in OFFBOARD; switching to Hold");
                engageHoldMode();
              }
            }
          }
        }
        break;

      case State::Preflight:
        // Stream setpoints for 2 s before engaging OFFBOARD (PX4 requirement).
        publishOffboardControlMode();
        publishTrajectorySetpoint(0.f, 0.f, 0.f, 0.f);
        ++offboard_setpoint_counter_;
        if (offboard_setpoint_counter_ > 40) {
          RCLCPP_INFO(get_logger(), "Switching to offboard mode");
          engageOffboardMode();
          state_ = State::Arming;
          offboard_setpoint_counter_ = 0;
        }
        break;

      case State::Arming:
        publishOffboardControlMode();
        publishTrajectorySetpoint(0.f, 0.f, 0.f, 0.f);
        ++offboard_setpoint_counter_;
        if (offboard_setpoint_counter_ % 20 == 0) {
          if (vehicle_status_->nav_state != 14) {
            engageOffboardMode();
          }
          if (vehicle_status_->arming_state != 2) {
            arm();
          }
        }
        if (vehicle_status_->nav_state == 14 && vehicle_status_->arming_state == 2) {
          RCLCPP_INFO(get_logger(), "Armed and in offboard mode");
          corner_index_ = 0;
          corner_arrival_.reset();
          state_ = State::Flying;
        }
        break;

      case State::Flying: {
        const auto & wp = waypoints_[corner_index_];
        publishOffboardControlMode();
        publishWaypointSetpoint(wp);
        const float distance = distanceToWaypoint(wp);
        if (distance < static_cast<float>(waypoint_tolerance_)) {
          if (!corner_arrival_) {
            corner_arrival_ = now;
            RCLCPP_INFO(
              get_logger(), "Reached waypoint %zu: (%.1f, %.1f, %.1f)", corner_index_, wp[0],
              wp[1], wp[2]);
          }
          if (std::chrono::duration<double>(now - *corner_arrival_).count() >= corner_hold_time_) {
            corner_arrival_.reset();
            ++corner_index_;
            if (corner_index_ >= waypoints_.size()) {
              RCLCPP_INFO(get_logger(), "Square complete, landing");
              land();
              offboard_setpoint_counter_ = 0;
              state_ = State::Landing;
            } else {
              RCLCPP_INFO(get_logger(), "Moving to waypoint %zu", corner_index_);
            }
          }
        }
        break;
      }

      case State::Landing:
        // Stop streaming setpoints so PX4 can leave OFFBOARD for AUTO_LAND.
        if (offboard_setpoint_counter_ % 40 == 0) {
          land();
        }
        ++offboard_setpoint_counter_;
        if (vehicle_status_->arming_state != 2) {
          RCLCPP_INFO(get_logger(), "Mission complete (disarmed)");
          engageHoldMode();
          state_ = State::Complete;
        }
        break;

      case State::Complete:
        rclcpp::shutdown();
        break;
    }
  }

  double square_side_{10.0};
  double altitude_{5.0};
  double max_altitude_{6.0};
  double corner_hold_time_{3.0};
  double mission_timeout_{180.0};
  double waypoint_tolerance_{0.5};
  double cruise_speed_{0.0};
  double yaw_spin_rate_{0.0};

  std::vector<std::array<float, 3>> waypoints_;
  State state_{State::Init};
  size_t corner_index_{0};
  int offboard_setpoint_counter_{0};
  int hold_requests_{0};
  bool preflight_fail_logged_{false};
  std::optional<std::chrono::steady_clock::time_point> mission_start_;
  std::optional<std::chrono::steady_clock::time_point> corner_arrival_;
  std::optional<float> spin_yaw_;
  std::optional<std::chrono::steady_clock::time_point> spin_last_;

  px4_msgs::msg::VehicleStatus::SharedPtr vehicle_status_;
  px4_msgs::msg::VehicleLocalPosition::SharedPtr vehicle_local_position_;

  rclcpp::Publisher<px4_msgs::msg::OffboardControlMode>::SharedPtr offboard_control_mode_pub_;
  rclcpp::Publisher<px4_msgs::msg::TrajectorySetpoint>::SharedPtr trajectory_setpoint_pub_;
  rclcpp::Publisher<px4_msgs::msg::VehicleCommand>::SharedPtr vehicle_command_pub_;
  rclcpp::Subscription<px4_msgs::msg::VehicleStatus>::SharedPtr status_sub_;
  rclcpp::Subscription<px4_msgs::msg::VehicleLocalPosition>::SharedPtr position_sub_;
  rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  int exit_code = 0;
  try {
    auto node = std::make_shared<SquareFlightNode>();
    rclcpp::spin(node);
  } catch (const std::exception & e) {
    RCLCPP_ERROR(rclcpp::get_logger("square_flight_cpp"), "%s", e.what());
    exit_code = 1;
  }
  if (rclcpp::ok()) {
    rclcpp::shutdown();
  }
  return exit_code;
}
