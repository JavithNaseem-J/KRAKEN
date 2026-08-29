import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'https://kraken-bdtw.onrender.com';
const smokeClientIp =
  process.env.PLAYWRIGHT_CLIENT_IP ??
  `198.51.100.${Math.floor(Math.random() * 200) + 1}`;

export default defineConfig({
  testDir: './e2e',
  timeout: 120_000,
  expect: { timeout: 20_000 },
  use: {
    baseURL,
    extraHTTPHeaders: {
      'X-Forwarded-For': smokeClientIp,
    },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
