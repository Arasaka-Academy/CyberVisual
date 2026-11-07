import type { ConfigPatch, RuntimeConfig } from "./types";
import type { NetworkCameraConfig } from "../network-camera/types";
export const NETWORK_DEFAULTS: NetworkCameraConfig = {
  enabled: false,
  advertise_host: "",
  discovery_interface: "",
  discovery_enabled: true,
  rtsp_port: 8554,
  encoder: "auto",
  raw_fps: 30,
  annotated_fps: 15,
  raw_bitrate_kbps: 2000,
  annotated_bitrate_kbps: 1000,
  ptz_driver: "disabled",
};
export const DEFAULT_CONFIG: RuntimeConfig = {
  camera_index: 0,
  camera_device: "",
  camera_fourcc: "MJPG",
  camera_fps: 30,
  source: "camera",
  sample_video: "",
  resolution: { width: 640, height: 480 },
  confidence: 0.35,
  iou: 0.45,
  class_allowlist: [],
  model_path: "models/yolov8n_fp16.engine",
  detector_backend: "auto",
  jpeg_quality: 78,
  retry_interval_seconds: 2,
  auto_snapshot_enabled: true,
  auto_snapshot_label: "person",
  auto_snapshot_cooldown_seconds: 30,
  network_camera: NETWORK_DEFAULTS,
};
export function normalizeConfig(config: RuntimeConfig): RuntimeConfig {
  return {
    ...DEFAULT_CONFIG,
    ...config,
    resolution: { ...DEFAULT_CONFIG.resolution, ...config.resolution },
    class_allowlist: config.class_allowlist || [],
    network_camera: { ...NETWORK_DEFAULTS, ...config.network_camera },
  };
}
export type ConfigGroup = "camera" | "ai" | "snapshot" | "network" | "ptz";
export const GROUPS: ConfigGroup[] = [
  "camera",
  "ai",
  "snapshot",
  "network",
  "ptz",
];
const FIELDS: Record<
  Exclude<ConfigGroup, "network" | "ptz">,
  Array<keyof RuntimeConfig>
> = {
  camera: [
    "source",
    "camera_index",
    "camera_device",
    "camera_fourcc",
    "camera_fps",
    "sample_video",
    "resolution",
    "jpeg_quality",
    "retry_interval_seconds",
  ],
  ai: [
    "confidence",
    "iou",
    "class_allowlist",
    "model_path",
    "detector_backend",
  ],
  snapshot: [
    "auto_snapshot_enabled",
    "auto_snapshot_label",
    "auto_snapshot_cooldown_seconds",
  ],
};
export function selectGroup(
  config: RuntimeConfig,
  group: ConfigGroup,
): ConfigPatch {
  if (group === "ptz")
    return {
      network_camera: { ptz_driver: config.network_camera!.ptz_driver, ...(config.network_camera!.pd42s1 ? { pd42s1: config.network_camera!.pd42s1 } : {}) },
    };
  if (group === "network") {
    const { ptz_driver: _driver, pd42s1: _hardware, ...settings } = config.network_camera!;
    return { network_camera: settings };
  }
  return Object.fromEntries(
    FIELDS[group].map((key) => [key, config[key]]),
  ) as ConfigPatch;
}
export function mergePatch(
  config: RuntimeConfig,
  patch: ConfigPatch,
): RuntimeConfig {
  return {
    ...config,
    ...patch,
    network_camera: { ...config.network_camera!, ...patch.network_camera },
  };
}
export function groupDirty(
  draft: RuntimeConfig | null,
  applied: RuntimeConfig | null,
  group: ConfigGroup,
): boolean {
  return (
    !!draft &&
    !!applied &&
    JSON.stringify(selectGroup(draft, group)) !==
      JSON.stringify(selectGroup(applied, group))
  );
}
