# Models

The printable Waveshare IMX477 HQ pan/tilt mount, 3MF files and interactive assembly figure are in [imx477-hq/README.zh-CN.md](imx477-hq/README.zh-CN.md). The original user-supplied STL files are kept alongside this directory.

Place YOLO model files here.

Expected default:

```text
models/yolov8n_fp16.engine
```

OpenCV DNN fallback:

```text
models/yolov5n.onnx
```

TensorRT engines are hardware, TensorRT, CUDA, and JetPack specific. Generate the engine on the Jetson Nano or inside a matching L4T/JetPack container. Do not commit `.engine`, `.onnx`, or `.pt` binaries to git.

For a first deployment on Jetson Nano without PyCUDA, download `yolov5n.onnx` with `scripts/download_yolo_onnx.sh` and set `CYBERVISUAL_DETECTOR=opencv`. For TensorRT, use a COCO-pretrained nano model at 640 image size and FP16 precision. If FPS is below target, try a smaller input size such as 416 or 320.
