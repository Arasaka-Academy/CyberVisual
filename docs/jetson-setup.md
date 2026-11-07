# CyberVisual Jetson Setup

For versioned production releases through GitHub OIDC and Tailscale SSH, follow
[Jetson automatic deployment](jetson-deploy.md). That path requires explicit
administrator preparation and is disabled by default; the legacy installer below
is not the per-release deployment command.

## 1. System Packages

Place the checkout at `/opt/cybervisual` for the default systemd unit. To use another location, update the paths in `deploy/systemd/cybervisual.service` before installing.

Run from the repository root:

```bash
./scripts/install_jetson.sh
```

The installer uses apt for JetPack-provided hardware packages:

- `python3-opencv`
- `v4l-utils`
- `python3-venv`
- `python3-pip`
- `libopenblas-base`
- `python3-gi`, `python3-gst-1.0`, `gir1.2-gst-rtsp-server-1.0`
- `gstreamer1.0-tools` and base/good/bad/ugly plugins

The Python virtual environment is created with `--system-site-packages` so it can import JetPack's OpenCV, TensorRT, and CUDA packages.

This repository includes committed `frontend/dist` assets because JetPack 4.x images often ship old Node.js versions. On-device frontend rebuilds require Node.js 20 or newer; otherwise the installer uses the committed assets.

The installer also installs, enables, and starts the systemd service by default. Use `INSTALL_SYSTEMD=0 ./scripts/install_jetson.sh` when you only want dependencies, or `START_SYSTEMD=0 ./scripts/install_jetson.sh` when you want the service installed for the next reboot without starting it now.

## 2. Camera Check

```bash
v4l2-ctl --list-devices
v4l2-ctl --device=/dev/video0 --list-formats-ext
```

If the camera is not `/dev/video0`, set either:

```bash
export CYBERVISUAL_CAMERA_INDEX=1
```

or:

```bash
export CYBERVISUAL_CAMERA_DEVICE=/dev/video2
```

## 3. Model Engine

For this Jetson Nano class of device, start with OpenCV DNN YOLO if PyCUDA or a TensorRT engine is not ready:

```bash
./scripts/download_yolo_onnx.sh
export CYBERVISUAL_DETECTOR=opencv
export CYBERVISUAL_MODEL_PATH=models/yolov5n.onnx
```

For optimized TensorRT, generate an engine on the target Jetson or a matching JetPack 4 container:

```bash
./scripts/export_yolo_engine.sh yolov8n.pt models
```

The default TensorRT config expects:

```text
models/yolov8n_fp16.engine
```

If the engine export fails or FPS is too low, use the OpenCV ONNX fallback, a smaller YOLO variant, or lower image size. Keep `detector_backend=auto` during bring-up so the web app remains usable while the engine is missing.

## 4. Run Manually

```bash
./scripts/run_backend.sh
```

Then open:

```text
http://<jetson-ip>:8000
```

## 5. systemd Service

```bash
sudo journalctl -u cybervisual -f
```

The service runs from `/opt/cybervisual` by default and starts automatically after reboot. For a different production path, edit `deploy/systemd/cybervisual.service` before installing.

## 6. Optional ONVIF / RTSP Camera

The service reads `/etc/cybervisual/camera.env` when present and stores its stable
device UUID and PTZ presets in `/var/lib/cybervisual`. Existing installations keep
network camera output disabled until explicitly enabled with credentials.

Follow [network camera setup and acceptance](network-camera.md) to enable the
two H.264 streams, verify `nvv4l2h264enc`, and connect an ONVIF client. Keep PTZ
disabled on production cameras until a hardware driver is implemented and tested.
