import { getJson } from "../../shared/api";
import type { RecentEvents } from "./types";
export const getRecentEvents = (signal?: AbortSignal) =>
  getJson<RecentEvents>("/api/events/recent", { signal });
