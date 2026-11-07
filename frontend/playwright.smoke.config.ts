import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "live.smoke.ts",
  workers: 1,
  timeout: 60000,
  reporter: [["list"], ["html", { open: "never", outputFolder: "artifacts/smoke-report" }]],
  outputDir: "artifacts/smoke-results",
  use: {
    ...devices["Desktop Chrome"],
    viewport: { width: 1440, height: 1000 },
    baseURL: process.env.CYBERVISUAL_LIVE_URL || "http://127.0.0.1:8119",
    locale: "zh-CN",
    timezoneId: "Asia/Shanghai",
    reducedMotion: "reduce",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
