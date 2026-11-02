'use strict';

const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { test } = require('node:test');
const ts = require('typescript');

const base = path.join(__dirname, '../src/app/inventario');
const helperSource = fs.readFileSync(path.join(base, 'movimientos/tipos-inventario.helper.ts'), 'utf8');
const compiled = ts.transpileModule(helperSource, {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
}).outputText;
const exported = { exports: {} };
new Function('module', 'exports', compiled)(exported, exported.exports);
const normalize = exported.exports.normalizarTipoInventario;

test('Las variantes históricas de aparatos y dispositivos son una clase', () => {
  for (const value of ['Aparato', 'Aparatos', ' APARATO ', 'aparatos']) {
    assert.equal(normalize(value), 'aparatos');
  }
  for (const value of ['Sistema', 'Sistemas', 'Dispositivo', 'Dispositivos']) {
    assert.equal(normalize(value), 'dispositivos');
  }
  assert.equal(normalize('Producto'), 'producto');
  assert.equal(normalize(null), '');
});

test('Movimientos usa la misma identidad para opciones y búsqueda', () => {
  const source = fs.readFileSync(path.join(base, 'movimientos/dialogo-registrar-movimiento/dialogo-registrar-movimiento.component.ts'), 'utf8');
  assert.match(source, /\.map\(item => normalizarTipoInventario\(item\.tipo\)\)/);
  assert.match(source, /normalizarTipoInventario\(inv\.tipo\) === this\.tipoFiltro/);
});

test('Alta del maestro no ofrece Aparato y Aparatos separados', () => {
  const source = fs.readFileSync(path.join(base, 'dialogo-inventario/dialogo-inventario.component.ts'), 'utf8');
  assert.match(source, /normalizarTipoInventario\(tipo\.nombre\)/);
  assert.match(source, /opciones\.has\(nombre\)/);
});
