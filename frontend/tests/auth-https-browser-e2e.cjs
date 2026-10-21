'use strict';
/**
 * Real Chromium + Angular + Flask, same-origin TLS, synthetic user and DB.
 * Lab time jumps affect Flask's refresh idle clock only; no production data.
 */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');

const BASE = 'https://127.0.0.1:4443';
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function eventually(check, message, timeout = 30_000) {
  const until = Date.now() + timeout;
  let last;
  while (Date.now() < until) {
    try {
      const value = await check();
      if (value) return value;
    } catch (error) {
      last = error.message;
    }
    await sleep(400);
  }
  throw new Error(message + (last ? ': ' + last : ''));
}

async function state(page) {
  return page.evaluate(async () =>
    fetch('/api/qa/rotation').then(response => response.json())
  );
}

async function jump(page, minutes) {
  const response = await page.evaluate(async value => {
    const result = await fetch('/api/qa/advance', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ minutes: value }),
    });
    return { status: result.status, body: await result.json() };
  }, minutes);
  assert.equal(response.status, 200);
}

(async function run() {
  let browser;
  try {
    await eventually(async () => {
      try {
        const response = await fetch(BASE + '/api/qa/health',
          { signal: AbortSignal.timeout(1500) });
        return response.ok;
      } catch {
        // The CI TLS certificate is intentionally self-signed.
        return require('node:child_process').spawnSync('curl', [
          '-ksS', '--max-time', '2', BASE + '/api/qa/health'
        ], { encoding: 'utf8' }).status === 0;
      }
    }, 'HTTPS lab was not ready', 180_000);

    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: 1440, height: 900 },
    });
    const page = await context.newPage();
    const consoleLines = [];
    page.on('console', message => consoleLines.push(message.text()));
    await page.goto(BASE + '/#/login');
    await page.locator('#usuario-login').fill('qa_browser');
    await page.locator('#password-login').fill('synthetic-password');
    await page.getByRole('button', { name: 'Iniciar sesión' }).click();
    await eventually(async () => page.evaluate(() => Boolean(localStorage.getItem('token'))),
      'Angular login did not store access JWT');
    await page.locator('app-layout').waitFor({ timeout: 45_000 });

    const cookie = (await context.cookies(BASE + '/api/auth/refresh'))
      .find(item => item.name === 'suite_refresh');
    assert.ok(cookie, 'Flask did not issue refresh cookie');
    assert.equal(cookie.httpOnly, true);
    assert.equal(cookie.secure, true);
    assert.equal(cookie.sameSite, 'Strict');
    assert.equal(cookie.path, '/api/auth');
    console.log('PASS HTTPS login issues HttpOnly+Secure+Strict cookie');

    // Short JWT lifetime (2m) forces real proactive refresh on human activity.
    await page.mouse.move(380, 185);
    await eventually(async () => (await state(page)).rotations > 0,
      'Active Angular client did not renew access JWT');
    assert.equal(await page.locator('.reauth-modal').count(), 0);
    console.log('PASS active Angular session renews silently, no modal');

    // Virtual backend minutes: two 40-minute spans with real browser
    // interactions between spans must not exceed 45-minute inactivity.
    let lastRotations = (await state(page)).rotations;
    for (let i = 0; i < 2; i++) {
      await jump(page, 40);
      await page.reload();
      await page.locator('app-layout').waitFor({ timeout: 45_000 });
      await page.mouse.move(420 + i * 10, 205 + i * 12);
      await eventually(async () => (await state(page)).rotations > lastRotations,
        'Refresh did not survive virtual minute ' + ((i + 1) * 40));
      lastRotations = (await state(page)).rotations;
      assert.equal((await state(page)).revoked, 0, 'Unexpected session revocation');
      assert.equal(await page.locator('.reauth-modal').count(), 0);
    }
    console.log('PASS active session survives 80 virtual server minutes');

    // Simulate a stale browser activity clock; no 45-minute real wait needed.
    await page.evaluate(() => {
      localStorage.setItem(
        'suite.auth.lastRealActivityAt', String(Date.now() - 46 * 60_000)
      );
      window.dispatchEvent(new Event('focus'));
    });
    const modal = page.locator('.reauth-modal');
    await modal.waitFor({ state: 'visible', timeout: 10_000 });
    assert.equal(await modal.locator('h2').innerText(), 'Reautenticación');
    console.log('PASS 46 minutes of browser inactivity opens only expected modal');

    await modal.locator('input[formcontrolname="password"]').fill('synthetic-password');
    await modal.locator('button[type=submit]').click();
    await modal.waitFor({ state: 'hidden', timeout: 20_000 });
    assert.equal(await page.evaluate(() =>
      Number(localStorage.getItem('suite.auth.lastRealActivityAt')) > Date.now() - 60_000), true);
    console.log('PASS password reauthentication closes inactivity modal');

    // Two tabs share the rotated HttpOnly cookie and the Web Locks namespace.
    const second = await context.newPage();
    await second.goto(BASE + '/#/main');
    await second.locator('app-layout').waitFor({ timeout: 45_000 });
    await Promise.all([
      page.mouse.move(570, 240),
      second.mouse.move(570, 240),
    ]);
    await sleep(1500);
    assert.equal((await state(page)).revoked, 0,
      'Cross-tab rotation replay unexpectedly revoked a session');
    console.log('PASS concurrent same-origin tabs preserve valid refresh session');

    const token = await page.evaluate(() => localStorage.getItem('token'));
    assert.ok(token);
    await page.getByRole('button', { name: 'Cerrar sesión' }).click();
    await eventually(async () => {
      const cookies = await context.cookies(BASE + '/api/auth/refresh');
      return !cookies.some(item => item.name === 'suite_refresh');
    }, 'Browser logout did not delete refresh cookie');

    await eventually(async () => {
      const u = new URL(second.url());
      return u.hash.startsWith('#/login');
    }, 'Second tab did not observe logout');

    const revoked = await context.request.get(BASE + '/api/qa/whoami', {
      headers: { Authorization: 'Bearer ' + token },
    });
    assert.equal(revoked.status(), 401);
    console.log('PASS logout invalidates JWT and synchronizes second tab');
    assert(!consoleLines.some(line => line.includes(token)),
      'Browser console contained raw JWT');
    console.log('PASS console did not expose raw access token');
    await context.close();
    console.log('AUTH_HTTPS_BROWSER_E2E_PASS');
  } catch (error) {
    // Avoid printing cookies, request/response objects or access tokens.
    console.error('AUTH_HTTPS_BROWSER_E2E_FAILED:', error.message);
    process.exitCode = 1;
  } finally {
    if (browser) await browser.close();
  }
})();
