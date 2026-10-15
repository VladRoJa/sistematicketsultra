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

const preview = {
  status: 'PREFLIGHT_OK', business_date: '2026-10-13',
  customer_id: '2739125201', campaign_rows: 27, group_rows: 43,
  approved_branches: 26, account_cost_mxn: '950.25',
  branch_cost_mxn: '900.00', unassigned_cost_mxn: '50.25',
  campaign_sha256: 'a'.repeat(64), ad_group_sha256: 'b'.repeat(64),
  raw_confirm_ticket: 'CI_SYNTHETIC_NOT_VALID_IN_PRODUCTION',
  ready_to_stage_raw: true,
};
const raw = {
  status: 'RAW_PAIR_STAGED', business_date: '2026-10-13',
  uploads: {
    google_ads_campaign_daily: { upload_id: 99101, file_hash_sha256: 'a'.repeat(64), reused_existing: false },
    google_ads_ad_group_daily: { upload_id: 99102, file_hash_sha256: 'b'.repeat(64), reused_existing: false },
  },
};
const structured = {
  status: 'STRUCTURED_PAIR_STAGED', business_date: '2026-10-13',
  campaign_upload_id: 99101, ad_group_upload_id: 99102,
  campaign_rows: 27, group_rows: 43, approval_version_id: 1,
  account_cost_mxn: '950.25', branch_cost_mxn: '900.00', unassigned_cost_mxn: '50.25',
};
const published = {
  status: 'CANONICAL_DAY_PUBLISHED', publication_id: 99002, revision: 1,
  business_date: '2026-10-13', campaign_rows: 27, group_rows: 43,
  account_cost_mxn: '950.25', branch_cost_mxn: '900.00', unassigned_cost_mxn: '50.25',
};

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
    } else if (pathname.endsWith('/integrations/google-ads/corrections/capabilities')) {
      const isAdmicorp = user.username === 'ADMICORP';
      body = { can_read: isAdmicorp, can_stage_raw: isAdmicorp,
        can_ingest: false, can_review: false, can_promote: false };
    } else if (pathname.endsWith('/integrations/google-ads/corrections/candidates')) {
      body = { cases: [] };
    } else if (pathname.endsWith('/integrations/google-ads/manual/preview')) {
      body = preview;
    } else if (pathname.endsWith('/integrations/google-ads/manual/confirm')) {
      body = raw;
    } else if (pathname.endsWith('/integrations/google-ads/manual/ingest')) {
      body = structured;
    } else if (pathname.endsWith('/integrations/google-ads/manual/publish')) {
      body = published;
    } else if (pathname.includes('/integrations/google-ads/')) {
      body = { enabled: false, authorized: false, customer_id: '2739125201' };
    } else if (pathname.includes('/warehouse/catalog')) {
      body = { sources: [], families: [], operational_roles: [], report_types: [
        { key: 'google_ads_campaign_daily', label: 'Ads campañas', default_period_type: 'rango' },
        { key: 'google_ads_ad_group_daily', label: 'Ads grupos', default_period_type: 'rango' },
        { key: 'venta_total', label: 'Venta total', default_period_type: 'diario' },
      ] };
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
          await run('Warehouse exposes only guarded paired M6 upload - ' + size.name, async () => {
            await page.goto(BASE + '/#/warehouse');
            await page.getByRole('heading', { name: 'Gestión documental' }).waitFor({ timeout: 20000 });
            assert(await page.getByRole('heading', { name: 'Nuevo upload' }).count() === 1,
              'Warehouse upload area missing');
            assert(await page.locator('#warehouse-file[type=file]').count() === 1,
              'Other Warehouse reports lost their original upload');
            assert(await page.getByRole('button', { name: 'Subir archivo' }).count() === 1,
              'Warehouse submit control missing');
            const types = page.locator('#warehouse-report-type');
            await types.getByRole('option', { name: 'Venta total' }).waitFor();
            assert(await types.locator('option[value=google_ads_campaign_daily]').count() === 0,
              'Legacy campaign type still selectable');
            assert(await types.locator('option[value=google_ads_ad_group_daily]').count() === 0,
              'Legacy group type still selectable');
            assert(await types.locator('option[value=google_ads_m6_paired]').count() === 1,
              'M6 paired type missing');
            await types.selectOption('google_ads_m6_paired');
            await page.getByRole('heading', { name: 'Carga manual de reportes diarios' }).waitFor();
            assert(await page.locator('#warehouse-file').count() === 0,
              'Generic single uploader is still visible for Google Ads');
            assert(await page.getByLabel('Archivo Excel de campañas').count() === 1,
              'Paired campaign upload missing');
            assert(await page.getByLabel('Archivo Excel de grupos de anuncios').count() === 1,
              'Paired group upload missing');
            assert(!requests.some(r => r.method === 'POST'), 'Warehouse selection wrote data');
          });

          await run('Warehouse M6 preview-RAW-ingest-publish remain explicit - ' + size.name, async () => {
            await page.getByLabel('Archivo Excel de campañas').setInputFiles({
              name: 'campaign.xlsx',
              mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
              buffer: Buffer.from('SYNTHETIC_CAMPAIGNS'),
            });
            await page.getByLabel('Archivo Excel de grupos de anuncios').setInputFiles({
              name: 'groups.xlsx',
              mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
              buffer: Buffer.from('SYNTHETIC_GROUPS'),
            });
            await page.getByRole('button', { name: 'Validar ambos Excel' }).click();
            await page.getByText('Vista previa · 2026-10-13').waitFor();
            assert(!requests.some(r => r.pathname.endsWith('/manual/confirm')),
              'Preview auto-confirmed RAW');
            await page.getByText(/Confirmo guardar exclusivamente los RAW/).locator('..').locator('input').check();
            await page.getByRole('button', { name: 'Confirmar carga RAW' }).click();
            await page.getByText('RAW_PAIR_STAGED').first().waitFor();
            assert(!requests.some(r => r.pathname.endsWith('/manual/ingest')),
              'RAW auto-ingested');
            await page.getByText(/Confirmo ingerir campañas y grupos/).locator('..').locator('input').check();
            await page.getByRole('button', { name: 'Ingestar ambos reportes (sin publicar)' }).click();
            await page.getByText('Resultado de ingesta · STRUCTURED_PAIR_STAGED').waitFor();
            assert(!requests.some(r => r.pathname.endsWith('/manual/publish')),
              'Ingestion auto-published');
            await page.getByText(/Autorizo publicar este día como versión canónica/).locator('..').locator('input').check();
            await page.getByRole('button', { name: 'Publicar este día en Funnel' }).click();
            await page.getByRole('heading', { name: 'Día canónico publicado' }).waitFor();
            for (const suffix of ['preview', 'confirm', 'ingest', 'publish']) {
              assert(requests.filter(r => r.pathname.endsWith('/manual/' + suffix) && r.method === 'POST').length === 1,
                'Expected one explicit M6 ' + suffix + ' request');
            }
            assert(!requests.some(r => r.pathname === '/api/warehouse/uploads' && r.method === 'POST'),
              'M6 used generic Warehouse uploader');
            await page.screenshot({
              path: path.join(EVIDENCE, 'warehouse-m6-' + size.name + '.png'), fullPage: true
            });
          });
        }
        if (user.username !== 'ADMICORP') {
          await run('Other administrators cannot select or access M6 uploads - ' + size.name, async () => {
            await page.goto(BASE + '/#/warehouse');
            const types = page.locator('#warehouse-report-type');
            await types.getByRole('option', { name: 'Venta total' }).waitFor({ timeout: 20000 });
            assert(await types.locator('option[value=google_ads_m6_paired]').count() === 0,
              'Unauthorized administrator can select paired M6 upload');
            assert(await page.getByLabel('Archivo Excel de campañas').count() === 0,
              'Unauthorized administrator sees M6 upload');
            assert(await page.getByText('Correcciones históricas auditadas').count() === 0,
              'Unauthorized administrator sees correction workflow');
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
