// C++ port of drone_localization/square_flight.py using px4-ros2-interface-lib.
//
// Same profile: 10 m square at 5 m (NED z=-5), position setpoints, 0.5 m
// waypoint tolerance, 3 s hold per corner, 180 s timeout, soft altitude
// abort above max_altitude + 0.5 m, then land.
//
// Structure: an external mode ("Square Flight") streams the position
// setpoints; a mode executor arms, runs the mode, lands and waits for
// disarm. Executor activation is ActivateImmediately, so PX4 never
// sits in OFFBOARD after landing (the Python node's Hold workaround is
// not needed; the startup Hold switch is kept for runs that follow a
// Python run).
#include <px4_ros2/components/mode.hpp>
#include <px4_ros2/components/mode_executor.hpp>
#include <px4_ros2/components/node_with_mode.hpp>
#include <px4_ros2/control/setpoint_types/experimental/trajectory.hpp>
#include <px4_ros2/odometry/local_position.hpp>

#include <px4_msgs/msg/vehicle_command.hpp>
#include <px4_msgs/msg/vehicle_local_position.hpp>
#include <px4_msgs/msg/vehicle_status.hpp>
#include <rclcpp/rclcpp.hpp>

#include <Eigen/Core>
#include <array>
#include <chrono>
#include <cstdlib>
#include <stdexcept>
#include <string>
#include <thread>

using namespace std::chrono_literals;  // NOLINT

static const std::string kModeName = "Square Flight";

struct Params
{
  float side{10.f};
  float altitude{5.f};
  float max_altitude{6.f};
  double hold_s{3.0};
  double timeout_s{180.0};
  float tolerance{0.5f};
};

static int g_exit_code = 1;

class SquareMode : public px4_ros2::ModeBase
{
public:
  explicit SquareMode(rclcpp::Node & node)
  : ModeBase(node, kModeName)
  {
    p_.side = static_cast<float>(node.declare_parameter("square_side", 10.0));
    p_.altitude = static_cast<float>(node.declare_parameter("altitude", 5.0));
    p_.max_altitude = static_cast<float>(node.declare_parameter("max_altitude", 6.0));
    p_.hold_s = node.declare_parameter("corner_hold_time", 3.0);
    p_.timeout_s = node.declare_parameter("mission_timeout", 180.0);
    p_.tolerance = static_cast<float>(node.declare_parameter("waypoint_tolerance", 0.5));
    if (p_.altitude > p_.max_altitude) {
      throw std::runtime_error("Target altitude exceeds safety limit");
    }
    const float z = -p_.altitude;
    wps_ = {{
      {0.f, 0.f, z}, {p_.side, 0.f, z}, {p_.side, p_.side, z}, {0.f, p_.side, z}, {0.f, 0.f, z}}};
    setpoint_ = std::make_shared<px4_ros2::TrajectorySetpointType>(*this);
    local_pos_ = std::make_shared<px4_ros2::OdometryLocalPosition>(*this);
    setSetpointUpdateRate(20.f);  // match the Python node's 20 Hz loop
    RCLCPP_INFO(
      node.get_logger(), "Square flight (C++): side=%.1fm, alt=%.1fm, hold=%.1fs, timeout=%.0fs",
      p_.side, p_.altitude, p_.hold_s, p_.timeout_s);
  }

  void onActivate() override
  {
    idx_ = 0;
    arrived_ = false;
    start_ = node().get_clock()->now();
  }

  void onDeactivate() override {}

  void updateSetpoint(float) override
  {
    const rclcpp::Time now = node().get_clock()->now();
    const Eigen::Vector3f pos = local_pos_->positionNed();
    if ((now - start_).seconds() > p_.timeout_s) {
      RCLCPP_ERROR(node().get_logger(), "Mission timeout (%.0fs), landing", p_.timeout_s);
      completed(px4_ros2::Result::Timeout);
      return;
    }
    if (pos.z() < -p_.max_altitude - 0.5f) {
      RCLCPP_ERROR(node().get_logger(), "Altitude %.1fm exceeds max, landing", -pos.z());
      completed(px4_ros2::Result::Rejected);
      return;
    }
    const Eigen::Vector3f & wp = wps_[idx_];
    setpoint_->updatePosition(wp);  // yaw unset (NaN); Python sent yaw 0
    if ((pos - wp).norm() < p_.tolerance) {
      if (!arrived_) {
        arrived_ = true;
        arrival_ = now;
        RCLCPP_INFO(
          node().get_logger(), "Reached waypoint %zu: (%.1f, %.1f, %.1f)", idx_, wp.x(), wp.y(),
          wp.z());
      }
      if ((now - arrival_).seconds() >= p_.hold_s) {
        arrived_ = false;
        if (++idx_ >= wps_.size()) {
          RCLCPP_INFO(node().get_logger(), "Square complete, landing");
          completed(px4_ros2::Result::Success);
          return;
        }
        RCLCPP_INFO(node().get_logger(), "Moving to waypoint %zu", idx_);
      }
    }
  }

private:
  Params p_;
  std::array<Eigen::Vector3f, 5> wps_;
  std::shared_ptr<px4_ros2::TrajectorySetpointType> setpoint_;
  std::shared_ptr<px4_ros2::OdometryLocalPosition> local_pos_;
  size_t idx_{0};
  bool arrived_{false};
  rclcpp::Time start_{}, arrival_{};
};

class SquareExecutor : public px4_ros2::ModeExecutorBase
{
public:
  explicit SquareExecutor(px4_ros2::ModeBase & owned_mode)
  : ModeExecutorBase(
      px4_ros2::ModeExecutorBase::Settings{}.activate(
        px4_ros2::ModeExecutorBase::Settings::Activation::ActivateImmediately),
      owned_mode),
    node_(owned_mode.node())
  {
  }

  void onActivate() override
  {
    if (started_) {return;}
    started_ = true;
    RCLCPP_INFO(node_.get_logger(), "Executor active, arming");
    arm([this](px4_ros2::Result r) {
        if (r != px4_ros2::Result::Success) {return finish("arm", r);}
        RCLCPP_INFO(node_.get_logger(), "Armed, flying square");
        scheduleMode(ownedMode().id(), [this](px4_ros2::Result r2) {
          mission_ok_ = (r2 == px4_ros2::Result::Success);
          if (!mission_ok_) {
            RCLCPP_ERROR(node_.get_logger(), "Square mode ended: %s", resultToString(r2));
          }
          land([this](px4_ros2::Result r3) {
            if (r3 != px4_ros2::Result::Success) {return finish("land", r3);}
            waitUntilDisarmed([this](px4_ros2::Result r4) {
              if (r4 != px4_ros2::Result::Success) {return finish("disarm", r4);}
              RCLCPP_INFO(node_.get_logger(), "Mission complete (disarmed)");
              g_exit_code = mission_ok_ ? 0 : 1;
              rclcpp::shutdown();
            });
          });
        });
      });
  }

  void onDeactivate(DeactivateReason reason) override
  {
    if (started_ && !done_) {
      RCLCPP_WARN(
        node_.get_logger(), "Executor deactivated (%s)",
        reason == DeactivateReason::FailsafeActivated ? "failsafe" : "other");
    }
  }

private:
  void finish(const char * step, px4_ros2::Result r)
  {
    done_ = true;
    RCLCPP_ERROR(node_.get_logger(), "%s failed: %s", step, resultToString(r));
    g_exit_code = 1;
    rclcpp::shutdown();
  }

  rclcpp::Node & node_;
  bool started_{false}, done_{false}, mission_ok_{false};
};

// Wait for valid local position and passing preflight checks before
// registering, like the Python node's INIT state. Switches a disarmed
// vehicle left in OFFBOARD (nav_state 14) to Hold.
static bool waitReady()
{
  auto n = std::make_shared<rclcpp::Node>("square_flight_cpp_wait");
  rclcpp::QoS qos = rclcpp::QoS(10).best_effort().transient_local();
  px4_msgs::msg::VehicleStatus::SharedPtr st;
  px4_msgs::msg::VehicleLocalPosition::SharedPtr lp;
  auto s1 = n->create_subscription<px4_msgs::msg::VehicleStatus>(
    "/fmu/out/vehicle_status_v1", qos, [&](px4_msgs::msg::VehicleStatus::SharedPtr m) {st = m;});
  auto s2 = n->create_subscription<px4_msgs::msg::VehicleLocalPosition>(
    "/fmu/out/vehicle_local_position_v1", qos,
    [&](px4_msgs::msg::VehicleLocalPosition::SharedPtr m) {lp = m;});
  auto cmd = n->create_publisher<px4_msgs::msg::VehicleCommand>("/fmu/in/vehicle_command", qos);
  bool logged = false;
  int hold_req = 0;
  const auto deadline = std::chrono::steady_clock::now() + 120s;
  while (rclcpp::ok() && std::chrono::steady_clock::now() < deadline) {
    rclcpp::spin_some(n);
    if (st && lp && lp->xy_valid && lp->z_valid) {
      if (st->pre_flight_checks_pass) {
        RCLCPP_INFO(n->get_logger(), "Preflight checks passed, starting mission");
        return true;
      }
      if (!logged) {RCLCPP_WARN(n->get_logger(), "Waiting for preflight checks to pass..."); logged = true;}
      if (st->nav_state == 14 && st->arming_state != 2 && (hold_req++ % 20) == 0) {
        RCLCPP_INFO(n->get_logger(), "Disarmed in OFFBOARD; switching to Hold");
        px4_msgs::msg::VehicleCommand c{};
        c.timestamp = n->get_clock()->now().nanoseconds() / 1000;
        c.command = px4_msgs::msg::VehicleCommand::VEHICLE_CMD_DO_SET_MODE;
        c.param1 = 1.f; c.param2 = 4.f; c.param3 = 3.f;
        c.target_system = 1; c.target_component = 1;
        c.source_system = 1; c.source_component = 1; c.from_external = true;
        cmd->publish(c);
      }
    }
    std::this_thread::sleep_for(50ms);
  }
  RCLCPP_ERROR(n->get_logger(), "Vehicle not ready within 120 s");
  return false;
}

using SquareNode = px4_ros2::NodeWithModeExecutor<SquareExecutor, SquareMode>;

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  if (!waitReady()) {rclcpp::shutdown(); return 1;}
  try {
    rclcpp::spin(std::make_shared<SquareNode>("square_flight_cpp", false));
  } catch (const std::exception & e) {
    RCLCPP_ERROR(rclcpp::get_logger("square_flight_cpp"), "%s", e.what());
    g_exit_code = 1;
  }
  if (rclcpp::ok()) {rclcpp::shutdown();}
  return g_exit_code;
}
