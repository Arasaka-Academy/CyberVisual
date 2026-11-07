import { getJson, jsonBody } from "../../shared/api";
import type { PTZStatus, PTZCommand } from "./types";
export const getPTZ = (signal?: AbortSignal) =>
  getJson<PTZStatus>("/api/ptz", { signal });

export const commandPTZ = (command: PTZCommand) =>
  getJson<PTZStatus>("/api/ptz/command", jsonBody(command));
export const calibratePTZ = () =>
  getJson<PTZStatus>("/api/ptz/calibrate-center", jsonBody({ confirm: true }));
