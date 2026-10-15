/**
 * Browser regression for Warehouse-only Google Ads upload UI.
 * No production credentials, uploads, or API writes: all /api responses are mocked.
 */
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = 'http://127.0.0.1:4300';
const EVIDENCE = path.resolve(__dirname, '../../playwright-evidence');
fs.mkdirSync(EVIDENCE, { recursive: true });

const qaJwt = [
  Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url'),
  Buffer.from(JSON.stringify({ exp: 4102444800, sub: 'ci-browser-only' })).toString('base64url'),
  Buffer.from('synthetic-signature-never-valid').toString('base64url')
].join('.');
const results = [];

function assert(condition, reason) {
  if (!condition) throw new Error(reason);
}
async function waitForServer() {
  for (let i = 0; i < 90; i++) {
    try {
      if ((await fetch(BASE)).ok) return;
    } catch {}
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
  throw new Error('Angular dev server did not become ready');
}
async function setup(context, page, user, requests) {
  await context.addInitScript(({ user, token }) => {
    localStorage.setItem('token', token);
    localStorage.setItem('user', JSON.stringify(user));
  }, { user, token: qaJwt });
  await page.route('**/api/**', async route => {
    const req = route.request();
    const pathname = new URL(req.url()).pathname;
    requests.push({ pathname, method: req.method() });
    let body = {};
    if (pathname.endsWith('/auth/session-info')) {
      body = { user };
    } else if (pathname.includes('/integrations/google-ads/')) {
      body = { enabled: false, authorized: false, customer_id: '2739125201' };
    } else if (pathname.includes('/warehouse/catalog')) {
      body = { sources: [], families: [], operational_roles: [], report_types: [] };
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
}
async function run(name, action) {
  try {
    await action();
    results.push({ name, status: 'PASS' });
    console.log('PASS', name);
  } catch (error) {
    results.push({ name, status: 'FAIL', error: String(error) });
    console.error('FAIL', name, error);
  }
}

(async () => {
  let browser;
  try {
    await waitForServer();
    browser = await chromium.launch({ headless: true });
    for (const size of [
      { name: 'desktop', width: 1440, height: 900 },
      { name: 'mobile', width: 390, height: 844 }
    ]) {
      for (const user of [
        { id: 1, username: 'ADMICORP', rol: 'ADMINISTRADOR' },
        { id: 2, username: 'REGIONAL_QA', rol: 'ADMINISTRADOR' }
      ]) {
        const context = await browser.newContext({ viewport: { width: size.width, height: size.height } });
        const page = await context.newPage();
        const requests = [];
        await setup(context, page, user, requests);
        await run('Google Ads administration has no upload form - ' + user.username + ' ' + size.name, async () => {
          await page.goto(BASE + '/#/marketing/google-ads');
          await page.getByRole('heading', { name: 'Google Ads', exact: true }).waitFor({ timeout: 20000 });
          assert(await page.getByRole('heading', { name: '1. Autorización de la cuenta' }).count() === 1,
            'OAuth administration missing');
          assert(await page.getByRole('heading', { name: '3. Consultar campañas' }).count() === 1,
            'Read-only campaign query missing');
          assert(await page.getByText('Carga manual de reportes diarios').count() === 0,
            'M6 daily upload form still visible');
          assert(await page.getByText('Correcciones históricas auditadas').count() === 0,
            'Correction upload UI still visible');
          assert(await page.locator('input[type=file]').count() === 0,
            'Google Ads still exposes a file input');
          assert(await page.getByText(/exclusivamente desde Warehouse/).count() === 1,
            'Warehouse-only user guidance missing');
          assert(!requests.some(r => r.method === 'POST'), 'Admin view posted to an API');
          await page.screenshot({
            path: path.join(EVIDENCE, 'ads-admin-' + user.username.toLowerCase() + '-' + size.name + '.png'),
            fullPage: true
          });
        });

        if (user.username === 'ADMICORP') {
          await run('Warehouse preserves upload form - ' + size.name, async () => {
            await page.goto(BASE + '/#/warehouse');
            await page.getByRole('heading', { name: 'Gestión documental' }).waitFor({ timeout: 20000 });
            assert(await page.getByRole('heading', { name: 'Nuevo upload' }).count() === 1,
              'Warehouse upload area missing');
            assert(await page.locator('#warehouse-file[type=file]').count() === 1,
              'Warehouse file input missing');
            assert(await page.getByRole('button', { name: 'Subir archivo' }).count() === 1,
              'Warehouse submit control missing');
            assert(!requests.some(r => r.method === 'POST'), 'Inspection uploaded a document');
          });
        }
        await context.close();
      }
    }
  } catch (error) {
    results.push({ name: 'Harness', status: 'FAIL', error: String(error) });
    console.error(error);
  } finally {
    fs.writeFileSync(path.join(EVIDENCE, 'qa-results.json'), JSON.stringify(results, null, 2));
    if (browser) await browser.close();
    const failures = results.filter(r => r.status === 'FAIL');
    console.log('GOOGLE_ADS_WAREHOUSE_ONLY_QA', results.length - failures.length + '/' + results.length, 'PASS');
    if (failures.length) process.exitCode = 1;
  }
})();
