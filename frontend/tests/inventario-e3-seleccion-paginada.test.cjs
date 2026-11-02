'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const ts = require('typescript');
const { webcrypto } = require('node:crypto');

globalThis.crypto ??= webcrypto;

const componentPath = path.join(
  __dirname, '../src/app/inventario/revision-correcciones/revision-correcciones.component.ts'
);
const html = fs.readFileSync(componentPath.replace('.ts', '.html'), 'utf8');
const compiled = ts.transpileModule(fs.readFileSync(componentPath, 'utf8'), {
  compilerOptions: {
    target: ts.ScriptTarget.ES2020,
    module: ts.ModuleKind.CommonJS,
    experimentalDecorators: true,
  },
}).outputText;
const mod = { exports: {} };
new Function('require', 'module', 'exports', compiled)(
  name => name === '@angular/core' ? { Component: () => cls => cls } : {},
  mod, mod.exports,
);
const { RevisionCorreccionesComponent } = mod.exports;

function solicitud(id, estado = 'PENDING') {
  return {
    id, tipo: 'MASTER_FIELD', campo: 'codigo_interno', estado,
    sucursal_id: 6, inventario_id: 2500 + id,
    valor_original: '05PI' + id, valor_propuesto: '06PI' + id,
    baseline_canonico: {}, motivo: 'Se requiere regularizar prefijo',
    evidencia_descriptiva: null, fecha_observacion_local: null,
  };
}
const first = [solicitud(7), ...Array.from({ length: 9 }, (_, i) => solicitud(100 + i))];
const second = [solicitud(8), solicitud(9)];

function crear() {
  let posted = null;
  let firstOverride = null;
  const api = {
    listarRevisionCorrecciones: params => ({
      subscribe: observer => {
        const items = params.page === 1 ? firstOverride || first : second;
        observer.next({ items, total: 12 });
        return { unsubscribe() {} };
      },
    }),
    decidirCorreccionesLote: payload => ({
      subscribe: observer => {
        posted = payload;
        observer.next({ lote_id: 50, items: payload.solicitud_ids.map(solicitud_id => ({ solicitud_id })) });
        return { unsubscribe() {} };
      },
    }),
  };
  const vm = new RevisionCorreccionesComponent(api);
  vm.contexto = { corporativo: true, sucursales: [] };
  vm.cargar();
  return { vm, posted: () => posted, setFirst: rows => { firstOverride = rows; } };
}

test('marcar #8/#9 en página 2 y #7 en página 1 crea un solo lote E3', () => {
  const { vm, posted } = crear();
  vm.cambiarPagina(1);
  vm.marcar(8);
  vm.marcar(9);
  vm.cambiarPagina(-1);
  assert.deepEqual(vm.seleccionadas.map(s => s.id), [8, 9]);
  vm.marcar(7);
  assert.deepEqual(vm.seleccionadas.map(s => s.id), [7, 8, 9]);
  vm.preparar('APPROVED');
  vm.motivo = 'Verificadas las etiquetas físicas de los tres aparatos';
  vm.confirmo = true;
  assert.equal(vm.puedeConfirmar, true);
  vm.ejecutar();
  assert.deepEqual(posted().solicitud_ids, [7, 8, 9]);
  assert.equal(vm.seleccionadas.length, 0);
});

test('seleccionar/desmarcar una página conserva otras y máximo diez', () => {
  const { vm } = crear();
  vm.cambiarPagina(1);
  vm.marcar(8);
  vm.marcar(9);
  vm.cambiarPagina(-1);
  vm.marcarPagina();
  assert.equal(vm.seleccionadas.length, 10);
  assert.equal(vm.seleccion.has(8), true);
  assert.equal(vm.seleccion.has(9), true);
  assert.equal(vm.seleccionadasEnPagina, 8);
  vm.marcar(7);
  assert.equal(vm.seleccionadas.length, 9);
  assert.equal(vm.seleccion.has(8), true);
  assert.equal(vm.seleccion.has(9), true);
  vm.marcarPagina();
  assert.equal(vm.seleccionadas.length, 10);
  vm.cambiarFiltros();
  assert.equal(vm.seleccionadas.length, 0);
});

test('al refrescar página elimina solicitudes ya decididas y recarga limpia selección', () => {
  const { vm, setFirst } = crear();
  vm.marcar(7);
  vm.cambiarPagina(1);
  vm.marcar(8);
  vm.cambiarPagina(-1);
  setFirst([solicitud(7, 'APPROVED'), ...first.slice(1)]);
  vm.cargar(true);
  assert.deepEqual(vm.seleccionadas.map(s => s.id), [8]);
  vm.cargar();
  assert.equal(vm.seleccionadas.length, 0);
});

test('la vista distingue selección total y por página y ofrece limpiar', () => {
  assert.match(html, /todasPaginaSeleccionadas/);
  assert.match(html, /seleccionadas entre páginas/);
  assert.match(html, /limpiarSeleccion\(\)/);
});
