import * as XLSX from 'xlsx';

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

const EXPORT_HEADERS = [
  'Sucursal',
  'Inversión',
  'Leads iVentas',
  'Visitas total',
  'Visitas iVentas',
  'Visitas sin trazabilidad',
  'Venta nueva total',
  'Venta iVentas',
  'Venta publicaciones',
  'Venta orgánico',
  'Venta no iVentas',
  'Ingreso total',
  'Costo por lead',
  'Costo por visita',
  'Costo por venta iVentas',
  'Lead → Visita iVentas',
  'Visita iVentas → Compra',
  'Visita sin trazabilidad → Compra',
  '% Venta iVentas',
];

const CURRENCY_COLUMNS = ['B', 'L', 'M', 'N', 'O'];
const PERCENT_COLUMNS = ['P', 'Q', 'R', 'S'];

export function exportMarketingSalesFunnelBranchTable(
  options: FunnelBranchExportOptions,
): void {
  if (!options.branches.length) {
    return;
  }

  const investmentByBranch = new Map<number, number | null>();
  if (
    options.investmentDashboard
    && options.investmentDashboard.month === options.month
  ) {
    for (const branch of options.investmentDashboard.branches) {
      investmentByBranch.set(branch.sucursal_id, branch.investment ?? null);
    }
  }

  const rows = options.branches.map((branch) => {
    const investment = investmentByBranch.get(branch.sucursal_id) ?? null;
    const costPerLead = (
      investment !== null && branch.leads_meta > 0
        ? investment / branch.leads_meta
        : null
    );
    const costPerVisit = (
      investment !== null && branch.visits_total > 0
        ? investment / branch.visits_total
        : null
    );
    const costPerSale = (
      investment !== null && branch.sales_iventas > 0
        ? investment / branch.sales_iventas
        : null
    );
    const leadToVisit = (
      branch.leads_meta > 0
        ? branch.visits_iventas / branch.leads_meta
        : null
    );

    return [
      branch.sucursal,
      investment,
      branch.leads_meta,
      branch.visits_total,
      branch.visits_iventas,
      branch.visits_not_iventas,
      branch.sales_total,
      branch.sales_iventas,
      branch.sales_iventas_meta,
      branch.sales_iventas_other,
      branch.sales_not_iventas,
      branch.revenue_total,
      costPerLead,
      costPerVisit,
      costPerSale,
      leadToVisit,
      branch.iventas_visit_conversion_rate,
      branch.not_iventas_visit_conversion_rate,
      branch.iventas_sale_share,
    ];
  });

  const worksheet = XLSX.utils.aoa_to_sheet([
    EXPORT_HEADERS,
    ...rows,
  ]);

  worksheet['!cols'] = [
    { wch: 24 },
    { wch: 14 },
    { wch: 13 },
    { wch: 13 },
    { wch: 14 },
    { wch: 23 },
    { wch: 17 },
    { wch: 14 },
    { wch: 19 },
    { wch: 15 },
    { wch: 17 },
    { wch: 15 },
    { wch: 15 },
    { wch: 16 },
    { wch: 20 },
    { wch: 21 },
    { wch: 22 },
    { wch: 30 },
    { wch: 16 },
  ];

  const lastRow = rows.length + 1;
  worksheet['!autofilter'] = { ref: `A1:S${lastRow}` };

  for (let rowIndex = 2; rowIndex <= lastRow; rowIndex += 1) {
    for (const column of CURRENCY_COLUMNS) {
      const cell = worksheet[`${column}${rowIndex}`];
      if (cell && typeof cell.v === 'number') {
        cell.z = '$#,##0.00';
      }
    }

    for (const column of PERCENT_COLUMNS) {
      const cell = worksheet[`${column}${rowIndex}`];
      if (cell && typeof cell.v === 'number') {
        cell.z = '0.0%';
      }
    }
  }

  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, worksheet, 'Por sucursal');

  XLSX.writeFile(
    workbook,
    buildExportFilename(options),
  );
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
