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

interface DataRange {
  firstRow: number;
  lastRow: number;
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
  'Ventas Mkt Digital',
  'Ventas Mkt Dig organico',
  'venta web',
  'venta btl',
  'ventas totales',
  'Ingreso digital',
  'Ingreso web',
  'Ingreso btl',
  'ingreso total',
  'Lead → visita',
  'Visita → venta dig',
  'Lead → venta',
  'Costo por lead (CPL)',
  'Costo por visita (CPT)',
  'Costo por venta (CAC)',
];

const CURRENCY_COLUMNS = ['B', 'J', 'K', 'L', 'M', 'Q', 'R', 'S'];
const PERCENT_COLUMNS = ['N', 'O', 'P'];
const INTEGER_COLUMNS = ['C', 'D', 'E', 'F', 'G', 'H', 'I'];

const CURRENCY_FORMAT = '$#,##0.00;[Red]-$#,##0.00';
const INTEGER_FORMAT = '#,##0';
const PERCENT_FORMAT = '0.0%';

const COLORS = {
  black: 'FF000000',
  white: 'FFFFFFFF',
  yellow: 'FFFFFF00',
  greenFill: 'FFC6EFCE',
  greenText: 'FF006100',
  amberFill: 'FFFFEB9C',
  amberText: 'FF9C5700',
  redFill: 'FFFFC7CE',
  redText: 'FF9C0006',
};

export function exportMarketingSalesFunnelBranchTable(
  options: FunnelBranchExportOptions,
): void {
  if (!options.branches.length) {
    return;
  }

  void exportReferenceWorkbook(options).catch((error) => {
    console.error(
      'No se pudo generar el Excel del Funnel Venta Nueva.',
      error,
    );
  });
}

async function exportReferenceWorkbook(
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
          ySplit: 1,
          topLeftCell: 'B2',
          activeCell: 'A2',
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
  writeHeader(worksheet);

  const branchById = new Map<number, MarketingSalesFunnelBranch>(
    options.branches.map((branch) => [branch.sucursal_id, branch]),
  );
  const investmentByBranch = buildInvestmentMap(options);
  const subtotalRows: number[] = [];
  const dataRanges: DataRange[] = [];
  let currentRow = 2;

  for (const section of REGION_SECTIONS) {
    const branches = section.branchIds
      .map((branchId) => branchById.get(branchId) ?? null)
      .filter(
        (branch): branch is MarketingSalesFunnelBranch => branch !== null,
      );

    if (!branches.length) {
      continue;
    }

    currentRow = writeSection(
      worksheet,
      currentRow,
      branches,
      investmentByBranch,
      subtotalRows,
      dataRanges,
    );
  }

  const knownIds = new Set(
    REGION_SECTIONS.flatMap((section) => section.branchIds),
  );
  const extraBranches = options.branches
    .filter((branch) => !knownIds.has(branch.sucursal_id))
    .sort((left, right) => left.sucursal.localeCompare(right.sucursal));

  if (extraBranches.length) {
    currentRow = writeSection(
      worksheet,
      currentRow,
      extraBranches,
      investmentByBranch,
      subtotalRows,
      dataRanges,
    );
  }

  const totals = buildTotals(options.branches, investmentByBranch);
  const grandInvestment = resolveGrandInvestment(options, totals.investment);

  const summaryHeaderRow = currentRow;
  const summaryValueRow = currentRow + 1;
  const summaryRateRow = currentRow + 2;
  writeCompactSummary(
    worksheet,
    summaryHeaderRow,
    summaryValueRow,
    summaryRateRow,
    subtotalRows,
    totals,
    grandInvestment,
  );

  writeCommercialSummary(
    worksheet,
    summaryRateRow + 2,
    summaryValueRow,
    totals,
  );

  applyConditionalFormats(worksheet, dataRanges);

  const buffer = await workbook.xlsx.writeBuffer();
  downloadWorkbook(
    buffer as BlobPart,
    buildExportFilename(options),
  );
}

function configureWorksheet(worksheet: Worksheet): void {
  worksheet.properties.defaultRowHeight = 15;
  worksheet.views = worksheet.views;

  const widths = [
    28,
    15,
    12,
    13,
    18,
    18,
    12,
    12,
    14,
    14.2,
    17,
    14,
    14,
    16,
    16,
    12.2,
    11.5,
    12,
    14,
  ];

  widths.forEach((width, index) => {
    worksheet.getColumn(index + 1).width = width;
  });
}

function writeHeader(worksheet: Worksheet): void {
  HEADER_VALUES.forEach((value, index) => {
    const cell = worksheet.getCell(1, index + 1);
    cell.value = value;
    cell.font = {
      name: 'Calibri',
      size: 12,
      bold: true,
      color: { argb: COLORS.black },
    };
    cell.alignment = {
      horizontal: 'center',
      vertical: 'middle',
      wrapText: true,
    };
  });

  worksheet.getRow(1).height = 39.75;
}

function writeSection(
  worksheet: Worksheet,
  firstRow: number,
  branches: MarketingSalesFunnelBranch[],
  investmentByBranch: Map<number, number | null>,
  subtotalRows: number[],
  dataRanges: DataRange[],
): number {
  let rowNumber = firstRow;

  for (const branch of branches) {
    writeBranchRow(
      worksheet,
      rowNumber,
      branch,
      investmentByBranch.get(branch.sucursal_id) ?? null,
    );
    rowNumber += 1;
  }

  const lastDataRow = rowNumber - 1;
  dataRanges.push({
    firstRow,
    lastRow: lastDataRow,
  });

  styleSectionBoundaries(
    worksheet,
    firstRow,
    lastDataRow,
  );

  const subtotalRow = rowNumber;
  const totals = buildTotals(branches, investmentByBranch);
  writeSubtotalRow(
    worksheet,
    subtotalRow,
    firstRow,
    lastDataRow,
    totals,
  );
  subtotalRows.push(subtotalRow);

  return subtotalRow + 1;
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

  styleBranchRow(worksheet, rowNumber);
}

function writeSubtotalRow(
  worksheet: Worksheet,
  rowNumber: number,
  firstDataRow: number,
  lastDataRow: number,
  totals: ExportTotals,
): void {
  worksheet.getCell(`A${rowNumber}`).value = null;

  const results: Array<[string, number | null]> = [
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
  ];

  for (const [column, result] of results) {
    setFormulaCell(
      worksheet,
      `${column}${rowNumber}`,
      `SUM(${column}${firstDataRow}:${column}${lastDataRow})`,
      result,
    );
  }

  setRateAndCostFormulas(worksheet, rowNumber, totals);
  styleSubtotalRow(worksheet, rowNumber);
}

function writeCompactSummary(
  worksheet: Worksheet,
  headerRow: number,
  valueRow: number,
  rateRow: number,
  subtotalRows: number[],
  totals: ExportTotals,
  grandInvestment: number | null,
): void {
  worksheet.getCell(`B${headerRow}`).value = 'Inversión';
  worksheet.getCell(`C${headerRow}`).value = 'Leads';
  worksheet.getCell(`D${headerRow}`).value = 'Visitantes';
  worksheet.getCell(`E${headerRow}`).value = 'Ventas Mkt Digital';
  worksheet.getCell(`J${headerRow}`).value = 'Costo por venta (CAC)';

  for (const column of ['B', 'C', 'D', 'E', 'J']) {
    const cell = worksheet.getCell(`${column}${headerRow}`);
    cell.font = {
      name: 'Calibri',
      size: 10,
      bold: true,
      color: { argb: COLORS.black },
    };
    cell.alignment = {
      horizontal: 'center',
      vertical: 'middle',
      wrapText: true,
    };
  }
  worksheet.getRow(headerRow).height = 30.75;

  if (grandInvestment !== null) {
    worksheet.getCell(`B${valueRow}`).value = grandInvestment;
  }

  const subtotalFormula = (column: string): string => {
    if (!subtotalRows.length) {
      return '0';
    }
    return subtotalRows.map((row) => `${column}${row}`).join('+');
  };

  setFormulaCell(
    worksheet,
    `C${valueRow}`,
    subtotalFormula('C'),
    totals.leads,
  );
  setFormulaCell(
    worksheet,
    `D${valueRow}`,
    subtotalFormula('D'),
    totals.visitors,
  );
  setFormulaCell(
    worksheet,
    `E${valueRow}`,
    `${subtotalFormula('E')}+${subtotalFormula('F')}`,
    totals.salesDigital + totals.salesDigitalOrganic,
  );
  setFormulaCell(
    worksheet,
    `J${valueRow}`,
    `IF(OR(B${valueRow}="",E${valueRow}=0),"",B${valueRow}/E${valueRow})`,
    safeDivide(
      grandInvestment,
      totals.salesDigital + totals.salesDigitalOrganic,
    ),
  );

  for (let column = 2; column <= 10; column += 1) {
    const cell = worksheet.getCell(valueRow, column);
    cell.fill = solidFill(COLORS.black);
    cell.font = {
      name: 'Calibri',
      size: 10,
      bold: true,
      italic: true,
      color: { argb: COLORS.white },
    };
    cell.alignment = {
      horizontal: 'center',
      vertical: 'middle',
    };
  }
  worksheet.getRow(valueRow).height = 30.75;

  worksheet.getCell(`B${valueRow}`).numFmt = CURRENCY_FORMAT;
  worksheet.getCell(`C${valueRow}`).numFmt = INTEGER_FORMAT;
  worksheet.getCell(`D${valueRow}`).numFmt = INTEGER_FORMAT;
  worksheet.getCell(`E${valueRow}`).numFmt = INTEGER_FORMAT;
  worksheet.getCell(`J${valueRow}`).numFmt = CURRENCY_FORMAT;

  setFormulaCell(
    worksheet,
    `D${rateRow}`,
    `IFERROR(D${valueRow}/C${valueRow},"")`,
    safeDivide(totals.visitors, totals.leads),
  );
  setFormulaCell(
    worksheet,
    `E${rateRow}`,
    `IFERROR(E${valueRow}/D${valueRow},"")`,
    safeDivide(
      totals.salesDigital + totals.salesDigitalOrganic,
      totals.visitors,
    ),
  );
  worksheet.getCell(`D${rateRow}`).numFmt = PERCENT_FORMAT;
  worksheet.getCell(`E${rateRow}`).numFmt = PERCENT_FORMAT;
  worksheet.getCell(`D${rateRow}`).alignment = { horizontal: 'center' };
  worksheet.getCell(`E${rateRow}`).alignment = { horizontal: 'center' };
}

function writeCommercialSummary(
  worksheet: Worksheet,
  startRow: number,
  summaryValueRow: number,
  totals: ExportTotals,
): void {
  const totalRow = startRow;
  const digitalRow = startRow + 1;
  const otherRow = startRow + 2;
  const checkRow = startRow + 3;

  worksheet.getCell(`A${totalRow}`).value = 'Total de ventas nuevas';
  worksheet.getCell(`B${totalRow}`).value = totals.salesTotal;
  worksheet.getCell(`D${totalRow}`).value =
    'GOAL: 50% del total de las venta vía Mkt Digital';

  worksheet.getCell(`A${digitalRow}`).value = 'Ventas via Mkt Digital';
  setFormulaCell(
    worksheet,
    `B${digitalRow}`,
    `E${summaryValueRow}`,
    totals.salesDigital + totals.salesDigitalOrganic,
  );
  setFormulaCell(
    worksheet,
    `C${digitalRow}`,
    `IFERROR(B${digitalRow}/B${totalRow},"")`,
    safeDivide(
      totals.salesDigital + totals.salesDigitalOrganic,
      totals.salesTotal,
    ),
  );
  setFormulaCell(
    worksheet,
    `D${digitalRow}`,
    `B${totalRow}*0.5`,
    totals.salesTotal * 0.5,
  );

  worksheet.getCell(`A${otherRow}`).value =
    'Ventas (Referidos, walk in, convenios)';
  setFormulaCell(
    worksheet,
    `B${otherRow}`,
    `B${totalRow}-B${digitalRow}`,
    totals.salesTotal - totals.salesDigital - totals.salesDigitalOrganic,
  );
  setFormulaCell(
    worksheet,
    `C${otherRow}`,
    `IFERROR(B${otherRow}/B${totalRow},"")`,
    safeDivide(
      totals.salesTotal - totals.salesDigital - totals.salesDigitalOrganic,
      totals.salesTotal,
    ),
  );
  setFormulaCell(
    worksheet,
    `D${otherRow}`,
    `B${otherRow}`,
    totals.salesTotal - totals.salesDigital - totals.salesDigitalOrganic,
  );
  setFormulaCell(
    worksheet,
    `D${checkRow}`,
    `SUM(B${digitalRow}:B${otherRow})`,
    totals.salesTotal,
  );

  worksheet.getCell(`B${totalRow}`).numFmt = INTEGER_FORMAT;
  worksheet.getCell(`B${digitalRow}`).numFmt = INTEGER_FORMAT;
  worksheet.getCell(`B${otherRow}`).numFmt = INTEGER_FORMAT;
  worksheet.getCell(`C${digitalRow}`).numFmt = '0%';
  worksheet.getCell(`C${otherRow}`).numFmt = '0%';
  worksheet.getCell(`D${digitalRow}`).numFmt = INTEGER_FORMAT;
  worksheet.getCell(`D${otherRow}`).numFmt = INTEGER_FORMAT;
  worksheet.getCell(`D${checkRow}`).numFmt = INTEGER_FORMAT;

  worksheet.getCell(`B${totalRow}`).font = { bold: true };
  worksheet.getCell(`B${digitalRow}`).font = { bold: true };
  worksheet.getCell(`D${totalRow}`).font = { bold: true };
  worksheet.getCell(`D${digitalRow}`).font = { bold: true };
  worksheet.getCell(`D${digitalRow}`).fill = solidFill(COLORS.yellow);
}

function styleBranchRow(
  worksheet: Worksheet,
  rowNumber: number,
): void {
  for (let column = 1; column <= 19; column += 1) {
    const cell = worksheet.getCell(rowNumber, column);
    cell.font = {
      name: 'Calibri',
      size: 11,
      color: { argb: COLORS.black },
    };
    cell.alignment = {
      vertical: 'middle',
      horizontal: column === 1 ? 'left' : 'center',
      wrapText: column === 1,
    };
  }

  worksheet.getCell(`A${rowNumber}`).border = {
    left: mediumBorder(),
  } as any;
  worksheet.getCell(`S${rowNumber}`).border = {
    right: mediumBorder(),
  } as any;

  applyNumberFormats(worksheet, rowNumber);
}

function styleSectionBoundaries(
  worksheet: Worksheet,
  firstRow: number,
  lastRow: number,
): void {
  for (let column = 1; column <= 19; column += 1) {
    const firstCell = worksheet.getCell(firstRow, column);
    firstCell.border = {
      ...firstCell.border,
      top: mediumBorder(),
      ...(column === 1 ? { left: mediumBorder() } : {}),
      ...(column === 19 ? { right: mediumBorder() } : {}),
    } as any;

    const lastCell = worksheet.getCell(lastRow, column);
    lastCell.border = {
      ...lastCell.border,
      bottom: mediumBorder(),
      ...(column === 1 ? { left: mediumBorder() } : {}),
      ...(column === 19 ? { right: mediumBorder() } : {}),
    } as any;
  }
}

function styleSubtotalRow(
  worksheet: Worksheet,
  rowNumber: number,
): void {
  for (let column = 1; column <= 19; column += 1) {
    const cell = worksheet.getCell(rowNumber, column);
    cell.font = {
      name: 'Calibri',
      size: 11,
      bold: true,
      italic: true,
      color: { argb: COLORS.black },
    };
    cell.alignment = {
      vertical: 'middle',
      horizontal: column === 1 ? 'left' : 'center',
      wrapText: true,
    };
  }

  worksheet.getCell(`A${rowNumber}`).border = {
    left: mediumBorder(),
  } as any;

  applyNumberFormats(worksheet, rowNumber);
  worksheet.getRow(rowNumber).height = 27;
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

function applyConditionalFormats(
  worksheet: Worksheet,
  ranges: DataRange[],
): void {
  for (const range of ranges) {
    addCellRule(
      worksheet,
      `N${range.firstRow}:N${range.lastRow}`,
      'greaterThan',
      0.15,
      COLORS.greenFill,
      COLORS.greenText,
    );
    addCellRule(
      worksheet,
      `O${range.firstRow}:O${range.lastRow}`,
      'greaterThan',
      0.30,
      COLORS.greenFill,
      COLORS.greenText,
    );

    addCellRule(
      worksheet,
      `P${range.firstRow}:P${range.lastRow}`,
      'lessThan',
      0.015,
      COLORS.redFill,
      COLORS.redText,
      true,
    );
    addCellRule(
      worksheet,
      `P${range.firstRow}:P${range.lastRow}`,
      'lessThan',
      0.032,
      COLORS.amberFill,
      COLORS.amberText,
      true,
    );
    addCellRule(
      worksheet,
      `P${range.firstRow}:P${range.lastRow}`,
      'greaterThan',
      0.033,
      COLORS.greenFill,
      COLORS.greenText,
    );
  }
}

function addCellRule(
  worksheet: Worksheet,
  ref: string,
  operator: 'greaterThan' | 'lessThan',
  threshold: number,
  fillColor: string,
  fontColor: string,
  stopIfTrue = false,
): void {
  worksheet.addConditionalFormatting({
    ref,
    rules: [
      {
        type: 'cellIs',
        operator,
        formulae: [threshold],
        stopIfTrue,
        style: {
          font: { color: { argb: fontColor } },
          fill: solidFill(fillColor),
        },
      } as any,
    ],
  });
}

function applyNumberFormats(
  worksheet: Worksheet,
  rowNumber: number,
): void {
  for (const column of CURRENCY_COLUMNS) {
    worksheet.getCell(`${column}${rowNumber}`).numFmt = CURRENCY_FORMAT;
  }
  for (const column of PERCENT_COLUMNS) {
    worksheet.getCell(`${column}${rowNumber}`).numFmt = PERCENT_FORMAT;
  }
  for (const column of INTEGER_COLUMNS) {
    worksheet.getCell(`${column}${rowNumber}`).numFmt = INTEGER_FORMAT;
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

function mediumBorder(): any {
  return {
    style: 'medium',
    color: { argb: COLORS.black },
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
  const suffix = rawYear ? ` ${rawYear}` : '';
  return `${monthName}${suffix}`.slice(0, 31);
}
