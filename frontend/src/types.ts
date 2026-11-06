export type BBox = {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
};

export type Detection = {
  label: string;
  confidence: number;
  bbox: BBox;
  frame_ts: number;
  class_id?: number;
};

export type RuntimeConfig = {
  network_camera?: {
    enabled: boolean;
    advertise_host: string;
    discovery_interface: string;
    discovery_enabled: boolean;
    rtsp_port: number;
    encoder: "auto" | "jetson" | "software";
    raw_fps: number;
    annotated_fps: number;
    raw_bitrate_kbps: number;
    annotated_bitrate_kbps: number;
    ptz_driver: "disabled" | "simulated";
  };
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

export type RuntimeStatus = {
  network_camera?: NetworkCameraStatus;
  health: "starting" | "running" | "error" | "thermal_warning" | string;
  camera: {
    connected: boolean;
    source: string;
    error: string | null;
  };
  model: {
    backend: string;
    path: string;
    loaded: boolean;
    error: string | null;
  };
  fps: number;
  latency_ms: number | null;
  detection_count: number;
  dropped_frames: number;
  last_error: string | null;
  last_frame_ts: number | null;
  temperature_c: number | null;
  memory: {
    total_mb: number;
    used_mb: number;
    percent: number;
  } | null;
  auto_snapshot: {
    enabled: boolean;
    label: string;
    cooldown_seconds: number;
    count: number;
    last_trigger_ts: number | null;
    last_image_path: string | null;
    last_metadata_path: string | null;
    last_error: string | null;
  };
};

export type NetworkCameraStatus = {
  enabled: boolean;
  state: string;
  credentials_configured: boolean;
  device_uuid: string | null;
  onvif_url: string | null;
  encoder: string | null;
  last_error: string | null;
  discovery: { state: string; last_error: string | null };
  events: { online: boolean; subscribers: number; presence: Record<string, boolean>; last_error: string | null };
  ptz: { enabled: boolean; driver: string; state?: string; last_error?: string | null; simulated: boolean; position: { pan: number; tilt: number; moving: boolean } | null };
  profiles: Array<{ token: string; name: string; rtsp_uri: string | null; snapshot_uri: string | null; active?: boolean; frames?: number; last_error?: string | null }>;
};

export type LatestDetectionsResponse = {
  frame_ts: number | null;
  version: number;
  detections: Detection[];
};
