import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  testMatch: /live-canary\.spec\.ts/,
  timeout: 120_000,
  expect: { timeout: 20_000 },
  use: {
    baseURL: process.env.PLAYWRIGHT_LIVE_BASE_URL ?? 'https://kraken-bdtw.onrender.com',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [{ name: 'live-chromium', use: { ...devices['Desktop Chrome'] } }],
  reporter: [['line'], ['json', { outputFile: '../reports/online-canary-playwright.json' }]],
});
