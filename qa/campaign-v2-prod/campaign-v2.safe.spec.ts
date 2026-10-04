import { expect, Page, test } from '@playwright/test';
import ExcelJS from 'exceljs';
import fs from 'node:fs';
import path from 'node:path';

const SCREENSHOT_DIR = path.resolve(process.cwd(), 'artifacts/campaign-v2-prod/screenshots');
const EXPECTED_SHEETS = ['Resumen', 'Campañas', 'KPIs', 'Evolución', 'Metadata'];

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function previewWindow(): { from: string; to: string } {
  const explicitFrom = process.env.SUITE_ULTRA_QA_EXPIRED_FROM?.trim();
  const explicitTo = process.env.SUITE_ULTRA_QA_EXPIRED_TO?.trim();
  if (explicitFrom && explicitTo) {
    return { from: explicitFrom, to: explicitTo };
  }

  const to = new Date();
  to.setDate(to.getDate() - 1);
  const from = new Date(to);
  from.setDate(from.getDate() - 90);
  return { from: isoDate(from), to: isoDate(to) };
}

async function installSafeCampaignGuard(page: Page): Promise<void> {
  await page.route('**/api/marketing/campaigns-v2**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method().toUpperCase();
    const pathname = url.pathname.replace(/\/+$/, '');

    const isRead = method === 'GET' || method === 'HEAD';
    const isReadOnlyPost =
      method === 'POST' &&
      (pathname.endsWith('/marketing/campaigns-v2/preview') ||
        pathname.endsWith('/marketing/campaigns-v2/preview-detail'));

    if (!isRead && !isReadOnlyPost) {
      await route.abort('blockedbyclient');
      throw new Error(
        `SAFE smoke blocked mutating Campaign V2 request: ${method} ${pathname}`,
      );
    }

    await route.continue();
  });
}

async function ensureAuthenticated(page: Page): Promise<void> {
  await page.goto('/#/marketing/campaigns-v2');

  if (!page.url().includes('/#/login')) {
    return;
  }

  const username = process.env.SUITE_ULTRA_QA_USERNAME?.trim();
  const password = process.env.SUITE_ULTRA_QA_PASSWORD?.trim();

  if (!username || !password) {
    throw new Error(
      'No QA session available. Run "npm run qa:campaign-v2:auth" once, or provide SUITE_ULTRA_QA_USERNAME/SUITE_ULTRA_QA_PASSWORD.',
    );
  }

  await page.locator('#usuario-login').fill(username);
  await page.locator('#password-login').fill(password);
  await page.getByRole('button', { name: 'Iniciar sesión' }).click();
  await expect(page).toHaveURL(/\/#\/(control|main)/, { timeout: 15_000 });
}

async function openCampaignV2(page: Page): Promise<void> {
  if (!page.url().includes('/#/marketing/campaigns-v2')) {
    await page.goto('/#/marketing/campaigns-v2');
  }

  const reauth = page.getByRole('heading', { name: 'Reautenticación' });
  if (await reauth.isVisible({ timeout: 1_500 }).catch(() => false)) {
    throw new Error(
      'QA session requires reauthentication. Run "npm run qa:campaign-v2:auth" again before continuing.',
    );
  }

  await expect(page.getByRole('heading', { name: 'Campañas V2' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Nueva campaña' })).toBeVisible();
}

async function selectBuilderSource(page: Page, label: string): Promise<void> {
  const builder = page.getByRole('region', { name: 'Nueva campaña' });
  await builder.getByRole('combobox', { name: /Fuente/ }).click();
  await page.getByRole('option', { name: label }).click();
}

function previousCalendarMonth(): string {
  const date = new Date();
  date.setDate(1);
  date.setMonth(date.getMonth() - 1);
  return date.toISOString().slice(0, 7);
}

async function chooseExpiredMembersAudience(page: Page): Promise<void> {
  const builder = page.getByRole('region', { name: 'Nueva campaña' });

  await selectBuilderSource(page, 'Socios vencidos');

  const { from, to } = previewWindow();
  await builder.getByLabel('Vencimiento desde').fill(from);
  await builder.getByLabel('Vencimiento hasta').fill(to);

  for (const family of ['Domiciliado', 'Trimestral']) {
    const checkbox = builder.getByRole('checkbox', { name: family });
    if (!(await checkbox.isChecked())) {
      await checkbox.check();
    }
  }
}

async function chooseActiveMembersAudience(page: Page): Promise<void> {
  const builder = page.getByRole('region', { name: 'Nueva campaña' });

  await selectBuilderSource(page, 'Socios activos');
  const domiciliado = builder.getByRole('checkbox', { name: 'Domiciliado' });
  if (await domiciliado.isVisible()) {
    await domiciliado.check();
  }
}

async function chooseFunnelAudience(page: Page): Promise<void> {
  const builder = page.getByRole('region', { name: 'Nueva campaña' });

  await selectBuilderSource(page, 'Cartera Funnel / Venta Nueva');

  const month = process.env.SUITE_ULTRA_QA_FUNNEL_MONTH?.trim() || previousCalendarMonth();
  await builder.getByLabel('Mes Funnel').fill(month);

  const cutoff = builder.getByLabel('Corte Funnel');
  await expect(cutoff).toBeEnabled({ timeout: 20_000 });
  await expect(builder.getByRole('button', { name: 'Revisar audiencia' })).toBeEnabled({
    timeout: 20_000,
  });
}

async function runPreview(page: Page): Promise<void> {
  const responsePromise = page.waitForResponse(response => {
    const url = new URL(response.url());
    return (
      response.request().method() === 'POST' &&
      url.pathname.replace(/\/+$/, '').endsWith('/marketing/campaigns-v2/preview')
    );
  });

  await page.getByRole('button', { name: 'Revisar audiencia' }).click();
  const response = await responsePromise;
  expect(response.ok(), `Preview failed with HTTP ${response.status()}`).toBeTruthy();
  await expect(page.getByRole('heading', { name: 'Preview vigente' })).toBeVisible();
}

async function screenshot(page: Page, name: string): Promise<void> {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, name),
    fullPage: true,
  });
}

test.beforeEach(async ({ page }) => {
  await installSafeCampaignGuard(page);
  await ensureAuthenticated(page);
});

test('SAFE F1: vencidos Preview sin Freeze', async ({ page }) => {
  await openCampaignV2(page);
  await chooseExpiredMembersAudience(page);
  await runPreview(page);

  await expect(page.getByRole('button', { name: 'Congelar campaña' })).toBeDisabled();
  await expect(page.getByText('Destinatarios finales')).toBeVisible();

  await screenshot(page, 'f1-vencidos-preview.png');
});

test('SAFE F2: vencidos multisegmento', async ({ page }) => {
  await openCampaignV2(page);
  await chooseExpiredMembersAudience(page);

  const builder = page.getByRole('region', { name: 'Nueva campaña' });
  await builder.getByRole('button', { name: 'Seleccionar todas' }).click();

  for (const family of ['Domiciliado', 'Trimestral', 'Convenio', 'Semestre', 'Estudiante']) {
    await expect(builder.getByRole('checkbox', { name: family })).toBeChecked();
  }

  await runPreview(page);
  await screenshot(page, 'f2-vencidos-multisegmento.png');
});

test('SAFE F3: socios activos Preview', async ({ page }) => {
  await openCampaignV2(page);
  await chooseActiveMembersAudience(page);

  const builder = page.getByRole('region', { name: 'Nueva campaña' });
  await expect(builder.getByLabel('Vencimiento desde')).toHaveCount(0);
  await expect(builder.getByLabel('Vencimiento hasta')).toHaveCount(0);

  await runPreview(page);
  await screenshot(page, 'f3-socios-activos-preview.png');
});

test('SAFE F4: Funnel Preview con corte completo', async ({ page }) => {
  await openCampaignV2(page);
  await chooseFunnelAudience(page);
  await runPreview(page);

  await expect(page.getByText('Leads Funnel')).toBeVisible();
  await expect(page.getByText('Compradores excluidos')).toBeVisible();
  await expect(page.getByText('Socios activos excluidos')).toBeVisible();

  await screenshot(page, 'f4-funnel-preview.png');
});

test('SAFE F5: Historical Targeting INCLUDE + ALL', async ({ page }) => {
  await openCampaignV2(page);
  await chooseExpiredMembersAudience(page);

  await page.getByRole('checkbox', { name: 'Aplicar regla histórica' }).check();

  const modeField = page.locator('mat-form-field').filter({ hasText: 'Modo' });
  await modeField.locator('mat-select').click();
  await page.getByRole('option', { name: /Incluir/i }).click();

  const matchField = page.locator('mat-form-field').filter({ hasText: 'Cumplimiento' });
  await matchField.locator('mat-select').click();
  await page.getByRole('option', { name: /Todas|ALL/i }).click();

  await page.getByRole('checkbox', { name: 'Visto' }).check();
  await page.getByRole('checkbox', { name: /Interactuó con un botón/i }).check();

  await runPreview(page);

  await expect(page.getByText(/Historial de campañas/i).first()).toBeVisible();
  await screenshot(page, 'f5-historical-include-all.png');
});

test('SAFE F6: Historical Targeting EXCLUDE + ANY', async ({ page }) => {
  await openCampaignV2(page);
  await chooseExpiredMembersAudience(page);

  const history = page.getByRole('region', { name: 'Historial de campañas' });
  await history.getByRole('checkbox', { name: 'Aplicar regla histórica' }).check();

  const modeField = history.locator('mat-form-field').filter({ hasText: 'Modo' });
  await modeField.locator('mat-select').click();
  await page.getByRole('option', { name: /Excluir/i }).click();

  const matchField = history.locator('mat-form-field').filter({ hasText: 'Cumplimiento' });
  await matchField.locator('mat-select').click();
  await page.getByRole('option', { name: /Cualquiera/i }).click();

  await history.getByRole('checkbox', { name: 'Visto' }).check();
  await history.getByRole('checkbox', { name: 'Fallido' }).check();

  await runPreview(page);
  await screenshot(page, 'f6-historical-exclude-any.png');
});

test('SAFE F7: campaña congelada, Reporting individual y consolidado', async ({ page }) => {
  const qaCampaignName = 'QA V2 - PROD SMOKE - VENCIDOS';
  await openCampaignV2(page);

  const row = page.getByRole('row').filter({ hasText: qaCampaignName }).first();
  await expect(row).toBeVisible({ timeout: 15_000 });
  const frozenCountText = await row.locator('td').nth(4).textContent();
  const frozenCount = Number((frozenCountText || '').replace(/[^0-9]/g, ''));
  expect(frozenCount).toBeGreaterThan(0);

  await row.getByRole('button', { name: 'Ver detalle' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('heading', { name: qaCampaignName })).toBeVisible();

  await dialog.getByRole('button', { name: 'Cargar resultados' }).click();
  await expect(
    dialog.getByText('Aún no hay observaciones persistidas para esta campaña.'),
  ).toBeVisible({ timeout: 20_000 });
  await expect(dialog.getByText('Sin observación')).toBeVisible();
  await expect(
    dialog.getByRole('heading', { name: 'Destinatarios congelados' }),
  ).toBeVisible();

  const individualDownloadPromise = page.waitForEvent('download');
  await dialog.getByRole('button', { name: 'Exportar reporte' }).click();
  const individualDownload = await individualDownloadPromise;
  const individualPath = await individualDownload.path();
  expect(individualPath).toBeTruthy();

  const individualWorkbook = new ExcelJS.Workbook();
  await individualWorkbook.xlsx.readFile(individualPath!);
  expect(individualWorkbook.worksheets.map(sheet => sheet.name)).toEqual(EXPECTED_SHEETS);

  await screenshot(page, 'f7-individual-report.png');
  await dialog.getByRole('button', { name: 'Cerrar' }).click();

  const reporting = page.getByRole('region', { name: 'Reporting Campaign V2' });
  const snapshotField = reporting
    .locator('mat-form-field')
    .filter({ hasText: 'Estado de observación' });
  await snapshotField.locator('mat-select').click();
  await page.getByRole('option', { name: 'Sin observación' }).click();

  await reporting.getByRole('button', { name: 'Cargar reporte' }).click();
  await expect(reporting.getByText(qaCampaignName).first()).toBeVisible({ timeout: 20_000 });
  await expect(reporting.getByText('Exposiciones de destinatarios')).toBeVisible();

  const consolidatedDownloadPromise = page.waitForEvent('download');
  await reporting.getByRole('button', { name: 'Exportar Excel' }).click();
  const consolidatedDownload = await consolidatedDownloadPromise;
  const consolidatedPath = await consolidatedDownload.path();
  expect(consolidatedPath).toBeTruthy();

  const consolidatedWorkbook = new ExcelJS.Workbook();
  await consolidatedWorkbook.xlsx.readFile(consolidatedPath!);
  expect(consolidatedWorkbook.worksheets.map(sheet => sheet.name)).toEqual(EXPECTED_SHEETS);

  await screenshot(page, 'f7-consolidated-report.png');
});

test('SAFE F8: Reporting consolidado, filtro y Excel', async ({ page }) => {
  await openCampaignV2(page);

  const reporting = page.getByRole('region', { name: 'Reporting Campaign V2' });
  const initialResponse = page.waitForResponse(response => {
    const url = new URL(response.url());
    return (
      response.request().method() === 'GET' &&
      url.pathname.replace(/\/+$/, '').endsWith('/marketing/campaigns-v2/reporting')
    );
  });
  await reporting.getByRole('button', { name: 'Cargar reporte' }).click();
  expect((await initialResponse).ok()).toBeTruthy();

  const summaryOrEmpty = reporting
    .getByText('Exposiciones de destinatarios')
    .or(reporting.getByText('No hay campañas visibles que coincidan con estos filtros.'));
  await expect(summaryOrEmpty.first()).toBeVisible();

  const snapshotField = reporting
    .locator('mat-form-field')
    .filter({ hasText: 'Estado de observación' });
  await snapshotField.locator('mat-select').click();
  await page.getByRole('option', { name: 'Sin observación' }).click();

  const filteredResponse = page.waitForResponse(response => {
    const url = new URL(response.url());
    return (
      response.request().method() === 'GET' &&
      url.pathname.replace(/\/+$/, '').endsWith('/marketing/campaigns-v2/reporting') &&
      url.searchParams.get('snapshot_status') === 'WITHOUT_SNAPSHOT'
    );
  });
  await page.getByRole('button', { name: 'Cargar reporte' }).click();
  expect((await filteredResponse).ok()).toBeTruthy();

  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Exportar Excel' }).click();
  const download = await downloadPromise;
  const downloadPath = await download.path();
  expect(downloadPath).toBeTruthy();

  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.readFile(downloadPath!);
  expect(workbook.worksheets.map(sheet => sheet.name)).toEqual(EXPECTED_SHEETS);

  await screenshot(page, 'f8-reporting-without-snapshot.png');
});
