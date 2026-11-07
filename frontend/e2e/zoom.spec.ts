import { chromium } from "@playwright/test";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test as consoleTest, expect, openConsole, routes } from "./fixtures";

type ZoomAPI = {
  tabs: {
    query: (options: { active: boolean }) => Promise<Array<{ id: number }>>;
    setZoom: (tabId: number, factor: number) => Promise<void>;
    getZoom: (tabId: number) => Promise<number>;
  };
};

const test = consoleTest.extend({
  context: async ({}, use) => {
    const extension = await mkdtemp(join(tmpdir(), "cybervisual-browser-zoom-"));
    await writeFile(join(extension, "manifest.json"), JSON.stringify({
      manifest_version: 3,
      name: "CyberVisual isolated zoom test",
      version: "1.0.0",
      permissions: ["tabs"],
      background: { service_worker: "background.js" },
    }));
    await writeFile(join(extension, "background.js"), "chrome.runtime.onInstalled.addListener(() => {});");
    const context = await chromium.launchPersistentContext("", {
      channel: "chromium",
      headless: true,
      baseURL: "http://127.0.0.1:5179",
      viewport: { width: 1440, height: 1000 },
      locale: "zh-CN",
      timezoneId: "Asia/Shanghai",
      reducedMotion: "reduce",
      args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`],
    });
    try {
      await use(context);
    } finally {
      await context.close();
      await rm(extension, { recursive: true, force: true });
    }
  },
});

test("native Chromium 200% page zoom reflows all five pages and their dialogs", async ({ page, context, device }) => {
  void device;
  await openConsole(page);
  await page.bringToFront();
  const worker = context.serviceWorkers()[0] || await context.waitForEvent("serviceworker");
  const zoom = await worker.evaluate(async () => {
    const { tabs } = (globalThis as typeof globalThis & { chrome: ZoomAPI }).chrome;
    const [tab] = await tabs.query({ active: true });
    await tabs.setZoom(tab.id, 2);
    return tabs.getZoom(tab.id);
  });
  expect(zoom).toBe(2);
  for (const route of routes) {
    await openConsole(page, route);
    await expect.poll(() => page.evaluate(() => window.innerWidth)).toBe(720);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await expect(page.getByRole("button", { name: "打开导航" })).toBeVisible();
    await page.getByRole("button", { name: "外观设置" }).click();
    const dialog = await page.getByRole("dialog").boundingBox();
    expect(dialog!.x).toBeGreaterThanOrEqual(0);
    expect(dialog!.x + dialog!.width).toBeLessThanOrEqual(720);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("button", { name: "外观设置" })).toBeFocused();
  }
});
