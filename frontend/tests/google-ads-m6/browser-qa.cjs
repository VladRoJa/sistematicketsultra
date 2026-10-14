/**
 * Isolated M6 Chromium QA. No production logins, secrets, uploads or API writes.
 * All /api responses are synthetic and intercepted before Angular sees them.
 */
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = 'http://127.0.0.1:4300';
const EVIDENCE = path.resolve(__dirname, '../../playwright-evidence');
fs.mkdirSync(EVIDENCE, { recursive: true });

const reports = [];
// A decodable, future-expiring synthetic JWT is required because Suite Ultra's
// JwtInterceptor calls isTokenExpired(). All API requests remain intercepted,
// and this fabricated token is never accepted by a real backend.
const qaJwt = [
  Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url'),
  Buffer.from(JSON.stringify({ exp: 4102444800, sub: 'ci-browser-only' })).toString('base64url'),
  Buffer.from('synthetic-signature-never-valid').toString('base64url'),
].join('.');
const fixture = {
  status: 'PREFLIGHT_OK', business_date: '2026-10-13', customer_id: '2739125201',
  campaign_rows: 27, group_rows: 43, approved_branches: 26,
  account_cost_mxn: '950.25', branch_cost_mxn: '900.00', unassigned_cost_mxn: '50.25',
  campaign_sha256: 'a'.repeat(64), ad_group_sha256: 'b'.repeat(64),
  raw_confirm_ticket: 'CI_SYNTHETIC_NO_REAL_SIGNATURE',
  ready_to_stage_raw: true, initial_m6_approval_verified: false,
  eligible_for_structured_ingestion: false, eligible_for_publication: false,
};
const raw = {
  status: 'RAW_PAIR_STAGED', business_date: '2026-10-13',
  uploads: {
    google_ads_campaign_daily: { upload_id: 99101, file_hash_sha256: 'a'.repeat(64), reused_existing: false },
    google_ads_ad_group_daily: { upload_id: 99102, file_hash_sha256: 'b'.repeat(64), reused_existing: false },
  },
  eligible_for_structured_ingestion: false, eligible_for_publication: false,
};
const structured = {
  status: 'STRUCTURED_PAIR_STAGED', business_date: '2026-10-13',
  campaign_upload_id: 99101, ad_group_upload_id: 99102,
  campaign_rows: 27, group_rows: 43, approval_version_id: 99001,
  account_cost_mxn: '950.25', branch_cost_mxn: '900.00',
  unassigned_cost_mxn: '50.25', eligible_for_publication: false,
  funnel_publication: 'NOT_AUTHORIZED',
};
const published = {
  status: 'CANONICAL_DAY_PUBLISHED', publication_id: 99002, revision: 1,
  business_date: '2026-10-13', customer_id: '2739125201',
  campaign_upload_id: 99101, ad_group_upload_id: 99102,
  approval_version_id: 99001, campaign_rows: 27, group_rows: 43,
  account_cost_mxn: '950.25', branch_cost_mxn: '900.00',
  unassigned_cost_mxn: '50.25', is_canonical: true,
};
const correction = {
  business_date: '2026-10-13', customer_id: '2739125201',
  state: 'RAW_ONLY_UNPUBLISHED', raw_reports: [
    { upload_id: 21654, report_type_key: 'google_ads_ad_group_daily', status: 'ACTIVE',
      manual_pair_upload_audit_count: 0, pair_import_audit_count: 0, pair_publish_audit_count: 0 },
    { upload_id: 21655, report_type_key: 'google_ads_campaign_daily', status: 'ACTIVE',
      manual_pair_upload_audit_count: 0, pair_import_audit_count: 0, pair_publish_audit_count: 0 },
  ],
  structured: { campaign_rows: 0, group_rows: 0, campaign_sources: [], group_sources: [] },
  publications: [], has_existing_period_evidence: true,
  replacement_authorized: false, can_delete_existing_raw: false,
  can_auto_republish: false, next_action: 'REVIEW_CORRECTION_POLICY_REQUIRED',
};

async function serverReady() {
  for (let i = 0; i < 90; i++) {
    try { const response = await fetch(BASE); if (response.ok) return; } catch {}
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
  throw new Error('Angular dev server failed to start');
}
async function session(context, role) {
  await context.addInitScript(({ user, token }) => {
    localStorage.setItem('token', token);
    localStorage.setItem('user', JSON.stringify(user));
  }, { user: role, token: qaJwt });
}
async function setup(page, requests) {
  await page.route('**/api/**', async route => {
    const req = route.request();
    const url = new URL(req.url());
    const pathname = url.pathname;
    requests.push({ path: pathname, method: req.method() });
    let status = 200, json = {};
    if (pathname.endsWith('/integrations/google-ads/manual/preview')) json = fixture;
    else if (pathname.endsWith('/integrations/google-ads/manual/confirm')) { status = 201; json = raw; }
    else if (pathname.endsWith('/integrations/google-ads/manual/ingest')) { status = 201; json = structured; }
    else if (pathname.endsWith('/integrations/google-ads/manual/publish')) { status = 201; json = published; }
    else if (pathname.endsWith('/integrations/google-ads/manual/correction-status')) json = correction;
    else if (pathname.includes('/integrations/google-ads/')) json = { enabled: false, authorized: false, customer_id: '2739125201' };
    else if (pathname.endsWith('/auth/session-info')) json = { user: { id: 1, username: 'ADMICORP', rol: 'ADMINISTRADOR' } };
    else if (pathname.endsWith('/auth/')) json = {};
    else json = {};
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(json) });
  });
}
function assert(condition, reason) { if (!condition) throw Error(reason); }
async function run(name, action) {
  try { await action(); reports.push({ name, status: 'PASS' }); console.log('PASS', name); }
  catch (e) { reports.push({ name, status: 'FAIL', error: String(e) }); console.error('FAIL', name, e); }
}
(async () => {
  let browser;
  try {
    await serverReady();
    browser = await chromium.launch({ headless: true });
    for (const size of [{name: 'desktop', width: 1440, height: 900}, {name: 'mobile', width: 390, height: 844}]) {
      const context = await browser.newContext({ viewport: { width: size.width, height: size.height } });
      await session(context, { id: 1, username: 'ADMICORP', rol: 'ADMINISTRADOR' });
      const page = await context.newPage();
      const requests = [];
      await setup(page, requests);
      await run('ADMICORP form displayed - ' + size.name, async () => {
        await page.goto(BASE + '/#/marketing/google-ads');
        await page.getByText('Carga manual de reportes diarios').waitFor({ timeout: 20000 });
        assert(await page.getByLabel('Archivo Excel de campañas').count() === 1, 'campaign input not visible');
        assert(await page.getByLabel('Archivo Excel de grupos de anuncios').count() === 1, 'group input not visible');
        assert(await page.getByText('Consultar estado de un corte existente').count() === 1, 'diagnostic missing');
        await page.screenshot({path: path.join(EVIDENCE, 'form-' + size.name + '.png'), fullPage: true});
      });
      await run('Read-only diagnostic - ' + size.name, async () => {
        const dateControl = page.locator('.manual-ads__diagnostic-date input[type=date]');
        await dateControl.fill('2026-10-13');
        // Fire the same change event Angular binds to when a date input commits.
        await dateControl.dispatchEvent('change');
        const diagnosticButton = page.getByRole('button', { name: 'Consultar evidencias' });
        assert(await diagnosticButton.isEnabled(),
          'diagnostic date not accepted: ' + JSON.stringify(await dateControl.inputValue()));
        await diagnosticButton.click();
        await page.getByText('RAW registrado, sin ingesta estructurada').waitFor();
        assert(await page.getByText('#21654').count() >= 1, 'historical group RAW missing');
        assert(!requests.some(x => x.path.endsWith('/manual/publish')), 'diagnostic caused publish');
        await page.screenshot({path: path.join(EVIDENCE, 'diagnostic-' + size.name + '.png'), fullPage: true});
      });
      await run('Synthetic preview and separate stages - ' + size.name, async () => {
        await page.getByLabel('Archivo Excel de campañas').setInputFiles({
          name: 'Informe de campaña.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          buffer: Buffer.from('SYNTHETIC_CAMPAIGN_CI') });
        await page.getByLabel('Archivo Excel de grupos de anuncios').setInputFiles({
          name: 'Informe de grupo de anuncios.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          buffer: Buffer.from('SYNTHETIC_GROUP_CI') });
        await page.getByRole('button', { name: 'Validar ambos Excel' }).click();
        await page.getByText('Vista previa · 2026-10-13').waitFor();
        assert(!requests.some(x => x.path.endsWith('/manual/confirm')), 'preview saved RAW without confirmation');
        await page.getByText(/Confirmo guardar exclusivamente los RAW/).locator('..').locator('input').check();
        await page.getByRole('button', { name: 'Confirmar carga RAW' }).click();
        await page.getByText('RAW_PAIR_STAGED').first().waitFor();
        assert(!requests.some(x => x.path.endsWith('/manual/ingest')), 'RAW auto-ingested');
        await page.getByText(/Confirmo ingerir campañas y grupos/).locator('..').locator('input').check();
        await page.getByRole('button', { name: 'Ingestar ambos reportes (sin publicar)' }).click();
        await page.getByText(/Resultado de ingesta · STRUCTURED_PAIR_STAGED/).waitFor();
        assert(!requests.some(x => x.path.endsWith('/manual/publish')), 'ingestion auto-published');
        await page.getByText(/Autorizo publicar este día como versión canónica/).locator('..').locator('input').check();
        await page.getByRole('button', { name: 'Publicar este día en Funnel' }).click();
        await page.getByText('Día canónico publicado').waitFor();
        await page.screenshot({path: path.join(EVIDENCE, 'published-' + size.name + '.png'), fullPage: true});
        for (const suffix of ['preview', 'confirm', 'ingest', 'publish']) {
          assert(requests.some(x => x.path.endsWith('/manual/' + suffix)), 'missing explicit ' + suffix);
        }
      });
      await context.close();
    }
    {
      const context = await browser.newContext({ viewport: { width: 1200, height: 800 } });
      await session(context, { id: 2, username: 'REGIONAL_QA', rol: 'ADMINISTRADOR' });
      const page = await context.newPage(), requests = [];
      await setup(page, requests);
      await run('Different administrator never sees ADMICORP manual form', async () => {
        await page.goto(BASE + '/#/marketing/google-ads');
        await page.getByText('Google Ads', { exact: true }).first().waitFor({ timeout: 20000 });
        assert(await page.getByText('Carga manual de reportes diarios').count() === 0, 'manual form exposed');
        assert(!requests.some(x => x.path.includes('/manual/')), 'manual API called');
      });
      await context.close();
    }
  } catch (e) { reports.push({ name: 'Harness', status: 'FAIL', error: String(e) }); console.error(e); }
  finally {
    fs.writeFileSync(path.join(EVIDENCE, 'qa-results.json'), JSON.stringify(reports, null, 2));
    if (browser) await browser.close();
    const failed = reports.filter(x => x.status === 'FAIL');
    console.log('M6_BROWSER_QA', reports.length - failed.length + '/' + reports.length, 'PASS');
    if (failed.length) process.exitCode = 1;
  }
})();
