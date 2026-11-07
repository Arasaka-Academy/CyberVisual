import AxeBuilder from "@axe-core/playwright";
import { test, expect, openConsole, schemes, modes, routes } from "./fixtures";

const darkBackgrounds = { neon: "rgb(30, 21, 23)", mono: "rgb(0, 0, 0)", graphite: "rgb(0, 0, 0)", synthwave: "rgb(0, 0, 0)", bloodline: "rgb(11, 5, 5)", terminal: "rgb(11, 20, 16)", amber: "rgb(20, 14, 5)" };

for (const width of [375, 768, 1440]) {
  for (const route of routes) {
    for (const scheme of schemes) {
      for (const mode of modes) {
        test(`${route}-${scheme}-${mode}-${width}`, async ({ page, device }, info) => {
          void device;
          await page.setViewportSize({ width, height: 1000 });
          await openConsole(page, route, scheme, mode);
          const root = page.locator("[data-cyberui]");
          await expect(root).toHaveAttribute("data-mode", mode);
          await expect(root).toHaveCSS("background-color", mode === "light" ? "rgb(255, 255, 255)" : darkBackgrounds[scheme]);
          const geometry = await root.evaluate((element) => {
            const styles = getComputedStyle(element);
            return Object.fromEntries(["cut", "cut-small", "stroke", "hair", "bracket", "touch"].map((key) => [key, styles.getPropertyValue(`--cyber-${key}`).trim()]));
          });
          expect(geometry).toEqual({ cut: "12px", "cut-small": "8px", stroke: "2px", hair: "1px", bracket: "16px", touch: "44px" });
          await expect(root).toHaveCSS("font-family", /Oxanium/);
          await expect(page.locator(".page-heading h1")).toHaveCSS("font-size", width <= 580 ? "27px" : width <= 850 ? "28px" : "34.56px");
          if (route === "overview") {
            await expect(page.locator(".metric strong").first()).toHaveCSS("font-size", width <= 580 ? "38px" : width <= 850 ? "34px" : "42px");
          }
          expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
          const header = await page.locator(".topbar").boundingBox();
          expect(header!.height).toBeGreaterThanOrEqual(72);
          if (width === 1440) {
            expect((await page.locator(".sidebar").boundingBox())!.width).toBe(180);
            const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
            await info.attach("accessibility", { body: JSON.stringify(results, null, 2), contentType: "application/json" });
            expect(results.violations.filter((violation) => ["serious", "critical"].includes(violation.impact || ""))).toEqual([]);
          } else {
            await expect(page.getByRole("button", { name: "打开导航" })).toBeVisible();
          }
          const name = `${route}-${scheme}-${mode}-${width}.png`;
          await page.screenshot({ path: info.outputPath(name), fullPage: true, animations: "disabled" });
          if (!process.env.CYBERVISUAL_CAPTURE_ONLY) await expect(page).toHaveScreenshot(name, { fullPage: true });
        });
      }
    }
  }
}
