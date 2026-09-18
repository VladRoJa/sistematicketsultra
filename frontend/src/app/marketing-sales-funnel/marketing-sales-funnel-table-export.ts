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
  label: string;
  branchIds: number[];
}

interface DataRange {
  firstRow: number;
  lastRow: number;
}

const REGION_SECTIONS: RegionSection[] = [
  {
    label: 'REGIÓN MEXICALI BC',
    branchIds: [1, 2, 3, 4, 5, 6],
  },
  {
    label: 'REGIÓN COSTA BC',
    branchIds: [7, 8, 9, 10, 11, 12, 13],
  },
  {
    label: 'REGIÓN CLN / LA PAZ',
    branchIds: [14, 15, 16, 20],
  },
  {
    label: 'REGIÓN NORESTE',
    branchIds: [17, 18, 24, 26],
  },
  {
    label: 'REGIÓN CENTRO',
    branchIds: [19, 21, 22, 23, 25],
  },
];

const HEADER_VALUES = [
  'Sucursal',
  'Leads',
  'Visitantes totales',
  'Ventas digitales',
  'Ventas digitales orgánicas',
  'Venta web',
  'Venta BTL',
  'Ventas totales',
  'Lead → visita',
  'Visita → venta digital',
  'Lead → venta',
  'Inversión',
  'Ingreso digital',
  'Ingreso web',
  'Ingreso BTL',
  'Ingreso total',
  'Costo por lead (CPL)',
  'Costo por visita (CPT)',
  'Costo por venta (CAC)',
];

const CURRENCY_COLUMNS = ['L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S'];
const PERCENT_COLUMNS = ['I', 'J', 'K'];
const INTEGER_COLUMNS = ['B', 'C', 'D', 'E', 'F', 'G', 'H'];

const CURRENCY_FORMAT = '$#,##0.00;[Red]-$#,##0.00';
const INTEGER_FORMAT = '#,##0';
const PERCENT_FORMAT = '0.0%';

const COLORS = {
  navy: 'FF1F2937',
  slate: 'FF374151',
  text: 'FF111827',
  muted: 'FF6B7280',
  white: 'FFFFFFFF',
  border: 'FFD1D5DB',
  regionFill: 'FFE5E7EB',
  subtotalFill: 'FFF3F4F6',
  totalFill: 'FFE8EEF7',
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

  void exportStyledWorkbook(options).catch((error) => {
    console.error(
      'No se pudo generar el Excel del Funnel Venta Nueva.',
      error,
    );
  });
}

async function exportStyledWorkbook(
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
          activeCell: 'A5',
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
  const dataRanges: DataRange[] = [];
  let currentRow = 5;

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
      section.label,
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
      'OTRAS SUCURSALES',
      extraBranches,
      investmentByBranch,
      subtotalRows,
      dataRanges,
    );
  }

  const totals = buildTotals(options.branches, investmentByBranch);
  const grandInvestment = resolveGrandInvestment(options, totals.investment);

  const totalRow = currentRow + 1;
  writeGrandTotalRow(
    worksheet,
    totalRow,
    subtotalRows,
    totals,
    grandInvestment,
  );

  const commercialHeaderRow = totalRow + 3;
  writeCommercialSummary(
    worksheet,
    commercialHeaderRow,
    totals,
    grandInvestment,
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

  const widths = [
    28,
    12,
    13,
    18,
    20,
    12,
    12,
    14,
    16,
    19,
    12.2,
    15,
    14.2,
    17,
    14,
    14,
    16,
    17,
    17,
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
  worksheet.getCell('A1').value =
    'FUNNEL DE VENTA NUEVA · DETALLE POR SUCURSAL';
  worksheet.getCell('A1').fill = solidFill(COLORS.navy);
  worksheet.getCell('A1').font = {
    name: 'Calibri',
    size: 16,
    bold: true,
    color: { argb: COLORS.white },
  };
  worksheet.getCell('A1').alignment = {
    horizontal: 'left',
    vertical: 'middle',
  };
  worksheet.getRow(1).height = 24;

  worksheet.mergeCells('A2:S2');
  worksheet.getCell('A2').value =
    `${resolveMonthSheetName(options.month)} · Alcance: ${resolveScopeLabel(options)}`;
  worksheet.getCell('A2').font = {
    name: 'Calibri',
    size: 10,
    italic: true,
    color: { argb: COLORS.muted },
  };
  worksheet.getCell('A2').alignment = {
    horizontal: 'left',
    vertical: 'middle',
  };
  worksheet.getRow(2).height = 18;
  worksheet.getRow(3).height = 8;
}

function writeHeader(
  worksheet: Worksheet,
  rowNumber: number,
): void {
  HEADER_VALUES.forEach((value, index) => {
    const cell = worksheet.getCell(rowNumber, index + 1);
    cell.value = value;
    cell.fill = solidFill(COLORS.slate);
    cell.font = {
      name: 'Calibri',
      size: 9,
      bold: true,
      color: { argb: COLORS.white },
    };
    cell.alignment = {
      horizontal: 'center',
      vertical: 'middle',
      wrapText: true,
    };
    cell.border = allThinBorders();
  });

  worksheet.getRow(rowNumber).height = 31;
}

function writeSection(
  worksheet: Worksheet,
  firstRow: number,
  label: string,
  branches: MarketingSalesFunnelBranch[],
  investmentByBranch: Map<number, number | null>,
  subtotalRows: number[],
  dataRanges: DataRange[],
): number {
  writeRegionRow(worksheet, firstRow, label);

  const firstDataRow = firstRow + 1;
  let rowNumber = firstDataRow;

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
    firstRow: firstDataRow,
    lastRow: lastDataRow,
  });

  const subtotalRow = rowNumber;
  const totals = buildTotals(branches, investmentByBranch);

  writeSubtotalRow(
    worksheet,
    subtotalRow,
    firstDataRow,
    lastDataRow,
    totals,
  );
  subtotalRows.push(subtotalRow);

  worksheet.getRow(subtotalRow + 1).height = 8;
  return subtotalRow + 2;
}

function writeRegionRow(
  worksheet: Worksheet,
  rowNumber: number,
  label: string,
): void {
  for (let column = 1; column <= 19; column += 1) {
    const cell = worksheet.getCell(rowNumber, column);
    cell.fill = solidFill(COLORS.regionFill);
  }

  const labelCell = worksheet.getCell(`A${rowNumber}`);
  labelCell.value = label;
  labelCell.font = {
    name: 'Calibri',
    size: 10,
    bold: true,
    color: { argb: COLORS.text },
  };
  labelCell.alignment = {
    horizontal: 'left',
    vertical: 'middle',
  };

  worksheet.getRow(rowNumber).height = 18;
}

function writeBranchRow(
  worksheet: Worksheet,
  rowNumber: number,
  branch: MarketingSalesFunnelBranch,
  investment: number | null,
): void {
  worksheet.getCell(`A${rowNumber}`).value = branch.sucursal;
  worksheet.getCell(`B${rowNumber}`).value = branch.leads_meta;
  worksheet.getCell(`C${rowNumber}`).value = branch.visits_total;
  worksheet.getCell(`D${rowNumber}`).value = branch.sales_digital;
  worksheet.getCell(`E${rowNumber}`).value = branch.sales_digital_organic;
  worksheet.getCell(`F${rowNumber}`).value = branch.sales_web;
  worksheet.getCell(`G${rowNumber}`).value = branch.sales_btl;

  setFormulaCell(
    worksheet,
    `H${rowNumber}`,
    `SUM(D${rowNumber}:G${rowNumber})`,
    branch.sales_total,
  );
  setFormulaCell(
    worksheet,
    `I${rowNumber}`,
    `IFERROR(C${rowNumber}/B${rowNumber},"")`,
    branch.lead_to_visit_rate,
  );
  setFormulaCell(
    worksheet,
    `J${rowNumber}`,
    `IFERROR(D${rowNumber}/C${rowNumber},"")`,
    branch.visit_to_digital_sale_rate,
  );
  setFormulaCell(
    worksheet,
    `K${rowNumber}`,
    `IFERROR(D${rowNumber}/B${rowNumber},"")`,
    branch.lead_to_sale_rate,
  );

  worksheet.getCell(`L${rowNumber}`).value = investment;
  worksheet.getCell(`M${rowNumber}`).value = branch.revenue_digital;
  worksheet.getCell(`N${rowNumber}`).value = branch.revenue_web;
  worksheet.getCell(`O${rowNumber}`).value = branch.revenue_btl;

  setFormulaCell(
    worksheet,
    `P${rowNumber}`,
    `SUM(M${rowNumber}:O${rowNumber})`,
    branch.revenue_total,
  );
  setFormulaCell(
    worksheet,
    `Q${rowNumber}`,
    `IF(OR(L${rowNumber}="",B${rowNumber}=0),"",L${rowNumber}/B${rowNumber})`,
    safeDivide(investment, branch.leads_meta),
  );
  setFormulaCell(
    worksheet,
    `R${rowNumber}`,
    `IF(OR(L${rowNumber}="",C${rowNumber}=0),"",L${rowNumber}/C${rowNumber})`,
    safeDivide(investment, branch.visits_total),
  );
  setFormulaCell(
    worksheet,
    `S${rowNumber}`,
    `IF(OR(L${rowNumber}="",D${rowNumber}+E${rowNumber}=0),"",L${rowNumber}/(D${rowNumber}+E${rowNumber}))`,
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

  const results: Array<[string, number | null]> = [
    ['B', totals.leads],
    ['C', totals.visitors],
    ['D', totals.salesDigital],
    ['E', totals.salesDigitalOrganic],
    ['F', totals.salesWeb],
    ['G', totals.salesBtl],
    ['H', totals.salesTotal],
    ['L', totals.investment],
    ['M', totals.revenueDigital],
    ['N', totals.revenueWeb],
    ['O', totals.revenueBtl],
    ['P', totals.revenueTotal],
  ];

  for (const [column, result] of results) {
    setFormulaCell(
      worksheet,
      `${column}${rowNumber}`,
      `SUM(${column}${firstDataRow}:${column}${lastDataRow})`,
      result,
    );
  }

  setRateAndCostFormulas(
    worksheet,
    rowNumber,
    totals,
    totals.investment,
  );

  styleDataRow(worksheet, rowNumber, true);
  fillRow(worksheet, rowNumber, COLORS.subtotalFill);
  worksheet.getRow(rowNumber).height = 18;
}

function writeGrandTotalRow(
  worksheet: Worksheet,
  rowNumber: number,
  subtotalRows: number[],
  totals: ExportTotals,
  grandInvestment: number | null,
): void {
  worksheet.getCell(`A${rowNumber}`).value = 'TOTAL';

  if (grandInvestment !== null) {
    worksheet.getCell(`L${rowNumber}`).value = grandInvestment;
  }

  const subtotalFormula = (column: string): string => {
    if (!subtotalRows.length) {
      return '0';
    }
    return subtotalRows.map((row) => `${column}${row}`).join('+');
  };

  const results: Array<[string, number]> = [
    ['B', totals.leads],
    ['C', totals.visitors],
    ['D', totals.salesDigital],
    ['E', totals.salesDigitalOrganic],
    ['F', totals.salesWeb],
    ['G', totals.salesBtl],
    ['H', totals.salesTotal],
    ['M', totals.revenueDigital],
    ['N', totals.revenueWeb],
    ['O', totals.revenueBtl],
    ['P', totals.revenueTotal],
  ];

  for (const [column, result] of results) {
    setFormulaCell(
      worksheet,
      `${column}${rowNumber}`,
      subtotalFormula(column),
      result,
    );
  }

  setRateAndCostFormulas(
    worksheet,
    rowNumber,
    totals,
    grandInvestment,
  );

  styleDataRow(worksheet, rowNumber, true);
  fillRow(worksheet, rowNumber, COLORS.totalFill);
  worksheet.getRow(rowNumber).height = 20;
}

function writeCommercialSummary(
  worksheet: Worksheet,
  headerRow: number,
  totals: ExportTotals,
  grandInvestment: number | null,
): void {
  const sourceTotalRow = headerRow - 3;
  const totalRow = headerRow + 1;
  const digitalRow = headerRow + 2;
  const otherRow = headerRow + 3;
  const investmentRow = headerRow + 4;

  for (let column = 1; column <= 6; column += 1) {
    const cell = worksheet.getCell(headerRow, column);
    cell.fill = solidFill(COLORS.navy);
  }

  worksheet.getCell(`A${headerRow}`).value = 'RESUMEN COMERCIAL';
  worksheet.getCell(`A${headerRow}`).font = {
    name: 'Calibri',
    size: 10,
    bold: true,
    color: { argb: COLORS.white },
  };
  worksheet.getRow(headerRow).height = 18;

  worksheet.getCell(`A${totalRow}`).value = 'Total de ventas nuevas';
  setFormulaCell(
    worksheet,
    `B${totalRow}`,
    `H${sourceTotalRow}`,
    totals.salesTotal,
  );
  worksheet.getCell(`E${totalRow}`).value = 'Meta digital (50%)';
  setFormulaCell(
    worksheet,
    `F${totalRow}`,
    `B${totalRow}*0.5`,
    totals.salesTotal * 0.5,
  );

  worksheet.getCell(`A${digitalRow}`).value = 'Ventas vía Digital';
  setFormulaCell(
    worksheet,
    `B${digitalRow}`,
    `D${sourceTotalRow}+E${sourceTotalRow}`,
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
  worksheet.getCell(`E${digitalRow}`).value = 'Brecha vs meta';
  setFormulaCell(
    worksheet,
    `F${digitalRow}`,
    `B${digitalRow}-F${totalRow}`,
    totals.salesDigital
      + totals.salesDigitalOrganic
      - totals.salesTotal * 0.5,
  );

  worksheet.getCell(`A${otherRow}`).value = 'Ventas otros canales';
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

  worksheet.getCell(`A${investmentRow}`).value = 'Inversión';
  setFormulaCell(
    worksheet,
    `B${investmentRow}`,
    `IF(L${sourceTotalRow}="","",L${sourceTotalRow})`,
    grandInvestment,
  );

  for (let row = totalRow; row <= investmentRow; row += 1) {
    for (const column of [1, 2, 3, 5, 6]) {
      const cell = worksheet.getCell(row, column);
      cell.border = allThinBorders();
      cell.font = {
        name: 'Calibri',
        size: 10,
        color: { argb: COLORS.text },
        bold: column === 1 && row === totalRow,
      };
      cell.alignment = {
        vertical: 'middle',
        horizontal: column === 1 || column === 5 ? 'left' : 'right',
      };
    }

    worksheet.getCell(`D${row}`).value = null;
  }

  worksheet.getCell(`B${totalRow}`).numFmt = INTEGER_FORMAT;
  worksheet.getCell(`B${digitalRow}`).numFmt = INTEGER_FORMAT;
  worksheet.getCell(`B${otherRow}`).numFmt = INTEGER_FORMAT;
  worksheet.getCell(`B${investmentRow}`).numFmt = CURRENCY_FORMAT;
  worksheet.getCell(`C${digitalRow}`).numFmt = PERCENT_FORMAT;
  worksheet.getCell(`C${otherRow}`).numFmt = PERCENT_FORMAT;
  worksheet.getCell(`F${totalRow}`).numFmt = INTEGER_FORMAT;
  worksheet.getCell(`F${digitalRow}`).numFmt = INTEGER_FORMAT;
  worksheet.getCell(`F${digitalRow}`).fill = solidFill(COLORS.yellow);
  worksheet.getCell(`F${digitalRow}`).font = {
    name: 'Calibri',
    size: 10,
    bold: true,
    color: { argb: COLORS.text },
  };
}

function styleDataRow(
  worksheet: Worksheet,
  rowNumber: number,
  bold: boolean,
): void {
  for (let column = 1; column <= 19; column += 1) {
    const cell = worksheet.getCell(rowNumber, column);
    cell.font = {
      name: 'Calibri',
      size: 10,
      bold: bold || column === 1,
      color: { argb: COLORS.text },
    };
    cell.alignment = {
      vertical: 'middle',
      horizontal: column === 1 ? 'left' : 'right',
      wrapText: column === 1,
    };
    cell.border = allThinBorders();
  }

  applyNumberFormats(worksheet, rowNumber);
}

function fillRow(
  worksheet: Worksheet,
  rowNumber: number,
  color: string,
): void {
  for (let column = 1; column <= 19; column += 1) {
    worksheet.getCell(rowNumber, column).fill = solidFill(color);
  }
}

function setRateAndCostFormulas(
  worksheet: Worksheet,
  rowNumber: number,
  totals: ExportTotals,
  investment: number | null,
): void {
  setFormulaCell(
    worksheet,
    `I${rowNumber}`,
    `IFERROR(C${rowNumber}/B${rowNumber},"")`,
    safeDivide(totals.visitors, totals.leads),
  );
  setFormulaCell(
    worksheet,
    `J${rowNumber}`,
    `IFERROR(D${rowNumber}/C${rowNumber},"")`,
    safeDivide(totals.salesDigital, totals.visitors),
  );
  setFormulaCell(
    worksheet,
    `K${rowNumber}`,
    `IFERROR(D${rowNumber}/B${rowNumber},"")`,
    safeDivide(totals.salesDigital, totals.leads),
  );
  setFormulaCell(
    worksheet,
    `Q${rowNumber}`,
    `IF(OR(L${rowNumber}="",B${rowNumber}=0),"",L${rowNumber}/B${rowNumber})`,
    safeDivide(investment, totals.leads),
  );
  setFormulaCell(
    worksheet,
    `R${rowNumber}`,
    `IF(OR(L${rowNumber}="",C${rowNumber}=0),"",L${rowNumber}/C${rowNumber})`,
    safeDivide(investment, totals.visitors),
  );
  setFormulaCell(
    worksheet,
    `S${rowNumber}`,
    `IF(OR(L${rowNumber}="",D${rowNumber}+E${rowNumber}=0),"",L${rowNumber}/(D${rowNumber}+E${rowNumber}))`,
    safeDivide(
      investment,
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
      `I${range.firstRow}:I${range.lastRow}`,
      'greaterThanOrEqual',
      0.15,
      COLORS.greenFill,
      COLORS.greenText,
    );
    addCellRule(
      worksheet,
      `J${range.firstRow}:J${range.lastRow}`,
      'greaterThanOrEqual',
      0.30,
      COLORS.greenFill,
      COLORS.greenText,
    );

    addCellRule(
      worksheet,
      `K${range.firstRow}:K${range.lastRow}`,
      'lessThan',
      0.015,
      COLORS.redFill,
      COLORS.redText,
      true,
    );
    addCellRule(
      worksheet,
      `K${range.firstRow}:K${range.lastRow}`,
      'lessThan',
      0.033,
      COLORS.amberFill,
      COLORS.amberText,
      true,
    );
    addCellRule(
      worksheet,
      `K${range.firstRow}:K${range.lastRow}`,
      'greaterThanOrEqual',
      0.033,
      COLORS.greenFill,
      COLORS.greenText,
    );
  }
}

function addCellRule(
  worksheet: Worksheet,
  ref: string,
  operator: 'greaterThan' | 'greaterThanOrEqual' | 'lessThan',
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

function allThinBorders(): any {
  const border = {
    style: 'thin',
    color: { argb: COLORS.border },
  };

  return {
    top: border,
    bottom: border,
    left: border,
    right: border,
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
