'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const ts = require('typescript');

const inventory = path.join(__dirname, '../src/app/inventario');
const read = p => fs.readFileSync(path.join(inventory, p), 'utf8');
const parentTs = read('inventario.component.ts');
const parentHtml = read('inventario.component.html');
const dialogTs = read('dialogo-corregir-codigo/dialogo-corregir-codigo.component.ts');
const dialogHtml = read('dialogo-corregir-codigo/dialogo-corregir-codigo.component.html');

function load(source, mocks = {}) {
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2020,
      module: ts.ModuleKind.CommonJS,
      experimentalDecorators: true,
    },
  }).outputText;
  const mod = { exports: {} };
  new Function('require', 'module', 'exports', compiled)(
    name => name === '@angular/core'
      ? { Component: () => clazz => clazz, ViewChild: () => () => {} }
      : (mocks[name] || {}),
    mod, mod.exports,
  );
  return mod.exports;
}

const { InventarioComponent } = load(parentTs, {
  'src/app/utils/alertas': { mostrarAlertaToast: () => {} },
});

test('botón de corrección está junto a cada registro duplicado', () => {
  assert.match(parentHtml, /let articulo of grupo\.registros/);
  assert.match(parentHtml, /\(click\)="corregirCodigoDuplicado\(articulo\)"/);
  assert.match(parentHtml, /Corregir código/);
  assert.match(parentTs, /this\.dialog\.open\(DialogoCorregirCodigoComponent/);
});

test('corrección exitosa refresca catálogo y grupos; cancelación no', () => {
  let callback;
  let selectedItem;
  let reloads = 0;
  const item = { id: 427, codigo_interno: '01PIELF07', nombre: 'Escalera' };
  const vm = new InventarioComponent(
    {}, {
      open: (_, opts) => {
        selectedItem = opts.data;
        return {
          afterClosed: () => ({ subscribe: next => { callback = next; } }),
        };
      },
    }, { getRol: () => 'ADMINISTRADOR' },
  );
  vm.puedeAdministrarInventario = true;
  vm.cargarInventario = () => { reloads++; };
  vm.corregirCodigoDuplicado(item);
  assert.deepEqual(selectedItem, item);
  callback(null);
  assert.equal(reloads, 0);
  callback({ status: 'corregido' });
  assert.equal(reloads, 1);
});

test('no se permite abrir corrector si faltan permisos', () => {
  let opened = 0;
  const vm = new InventarioComponent({}, { open: () => { opened++; } }, {});
  vm.puedeAdministrarInventario = false;
  vm.corregirCodigoDuplicado({ id: 427, codigo_interno: 'X' });
  assert.equal(opened, 0);
});

test('diálogo requiere motivo y código; muestra historial y no modifica stock', () => {
  assert.match(dialogTs, /codigo_anterior: codigoAnterior/);
  assert.match(dialogTs, /codigo_nuevo: codigoNuevo/);
  assert.match(dialogTs, /motivo,/);
  assert.match(dialogTs, /Validators\.minLength\(10\)/);
  assert.match(dialogTs, /obtenerHistorialCodigos/);
  assert.match(dialogTs, /corregirCodigoInterno/);
  assert.match(dialogHtml, /Historial de correcciones/);
  assert.match(dialogHtml, /evento\.usuario_id/);
  assert.match(dialogHtml, /evento\.codigo_anterior/);
  assert.match(dialogHtml, /evento\.codigo_nuevo/);
  assert.match(dialogHtml, /evento\.motivo/);
  assert.doesNotMatch(dialogHtml, /style="/);
});
