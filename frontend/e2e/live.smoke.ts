import { test, expect } from "@playwright/test";

test("production console talks to the isolated synthetic-camera backend without HTTP mocks", async ({ page, request }, info) => {
  const errors: string[] = [];
  const writes: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    if (request.method() === "PUT") writes.push(request.url());
  });
  const status = await (await request.get("/api/status")).json();
  expect(status.camera.source).toBe("synthetic");
  expect(status.model.backend).toBe("mock");
  expect(status.network_camera.enabled).toBe(false);
  const original = await (await request.get("/api/config")).json();
  const confidence = original.confidence === 0.61 ? 0.62 : 0.61;
  const evidence: Record<string, unknown> = { source: status.camera.source, detector: status.model.backend };

  await page.goto("/#/overview");
  await expect(page.locator(".topbar-status")).toContainText("设备运行中");
  await expect(page.locator("[data-cyberui]")).toHaveAttribute("data-scheme", "neon");
  await expect(page.locator("[data-cyberui]")).toHaveAttribute("data-mode", "dark");

  for (const [route, heading] of [["overview", "设备总览"], ["monitor", "实时监看"], ["nvr", "NVR 接入"], ["events", "AI 事件"], ["settings", "系统设置"]]) {
    await page.goto(`/#/${route}`, { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
    if (route === "monitor") {
      const preview = page.getByRole("img", { name: "摄像头 AI 标注实时画面" });
      await expect.poll(() => preview.evaluate((image) => (image as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
      const stream = await preview.getAttribute("src");
      await page.getByRole("button", { name: "外观设置" }).click();
      await page.getByRole("button", { name: /amber/ }).click();
      await page.keyboard.press("Escape");
      await expect(preview).toHaveAttribute("src", stream!);
      expect(writes).toEqual([]);
      const saved = page.waitForResponse((response) => response.url().endsWith("/api/snapshot") && response.request().method() === "POST");
      await page.getByRole("button", { name: "保存快照" }).click();
      const snapshot = await saved;
      expect(snapshot.status()).toBe(201);
      evidence.snapshot = await snapshot.json();
      await page.getByRole("button", { name: "暂停预览" }).click();
      await expect(preview).toHaveCount(0);
      await page.getByRole("button", { name: "恢复预览" }).click();
      await expect.poll(() => preview.evaluate((image) => (image as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
    }
    if (route === "nvr") {
      await expect(page.getByLabel("RTSP 端口")).toBeVisible();
      await expect(page.getByRole("img")).toHaveCount(0);
      await expect(page.getByText("未配置", { exact: true }).first()).toBeVisible();
    }
    if (route === "events") await expect(page.getByText("分析在线", { exact: true })).toBeVisible();
    if (route === "settings") await expect(page.getByLabel("置信度阈值")).toBeVisible();
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: info.outputPath(`${route}-live.png`), fullPage: true });
  }

  await page.getByLabel("置信度阈值").fill(String(confidence));
  await page.goto("/#/nvr");
  await page.goto("/#/settings");
  await expect(page.getByLabel("置信度阈值")).toHaveValue(String(confidence));
  const saved = page.waitForResponse((response) => response.url().endsWith("/api/config") && response.request().method() === "PUT");
  await page.getByRole("heading", { name: "AI 检测", exact: true }).locator("xpath=ancestor::section").getByRole("button", { name: "保存配置" }).click();
  expect((await saved).ok()).toBe(true);
  expect((await (await request.get("/api/config")).json()).confidence).toBe(confidence);
  await page.reload();
  await expect(page.getByLabel("置信度阈值")).toHaveValue(String(confidence));
  await expect(page.locator("[data-cyberui]")).toHaveAttribute("data-scheme", "amber");
  expect(writes).toHaveLength(1);
  const restored = await request.put("/api/config", { data: { confidence: original.confidence } });
  expect(restored.ok()).toBe(true);
  evidence.configRoundTrip = { original: original.confidence, saved: confidence, restored: original.confidence };
  expect(errors).toEqual([]);
  await info.attach("live-integration", { body: JSON.stringify(evidence, null, 2), contentType: "application/json" });
});
