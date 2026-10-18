'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const Module = require('node:module');
const path = require('node:path');
const ts = require('typescript');

const src = path.resolve(__dirname, '../src/app/shared/modal-submit-state.ts');
const compiled = ts.transpileModule(fs.readFileSync(src, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const mod = new Module(src, module);
mod.filename = src;
mod.paths = Module._nodeModulePaths(path.dirname(src));
mod._compile(compiled, src);
const { isModalSubmitDisabled } = mod.exports;

// Reasignar: motivo obligatorio, usuario interno requerido y cambio real.
assert.equal(isModalSubmitDisabled({
  requiredText: ['   '],
  requiredSelections: ['INTERNA', 68],
}), true, 'Motivo vacío bloquea confirmar');
assert.equal(isModalSubmitDisabled({
  requiredText: ['Corrección de sucursal'],
  requiredSelections: ['INTERNA', null],
}), true, 'Responsable interno sin seleccionar bloquea');
assert.equal(isModalSubmitDisabled({
  requiredText: ['Cambio a proveedor'],
  requiredSelections: ['EXTERNA'],
}), false, 'Proveedor con motivo habilita confirmar');
assert.equal(isModalSubmitDisabled({
  requiredText: ['Corrección de sucursal'],
  requiredSelections: ['INTERNA', 68],
}), false, 'Formulario interno completo habilita confirmar');
assert.equal(isModalSubmitDisabled({
  requiredText: ['Corrección de sucursal'],
  requiredSelections: ['INTERNA', 68],
  blocked: true,
}), true, 'Guardando o sin cambio bloquea');

// Fecha inicial: fecha/motivo obligatorios, además del responsable cuando aplica.
assert.equal(isModalSubmitDisabled({
  requiredText: ['Compromiso'],
  requiredSelections: [null, 'INTERNA', 68],
}), true, 'Sin fecha no se puede guardar');
assert.equal(isModalSubmitDisabled({
  requiredText: [''],
  requiredSelections: [new Date('2026-10-24'), 'INTERNA', 68],
}), true, 'Sin motivo no se puede guardar');
assert.equal(isModalSubmitDisabled({
  requiredText: ['Compromiso'],
  requiredSelections: [new Date('2026-10-24'), 'INTERNA', 68],
}), false, 'Fecha y responsable completos permiten guardar');

for (const rel of [
  '../src/app/shared/reasignar-responsable-modal/reasignar-responsable-modal.component.html',
  '../src/app/shared/asignar-fecha-modal/asignar-fecha-modal.component.html',
]) {
  const html = fs.readFileSync(path.resolve(__dirname, rel), 'utf8');
  assert.match(html, /ultra-modal-confirm/, rel + ' debe reutilizar la clase visual');
  assert.match(html, /\[disabled\]="guardarDeshabilitado"/, rel + ' debe usar disabled nativo');
}
const css = fs.readFileSync(path.resolve(__dirname, '../src/styles.scss'), 'utf8');
assert.match(css, /ultra-modal-confirm:disabled/, 'Debe existir estilo disabled visible');
assert.match(css, /ultra-modal-confirm:not\(:disabled\)/, 'Debe conservar naranja en enabled');
console.log('PASS: habilitación reusable y estilo enabled/disabled en ambos modales');
