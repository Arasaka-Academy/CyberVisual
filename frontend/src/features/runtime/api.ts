import { getJson } from "../../shared/api";
import type { RuntimeStatus } from "./types";
export const getStatus = (signal?: AbortSignal) =>
  getJson<RuntimeStatus>("/api/status", { signal });
