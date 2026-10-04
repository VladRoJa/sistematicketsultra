import { expect, Page, test } from '@playwright/test';
import ExcelJS from 'exceljs';
import fs from 'node:fs';
import path from 'node:path';

const QA_CAMPAIGN_NAME = 'QA V2 - PROD SMOKE - VENCIDOS';
const EXPECTED_SHEETS = ['Resumen', 'Campañas', 'KPIs', 'Evolución', 'Metadata'];
const SCREENSHOT_DIR = path.resolve(process.cwd(), 'artifacts/campaign-v2-prod/screenshots');

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

function parseDisplayedCount(text: string | null): number {
  const normalized = (text || '').replace(/[^0-9]/g, '');
  return normalized ? Number(normalized) : 0;
}

async function installFreezeOnlyGuard(page: Page): Promise<void> {
  let freezeCount = 0;

  await page.route('**/api/marketing/campaigns-v2**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method().toUpperCase();
    const pathname = url.pathname.replace(/\/+$/, '');

    const rootPath = '/api/marketing/campaigns-v2';
    const isRead = method === 'GET' || method === 'HEAD';
    const isReadOnlyPost =
      method === 'POST' &&
      (pathname.endsWith('/marketing/campaigns-v2/preview') ||
        pathname.endsWith('/marketing/campaigns-v2/preview-detail'));

    if (isRead || isReadOnlyPost) {
      await route.continue();
      return;
    }

    if (method === 'POST' && pathname === rootPath) {
      const body = request.postDataJSON() as { name?: string } | null;
      if (freezeCount === 0 && body?.name === QA_CAMPAIGN_NAME) {
        freezeCount += 1;
        await route.continue();
        return;
      }
    }

    await route.abort('blockedbyclient');
    throw new Error(
      `WRITE_QA blocked unexpected Campaign V2 mutation: ${method} ${pathname}`,
    );
  });
}

async function ensureAuthenticated(page: Page): Promise<void> {
  await page.goto('/#/marketing/campaigns-v2');

  if (!page.url().includes('/#/login')) {
    return;
  }

  throw new Error(
    'No QA session available. Run "npm run qa:campaign-v2:auth" before WRITE_QA.',
  );
}

async function openCampaignV2(page: Page): Promise<void> {
  if (!page.url().includes('/#/marketing/campaigns-v2')) {
    await page.goto('/#/marketing/campaigns-v2');
  }
  await expect(page.getByRole('heading', { name: 'Campañas V2' })).toBeVisible();
}

async function prepareExpiredAudience(page: Page): Promise<number> {
  const builder = page.getByRole('region', { name: 'Nueva campaña' });
  await builder.getByRole('combobox', { name: /Fuente/ }).click();
  await page.getByRole('option', { name: 'Socios vencidos' }).click();

  const { from, to } = previewWindow();
  await builder.getByLabel('Vencimiento desde').fill(from);
  await builder.getByLabel('Vencimiento hasta').fill(to);

  for (const family of ['Domiciliado', 'Trimestral']) {
    const checkbox = builder.getByRole('checkbox', { name: family });
    if (!(await checkbox.isChecked())) {
      await checkbox.check();
    }
  }

  const responsePromise = page.waitForResponse(response => {
    const url = new URL(response.url());
    return (
      response.request().method() === 'POST' &&
      url.pathname.replace(/\/+$/, '').endsWith('/marketing/campaigns-v2/preview')
    );
  });

  await builder.getByRole('button', { name: 'Revisar audiencia' }).click();
  const response = await responsePromise;
  expect(response.ok(), `Preview failed with HTTP ${response.status()}`).toBeTruthy();

  const recipientsMetric = page.getByRole('button').filter({ hasText: 'Destinatarios finales' });
  await expect(recipientsMetric).toBeVisible();
  const previewCount = parseDisplayedCount(await recipientsMetric.locator('strong').textContent());
  expect(previewCount, 'WRITE_QA requires a non-empty Preview before Freeze').toBeGreaterThan(0);

  return previewCount;
}

async function validateWorkbook(downloadPath: string): Promise<void> {
  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.readFile(downloadPath);
  expect(workbook.worksheets.map(sheet => sheet.name)).toEqual(EXPECTED_SHEETS);
}

async function screenshot(page: Page, name: string): Promise<void> {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, name),
    fullPage: true,
  });
}

test.beforeEach(async ({ page }) => {
  expect(
    process.env.SUITE_ULTRA_QA_ALLOW_WRITE,
    'WRITE_QA requires SUITE_ULTRA_QA_ALLOW_WRITE=FREEZE_ONCE',
  ).toBe('FREEZE_ONCE');

  await installFreezeOnlyGuard(page);
  await ensureAuthenticated(page);
});

test('WRITE_QA: Freeze único + detalle + Reporting individual + consolidado', async ({ page }) => {
  test.setTimeout(360_000);
  await openCampaignV2(page);

  let row = page.getByRole('row').filter({ hasText: QA_CAMPAIGN_NAME });
  let frozenCount: number;

  if (await row.count()) {
    frozenCount = parseDisplayedCount(await row.locator('td').nth(4).textContent());
    expect(frozenCount).toBeGreaterThan(0);
  } else {
    const previewCount = await prepareExpiredAudience(page);
    const builder = page.getByRole('region', { name: 'Nueva campaña' });

    await builder.getByLabel('Nombre de campaña').fill(QA_CAMPAIGN_NAME);
    const freezeButton = builder.getByRole('button', { name: 'Congelar campaña' });
    await expect(freezeButton).toBeEnabled();

    const freezeResponsePromise = page.waitForResponse(
      response => {
        const url = new URL(response.url());
        return (
          response.request().method() === 'POST' &&
          url.pathname.replace(/\/+$/, '') === '/api/marketing/campaigns-v2'
        );
      },
      { timeout: 300_000 },
    );

    await freezeButton.click();
    const freezeResponse = await freezeResponsePromise;
    expect(freezeResponse.ok(), `Freeze failed with HTTP ${freezeResponse.status()}`).toBeTruthy();

    const frozen = (await freezeResponse.json()) as {
      id: number;
      name: string;
      recipient_count: number;
    };
    expect(frozen.name).toBe(QA_CAMPAIGN_NAME);
    expect(frozen.recipient_count).toBe(previewCount);
    expect(frozen.id).toBeGreaterThan(0);
    frozenCount = frozen.recipient_count;

    await expect(page.getByText(new RegExp(`Campaña "${QA_CAMPAIGN_NAME}" creada con`))).toBeVisible();

    row = page.getByRole('row').filter({ hasText: QA_CAMPAIGN_NAME });
    await expect(row).toBeVisible();
  }

  await expect(row).toContainText(frozenCount.toLocaleString('en-US'));

  await row.getByRole('button', { name: 'Ver detalle' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('heading', { name: QA_CAMPAIGN_NAME })).toBeVisible();

  await dialog.getByRole('button', { name: 'Cargar resultados' }).click();
  await expect(
    dialog.getByText('Aún no hay observaciones persistidas para esta campaña.'),
  ).toBeVisible();
  await expect(dialog.getByText('Sin observación')).toBeVisible();

  await screenshot(page, 'write-qa-individual-report.png');

  const individualDownloadPromise = page.waitForEvent('download');
  await dialog.getByRole('button', { name: 'Exportar reporte' }).click();
  const individualDownload = await individualDownloadPromise;
  const individualPath = await individualDownload.path();
  expect(individualPath).toBeTruthy();
  await validateWorkbook(individualPath!);

  await dialog.getByRole('button', { name: 'Cerrar' }).click();

  const reporting = page.getByRole('region', { name: 'Reporting Campaign V2' });
  const snapshotField = reporting
    .locator('mat-form-field')
    .filter({ hasText: 'Estado de observación' });
  await snapshotField.locator('mat-select').click();
  await page.getByRole('option', { name: 'Sin observación' }).click();

  await reporting.getByRole('button', { name: 'Cargar reporte' }).click();
  await expect(reporting.getByText(QA_CAMPAIGN_NAME)).toBeVisible();
  await expect(reporting.getByText('Exposiciones de destinatarios')).toBeVisible();

  await screenshot(page, 'write-qa-consolidated-report.png');

  const consolidatedDownloadPromise = page.waitForEvent('download');
  await reporting.getByRole('button', { name: 'Exportar Excel' }).click();
  const consolidatedDownload = await consolidatedDownloadPromise;
  const consolidatedPath = await consolidatedDownload.path();
  expect(consolidatedPath).toBeTruthy();
  await validateWorkbook(consolidatedPath!);
});
