import { getJson, jsonBody } from "../../shared/api";
import type { RuntimeConfig, ConfigPatch } from "./types";
export const getConfig = (signal?: AbortSignal) =>
  getJson<RuntimeConfig>("/api/config", { signal });

export const updateConfig = (config: ConfigPatch) =>
  getJson<RuntimeConfig>("/api/config", jsonBody(config, "PUT"));
