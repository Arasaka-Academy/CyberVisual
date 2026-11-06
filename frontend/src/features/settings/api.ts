import { getJson } from "../../shared/api";
import type { RuntimeConfig } from "./types";

export async function getConfig(): Promise<RuntimeConfig> {
  return getJson<RuntimeConfig>("/api/config");
}

export async function updateConfig(config: Partial<RuntimeConfig>): Promise<RuntimeConfig> {
  return getJson<RuntimeConfig>("/api/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config)
  });
}
