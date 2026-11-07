import AxeBuilder from "@axe-core/playwright";
import { test, expect, openConsole, storageKey } from "./fixtures";

test("theme dialog preserves drafts, inherits its palette and restores focus", async ({ page, device }) => {
  await openConsole(page, "settings");
  await page.getByLabel("置信度阈值").fill("0.73");
  const trigger = page.getByRole("button", { name: "外观设置" });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "外观设置" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "amber", exact: true }).click();
  await dialog.getByRole("radio", { name: "浅色" }).click();
  await expect(page.locator("[data-cyberui-portal]")).toHaveAttribute("data-mode", "light");
  await expect(page.locator("[data-cyberui-portal]")).toHaveAttribute("data-scheme", "amber");
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(results.violations.filter((violation) => ["serious", "critical"].includes(violation.impact || ""))).toEqual([]);
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await expect(page.getByLabel("置信度阈值")).toHaveValue("0.73");
  expect(device.writes).toHaveLength(0);
  await page.reload();
  await expect(page.locator("[data-cyberui]")).toHaveAttribute("data-scheme", "amber");
  await expect(page.locator("[data-cyberui]")).toHaveAttribute("data-mode", "light");
});

test("system mode follows operating-system changes without reloading", async ({ page, device }) => {
  void device;
  await page.emulateMedia({ colorScheme: "light" });
  await openConsole(page, "overview", "neon", "system");
  await expect(page.locator("[data-cyberui]")).toHaveAttribute("data-mode", "light");
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("[data-cyberui]")).toHaveAttribute("data-mode", "dark");
  expect(await page.evaluate((key) => JSON.parse(localStorage.getItem(key)!).mode, storageKey)).toBe("system");
});

test("touch navigation closes the drawer without losing the chosen page", async ({ browser }) => {
  const context = await browser.newContext({ baseURL: "http://127.0.0.1:5179", viewport: { width: 375, height: 812 }, hasTouch: true, isMobile: true });
  const page = await context.newPage();
  await page.route("**/api/**", (route) => route.fulfill({ status: 503, json: { error: "离线测试" } }));
  await page.goto("/#/overview");
  await page.getByRole("button", { name: "打开导航" }).tap();
  await page.getByRole("dialog").getByRole("link", { name: "系统设置" }).tap();
  await expect(page).toHaveURL(/#\/settings$/);
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(page.getByRole("heading", { name: "系统设置" })).toBeVisible();
  await context.close();
});

test("holding a direction stops on pointer release and keyboard release", async ({ page, device }) => {
  await openConsole(page, "monitor");
  const direction = page.getByRole("button", { name: "向右移动" });
  await expect(direction).toBeEnabled();
  const bounds = await direction.boundingBox();
  await page.mouse.move(bounds!.x + bounds!.width / 2, bounds!.y + bounds!.height / 2);
  await page.mouse.down();
  await expect.poll(() => device.commands.some((command) => command.action === "continuous_move")).toBe(true);
  await page.mouse.move(1, 1);
  await page.mouse.up();
  await expect.poll(() => device.commands.at(-1)?.action).toBe("stop");
  device.commands.length = 0;
  await direction.focus();
  await page.keyboard.down("Space");
  await expect.poll(() => device.commands.some((command) => command.action === "continuous_move")).toBe(true);
  await page.keyboard.up("Space");
  await expect.poll(() => device.commands.at(-1)?.action).toBe("stop");
});

test("leaving monitor stops movement and releases the preview", async ({ page, device }) => {
  await openConsole(page, "monitor");
  const direction = page.getByRole("button", { name: "向右移动" });
  await expect(direction).toBeEnabled();
  await direction.focus();
  await page.keyboard.down("Enter");
  await expect.poll(() => device.commands.some((command) => command.action === "continuous_move")).toBe(true);
  await page.evaluate(() => { window.location.hash = "/events"; });
  await expect(page.getByRole("img")).toHaveCount(0);
  await expect.poll(() => device.commands.at(-1)?.action).toBe("stop");
  await page.keyboard.up("Enter");
});

test("configuration failures retain the draft and focus the error", async ({ page, device }) => {
  await openConsole(page, "settings");
  device.failSaves = true;
  await page.getByLabel("置信度阈值").fill("0.74");
  await page.getByRole("heading", { name: "AI 检测", exact: true }).locator("xpath=ancestor::section").getByRole("button", { name: "保存配置" }).click();
  await expect(page.getByText("配置保存失败", { exact: true })).toBeVisible();
  await expect(page.getByLabel("置信度阈值")).toHaveValue("0.74");
  expect(device.writes[0]).toMatchObject({ confidence: .74 });
  expect(device.writes[0]).not.toHaveProperty("network_camera");
});

test("event filters and pagination preserve unknown analysis state", async ({ page, device }) => {
  device.analysisOnline = false;
  await openConsole(page, "events");
  await expect(page.getByText("状态未知")).toHaveCount(2);
  await page.getByRole("button", { name: "下一页", exact: true }).click();
  await expect(page.getByText("第 2 / 3 页")).toBeVisible();
  await page.getByRole("button", { name: /事件类别/ }).click();
  await page.getByRole("option", { name: "人物", exact: true }).click();
  await expect(page.getByText("第 1 / 2 页")).toBeVisible();
  await expect(page.getByRole("table").getByText("车辆出现")).toHaveCount(0);
});

for (const width of [320, 720]) {
  test(`reflows without page overflow at ${width}px`, async ({ page, device }) => {
    void device;
    await page.setViewportSize({ width, height: 900 });
    for (const route of ["overview", "monitor", "nvr", "events", "settings"]) {
      await openConsole(page, route);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    }
  });
}

test("keyboard users can skip navigation and see a focus indicator", async ({ page, device }) => {
  void device;
  await openConsole(page);
  await page.evaluate(() => {
    document.body.tabIndex = -1;
    document.body.focus();
    document.body.removeAttribute("tabindex");
    window.scrollTo(0, 0);
  });
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "跳到主要内容" })).toBeFocused();
  await expect(page.getByRole("link", { name: "跳到主要内容" })).toHaveCSS("top", "12px");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("main")).toBeFocused();
});
