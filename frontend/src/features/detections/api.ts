import { getJson } from "../../shared/api";
import type { LatestDetectionsResponse } from "./types";

export async function getLatestDetections(): Promise<LatestDetectionsResponse> {
  return getJson<LatestDetectionsResponse>("/api/detections/latest");
}

export async function captureSnapshot(): Promise<{ image_path: string; metadata_path: string }> {
  return getJson<{ image_path: string; metadata_path: string }>("/api/snapshot", { method: "POST" });
}
