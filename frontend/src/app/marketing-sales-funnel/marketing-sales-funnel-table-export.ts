import {
  Workbook,
  Worksheet,
} from 'exceljs';

import { MarketingDashboardResponse } from '../marketing-conversion/marketing.models';
import {
  MarketingSalesFunnelBranch,
  MarketingSalesFunnelScopeOption,
} from './marketing-sales-funnel.models';

interface FunnelBranchExportOptions {
  month: string;
  branches: MarketingSalesFunnelBranch[];
  investmentDashboard: MarketingDashboardResponse | null;
  scopeOptions: MarketingSalesFunnelScopeOption[];
  regionId: number | null;
  branchId: number | null;
}

interface BranchRowLayout {
  branchId: number;
  row: number;
}

interface RegionLayout {
  branchIds: number[];
  firstRow: number;
  lastRow: number;
  subtotalRow: number;
}

interface ExportTotals {
  investment: number | null;
  leads: number;
  visitors: number;
  salesDigital: number;
  salesDigitalOrganic: number;
  salesWeb: number;
  salesBtl: number;
  salesTotal: number;
  revenueDigital: number;
  revenueWeb: number;
  revenueBtl: number;
  revenueTotal: number;
}

const TEMPLATE_ASSET =
  'assets/templates/marketing-sales-funnel-agosto-template.b64';

const BRANCH_LAYOUT: BranchRowLayout[] = [
  { branchId: 1, row: 2 },
  { branchId: 2, row: 3 },
  { branchId: 3, row: 4 },
  { branchId: 4, row: 5 },
  { branchId: 5, row: 6 },
  { branchId: 6, row: 7 },
  { branchId: 7, row: 9 },
  { branchId: 8, row: 10 },
  { branchId: 9, row: 11 },
  { branchId: 10, row: 12 },
  { branchId: 11, row: 13 },
  { branchId: 12, row: 14 },
  { branchId: 13, row: 15 },
  { branchId: 14, row: 17 },
  { branchId: 15, row: 18 },
  { branchId: 16, row: 19 },
  { branchId: 20, row: 20 },
  { branchId: 17, row: 22 },
  { branchId: 18, row: 23 },
  { branchId: 24, row: 24 },
  { branchId: 26, row: 25 },
  { branchId: 19, row: 27 },
  { branchId: 21, row: 28 },
  { branchId: 22, row: 29 },
  { branchId: 23, row: 30 },
  { branchId: 25, row: 31 },
];

const REGION_LAYOUT: RegionLayout[] = [
  {
    branchIds: [1, 2, 3, 4, 5, 6],
    firstRow: 2,
    lastRow: 7,
    subtotalRow: 8,
  },
  {
    branchIds: [7, 8, 9, 10, 11, 12, 13],
    firstRow: 9,
    lastRow: 15,
    subtotalRow: 16,
  },
  {
    branchIds: [14, 15, 16, 20],
    firstRow: 17,
    lastRow: 20,
    subtotalRow: 21,
  },
  {
    branchIds: [17, 18, 24, 26],
    firstRow: 22,
    lastRow: 25,
    subtotalRow: 26,
  },
  {
    branchIds: [19, 21, 22, 23, 25],
    firstRow: 27,
    lastRow: 31,
    subtotalRow: 32,
  },
];

const HEADER_VALUES = [
  'Sucursal',
  'Inversión',
  'Leads',
  'Visitantes totales',
  'Ventas digitales',
  'Ventas digitales orgánicas',
  'Venta web',
  'Venta BTL',
  'Ventas totales',
  'Ingreso digital',
  'Ingreso web',
  'Ingreso BTL',
  'Ingreso total',
  'Lead → visita',
  'Visita → venta digital',
  'Lead → venta',
  'Costo por lead (CPL)',
  'Costo por visita (CPT)',
  'Costo por venta (CAC)',
];

const SUBTOTAL_ROWS = REGION_LAYOUT.map((region) => region.subtotalRow);
const DATA_COLUMNS = 'BCDEFGHIJKLMNOPQRS'.split('');

export function exportMarketingSalesFunnelBranchTable(
  options: FunnelBranchExportOptions,
): void {
  if (!options.branches.length) {
    return;
  }

  void exportFromAugustTemplate(options).catch((error) => {
    console.error(
      'No se pudo exportar el Funnel Venta Nueva con la plantilla oficial.',
      error,
    );
  });
}

async function exportFromAugustTemplate(
  options: FunnelBranchExportOptions,
): Promise<void> {
  const workbook = await loadTemplateWorkbook();
  const worksheet = workbook.getWorksheet('Agosto');

  if (!worksheet) {
    throw new Error('La plantilla no contiene la pestaña Agosto.');
  }

  removeNonTemplateWorksheets(workbook, worksheet);
  worksheet.name = resolveMonthSheetName(options.month);

  writeHeaders(worksheet);

  const branchById = new Map<number, MarketingSalesFunnelBranch>(
    options.branches.map((branch) => [branch.sucursal_id, branch]),
  );
  const investmentByBranch = buildInvestmentMap(options);

  for (const layout of BRANCH_LAYOUT) {
    const branch = branchById.get(layout.branchId) ?? null;
    clearBranchRow(worksheet, layout.row);
    worksheet.getRow(layout.row).hidden = branch === null;

    if (branch !== null) {
      writeBranchRow(
        worksheet,
        layout.row,
        branch,
        investmentByBranch.get(branch.sucursal_id) ?? null,
      );
    }
  }

  for (const region of REGION_LAYOUT) {
    const regionBranches = region.branchIds
      .map((branchId) => branchById.get(branchId) ?? null)
      .filter(
        (branch): branch is MarketingSalesFunnelBranch => branch !== null,
      );

    worksheet.getRow(region.subtotalRow).hidden = (
      options.branchId !== null || regionBranches.length === 0
    );

    writeRegionSubtotal(
      worksheet,
      region,
      regionBranches,
      investmentByBranch,
    );
  }

  const totals = buildTotals(options.branches, investmentByBranch);
  writeBottomSummary(worksheet, totals);

  workbook.calcProperties.fullCalcOnLoad = true;

  const buffer = await workbook.xlsx.writeBuffer();
  downloadWorkbook(
    buffer as BlobPart,
    buildExportFilename(options),
  );
}

async function loadTemplateWorkbook(): Promise<Workbook> {
  const response = await fetch(TEMPLATE_ASSET, {
    cache: 'no-store',
  });

  if (!response.ok) {
    throw new Error(
      `No se pudo cargar la plantilla Excel (${response.status}).`,
    );
  }

  const encoded = (await response.text()).replace(/\s+/g, '');
  const bytes = decodeBase64(encoded);
  const workbook = new Workbook();

  await workbook.xlsx.load(bytes.buffer as any);

  return workbook;
}

function decodeBase64(value: string): Uint8Array {
  const binary = window.atob(value);
  const bytes = new Uint8Array(binary.length);

  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }

  return bytes;
}

function removeNonTemplateWorksheets(
  workbook: Workbook,
  templateWorksheet: Worksheet,
): void {
  for (const worksheet of [...workbook.worksheets]) {
    if (worksheet.id !== templateWorksheet.id) {
      workbook.removeWorksheet(worksheet.id);
    }
  }
}

function writeHeaders(worksheet: Worksheet): void {
  HEADER_VALUES.forEach((value, index) => {
    worksheet.getCell(1, index + 1).value = value;
  });
}

function buildInvestmentMap(
  options: FunnelBranchExportOptions,
): Map<number, number | null> {
  const result = new Map<number, number | null>();

  if (
    options.investmentDashboard
    && options.investmentDashboard.month === options.month
  ) {
    for (const branch of options.investmentDashboard.branches) {
      result.set(
        branch.sucursal_id,
        branch.investment ?? null,
      );
    }
  }

  return result;
}

function clearBranchRow(
  worksheet: Worksheet,
  rowNumber: number,
): void {
  for (const column of DATA_COLUMNS) {
    worksheet.getCell(`${column}${rowNumber}`).value = null;
  }
}

function writeBranchRow(
  worksheet: Worksheet,
  rowNumber: number,
  branch: MarketingSalesFunnelBranch,
  investment: number | null,
): void {
  worksheet.getCell(`A${rowNumber}`).value = branch.sucursal;
  worksheet.getCell(`B${rowNumber}`).value = investment;
  worksheet.getCell(`C${rowNumber}`).value = branch.leads_meta;
  worksheet.getCell(`D${rowNumber}`).value = branch.visits_total;
  worksheet.getCell(`E${rowNumber}`).value = branch.sales_digital;
  worksheet.getCell(`F${rowNumber}`).value = branch.sales_digital_organic;
  worksheet.getCell(`G${rowNumber}`).value = branch.sales_web;
  worksheet.getCell(`H${rowNumber}`).value = branch.sales_btl;

  setFormulaCell(
    worksheet,
    `I${rowNumber}`,
    `SUM(E${rowNumber}:H${rowNumber})`,
    branch.sales_total,
  );

  worksheet.getCell(`J${rowNumber}`).value = branch.revenue_digital;
  worksheet.getCell(`K${rowNumber}`).value = branch.revenue_web;
  worksheet.getCell(`L${rowNumber}`).value = branch.revenue_btl;

  setFormulaCell(
    worksheet,
    `M${rowNumber}`,
    `SUM(J${rowNumber}:L${rowNumber})`,
    branch.revenue_total,
  );

  setFormulaCell(
    worksheet,
    `N${rowNumber}`,
    `IFERROR(D${rowNumber}/C${rowNumber},"")`,
    branch.lead_to_visit_rate,
  );
  setFormulaCell(
    worksheet,
    `O${rowNumber}`,
    `IFERROR(E${rowNumber}/D${rowNumber},"")`,
    branch.visit_to_digital_sale_rate,
  );
  setFormulaCell(
    worksheet,
    `P${rowNumber}`,
    `IFERROR(E${rowNumber}/C${rowNumber},"")`,
    branch.lead_to_sale_rate,
  );

  setFormulaCell(
    worksheet,
    `Q${rowNumber}`,
    `IF(OR(B${rowNumber}="",C${rowNumber}=0),"",B${rowNumber}/C${rowNumber})`,
    safeDivide(investment, branch.leads_meta),
  );
  setFormulaCell(
    worksheet,
    `R${rowNumber}`,
    `IF(OR(B${rowNumber}="",D${rowNumber}=0),"",B${rowNumber}/D${rowNumber})`,
    safeDivide(investment, branch.visits_total),
  );
  setFormulaCell(
    worksheet,
    `S${rowNumber}`,
    `IF(OR(B${rowNumber}="",E${rowNumber}+F${rowNumber}=0),"",B${rowNumber}/(E${rowNumber}+F${rowNumber}))`,
    safeDivide(
      investment,
      branch.sales_digital + branch.sales_digital_organic,
    ),
  );
}

function writeRegionSubtotal(
  worksheet: Worksheet,
  region: RegionLayout,
  branches: MarketingSalesFunnelBranch[],
  investmentByBranch: Map<number, number | null>,
): void {
  const totals = buildTotals(branches, investmentByBranch);
  const row = region.subtotalRow;

  worksheet.getCell(`A${row}`).value = null;

  setSumFormula(worksheet, `B${row}`, 'B', region, totals.investment);
  setSumFormula(worksheet, `C${row}`, 'C', region, totals.leads);
  setSumFormula(worksheet, `D${row}`, 'D', region, totals.visitors);
  setSumFormula(worksheet, `E${row}`, 'E', region, totals.salesDigital);
  setSumFormula(
    worksheet,
    `F${row}`,
    'F',
    region,
    totals.salesDigitalOrganic,
  );
  setSumFormula(worksheet, `G${row}`, 'G', region, totals.salesWeb);
  setSumFormula(worksheet, `H${row}`, 'H', region, totals.salesBtl);
  setSumFormula(worksheet, `I${row}`, 'I', region, totals.salesTotal);
  setSumFormula(worksheet, `J${row}`, 'J', region, totals.revenueDigital);
  setSumFormula(worksheet, `K${row}`, 'K', region, totals.revenueWeb);
  setSumFormula(worksheet, `L${row}`, 'L', region, totals.revenueBtl);
  setSumFormula(worksheet, `M${row}`, 'M', region, totals.revenueTotal);

  setFormulaCell(
    worksheet,
    `N${row}`,
    `IFERROR(D${row}/C${row},"")`,
    safeDivide(totals.visitors, totals.leads),
  );
  setFormulaCell(
    worksheet,
    `O${row}`,
    `IFERROR(E${row}/D${row},"")`,
    safeDivide(totals.salesDigital, totals.visitors),
  );
  setFormulaCell(
    worksheet,
    `P${row}`,
    `IFERROR(E${row}/C${row},"")`,
    safeDivide(totals.salesDigital, totals.leads),
  );
  setFormulaCell(
    worksheet,
    `Q${row}`,
    `IF(OR(B${row}="",C${row}=0),"",B${row}/C${row})`,
    safeDivide(totals.investment, totals.leads),
  );
  setFormulaCell(
    worksheet,
    `R${row}`,
    `IF(OR(B${row}="",D${row}=0),"",B${row}/D${row})`,
    safeDivide(totals.investment, totals.visitors),
  );
  setFormulaCell(
    worksheet,
    `S${row}`,
    `IF(OR(B${row}="",E${row}+F${row}=0),"",B${row}/(E${row}+F${row}))`,
    safeDivide(
      totals.investment,
      totals.salesDigital + totals.salesDigitalOrganic,
    ),
  );
}

function setSumFormula(
  worksheet: Worksheet,
  address: string,
  column: string,
  region: RegionLayout,
  result: number | null,
): void {
  setFormulaCell(
    worksheet,
    address,
    `SUM(${column}${region.firstRow}:${column}${region.lastRow})`,
    result,
  );
}

function buildTotals(
  branches: MarketingSalesFunnelBranch[],
  investmentByBranch: Map<number, number | null>,
): ExportTotals {
  const investments = branches
    .map((branch) => investmentByBranch.get(branch.sucursal_id) ?? null)
    .filter((value): value is number => value !== null);

  return {
    investment: (
      investments.length > 0
        ? investments.reduce((sum, value) => sum + value, 0)
        : null
    ),
    leads: sumBranchMetric(branches, (branch) => branch.leads_meta),
    visitors: sumBranchMetric(branches, (branch) => branch.visits_total),
    salesDigital: sumBranchMetric(
      branches,
      (branch) => branch.sales_digital,
    ),
    salesDigitalOrganic: sumBranchMetric(
      branches,
      (branch) => branch.sales_digital_organic,
    ),
    salesWeb: sumBranchMetric(branches, (branch) => branch.sales_web),
    salesBtl: sumBranchMetric(branches, (branch) => branch.sales_btl),
    salesTotal: sumBranchMetric(branches, (branch) => branch.sales_total),
    revenueDigital: sumBranchMetric(
      branches,
      (branch) => branch.revenue_digital,
    ),
    revenueWeb: sumBranchMetric(branches, (branch) => branch.revenue_web),
    revenueBtl: sumBranchMetric(branches, (branch) => branch.revenue_btl),
    revenueTotal: sumBranchMetric(branches, (branch) => branch.revenue_total),
  };
}

function sumBranchMetric(
  branches: MarketingSalesFunnelBranch[],
  selector: (branch: MarketingSalesFunnelBranch) => number,
): number {
  return branches.reduce(
    (total, branch) => total + selector(branch),
    0,
  );
}

function writeBottomSummary(
  worksheet: Worksheet,
  totals: ExportTotals,
): void {
  setFormulaCell(
    worksheet,
    'B34',
    subtotalSumFormula('B'),
    totals.investment,
  );
  setFormulaCell(
    worksheet,
    'C34',
    subtotalSumFormula('C'),
    totals.leads,
  );
  setFormulaCell(
    worksheet,
    'D34',
    subtotalSumFormula('D'),
    totals.visitors,
  );
  setFormulaCell(
    worksheet,
    'E34',
    subtotalSumFormula('E'),
    totals.salesDigital,
  );
  setFormulaCell(
    worksheet,
    'J34',
    `IF(OR(B34="",${subtotalMultiSumFormula(['E', 'F'])}=0),"",B34/${subtotalMultiSumFormula(['E', 'F'])})`,
    safeDivide(
      totals.investment,
      totals.salesDigital + totals.salesDigitalOrganic,
    ),
  );

  setFormulaCell(
    worksheet,
    'D35',
    'IFERROR(D34/C34,"")',
    safeDivide(totals.visitors, totals.leads),
  );
  setFormulaCell(
    worksheet,
    'E35',
    'IFERROR(E34/D34,"")',
    safeDivide(totals.salesDigital, totals.visitors),
  );

  worksheet.getCell('A37').value = 'Total de ventas nuevas';
  setFormulaCell(
    worksheet,
    'B37',
    subtotalSumFormula('I'),
    totals.salesTotal,
  );

  worksheet.getCell('A38').value = 'Ventas via Mkt Digital';
  setFormulaCell(
    worksheet,
    'B38',
    `${subtotalSumFormula('E')}+${subtotalSumFormula('F')}`,
    totals.salesDigital + totals.salesDigitalOrganic,
  );
  setFormulaCell(
    worksheet,
    'C38',
    'IFERROR(B38/B37,"")',
    safeDivide(
      totals.salesDigital + totals.salesDigitalOrganic,
      totals.salesTotal,
    ),
  );

  worksheet.getCell('A39').value = 'Ventas (Referidos, walk in, convenios)';
  setFormulaCell(
    worksheet,
    'B39',
    'B37-B38',
    totals.salesTotal - totals.salesDigital - totals.salesDigitalOrganic,
  );
  setFormulaCell(
    worksheet,
    'C39',
    'IFERROR(B39/B37,"")',
    safeDivide(
      totals.salesTotal - totals.salesDigital - totals.salesDigitalOrganic,
      totals.salesTotal,
    ),
  );

  worksheet.getCell('D37').value =
    'GOAL: 50% del total de las venta vía Mkt Digital';
  setFormulaCell(
    worksheet,
    'D38',
    'B37*0.5',
    totals.salesTotal * 0.5,
  );
  setFormulaCell(
    worksheet,
    'D39',
    'B39',
    totals.salesTotal - totals.salesDigital - totals.salesDigitalOrganic,
  );
  setFormulaCell(
    worksheet,
    'D40',
    'SUM(D38:D39)',
    (
      (totals.salesTotal * 0.5)
      + totals.salesTotal
      - totals.salesDigital
      - totals.salesDigitalOrganic
    ),
  );
}

function subtotalSumFormula(column: string): string {
  return `SUM(${SUBTOTAL_ROWS.map((row) => `${column}${row}`).join(',')})`;
}

function subtotalMultiSumFormula(columns: string[]): string {
  const cells = columns.flatMap((column) =>
    SUBTOTAL_ROWS.map((row) => `${column}${row}`),
  );

  return `SUM(${cells.join(',')})`;
}

function setFormulaCell(
  worksheet: Worksheet,
  address: string,
  formula: string,
  result: number | null,
): void {
  worksheet.getCell(address).value = {
    formula,
    result: result ?? '',
  } as any;
}

function safeDivide(
  numerator: number | null,
  denominator: number,
): number | null {
  if (numerator === null || denominator <= 0) {
    return null;
  }

  return numerator / denominator;
}

function downloadWorkbook(
  buffer: BlobPart,
  filename: string,
): void {
  const blob = new Blob(
    [buffer],
    {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    },
  );
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');

  anchor.href = url;
  anchor.download = filename;
  anchor.click();

  window.URL.revokeObjectURL(url);
}

function buildExportFilename(options: FunnelBranchExportOptions): string {
  const scopeLabel = resolveScopeLabel(options);
  const safeScope = scopeLabel
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'alcance';

  return `funnel_venta_nueva_${options.month}_${safeScope}.xlsx`;
}

function resolveScopeLabel(options: FunnelBranchExportOptions): string {
  if (options.branchId !== null) {
    return options.scopeOptions.find(
      (option) => option.sucursal_id === options.branchId,
    )?.sucursal ?? `sucursal-${options.branchId}`;
  }

  if (options.regionId !== null) {
    return options.scopeOptions.find(
      (option) => option.region_id === options.regionId,
    )?.region ?? `region-${options.regionId}`;
  }

  return 'todo-ultra';
}

function resolveMonthSheetName(month: string): string {
  const [, rawMonth] = month.split('-');
  const monthNumber = Number(rawMonth);
  const monthNames = [
    'Enero',
    'Febrero',
    'Marzo',
    'Abril',
    'Mayo',
    'Junio',
    'Julio',
    'Agosto',
    'Septiembre',
    'Octubre',
    'Noviembre',
    'Diciembre',
  ];

  return monthNames[monthNumber - 1] ?? 'Funnel';
}
