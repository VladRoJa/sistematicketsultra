import { chromium } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const baseURL = (process.env.SUITE_ULTRA_BASE_URL || 'https://suiteultragym.com').replace(/\/$/, '');
const username = process.env.SUITE_ULTRA_QA_USERNAME || 'admicorp';
const statePath = path.resolve(process.cwd(), 'artifacts/campaign-v2-prod/auth.json');

fs.mkdirSync(path.dirname(statePath), { recursive: true });

const browser = await chromium.launch({ headless: false });
const context = await browser.newContext({ ignoreHTTPSErrors: true });
const page = await context.newPage();

console.log('QA auth: complete the login in the opened Chromium window.');
console.log('The resulting session will be stored locally under artifacts/ and is ignored by Git.');

await page.goto(`${baseURL}/#/login`);
await page.locator('#usuario-login').fill(username);

await page.waitForURL(/\/#\/(control|main)/, { timeout: 180_000 });
await context.storageState({ path: statePath });

console.log(`QA auth state saved to ${statePath}`);
await browser.close();
