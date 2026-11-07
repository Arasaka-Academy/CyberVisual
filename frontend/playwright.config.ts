import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : 4,
  reporter: [["list"], ["html", { open: "never", outputFolder: "artifacts/playwright-report" }]],
  outputDir: "artifacts/test-results",
  snapshotPathTemplate: "{testDir}/snapshots/{platform}/{arg}{ext}",
  expect: { toHaveScreenshot: { animations: "disabled", caret: "hide", maxDiffPixelRatio: 0.001 } },
  use: { ...devices["Desktop Chrome"], baseURL: "http://127.0.0.1:5179", timezoneId: "Asia/Shanghai", locale: "zh-CN", trace: "retain-on-failure", screenshot: "only-on-failure", reducedMotion: "reduce" },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 5179 --strictPort",
    url: "http://127.0.0.1:5179",
    reuseExistingServer: !process.env.CI,
  },
});
