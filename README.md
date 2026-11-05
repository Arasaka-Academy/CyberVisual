# CyberVisual

CyberVisual is an edge vision console for USB-camera object detection on Jetson Nano, with a YOLO TensorRT runtime and a black/green web dashboard. The backend streams an annotated MJPEG feed and REST status/config endpoints; the frontend shows live detections, system health, metrics, snapshots, and runtime controls.

Based on [nvidia-jetson-nano-visual](https://github.com/zhubby/nvidia-jetson-nano-visual) at commit `326f9e2`.

## IMX477 HQ Mount

View the [interactive assembly figure](https://arasaka-academy.github.io/CyberVisual/figure/) and download the printable 3MF files. The [print and assembly guide](models/imx477-hq/README.zh-CN.md) covers the camera mount, fasteners and reference dimensions.

GitHub Pages publishes the figure and its downloads automatically when these assets change on `main`. See [Pages deployment](docs/figure-pages.md) for the local preview and publishing workflow.

## Project Layout

- `backend/` - Flask backend, camera worker, detector adapters, MJPEG stream, REST API, tests.
- `frontend/` - React/Vite/TypeScript CyberVisual dashboard.
- `models/` - TensorRT engine and model export notes. Engine binaries are ignored by git.
- `scripts/` - Jetson install, engine export, and local run helpers.
- `deploy/systemd/` - systemd unit for boot-time service recovery.
- `docs/` - architecture and Jetson deployment notes.

## Local Demo

Use the synthetic camera and mock detector when developing without a Jetson or USB camera. The local development commands below use Python 3.12 and Node.js 22.

```bash
git clone https://github.com/Arasaka-Academy/CyberVisual.git
cd CyberVisual
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt

cd backend
python -m pytest

cd ../frontend
npm ci
npm test
npm run build

cd ../backend
CYBERVISUAL_SOURCE=synthetic CYBERVISUAL_DETECTOR=mock CYBERVISUAL_FRONTEND_DIST=../frontend/dist python -m cybervisual
```

Open `http://127.0.0.1:8000`.

From the repository root, `./scripts/run_demo.sh` starts the same local demo using `.venv`. Runtime environment variables use the `CYBERVISUAL_` prefix, including `CYBERVISUAL_HOST`, `CYBERVISUAL_PORT`, `CYBERVISUAL_CONFIG`, and `CYBERVISUAL_CAPTURE_DIR`.

## Jetson Nano Runtime

Target baseline:

- Jetson Nano 4GB
- JetPack 4.6.x / L4T R32.x
- USB UVC camera at `/dev/video0`
- TensorRT FP16 YOLO engine generated on the Jetson or a matching L4T container

```bash
./scripts/install_jetson.sh
./scripts/download_yolo_onnx.sh
# Optional TensorRT path, when PyCUDA and an engine-export environment are ready:
# ./scripts/export_yolo_engine.sh yolov8n.pt models
```

The installer creates the Python environment, installs the systemd unit, enables it, and starts `cybervisual` by default. The unit expects the checkout at `/opt/cybervisual`; see [Jetson setup](docs/jetson-setup.md) for deployment details. Set `INSTALL_SYSTEMD=0` to skip service installation, or `START_SYSTEMD=0` to install and enable the service without starting it immediately.

The web UI listens on `0.0.0.0:8000` by default. From another device on the same LAN, open `http://<jetson-ip>:8000`.

## Backend API

- `GET /stream.mjpg` - annotated MJPEG stream.
- `GET /api/status` - camera/model/FPS/latency/temperature/memory status.
- `GET /api/detections/latest` - latest frame detections.
- `GET /api/config` - runtime config.
- `PUT /api/config` - update thresholds, source, model path, allowlist, and resolution.
- `POST /api/snapshot` - save current frame and detection JSON into `captures/`.

## Notes

Runtime does not depend on the latest `ultralytics` package. On older JetPack 4.x devices without PyCUDA, use `models/yolov5n.onnx` with `detector_backend=opencv` for real YOLO detection through OpenCV DNN. TensorRT `.engine` files remain the preferred optimized path when the target has the full TensorRT/PyCUDA runtime.
