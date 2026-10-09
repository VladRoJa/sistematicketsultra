const fs = require('node:fs');
const path = require('node:path');

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(
  path.join(
    root,
    'src/app/system-daily-check-bi/system-daily-check-bi.component.html',
  ),
  'utf8',
);
const css = fs.readFileSync(
  path.join(
    root,
    'src/app/system-daily-check-bi/system-daily-check-bi.component.css',
  ),
  'utf8',
);

for (const marker of [
  'Esperados hoy',
  'Completados',
  'Pendientes',
  'Operación normal',
  'Falla menor',
  'Afectación operativa',
  'Matriz por sucursal',
  'Incidencias y Soporte',
  'Historial de checklists',
  'El piloto aún no tiene sucursales esperadas',
  'Drill-down exacto',
]) {
  assert(
    html.includes(marker),
    `Falta marcador funcional: ${marker}`,
  );
}

assert(
  html.includes('(click)="openTodayPending()"'),
  'Pendientes debe abrir drill-down.',
);
assert(
  html.includes('(click)="openSupportIssues(true)"')
    && html.includes('(click)="openSupportIssues(false)"'),
  'Reportadas/no reportadas deben bajar a incidencias fuente.',
);
assert(
  html.includes('(click)="openDetail(item.id)"'),
  'Historial debe abrir el checklist fuente.',
);
assert(
  html.includes('row.cells[group.key]?.label'),
  'La matriz debe mostrar texto semántico además del color.',
);
assert(
  html.includes('aria-label="Leyenda del semáforo"'),
  'La matriz debe tener leyenda accesible.',
);
assert(
  (html.match(/aria-modal="true"/g) || []).length >= 4,
  'Los drill-downs deben usar modales accesibles.',
);
assert(
  css.includes('@media (max-width: 680px)'),
  'Debe existir breakpoint móvil explícito.',
);
assert(
  /\.systems-branch-card__cells\s*\{[\s\S]*?grid-template-columns:\s*repeat\(2,/m.test(
    css,
  ),
  'La matriz debe colapsar a dos columnas en móvil.',
);
assert(
  !/\.systems-branch-matrix\s*\{[^}]*overflow-x\s*:/m.test(css),
  'La matriz no debe depender de scroll horizontal.',
);

process.stdout.write(
  'System Daily Check M3 UI contract tests passed.\n',
);
