export type NetworkCameraConfig = {
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

export type NetworkCameraStatus = {
  enabled: boolean;
  state: string;
  credentials_configured: boolean;
  device_uuid: string | null;
  onvif_url: string | null;
  encoder: string | null;
  last_error: string | null;
  discovery: { state: string; last_error: string | null };
  events: {
    online: boolean;
    subscribers: number;
    presence: Record<string, boolean>;
    last_error: string | null;
  };
  ptz: {
    enabled: boolean;
    driver: string;
    state?: string;
    last_error?: string | null;
    simulated: boolean;
    position: { pan: number; tilt: number; moving: boolean } | null;
  };
  profiles: Array<{
    token: string;
    name: string;
    rtsp_uri: string | null;
    snapshot_uri: string | null;
    active?: boolean;
    frames?: number;
    last_error?: string | null;
  }>;
};
