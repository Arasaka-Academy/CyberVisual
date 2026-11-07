export type PTZPosition = { pan: number; tilt: number; moving: boolean };
export type PTZStatus = {
  enabled: boolean;
  driver: string;
  state: string;
  simulated: boolean;
  position: PTZPosition | null;
  capabilities: {
    pan_tilt?: boolean;
    zoom?: boolean;
    absolute_move?: boolean;
    relative_move?: boolean;
    continuous_move?: boolean;
    position_range?: number[];
    velocity_range?: number[];
  };
  presets: Array<{ token: string; name: string; pan: number; tilt: number }>;
  last_error: string | null;
  hardware_ready?: boolean;
  calibrated?: boolean;
  calibration_required?: boolean;
  fault?: string | null;
};
export type PTZCommand =
  | {
      action: "absolute_move" | "relative_move" | "continuous_move";
      pan: number;
      tilt: number;
    }
  | { action: "stop" | "home" }
  | { action: "set_preset"; name: string; token?: string }
  | { action: "goto_preset" | "remove_preset"; token: string };
