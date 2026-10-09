const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
const service = fs.readFileSync(
  path.join(
    root,
    'src',
    'app',
    'system-daily-check',
    'system-daily-check.service.ts',
  ),
  'utf8',
);
const component = fs.readFileSync(
  path.join(
    root,
    'src',
    'app',
    'system-daily-check',
    'system-daily-check-gate.component.ts',
  ),
  'utf8',
);

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

assert(
  service.includes('SystemDailyCheckBranchCatalog'),
  'El service debe tipar el catálogo propio del checklist.',
);
assert(
  service.includes('${this.apiUrl}/branches'),
  'El checklist debe consumir /system-daily-checks/branches.',
);
assert(
  !service.includes('/sucursales/listar'),
  'El checklist no debe reutilizar el catálogo global de sucursales.',
);
assert(
  component.includes('branches.preferred_branch_id'),
  'La sucursal preferida debe venir del backend.',
);
assert(
  !component.includes('resolvePreferredBranchId'),
  'El frontend no debe reinterpretar la sucursal técnica de sesión.',
);
assert(
  !component.includes('1000') && !component.includes('100'),
  'Los IDs del puente corporativo no deben vivir en Angular.',
);

console.log('system-daily-check corporate pilot contract: PASS');
