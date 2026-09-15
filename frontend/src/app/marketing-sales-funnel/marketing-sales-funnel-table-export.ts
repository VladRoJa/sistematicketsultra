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

interface RegionSection {
  branchIds: number[];
}

const REGION_SECTIONS: RegionSection[] = [
  { branchIds: [1, 2, 3, 4, 5, 6] },
  { branchIds: [7, 8, 9, 10, 11, 12, 13] },
  { branchIds: [14, 15, 16, 20] },
  { branchIds: [17, 18, 24, 26] },
  { branchIds: [19, 21, 22, 23, 25] },
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

const CURRENCY_COLUMNS = ['B', 'J', 'K', 'L', 'M', 'Q', 'R', 'S'];
const PERCENT_COLUMNS = ['N', 'O', 'P'];
const INTEGER_COLUMNS = ['C', 'D', 'E', 'F', 'G', 'H', 'I'];

const COLORS = {
  dark: 'FF1F2937',
  darkSoft: 'FF374151',
  accent: 'FFF4512C',
  accentSoft: 'FFFFEDE8',
  region: 'FFE5E7EB',
  subtotal: 'FFF3F4F6',
  total: 'FFE8EEF7',
  white: 'FFFFFFFF',
  text: 'FF111827',
  muted: 'FF6B7280',
  border: 'FFD1D5DB',
};

export function exportMarketingSalesFunnelBranchTable(
  options: FunnelBranchExportOptions,
): void {
  if (!options.branches.length) {
    return;
  }

  void exportProgrammaticWorkbook(options).catch((error) => {
    console.error(
      'No se pudo generar el Excel del Funnel Venta Nueva.',
      error,
    );
  });
}

async function exportProgrammaticWorkbook(
  options: FunnelBranchExportOptions,
): Promise<void> {
  const workbook = new Workbook();
  workbook.creator = 'Suite Ultra';
  workbook.company = 'Ultra Gym';
  workbook.created = new Date();
  workbook.calcProperties.fullCalcOnLoad = true;

  const worksheet = workbook.addWorksheet(
    resolveMonthSheetName(options.month),
    {
      views: [
        {
          state: 'frozen',
          xSplit: 1,
          ySplit: 4,
          topLeftCell: 'B5',
          activeCell: 'B5',
        },
      ],
      pageSetup: {
        orientation: 'landscape',
        fitToPage: true,
        fitToWidth: 1,
        fitToHeight: 0,
      },
    },
  );

  configureWorksheet(worksheet);
  writeTitle(worksheet, options);
  writeHeader(worksheet, 4);

  const branchById = new Map<number, MarketingSalesFunnelBranch>(
    options.branches.map((branch) => [branch.sucursal_id, branch]),
  );
  const investmentByBranch = buildInvestmentMap(options);
  const subtotalRows: number[] = [];
  let currentRow = 5;

  for (let index = 0; index < REGION_SECTIONS.length; index += 1) {
    const section = REGION_SECTIONS[index];
    const branches = section.branchIds
      .map((branchId) => branchById.get(branchId) ?? null)
      .filter(
        (branch): branch is MarketingSalesFunnelBranch => branch !== null,
      );

    if (!branches.length) {
      continue;
    }

    currentRow = writeRegionSection(
      worksheet,
      currentRow,
      index,
      branches,
      investmentByBranch,
      options.scopeOptions,
      subtotalRows,
    );
  }

  const knownIds = new Set(
    REGION_SECTIONS.flatMap((section) => section.branchIds),
  );
  const extraBranches = options.branches.filter(
    (branch) => !knownIds.has(branch.sucursal_id),
  );

  if (extraBranches.length) {
    currentRow = writeNamedSection(
      worksheet,
      currentRow,
      'OTRAS SUCURSALES',
      extraBranches,
      investmentByBranch,
      subtotalRows,
    );
  }

  const totals = buildTotals(options.branches, investmentByBranch);
  const grandInvestment = resolveGrandInvestment(options, totals.investment);
  const grandTotalRow = writeGrandTotal(
    worksheet,
    currentRow + 1,
    subtotalRows,
    totals,
    grandInvestment,
  );

  writeSummaryBlock(
    worksheet,
    grandTotalRow + 3,
    grandTotalRow,
    totals,
    grandInvestment,
  );

  const buffer = await workbook.xlsx.writeBuffer();
  downloadWorkbook(
    buffer as BlobPart,
    buildExportFilename(options),
  );
}

function configureWorksheet(worksheet: Worksheet): void {
  worksheet.properties.defaultRowHeight = 18;

  const widths = [
    26, 14, 12, 15, 15, 19, 12, 12, 14, 15,
    14, 14, 15, 14, 18, 14, 17, 18, 18,
  ];

  widths.forEach((width, index) => {
    worksheet.getColumn(index + 1).width = width;
  });
}

function writeTitle(
  worksheet: Worksheet,
  options: FunnelBranchExportOptions,
): void {
  worksheet.mergeCells('A1:S1');
  const title = worksheet.getCell('A1');
  title.value = 'FUNNEL DE VENTA NUEVA · DETALLE POR SUCURSAL';
  title.font = {
    bold: true,
    size: 16,
    color: { argb: COLORS.white },
  };
  title.fill = solidFill(COLORS.dark);
  title.alignment = { vertical: 'middle', horizontal: 'left' };
  worksheet.getRow(1).height = 28;

  worksheet.mergeCells('A2:S2');
  const scopeLabel = resolveScopeLabel(options);
  const meta = worksheet.getCell('A2');
  meta.value = `${formatMonthLabel(options.month)} · Alcance: ${scopeLabel}`;
  meta.font = {
    italic: true,
    color: { argb: COLORS.muted },
  };
  meta.alignment = { vertical: 'middle', horizontal: 'left' };

  const investmentAvailable = hasBranchInvestment(options);
  if (
    !investmentAvailable
    && options.regionId === null
    && options.branchId === null
    && options.investmentDashboard?.summary.investment != null
  ) {
    worksheet.mergeCells('A3:S3');
    const note = worksheet.getCell('A3');
    note.value =
      'Inversión global disponible; la asignación por sucursal no está disponible para este corte.';
    note.font = {
      italic: true,
      color: { argb: COLORS.accent },
    };
  }
}

function writeHeader(
  worksheet: Worksheet,
  rowNumber: number,
): void {
  HEADER_VALUES.forEach((value, index) => {
    const cell = worksheet.getCell(rowNumber, index + 1);
    cell.value = value;
    cell.font = {
      bold: true,
      color: { argb: COLORS.white },
      size: 9,
    };
    cell.fill = solidFill(COLORS.darkSoft);
    cell.alignment = {
      horizontal: 'center',
      vertical: 'middle',
      wrapText: true,
    };
    applyBorder(cell);
  });

  worksheet.getRow(rowNumber).height = 34;
}

function writeRegionSection(
  worksheet: Worksheet,
  startRow: number,
  sectionIndex: number,
  branches: MarketingSalesFunnelBranch[],
  investmentByBranch: Map<number, number | null>,
  scopeOptions: MarketingSalesFunnelScopeOption[],
  subtotalRows: number[],
): number {
  const label = resolveRegionLabel(
    branches,
    scopeOptions,
    sectionIndex,
  );

  return writeNamedSection(
    worksheet,
    startRow,
    label,
    branches,
    investmentByBranch,
    subtotalRows,
  );
}

function writeNamedSection(
  worksheet: Worksheet,
  startRow: number,
  label: string,
  branches: MarketingSalesFunnelBranch[],
  investmentByBranch: Map<number, number | null>,
  subtotalRows: number[],
): number {
  worksheet.mergeCells(`A${startRow}:S${startRow}`);
  const regionCell = worksheet.getCell(`A${startRow}`);
  regionCell.value = label.toUpperCase();
  regionCell.font = {
    bold: true,
    color: { argb: COLORS.text },
  };
  regionCell.fill = solidFill(COLORS.region);
  regionCell.alignment = { vertical: 'middle', horizontal: 'left' };
  worksheet.getRow(startRow).height = 21;

  const firstBranchRow = startRow + 1;
  let rowNumber = firstBranchRow;

  for (const branch of branches) {
    writeBranchRow(
      worksheet,
      rowNumber,
      branch,
      investmentByBranch.get(branch.sucursal_id) ?? null,
    );
    rowNumber += 1;
  }

  const subtotalRow = rowNumber;
  const totals = buildTotals(branches, investmentByBranch);
  writeSubtotalRow(
    worksheet,
    subtotalRow,
    firstBranchRow,
    subtotalRow - 1,
    totals,
  );
  subtotalRows.push(subtotalRow);

  return subtotalRow + 2;
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

  styleDataRow(worksheet, rowNumber, false);
}

function writeSubtotalRow(
  worksheet: Worksheet,
  rowNumber: number,
  firstDataRow: number,
  lastDataRow: number,
  totals: ExportTotals,
): void {
  worksheet.getCell(`A${rowNumber}`).value = 'SUBTOTAL REGIÓN';
  const ranges = [
    ['B', totals.investment],
    ['C', totals.leads],
    ['D', totals.visitors],
    ['E', totals.salesDigital],
    ['F', totals.salesDigitalOrganic],
    ['G', totals.salesWeb],
    ['H', totals.salesBtl],
    ['I', totals.salesTotal],
    ['J', totals.revenueDigital],
    ['K', totals.revenueWeb],
    ['L', totals.revenueBtl],
    ['M', totals.revenueTotal],
  ] as const;

  for (const [column, result] of ranges) {
    setFormulaCell(
      worksheet,
      `${column}${rowNumber}`,
      `SUM(${column}${firstDataRow}:${column}${lastDataRow})`,
      result,
    );
  }

  setRateAndCostFormulas(worksheet, rowNumber, totals);
  styleDataRow(worksheet, rowNumber, true);
}

function writeGrandTotal(
  worksheet: Worksheet,
  rowNumber: number,
  subtotalRows: number[],
  totals: ExportTotals,
  grandInvestment: number | null,
): number {
  worksheet.getCell(`A${rowNumber}`).value = 'TOTAL';

  if (grandInvestment !== null) {
    worksheet.getCell(`B${rowNumber}`).value = grandInvestment;
  }

  const resultByColumn: Array<[string, number]> = [
    ['C', totals.leads],
    ['D', totals.visitors],
    ['E', totals.salesDigital],
    ['F', totals.salesDigitalOrganic],
    ['G', totals.salesWeb],
    ['H', totals.salesBtl],
    ['I', totals.salesTotal],
    ['J', totals.revenueDigital],
    ['K', totals.revenueWeb],
    ['L', totals.revenueBtl],
    ['M', totals.revenueTotal],
  ];

  for (const [column, result] of resultByColumn) {
    const formula = subtotalRows.length
      ? `SUM(${subtotalRows.map((row) => `${column}${row}`).join(',')})`
      : '0';
    setFormulaCell(
      worksheet,
      `${column}${rowNumber}`,
      formula,
      result,
    );
  }

  setRateAndCostFormulas(
    worksheet,
    rowNumber,
    {
      ...totals,
      investment: grandInvestment,
    },
  );

  for (let column = 1; column <= 19; column += 1) {
    const cell = worksheet.getCell(rowNumber, column);
    cell.fill = solidFill(COLORS.total);
    cell.font = { bold: true, color: { argb: COLORS.text } };
    applyBorder(cell);
  }

  applyNumberFormats(worksheet, rowNumber);
  worksheet.getRow(rowNumber).height = 22;

  return rowNumber;
}

function setRateAndCostFormulas(
  worksheet: Worksheet,
  rowNumber: number,
  totals: ExportTotals,
): void {
  setFormulaCell(
    worksheet,
    `N${rowNumber}`,
    `IFERROR(D${rowNumber}/C${rowNumber},"")`,
    safeDivide(totals.visitors, totals.leads),
  );
  setFormulaCell(
    worksheet,
    `O${rowNumber}`,
    `IFERROR(E${rowNumber}/D${rowNumber},"")`,
    safeDivide(totals.salesDigital, totals.visitors),
  );
  setFormulaCell(
    worksheet,
    `P${rowNumber}`,
    `IFERROR(E${rowNumber}/C${rowNumber},"")`,
    safeDivide(totals.salesDigital, totals.leads),
  );
  setFormulaCell(
    worksheet,
    `Q${rowNumber}`,
    `IF(OR(B${rowNumber}="",C${rowNumber}=0),"",B${rowNumber}/C${rowNumber})`,
    safeDivide(totals.investment, totals.leads),
  );
  setFormulaCell(
    worksheet,
    `R${rowNumber}`,
    `IF(OR(B${rowNumber}="",D${rowNumber}=0),"",B${rowNumber}/D${rowNumber})`,
    safeDivide(totals.investment, totals.visitors),
  );
  setFormulaCell(
    worksheet,
    `S${rowNumber}`,
    `IF(OR(B${rowNumber}="",E${rowNumber}+F${rowNumber}=0),"",B${rowNumber}/(E${rowNumber}+F${rowNumber}))`,
    safeDivide(
      totals.investment,
      totals.salesDigital + totals.salesDigitalOrganic,
    ),
  );
}

function writeSummaryBlock(
  worksheet: Worksheet,
  startRow: number,
  grandTotalRow: number,
  totals: ExportTotals,
  grandInvestment: number | null,
): void {
  worksheet.mergeCells(`A${startRow}:F${startRow}`);
  const title = worksheet.getCell(`A${startRow}`);
  title.value = 'RESUMEN COMERCIAL';
  title.font = { bold: true, color: { argb: COLORS.white } };
  title.fill = solidFill(COLORS.dark);

  const rows = {
    total: startRow + 1,
    digital: startRow + 2,
    other: startRow + 3,
    investment: startRow + 4,
  };

  worksheet.getCell(`A${rows.total}`).value = 'Total de ventas nuevas';
  setFormulaCell(
    worksheet,
    `B${rows.total}`,
    `I${grandTotalRow}`,
    totals.salesTotal,
  );

  worksheet.getCell(`A${rows.digital}`).value = 'Ventas vía Mkt Digital';
  setFormulaCell(
    worksheet,
    `B${rows.digital}`,
    `E${grandTotalRow}+F${grandTotalRow}`,
    totals.salesDigital + totals.salesDigitalOrganic,
  );
  setFormulaCell(
    worksheet,
    `C${rows.digital}`,
    `IFERROR(B${rows.digital}/B${rows.total},"")`,
    safeDivide(
      totals.salesDigital + totals.salesDigitalOrganic,
      totals.salesTotal,
    ),
  );

  worksheet.getCell(`A${rows.other}`).value = 'Ventas otros canales';
  setFormulaCell(
    worksheet,
    `B${rows.other}`,
    `B${rows.total}-B${rows.digital}`,
    totals.salesTotal - totals.salesDigital - totals.salesDigitalOrganic,
  );
  setFormulaCell(
    worksheet,
    `C${rows.other}`,
    `IFERROR(B${rows.other}/B${rows.total},"")`,
    safeDivide(
      totals.salesTotal - totals.salesDigital - totals.salesDigitalOrganic,
      totals.salesTotal,
    ),
  );

  worksheet.getCell(`A${rows.investment}`).value = 'Inversión';
  worksheet.getCell(`B${rows.investment}`).value = grandInvestment;

  worksheet.getCell(`D${rows.total}`).value = 'Meta digital (50%)';
  setFormulaCell(
    worksheet,
    `E${rows.total}`,
    `B${rows.total}*0.5`,
    totals.salesTotal * 0.5,
  );
  worksheet.getCell(`D${rows.digital}`).value = 'Brecha vs meta';
  setFormulaCell(
    worksheet,
    `E${rows.digital}`,
    `B${rows.digital}-E${rows.total}`,
    (
      totals.salesDigital
      + totals.salesDigitalOrganic
      - (totals.salesTotal * 0.5)
    ),
  );

  for (let row = rows.total; row <= rows.investment; row += 1) {
    for (let column = 1; column <= 6; column += 1) {
      const cell = worksheet.getCell(row, column);
      applyBorder(cell);
    }
  }

  worksheet.getCell(`B${rows.investment}`).numFmt = '$#,##0.00';
  worksheet.getCell(`C${rows.digital}`).numFmt = '0.0%';
  worksheet.getCell(`C${rows.other}`).numFmt = '0.0%';
}

function styleDataRow(
  worksheet: Worksheet,
  rowNumber: number,
  subtotal: boolean,
): void {
  for (let column = 1; column <= 19; column += 1) {
    const cell = worksheet.getCell(rowNumber, column);
    applyBorder(cell);
    cell.alignment = {
      vertical: 'middle',
      horizontal: column === 1 ? 'left' : 'right',
    };

    if (subtotal) {
      cell.fill = solidFill(COLORS.subtotal);
      cell.font = { bold: true, color: { argb: COLORS.text } };
    }
  }

  worksheet.getCell(`A${rowNumber}`).font = {
    bold: true,
    color: { argb: COLORS.text },
  };

  applyNumberFormats(worksheet, rowNumber);
}

function applyNumberFormats(
  worksheet: Worksheet,
  rowNumber: number,
): void {
  for (const column of CURRENCY_COLUMNS) {
    worksheet.getCell(`${column}${rowNumber}`).numFmt = '$#,##0.00';
  }
  for (const column of PERCENT_COLUMNS) {
    worksheet.getCell(`${column}${rowNumber}`).numFmt = '0.0%';
  }
  for (const column of INTEGER_COLUMNS) {
    worksheet.getCell(`${column}${rowNumber}`).numFmt = '#,##0';
  }
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

function buildTotals(
  branches: MarketingSalesFunnelBranch[],
  investmentByBranch: Map<number, number | null>,
): ExportTotals {
  const investments = branches
    .map((branch) => investmentByBranch.get(branch.sucursal_id) ?? null)
    .filter((value): value is number => value !== null);

  return {
    investment: investments.length
      ? investments.reduce((sum, value) => sum + value, 0)
      : null,
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

function resolveGrandInvestment(
  options: FunnelBranchExportOptions,
  branchInvestment: number | null,
): number | null {
  if (branchInvestment !== null) {
    return branchInvestment;
  }

  if (
    options.regionId === null
    && options.branchId === null
    && options.investmentDashboard
    && options.investmentDashboard.month === options.month
  ) {
    return options.investmentDashboard.summary.investment ?? null;
  }

  return null;
}

function hasBranchInvestment(options: FunnelBranchExportOptions): boolean {
  if (
    !options.investmentDashboard
    || options.investmentDashboard.month !== options.month
  ) {
    return false;
  }

  return options.investmentDashboard.branches.some(
    (branch) => branch.investment !== null && branch.investment !== undefined,
  );
}

function resolveRegionLabel(
  branches: MarketingSalesFunnelBranch[],
  scopeOptions: MarketingSalesFunnelScopeOption[],
  sectionIndex: number,
): string {
  for (const branch of branches) {
    const option = scopeOptions.find(
      (candidate) => candidate.sucursal_id === branch.sucursal_id,
    );
    if (option?.region) {
      return option.region;
    }
  }

  return `Región ${sectionIndex + 1}`;
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

function solidFill(argb: string): any {
  return {
    type: 'pattern',
    pattern: 'solid',
    fgColor: { argb },
  };
}

function applyBorder(cell: any): void {
  cell.border = {
    top: { style: 'thin', color: { argb: COLORS.border } },
    left: { style: 'thin', color: { argb: COLORS.border } },
    bottom: { style: 'thin', color: { argb: COLORS.border } },
    right: { style: 'thin', color: { argb: COLORS.border } },
  };
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
  anchor.style.display = 'none';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();

  setTimeout(() => window.URL.revokeObjectURL(url), 0);
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

  return 'Todo Ultra';
}

function resolveMonthSheetName(month: string): string {
  return formatMonthLabel(month).slice(0, 31);
}

function formatMonthLabel(month: string): string {
  const [rawYear, rawMonth] = month.split('-');
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

  const monthName = monthNames[monthNumber - 1] ?? 'Funnel';
  return rawYear ? `${monthName} ${rawYear}` : monthName;
}
