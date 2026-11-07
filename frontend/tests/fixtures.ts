import { vi } from "vitest";
import type { ConfigPatch } from "../src/features/settings/types";
import { configPayload, ptzPayload, statusPayload, eventPayload } from "./payloads";
export { configPayload, ptzPayload, statusPayload, eventPayload } from "./payloads";
export function jsonResponse(payload: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}
export function installFetch(
  overrides: Record<string, () => ReturnType<typeof jsonResponse>> = {},
) {
  let config = structuredClone(configPayload);
  const mock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (overrides[path]) return overrides[path]();
    if (path === "/api/status") return jsonResponse(statusPayload());
    if (path === "/api/config" && init?.method === "PUT") {
      const patch = JSON.parse(String(init.body)) as ConfigPatch;
      config = {
        ...config,
        ...patch,
        network_camera: { ...config.network_camera!, ...patch.network_camera },
      };
      return jsonResponse(config);
    }
    if (path === "/api/config") return jsonResponse(config);
    if (path === "/api/ptz") return jsonResponse(ptzPayload);
    if (path === "/api/ptz/command") return jsonResponse(ptzPayload);
    if (path === "/api/events/recent") return jsonResponse(eventPayload());
    if (path === "/api/detections/latest")
      return jsonResponse({
        frame_ts: Date.now() / 1000,
        version: 7,
        detections: [
          {
            label: "person",
            confidence: 0.91,
            bbox: { x1: 1, y1: 1, x2: 20, y2: 20 },
            frame_ts: Date.now() / 1000,
          },
        ],
      });
    if (path === "/api/snapshot")
      return jsonResponse({
        image_path: "/captures/test.jpg",
        metadata_path: "/captures/test.json",
      });
    return jsonResponse({}, 404);
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}
