const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
const service = fs.readFileSync(
  path.join(
    root,
    'src',
    'app',
    'system-daily-check-bi',
    'system-daily-check-bi.service.ts',
  ),
  'utf8',
);
const component = fs.readFileSync(
  path.join(
    root,
    'src',
    'app',
    'system-daily-check-bi',
    'system-daily-check-bi.component.ts',
  ),
  'utf8',
);
const template = fs.readFileSync(
  path.join(
    root,
    'src',
    'app',
    'system-daily-check-bi',
    'system-daily-check-bi.component.html',
  ),
  'utf8',
);

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

assert(
  service.includes('/export.xlsx'),
  'El service BI debe consumir /export.xlsx.',
);
assert(
  service.includes("responseType: 'blob'"),
  'La exportación debe solicitar un Blob.',
);
assert(
  service.includes("observe: 'response'"),
  'La exportación debe conservar headers para el nombre del archivo.',
);
assert(
  component.includes('this.biService.exportExcel({'),
  'El componente debe delegar la exportación al service.',
);
assert(
  component.includes('dateFrom: this.dateFrom')
    && component.includes('dateTo: this.dateTo')
    && component.includes('branchId: this.selectedBranchId'),
  'La exportación debe respetar Desde, Hasta y Sucursal.',
);
assert(
  component.includes("response.headers.get('content-disposition')"),
  'El componente debe usar Content-Disposition para el nombre.',
);
assert(
  component.includes('URL.createObjectURL'),
  'La descarga debe generarse desde el Blob recibido.',
);
assert(
  template.includes('(click)="exportExcel()"')
    && template.includes('Exportar Excel'),
  'Salud de Sistemas debe mostrar el botón Exportar Excel.',
);

console.log('system-daily-check BI Excel export contract: PASS');
