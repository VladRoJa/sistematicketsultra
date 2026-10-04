import { defineConfig, devices } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const baseURL = process.env.SUITE_ULTRA_BASE_URL || 'https://suiteultragym.com';
const storageStatePath = path.resolve(process.cwd(), 'artifacts/campaign-v2-prod/auth.json');
const storageState = fs.existsSync(storageStatePath) ? storageStatePath : undefined;

export default defineConfig({
  testDir: '.',
  testMatch: '**/*.spec.ts',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [
    ['list'],
    ['html', { outputFolder: '../../artifacts/campaign-v2-prod/playwright-report', open: 'never' }],
  ],
  outputDir: '../../artifacts/campaign-v2-prod/test-results',
  use: {
    baseURL,
    storageState,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
    viewport: { width: 1600, height: 1000 },
    ignoreHTTPSErrors: true,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
