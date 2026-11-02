// Real Angular/Chromium and XLSX download; synthetic HTTP responses, no live DB.
const { chromium } = require('playwright');
const { Workbook } = require('exceljs');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');

(async () => {
  const root = path.resolve(__dirname, '../dist/frontend-angular');
  const server = http.createServer((req, res) => {
    const file = path.resolve(root, '.' + (req.url === '/' ? '/index.html' : req.url.split('?')[0]));
    if (!file.startsWith(root + path.sep) || !fs.existsSync(file)) { res.writeHead(404).end(); return; }
    res.setHeader('Content-Type', ({ '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html' })[path.extname(file)] || 'application/octet-stream');
    fs.createReadStream(file).pipe(res);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ acceptDownloads: true });
    const base = `http://127.0.0.1:${server.address().port}`;
    const user = { id: 17, username: 'external-test', rol: 'PROVEEDOR_FUNNEL_ORIGINAL', sucursal_id: 1000, sucursales_ids: [2, 7], department_id: 1 };
    const enc = obj => Buffer.from(JSON.stringify(obj)).toString('base64url');
    const token = enc({ alg: 'HS256' }) + '.' + enc({ sub: '17', rol: user.rol, exp: Math.floor(Date.now() / 1000) + 3600 }) + '.synthetic';
    const options = [
      { sucursal_id: 2, sucursal: 'Club Dos QA', region_id: 1, region: 'Región QA' },
      { sucursal_id: 7, sucursal: 'Club Siete QA', region_id: 2, region: 'Otra región QA' },
    ];
    const source = fs.readFileSync(path.join(__dirname, '../src/app/marketing-sales-funnel/marketing-sales-funnel.models.ts'), 'utf8');
    const metricBlock = source.split('export interface MarketingSalesFunnelMetrics {')[1].split('\n}')[0];
    const metrics = Object.fromEntries([...metricBlock.matchAll(/^\s+(\w+)\??:/gm)].map(m => [m[1], 0]));
    Object.assign(metrics, { origin_breakdown: [], btl_origin_breakdown: [], investment: 100, leads_meta: 10, sales_total: 2, visits_total: 4 });
    const unexpected = [], requests = [], errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.origin !== base) return route.abort();
      if (!url.pathname.startsWith('/api/')) return route.continue();
      requests.push(url);
      if (url.pathname === '/api/auth/login') return route.fulfill({ json: { token, user } });
      if (url.pathname === '/api/auth/session-info') return route.fulfill({ json: { user } });
      if (url.pathname !== '/api/marketing/sales-funnel') {
        unexpected.push(url.pathname); return route.fulfill({ status: 403, json: {} });
      }
      assert.equal(url.searchParams.get('visit_mode'), 'registered_only');
      const month = url.searchParams.get('month');
      const ids = url.searchParams.get('branch_ids')?.split(',').map(Number) || [2, 7];
      assert(ids.every(id => user.sucursales_ids.includes(id)));
      const cutoff = url.searchParams.get('cutoff_date') || month + '-28';
      return route.fulfill({ json: {
        month, selected_cutoff_date: cutoff, available_cutoff_dates: [month + '-27', month + '-28'],
        scope: { type: 'ASSIGNED_BRANCHES', branch_ids: ids }, scope_options: options,
        summary: metrics, branches: options.filter(b => ids.includes(b.sucursal_id)).map(b => ({ ...metrics, ...b })),
        source: { iventas_sync_run_ids: [], match_window_days: 30 },
        data_quality: { limitations: [], crm_history_available: true },
      }});
    });
    await page.goto(base + '/#/login');
    await page.getByLabel('Usuario', { exact: true }).fill('external-test');
    await page.getByLabel('Contraseña', { exact: true }).fill('test-password');
    await page.getByRole('button', { name: 'Iniciar sesión' }).click();
    await page.waitForURL('**/#/marketing-conversion/venta-total-original');
    await page.getByRole('button', { name: 'Exportar Excel' }).waitFor();
    assert.equal(await page.locator('.suite-main-nav__item').count(), 1);
    assert.equal(await page.locator('app-system-daily-check-gate').count(), 0);
    assert.equal(await page.locator('app-campaign-v2-background-dock').count(), 0);
    assert.equal(await page.locator('.suite-floating-layer').count(), 0);
    assert.equal(await page.locator('.table-detail-link:not([disabled])').count(), 0);
    await page.getByLabel('Sucursal del Funnel de Venta Nueva', { exact: true }).click();
    assert.deepEqual(await page.getByRole('option').allTextContents().then(xs => xs.map(x => x.trim())),
      ['Todas las sucursales', 'Club Dos QA', 'Club Siete QA']);
    const filteredResponse = page.waitForResponse(r => r.url().includes('branch_ids=7'));
    await page.getByRole('option', { name: 'Club Siete QA', exact: true }).click();
    await filteredResponse;
    await page.locator('.branch-export-action:not([disabled])').waitFor();
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Exportar Excel' }).click();
    const download = await downloadPromise;
    const workbook = new Workbook();
    await workbook.xlsx.readFile(await download.path());
    const cells = JSON.stringify(workbook.worksheets[0].getSheetValues());
    assert(cells.includes('Club Siete QA'));
    assert(!cells.includes('Club Dos QA'));
    for (const url of ['/main/ver-tickets', '/inventario', '/pm/calendario', '/warehouse',
      '/warehouse/track', '/marketing-conversion/venta-total', '/marketing/campaigns-v2', '/admin/usuarios', '/admin']) {
      await page.goto(base + '/#' + url);
      await page.waitForURL('**/#/marketing-conversion/venta-total-original');
      await page.getByRole('button', { name: 'Exportar Excel' }).waitFor();
    }
    await page.getByRole('button', { name: 'Cerrar sesión', exact: true }).click();
    await page.waitForURL('**/#/login');
    assert.deepEqual(unexpected, []);
    assert.deepEqual(errors, []);
    console.log('PASS: login, restricted menu, branch filter, real scoped XLSX, direct URLs, logout; no unrelated API requests. Requests:', requests.length);
  } finally {
    await browser?.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
