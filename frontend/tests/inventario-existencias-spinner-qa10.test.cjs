'use strict';

// QA-10C: el indicador debe existir y la carga terminar tanto con éxito como con error.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const ts = require('typescript');

const base = path.join(__dirname, '../src/app/inventario/existencias');
const source = fs.readFileSync(path.join(base, 'existencias.component.ts'), 'utf8');
const html = fs.readFileSync(path.join(base, 'existencias.component.html'), 'utf8');
const css = fs.readFileSync(path.join(base, 'existencias.component.css'), 'utf8');

function componente() {
  const js = ts.transpileModule(source, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2020,
      module: ts.ModuleKind.CommonJS,
      experimentalDecorators: true,
    },
  }).outputText;
  const module = { exports: {} };
  new Function('require', 'module', 'exports', js)(
    name => name === '@angular/core'
      ? { Component: () => klass => klass }
      : {},
    module,
    module.exports,
  );
  return module.exports.ExistenciasComponent;
}

function fixture() {
  const oldStorage = global.localStorage;
  global.localStorage = {
    getItem: key => key === 'user'
      ? JSON.stringify({ rol: 'ADMINISTRADOR', sucursal_id: 1000 })
      : null,
  };
  try {
    let pending;
    const service = {
      verExistencias: () => ({
        subscribe: observers => { pending = observers; },
      }),
    };
    const Existencias = componente();
    const vm = new Existencias(service);
    vm.sucursalSeleccionada = 1;
    return { vm, pending: () => pending };
  } finally {
    global.localStorage = oldStorage;
  }
}

test('spinner de Angular Material registrado y visible cuando loading=true', () => {
  assert.match(source, /import \{ MatProgressSpinnerModule \} from '@angular\/material\/progress-spinner'/);
  assert.match(source, /imports:\s*\[[\s\S]*?MatProgressSpinnerModule/);
  assert.match(source, /styleUrls:\s*\['\.\/existencias\.component\.css'\]/);
  assert.match(html, /<div \*ngIf="loading" class="existencias-loading"/);
  assert.match(html, /<mat-spinner/);
  assert.match(html, /Cargando existencias\.\.\./);
  assert.match(css, /\.existencias-loading \{/);
});

test('al cambiar de sucursal se ve loading hasta respuesta y se filtra el stock', () => {
  const { vm, pending } = fixture();
  vm.cargarExistencias();
  assert.equal(vm.loading, true);
  pending().next([
    { inventario_id: 27, sucursal_id: 1, nombre: 'Mouse', stock: 1 },
    { inventario_id: 46, sucursal_id: 2, nombre: 'Mouse', stock: 5 },
  ]);
  assert.equal(vm.loading, false);
  assert.deepEqual(vm.existencias.map(item => item.inventario_id), [27]);
});

test('si la API falla, el estado loading termina sin quedarse bloqueado', () => {
  const { vm, pending } = fixture();
  const originalConsoleError = console.error;
  console.error = () => {};
  try {
    vm.cargarExistencias();
    assert.equal(vm.loading, true);
    pending().error(new Error('simulated'));
    assert.equal(vm.loading, false);
    assert.deepEqual(vm.existencias, []);
  } finally {
    console.error = originalConsoleError;
  }
});
