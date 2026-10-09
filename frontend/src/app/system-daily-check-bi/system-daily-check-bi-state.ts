export type SystemDailyCheckHealthMatrixState =
  | 'GREEN'
  | 'YELLOW'
  | 'RED'
  | 'PENDING'
  | 'NA'
  | 'UNKNOWN';

export interface SystemDailyCheckHealthBranchLike {
  sucursal_id: number;
  sucursal?: string;
}

export type SystemDailyCheckQuickRange =
  | 'TODAY'
  | '7D'
  | '30D';

export type SystemDailyCheckMatrixTone =
  | 'success'
  | 'warning'
  | 'danger'
  | 'pending'
  | 'na'
  | 'unknown';

export interface SystemDailyCheckDateRange {
  dateFrom: string;
  dateTo: string;
}

function parseIsoBusinessDate(
  value: string,
): { year: number; month: number; day: number } {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(
    String(value || '').trim(),
  );
  if (!match) {
    throw new Error('Fecha de negocio inválida.');
  }

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const utc = new Date(Date.UTC(year, month - 1, day));

  if (
    utc.getUTCFullYear() !== year
    || utc.getUTCMonth() !== month - 1
    || utc.getUTCDate() !== day
  ) {
    throw new Error('Fecha de negocio inválida.');
  }
  return { year, month, day };
}

function formatUtcDate(value: Date): string {
  const year = String(value.getUTCFullYear()).padStart(4, '0');
  const month = String(value.getUTCMonth() + 1).padStart(2, '0');
  const day = String(value.getUTCDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function shiftSystemDailyCheckBusinessDate(
  value: string,
  days: number,
): string {
  const { year, month, day } = parseIsoBusinessDate(value);
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setUTCDate(date.getUTCDate() + Math.trunc(days));
  return formatUtcDate(date);
}

export function resolveSystemDailyCheckQuickRange(
  businessDate: string,
  range: SystemDailyCheckQuickRange,
): SystemDailyCheckDateRange {
  const span = range === 'TODAY'
    ? 1
    : range === '7D'
      ? 7
      : 30;

  return {
    dateFrom: shiftSystemDailyCheckBusinessDate(
      businessDate,
      -(span - 1),
    ),
    dateTo: businessDate,
  };
}

export function buildSystemDailyCheckRolloutSelection(
  expectedBranches: readonly SystemDailyCheckHealthBranchLike[],
): Set<number> {
  return new Set(
    expectedBranches.map(
      (branch) => Number(branch.sucursal_id),
    ),
  );
}

export function toggleSystemDailyCheckRolloutSelection(
  current: ReadonlySet<number>,
  branchId: number,
): Set<number> {
  const next = new Set(current);
  if (next.has(branchId)) {
    next.delete(branchId);
  } else {
    next.add(branchId);
  }
  return next;
}

export function systemDailyCheckMatrixTone(
  state: SystemDailyCheckHealthMatrixState,
): SystemDailyCheckMatrixTone {
  switch (state) {
    case 'GREEN':
      return 'success';
    case 'YELLOW':
      return 'warning';
    case 'RED':
      return 'danger';
    case 'PENDING':
      return 'pending';
    case 'NA':
      return 'na';
    default:
      return 'unknown';
  }
}

export function formatSystemDailyCheckBusinessDate(
  value: string | null | undefined,
): string {
  if (!value) {
    return '—';
  }
  const { year, month, day } = parseIsoBusinessDate(value);
  return `${String(day).padStart(2, '0')}/${String(month).padStart(2, '0')}/${year}`;
}
