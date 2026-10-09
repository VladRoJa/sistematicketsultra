import {
  buildSystemDailyCheckRolloutSelection,
  formatSystemDailyCheckBusinessDate,
  resolveSystemDailyCheckQuickRange,
  shiftSystemDailyCheckBusinessDate,
  systemDailyCheckMatrixTone,
  toggleSystemDailyCheckRolloutSelection,
} from '../src/app/system-daily-check-bi/system-daily-check-bi-state';

function assert(
  condition: boolean,
  message: string,
): void {
  if (!condition) {
    throw new Error(message);
  }
}

assert(
  shiftSystemDailyCheckBusinessDate(
    '2026-10-09',
    -8,
  ) === '2026-10-01',
  'Debe desplazar business_date sin usar zona horaria local.',
);

const sevenDays = resolveSystemDailyCheckQuickRange(
  '2026-10-09',
  '7D',
);
assert(
  sevenDays.dateFrom === '2026-10-03'
  && sevenDays.dateTo === '2026-10-09',
  '7D debe incluir exactamente siete business_date.',
);

const thirtyDays = resolveSystemDailyCheckQuickRange(
  '2026-10-09',
  '30D',
);
assert(
  thirtyDays.dateFrom === '2026-09-10'
  && thirtyDays.dateTo === '2026-10-09',
  '30D debe cruzar mes sin mover el día por TZ.',
);

const selected = buildSystemDailyCheckRolloutSelection([
  {
    sucursal_id: 10,
    sucursal: 'ALFA',
  },
  {
    sucursal_id: 11,
    sucursal: 'BETA',
  },
]);
assert(
  selected.has(10) && selected.has(11),
  'Debe inicializar participantes desde expected_branches.',
);

const toggled = toggleSystemDailyCheckRolloutSelection(
  selected,
  10,
);
assert(
  !toggled.has(10) && toggled.has(11),
  'Toggle debe crear un Set nuevo sin mutar selección original.',
);
assert(
  selected.has(10),
  'Toggle no debe mutar el Set original.',
);

assert(
  systemDailyCheckMatrixTone('GREEN') === 'success',
  'GREEN debe mapear a success.',
);
assert(
  systemDailyCheckMatrixTone('YELLOW') === 'warning',
  'YELLOW debe mapear a warning.',
);
assert(
  systemDailyCheckMatrixTone('RED') === 'danger',
  'RED debe mapear a danger.',
);
assert(
  systemDailyCheckMatrixTone('PENDING') === 'pending',
  'PENDING debe conservar semántica propia.',
);
assert(
  systemDailyCheckMatrixTone('NA') === 'na',
  'NA no debe confundirse con GREEN.',
);
assert(
  systemDailyCheckMatrixTone('UNKNOWN') === 'unknown',
  'UNKNOWN debe ser explícito.',
);

assert(
  formatSystemDailyCheckBusinessDate(
    '2026-10-09',
  ) === '09/10/2026',
  'Debe formatear business_date sin Date local.',
);
