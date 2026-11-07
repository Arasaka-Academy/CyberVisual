import { test as base, expect, type Page } from "@playwright/test";
import { configPayload, eventPayload, ptzPayload, statusPayload } from "../tests/payloads";
import type { ConfigPatch } from "../src/features/settings/types";

export const schemes = ["neon", "mono", "graphite", "synthwave", "bloodline", "terminal", "amber"] as const;
export const modes = ["dark", "light"] as const;
export const routes = ["overview", "monitor", "nvr", "events", "settings"] as const;
export const fixedTime = new Date("2026-11-07T09:00:00+08:00");
export const storageKey = "cybervisual.appearance.v1";

export type DeviceMock = {
  commands: Record<string, unknown>[];
  writes: ConfigPatch[];
  failStatus: boolean;
  analysisOnline: boolean;
  failSaves: boolean;
};

export const test = base.extend<{ device: DeviceMock }>({
  device: async ({ page }, use) => {
    const device: DeviceMock = { commands: [], writes: [], failStatus: false, analysisOnline: true, failSaves: false };
    let config = structuredClone(configPayload);
    await page.clock.setFixedTime(fixedTime);
    await page.route("**/api/**", async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      const stamp = fixedTime.getTime() / 1000;
      if (path === "/api/status") {
        const status = statusPayload();
        status.last_frame_ts = stamp;
        await route.fulfill({ status: device.failStatus ? 503 : 200, json: device.failStatus ? { error: "设备连接中断" } : status });
      } else if (path === "/api/config") {
        if (request.method() === "PUT") {
          const patch = request.postDataJSON() as ConfigPatch;
          device.writes.push(patch);
          if (device.failSaves) return route.fulfill({ status: 400, json: { error: "配置保存失败" } });
          config = { ...config, ...patch, network_camera: { ...config.network_camera!, ...patch.network_camera } };
        }
        await route.fulfill({ json: config });
      } else if (path === "/api/ptz" || path === "/api/ptz/command") {
        if (request.method() === "POST") device.commands.push(request.postDataJSON());
        await route.fulfill({ json: ptzPayload });
      } else if (path === "/api/events/recent") {
        const events = eventPayload();
        events.status.online = device.analysisOnline;
        events.started_at = stamp;
        events.events = Array.from({ length: 45 }, (_, index) => ({ ...events.events[0], id: `event-${index}`, category: index % 2 ? "vehicle" : "person", frame_ts: stamp - index * 20 }));
        await route.fulfill({ json: events });
      } else if (path === "/api/detections/latest") {
        await route.fulfill({ json: { frame_ts: stamp, version: 7, detections: [{ label: "person", confidence: .91, bbox: { x1: 190, y1: 100, x2: 360, y2: 390 }, frame_ts: stamp }] } });
      } else if (path === "/api/snapshot") {
        await route.fulfill({ json: { image_path: "/captures/test.jpg", metadata_path: "/captures/test.json" } });
      } else {
        await route.fulfill({ status: 404, json: { error: `Unknown fixture: ${path}` } });
      }
    });
    await page.route("**/stream.mjpg*", (route) => route.fulfill({ contentType: "image/svg+xml", body: `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480" viewBox="0 0 640 480"><defs><pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" stroke="#333" stroke-width="1"/></pattern></defs><rect width="640" height="480" fill="#151515"/><rect width="640" height="480" fill="url(#grid)"/><path d="M0 240H640M320 0V480" stroke="#777" stroke-dasharray="4 8"/><rect x="190" y="100" width="170" height="290" fill="none" stroke="#93e4ea" stroke-width="2"/><text x="190" y="90" fill="#93e4ea" font-family="monospace" font-size="14">person 91%</text><text x="24" y="450" fill="#bbb" font-family="monospace" font-size="12">CYBERVISUAL / SYNTHETIC TEST SOURCE</text></svg>` }));
    await use(device);
  },
});

export async function openConsole(page: Page, route = "overview", scheme = "neon", mode = "dark") {
  await page.addInitScript(({ key, scheme, mode }) => {
    if (!sessionStorage.getItem("cybervisual.test.initialized")) {
      localStorage.setItem(key, JSON.stringify({ scheme, mode }));
      sessionStorage.setItem("cybervisual.test.initialized", "true");
    }
  }, { key: storageKey, scheme, mode });
  await page.goto(`/#/${route}`);
  await expect(page.locator(".topbar-status")).toContainText("设备运行中");
  await expect(page.locator("[data-cyberui]")).toHaveAttribute("data-scheme", scheme);
  await page.evaluate(() => document.fonts.ready);
  if (route === "monitor") await expect(page.getByRole("img")).toBeVisible();
  if (route === "settings") await expect(page.getByLabel("置信度阈值")).toBeVisible();
  if (route === "nvr") await expect(page.getByLabel("RTSP 端口")).toBeVisible();
  if (route === "events") await expect(page.getByRole("table", { name: "近期 AI 事件" })).toBeVisible();
}

export { expect };
