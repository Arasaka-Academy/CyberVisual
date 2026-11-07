import { getJson } from "../../shared/api";
import type { LatestDetectionsResponse } from "./types";
export const getLatestDetections = (signal?: AbortSignal) =>
  getJson<LatestDetectionsResponse>("/api/detections/latest", { signal });

export const captureSnapshot = () =>
  getJson<{ image_path: string; metadata_path: string }>("/api/snapshot", {
    method: "POST",
  });
