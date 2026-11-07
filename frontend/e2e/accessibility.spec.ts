import AxeBuilder from "@axe-core/playwright";
import { test, expect, openConsole, schemes, modes } from "./fixtures";

for (const scheme of schemes) {
  for (const mode of modes) {
    test(`appearance-dialog-${scheme}-${mode}`, async ({ page, device }, info) => {
      void device;
      await openConsole(page, "settings", scheme, mode);
      const trigger = page.getByRole("button", { name: "外观设置" });
      await trigger.click();
      const dialog = page.getByRole("dialog");
      await expect(dialog).toBeVisible();
      const portal = page.locator("[data-cyberui-portal]");
      await expect(portal).toHaveAttribute("data-scheme", scheme);
      await expect(portal).toHaveAttribute("data-mode", mode);
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
      await info.attach("accessibility", { body: JSON.stringify(results, null, 2), contentType: "application/json" });
      expect(results.violations.filter((violation) => ["serious", "critical"].includes(violation.impact || ""))).toEqual([]);
      await page.getByRole("button", { name: "完成", exact: true }).focus();
      await page.keyboard.press("Tab");
      expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);
      await expect(page.locator(":focus")).toHaveCSS("outline-width", "2px");
      await expect(trigger).toHaveCSS("transition-duration", "1e-05s");
      await page.keyboard.press("Escape");
      await expect(dialog).not.toBeVisible();
      await expect(trigger).toBeFocused();
    });
  }
}

test("mobile navigation drawer is accessible and returns keyboard focus", async ({ page, device }, info) => {
  void device;
  await page.setViewportSize({ width: 375, height: 812 });
  await openConsole(page);
  const trigger = page.getByRole("button", { name: "打开导航" });
  await trigger.click();
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  await info.attach("accessibility", { body: JSON.stringify(results, null, 2), contentType: "application/json" });
  expect(results.violations.filter((violation) => ["serious", "critical"].includes(violation.impact || ""))).toEqual([]);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(trigger).toBeFocused();
});
