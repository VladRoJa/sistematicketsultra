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

console.log('system-daily-check no-freeze contract: PASS');
