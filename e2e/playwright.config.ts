import { defineConfig } from "@playwright/test";

// BASE_URL comes from the environment (never hard-coded). The journeys change data, so they run one
// at a time, in order, against a database that `manage.py e2e_seed` has filled with invented data.
const baseURL = process.env.BASE_URL || "http://localhost:8000";
const mobile = process.env.E2E_MOBILE === "1"; // E2E_MOBILE=1 runs the same journeys at 390px

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  globalSetup: "./global-setup.ts",
  timeout: 90_000,
  expect: { timeout: 10_000 },
  reporter: [["list"], ["html", { open: "never", outputFolder: "report" }]],
  use: {
    baseURL,
    channel: process.env.E2E_CHANNEL || undefined, // e.g. msedge on a PC without Playwright's Chromium
    viewport: mobile ? { width: 390, height: 844 } : { width: 1366, height: 900 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
