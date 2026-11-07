import type { RuntimeStatus } from "./types";

export const emptyStatus: RuntimeStatus = {
  health: "starting",
  camera: { connected: false, source: "camera", error: null },
  model: {
    backend: "auto",
    path: "models/yolov8n_fp16.engine",
    loaded: false,
    error: null,
  },
  fps: 0,
  latency_ms: null,
  detection_count: 0,
  dropped_frames: 0,
  last_error: null,
  last_frame_ts: null,
  temperature_c: null,
  memory: null,
  auto_snapshot: {
    enabled: false,
    label: "person",
    cooldown_seconds: 30,
    count: 0,
    last_trigger_ts: null,
    last_image_path: null,
    last_metadata_path: null,
    last_error: null,
  },
};

export function normalizeStatus(status: RuntimeStatus): RuntimeStatus {
  return {
    ...emptyStatus,
    ...status,
    camera: { ...emptyStatus.camera, ...status.camera },
    model: { ...emptyStatus.model, ...status.model },
    auto_snapshot: {
      ...emptyStatus.auto_snapshot,
      ...(status.auto_snapshot || {}),
    },
  };
}
