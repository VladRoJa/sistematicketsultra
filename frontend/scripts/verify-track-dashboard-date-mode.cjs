'use strict';

// Ejecuta los métodos reales del componente sin navegador ni backend.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');

const componentPath = path.resolve(
  __dirname, '../src/app/warehouse/track-dashboard/track-dashboard.component.ts',
);
const templatePath = componentPath.replace('.ts', '.html');
const cssPath = componentPath.replace('.ts', '.css');
const code = fs.readFileSync(componentPath, 'utf8');
const template = fs.readFileSync(templatePath, 'utf8');
const css = fs.readFileSync(cssPath, 'utf8');

const ast = ts.createSourceFile(componentPath, code, ts.ScriptTarget.ES2020, true);
const component = ast.statements.find(
  node => ts.isClassDeclaration(node) && node.name?.text === 'TrackDashboardComponent',
);
assert.ok(component, 'No se encontró TrackDashboardComponent');

function method(name) {
  const node = component.members.find(
    member => ts.isMethodDeclaration(member) && member.name?.getText(ast) === name,
  );
  assert.ok(node, 'Falta método Track: ' + name);
  return node.getText(ast);
}

const realMethods = [
  'onTrackDateChanged',
  'goToPreviousTrackDate',
  'goToNextTrackDate',
  'shouldDisableNextTrackDateButton',
  'shiftTrackDateByDays',
  'applyHistoricalModeForSelectedDate',
  'parseIsoDate',
  'formatDateAsIso',
  'syncSelectedModeLabel',
  'isSelectedTrackDateInPast',
  'getEmptyTrackMessage',
].map(method).join('\n');

const harness = `class Dashboard {
  trackDate = '2026-10-20';
  generationMode = 'manual_preview';
  selectedModeLabel = '';
  isLoadingMart = false;
  requests = [];
  getTodayIsoDate() { return '2026-10-20'; }
  clearCanonicalClosePoll() {}
  resetCanonicalCloseState() {}
  resetLoadedMartState() {}
  loadDailyMart() { this.requests.push([this.trackDate, this.generationMode]); }
  loadCanonicalCloseStatus() {}
  ${realMethods}
}
exports.Dashboard = Dashboard;`;

const compiled = ts.transpileModule(harness, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  reportDiagnostics: true,
});
const errors = (compiled.diagnostics || []).filter(d => d.category === ts.DiagnosticCategory.Error);
assert.equal(errors.length, 0, 'Error al compilar métodos reales del componente');

const testModule = new Module(componentPath, module);
testModule.filename = componentPath;
testModule.paths = Module._nodeModulePaths(path.dirname(componentPath));
testModule._compile(compiled.outputText, componentPath);
const { Dashboard } = testModule.exports;

const dashboard = new Dashboard();
dashboard.applyHistoricalModeForSelectedDate();
assert.equal(dashboard.generationMode, 'manual_preview');
assert.equal(dashboard.selectedModeLabel, 'Corte preliminar');
assert.equal(dashboard.getEmptyTrackMessage(), 'Corte preliminar no disponible para hoy.');

dashboard.trackDate = '2026-10-19';
dashboard.onTrackDateChanged();
assert.equal(dashboard.generationMode, 'official_closed_day');
assert.equal(dashboard.selectedModeLabel, 'Cierre consolidado');
assert.deepEqual(dashboard.requests.at(-1), ['2026-10-19', 'official_closed_day']);
assert.equal(dashboard.getEmptyTrackMessage(), 'Cierre no disponible para la fecha seleccionada.');

dashboard.goToNextTrackDate();
assert.equal(dashboard.trackDate, '2026-10-20');
assert.equal(dashboard.generationMode, 'manual_preview');
assert.deepEqual(dashboard.requests.at(-1), ['2026-10-20', 'manual_preview']);
assert.equal(dashboard.shouldDisableNextTrackDateButton(), true);

dashboard.trackDate = '2026-10-21';
dashboard.onTrackDateChanged();
assert.equal(dashboard.trackDate, '2026-10-20');
assert.equal(dashboard.generationMode, 'manual_preview');
assert.deepEqual(dashboard.requests.at(-1), ['2026-10-20', 'manual_preview']);

assert.doesNotMatch(template, /id="generationMode"|onGenerationModeChanged|generationModeOptions/,
  'La elección manual del modo no debe existir en Track');
assert.match(template, /\[max\]="getTodayIsoDate\(\)"/,
  'El calendario debe limitarse al día actual de Tijuana');
assert.match(template, /getEmptyTrackMessage\(\)/,
  'Una fecha sin cierre debe distinguirse de un día preliminar');
assert.match(css, /\.track-form--topbar\s*\{[^}]*grid-template-columns:\s*210px auto;/,
  'El topbar no debe reservar columna para el selector eliminado');
assert.match(code, /trackDate = this\.getTodayIsoDate\(\)/,
  'La fecha inicial debe usar America\/Tijuana');

console.log('PASS: hoy/preliminar, histórico/cierre, flechas, calendario, fecha futura, layout');
