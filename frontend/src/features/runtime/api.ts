import { getJson } from "../../shared/api";
import type { RuntimeStatus } from "./types";

export async function getStatus(): Promise<RuntimeStatus> {
  return getJson<RuntimeStatus>("/api/status");
}
