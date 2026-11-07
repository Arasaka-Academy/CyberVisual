# CyberVisual

CyberVisual is an edge vision console for USB-camera object detection on Jetson Nano, with a YOLO TensorRT runtime and a black/green web dashboard. The backend provides annotated MJPEG, ONVIF/RTSP, PTZ and event APIs. The Chinese device console separates overview, live monitoring, NVR integration, AI events and system settings.

Optional **ONVIF + RTSP** output makes each CyberVisual a managed network camera:
shared H.264 `/raw` and `/annotated` streams, person/vehicle PullPoint events,
WS-Discovery, Digest authentication, and a simulated PTZ adapter. It is disabled
by default. See the [network camera deployment and CyberOS integration contract](docs/network-camera.md)
for setup, supported ONVIF operations, and interoperability evidence.

Based on [nvidia-jetson-nano-visual](https://github.com/zhubby/nvidia-jetson-nano-visual) at commit `326f9e2`.

## IMX477 HQ Mount

View the [interactive assembly figure](https://arasaka-academy.github.io/CyberVisual/figure/) and download the printable 3MF files. The [print and assembly guide](models/imx477-hq/README.zh-CN.md) covers the camera mount, fasteners and reference dimensions.

GitHub Pages publishes the figure and its downloads automatically when these assets change on `main`. See [Pages deployment](docs/figure-pages.md) for the local preview and publishing workflow.

The [Jetson Nano pan/tilt 3D lesson](https://arasaka-academy.github.io/CyberVisual/lesson/) provides five Chinese interactive lessons and a build-your-own experiment explaining UART motor control and IMX477 CSI image return. It runs independently in the browser and includes an [offline single-file download](https://arasaka-academy.github.io/CyberVisual/lesson/lesson.html). See the [lesson source and run guide](viz-jetson-pan-tilt/README.md).

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

## 设备控制台

控制台默认进入设备总览，支持直接访问与浏览器前进／后退：

| 工作区 | 地址 | 用途 |
| --- | --- | --- |
| 设备总览 | `/#/overview` | 采集、推理、协议与云台状态 |
| 实时监看 | `/#/monitor` | 标注视频、快照、云台方向／归位／预置位 |
| NVR 接入 | `/#/nvr` | ONVIF、双路 RTSP、发现和编码配置 |
| AI 事件 | `/#/events` | 当前存在状态与最近 200 条内存事件 |
| 系统设置 | `/#/settings` | 视频源、AI 参数、自动快照与云台驱动 |

配置按区域独立保存，切页保留草稿。隐藏标签页会暂停预览和状态轮询，
离开监看、松开方向、失焦或触控取消会发送云台停止请求；每条浏览器连续移动指令最多运行 2 秒。
模拟云台只验证标准化位置与预置位，不带动真实画面或电机。

录像、回放和多设备管理由外部 NVR／CyberOS 承担。协议输出状态不代表 NVR 已接收或正在录像。
页面提供的管理 API 沿用现有可信管理网络访问范围；ONVIF／RTSP 账号只由部署环境配置。
详见 [控制台接口与接入说明](docs/network-camera.md#设备控制台与管理-api)。

## Backend API

- `GET /stream.mjpg` - annotated MJPEG stream.
- `GET /api/status` - camera/model/FPS/latency/temperature/memory status.
- `GET /api/detections/latest` - latest frame detections.
- `GET /api/config` - runtime config.
- `PUT /api/config` - update thresholds, source, model path, allowlist, and resolution.
- `POST /api/snapshot` - save current frame and detection JSON into `captures/`.
- `GET /api/ptz` - shared PTZ capabilities, position, presets and driver status.
- `POST /api/ptz/command` - JSON-only, allowlisted PTZ operations with a 2-second continuous movement lease.
- `GET /api/events/recent` - current analytics state and the most recent 200 process-lifetime events.

## Notes

Runtime does not depend on the latest `ultralytics` package. On older JetPack 4.x devices without PyCUDA, use `models/yolov5n.onnx` with `detector_backend=opencv` for real YOLO detection through OpenCV DNN. TensorRT `.engine` files remain the preferred optimized path when the target has the full TensorRT/PyCUDA runtime.
