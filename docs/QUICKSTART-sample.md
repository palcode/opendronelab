# View the v0.1.0 sample bag in Foxglove

This walkthrough uses the prepared `odl-v0.1.0-mc_gps-sample.mcap`
clip: about 10 seconds mid-square from a passing `mc_gps` SITL flight
(`20261113_195035`, official EKF2 Umeyama xy 0.256907 m, gate 0.39 m).
The clip has ground truth and PX4 EKF2 topics only. It does **not**
include a camera stream, so you do not need `RECORD_CAMERA=1`.

The file is not in the git tree. Download `odl-v0.1.0-mc_gps-sample.mcap`
from the [v0.1.0 release](https://github.com/palcode/opendronelab/releases/tag/v0.1.0)
and verify the checksum below.

SHA-256 (`odl-v0.1.0-mc_gps-sample.mcap`):

```
108878470a0ed75f909ff8b17219a83230f3608199fbefe0264e4bc96d31c703
```

OpenDroneLab is **not flight-certified**. This clip is SITL.

## 1. Import the layout

The in-tree Foxglove layout is
[`tools/foxglove/opendronelab-localization.json`](../tools/foxglove/opendronelab-localization.json).

In the Foxglove desktop app: **Layouts → Import from file** and choose
that JSON. The layout includes:

- a 3D / plot view of `/ground_truth/odometry` (teal in our brand
  usage) and `/fmu/out/vehicle_local_position_v1`
- arming and land-detected status
- camera panes, which stay empty on this GPS-only sample

The layout has not yet been re-verified inside the Foxglove app in
this repository’s setup notes; topic and field names match PX4 v1.17
`px4_msgs` and this sample bag.

## 2. Open the mcap

- **Foxglove desktop (optional host install):**
  [https://foxglove.dev/download](https://foxglove.dev/download). Open
  the `.mcap` as a local file. A host install is optional and is not
  part of the development image.
- **Foxglove web app:** you can open a local file in the browser app.
  Uploading a file to the hosted web app shares it with Foxglove’s
  site; only do that if you are comfortable sharing this SITL clip.
- **mcap CLI** (in `opendronelab-dev:latest`), if you only want
  counts and rates:

  ```bash
  mcap info odl-v0.1.0-mc_gps-sample.mcap
  ```

  Expect about 9.983 s, 3038 messages, eight channels including
  `/ground_truth/odometry` and `/fmu/out/vehicle_local_position_v1`.

## 3. What you should see

On this clip the vehicle is mid-square at about 5 m AGL, moving along
the far side of the 10 m square and into the next leg. The ground
truth and EKF2 paths should track closely (the official full-flight
xy RMSE is 0.26 m). There is no OpenVINS stream and no raw camera
image.

The example report (`report.md` / `report.html` plus plots) covers
the **full** source flight, not only these ten seconds. See
[release-notes/v0.1.0.md](release-notes/v0.1.0.md).
