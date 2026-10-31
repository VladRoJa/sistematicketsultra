const fs = require('fs');
const path = require('path');

const sourcePath = path.join(
  __dirname,
  '..',
  'src',
  'app',
  'system-daily-check',
  'system-daily-check-gate.component.ts',
);
const source = fs.readFileSync(sourcePath, 'utf8');

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

assert(
  !/get\s+questionGroups\s*\(/.test(source),
  'questionGroups no debe ser un getter dinámico durante change detection.',
);

assert(
  /questionGroups:\s*SystemDailyCheckGateQuestionGroup<[\s\S]*?>\[\]\s*=\s*\[\]/.test(source),
  'questionGroups debe mantenerse como estado cacheado del componente.',
);

assert(
  /this\.questionGroups\s*=\s*buildSystemDailyCheckQuestionGroups\(\s*this\.questions,?\s*\)/m.test(source),
  'questionGroups debe calcularse una sola vez al cargar las preguntas.',
);

// Una cuenta GERENTE de ULTRA DEMO no recibe sucursales elegibles
// en /branches: la ventana global debe liberarse en vez de bloquear Tickets.
const noBranchGuard = source.indexOf('if (this.branches.length === 0) {');
const preferredBranchSelection = source.indexOf('const preferredBranchId = Number(');
assert(
  noBranchGuard !== -1
    && preferredBranchSelection > noBranchGuard
    && /if \(this\.branches\.length === 0\) \{[\s\S]*?this\.setVisible\(false\);[\s\S]*?return;[\s\S]*?\}/.test(source),
  'Sin sucursal elegible (incluida ULTRA DEMO), el checklist debe ocultarse y liberar navegación.',
);

console.log('system-daily-check no-freeze contract: PASS');
