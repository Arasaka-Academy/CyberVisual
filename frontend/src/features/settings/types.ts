import type { NetworkCameraConfig } from "../network-camera/types";

export type RuntimeConfig = {
  network_camera?: NetworkCameraConfig;
  camera_index: number;
  camera_device: string;
  camera_fourcc: string;
  camera_fps: number;
  source: "camera" | "synthetic" | "video";
  sample_video: string;
  resolution: {
    width: number;
    height: number;
  };
  confidence: number;
  iou: number;
  class_allowlist: string[];
  model_path: string;
  detector_backend: "auto" | "mock" | "opencv" | "tensorrt";
  jpeg_quality: number;
  retry_interval_seconds: number;
  auto_snapshot_enabled: boolean;
  auto_snapshot_label: string;
  auto_snapshot_cooldown_seconds: number;
};
