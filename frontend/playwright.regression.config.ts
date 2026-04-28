import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright Regression Test Configuration
 * Covers E7.S2.T1 (API latency) and E7.S2.T2 (memory growth).
 *
 * Run:  npx playwright test --config=playwright.regression.config.ts --reporter=list
 *
 * Prerequisites:
 *   - Frontend + backend running on http://localhost:3601
 *   - For memory test heap visibility:
 *       PLAYWRIGHT_CHROMIUM_ARGS="--js-flags=--expose-gc" npx playwright test ...
 */
export default defineConfig({
  testDir: './tests/regression',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [
    ['html', { outputFolder: 'playwright-regression-report' }],
    ['list'],
  ],
  use: {
    baseURL: 'http://localhost:3601',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    navigationTimeout: 30_000,
    actionTimeout: 20_000,
    launchOptions: {
      args: ['--js-flags=--expose-gc'],
    },
  },
  timeout: 120_000, // memory test navigates 40 pages; allow up to 2 min
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  // No webServer block — assumes the app is already running.
  // Start it with: npm run dev   (port 3601)
});
