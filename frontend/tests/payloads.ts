import { DEFAULT_CONFIG } from "../src/features/settings/model";
import type {
  RuntimeConfig,
} from "../src/features/settings/types";
import type { RuntimeStatus } from "../src/features/runtime/types";
import type { PTZStatus } from "../src/features/ptz/types";
import type { RecentEvents } from "../src/features/events/types";
export const configPayload: RuntimeConfig = {
  ...DEFAULT_CONFIG,
  source: "synthetic",
  detector_backend: "mock",
  network_camera: {
    ...DEFAULT_CONFIG.network_camera!,
    enabled: true,
    ptz_driver: "simulated",
    advertise_host: "192.168.1.20",
  },
};
export const ptzPayload: PTZStatus = {
  enabled: true,
  driver: "simulated",
  state: "running",
  simulated: true,
  position: { pan: 0.2, tilt: -0.1, moving: false },
  capabilities: {
    pan_tilt: true,
    absolute_move: true,
    relative_move: true,
    continuous_move: true,
    zoom: false,
  },
  presets: [],
  last_error: null,
};
export function statusPayload(): RuntimeStatus {
  return {
    health: "running",
    camera: { connected: true, source: "synthetic", error: null },
    model: { backend: "mock", path: "model.engine", loaded: true, error: null },
    fps: 11.4,
    latency_ms: 47.8,
    detection_count: 2,
    dropped_frames: 0,
    last_error: null,
    last_frame_ts: Date.now() / 1000,
    temperature_c: 52.2,
    memory: { total_mb: 4096, used_mb: 1600, percent: 39.1 },
    auto_snapshot: {
      enabled: true,
      label: "person",
      cooldown_seconds: 30,
      count: 2,
      last_trigger_ts: null,
      last_image_path: null,
      last_metadata_path: null,
      last_error: null,
    },
    network_camera: {
      enabled: true,
      state: "running",
      credentials_configured: true,
      device_uuid: "urn:uuid:test-device",
      onvif_url: "http://192.168.1.20:8000/onvif/device_service",
      encoder: "x264enc",
      last_error: null,
      discovery: { state: "running", last_error: null },
      events: {
        online: true,
        subscribers: 0,
        presence: { person: true, vehicle: false },
        last_error: null,
      },
      ptz: { ...ptzPayload },
      profiles: ["raw", "annotated"].map((token) => ({
        token,
        name: token,
        rtsp_uri: `rtsp://192.168.1.20:8554/${token}`,
        snapshot_uri: `http://192.168.1.20:8000/onvif/snapshot/${token}`,
        active: token === "raw",
        frames: 20,
      })),
    },
  };
}
export function eventPayload(): RecentEvents {
  return {
    capacity: 200,
    started_at: Date.now() / 1000,
    status: {
      online: true,
      presence: { person: true, vehicle: false },
      last_error: null,
      subscribers: 0,
    },
    events: [
      {
        id: "person-1",
        topic: "Analytics/PersonPresence",
        source: "camera0",
        category: "person",
        state: true,
        frame_ts: Date.now() / 1000,
        initialized: false,
      },
    ],
  };
}
