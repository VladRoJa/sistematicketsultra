'use strict';

// QA-09D: el filtro de sucursal debe persistir después de Aplicar.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const ts = require('typescript');

function cargarTs(relativePath, mocks = {}) {
  const source = fs.readFileSync(path.join(__dirname, '../src/app', relativePath), 'utf8');
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2020,
      module: ts.ModuleKind.CommonJS,
      experimentalDecorators: true,
    },
  }).outputText;
  const module = { exports: {} };
  const fakeRequire = name => {
    if (name === '@angular/core') {
      return { Component: () => klass => klass, ViewChild: () => () => {} };
    }
    return mocks[name] || {};
  };
  new Function('require', 'module', 'exports', compiled)(
    fakeRequire, module, module.exports
  );
  return module.exports;
}

const helpers = cargarTs('/utils/tabla-filtros.helper.ts');
const { InventarioComponent } = cargarTs('/inventario/inventario.component.ts', {
  'src/app/utils/tabla-filtros.helper': helpers,
  'src/app/utils/alertas': { mostrarAlertaToast: () => {} },
});

function crearComponente() {
  const vm = new InventarioComponent(
    {},
    {},
    { getRol: () => 'ADMINISTRADOR' }
  );
  vm.inventarios = [
    { id: 27, nombre: 'Mouse', sucursales: 'Villas del rey', categoria: 'Equipo recepcion' },
    { id: 36, nombre: 'Mouse', sucursales: 'Villas del rey', categoria: 'Equipo gerencia' },
    { id: 46, nombre: 'Mouse', sucursales: 'Villa verde mexicali', categoria: 'Equipo recepcion' },
    { id: 65, nombre: 'Mouse', sucursales: 'Independencia', categoria: 'Equipo recepcion' },
    { id: 141, nombre: 'Cable', sucursales: 'Tec mexicali', categoria: 'Cardio' },
  ];
  vm.filtros = helpers.inicializarFiltros(vm.inventarios, vm.columnasFiltrables);
  vm.busquedaGlobal = 'mouse';
  vm.aplicarBusquedaGlobal();
  return vm;
}

test('aplicar Villas del rey conserva 2 Mouse y el filtro activo', () => {
  const vm = crearComponente();
  assert.equal(vm.inventariosFiltrados.length, 4);

  vm.seleccionarTodo('sucursales', false);
  vm.alternarSeleccionIndividual('sucursales', 'Villas del rey', true);
  vm.aplicarFiltro('sucursales');

  assert.deepEqual(vm.inventariosFiltrados.map(it => it.id), [27, 36]);
  assert.equal(vm.filtros.sucursales.opciones.length, 4);
  assert.equal(vm.isFilterActive('sucursales'), true);

  vm.abrirMenuFiltro('sucursales');
  assert.equal(vm.obtenerOpcionesVisibles(vm.filtros.sucursales).length, 3);

  vm.limpiarBusquedaGlobal();
  assert.deepEqual(vm.inventariosFiltrados.map(it => it.id), [27, 36]);
});

test('limpiar solo el filtro de sucursal restaura el catálogo completo', () => {
  const vm = crearComponente();
  vm.seleccionarTodo('sucursales', false);
  vm.alternarSeleccionIndividual('sucursales', 'Villas del rey', true);
  vm.aplicarFiltro('sucursales');

  vm.limpiarFiltro('sucursales');
  assert.equal(vm.isFilterActive('sucursales'), false);
  assert.deepEqual(vm.inventariosFiltrados.map(it => it.id), [27, 36, 46, 65]);
});

test('dos filtros por columna no pierden su estado al aplicarse en secuencia', () => {
  const vm = crearComponente();
  vm.seleccionarTodo('sucursales', false);
  vm.alternarSeleccionIndividual('sucursales', 'Villas del rey', true);
  vm.aplicarFiltro('sucursales');

  vm.seleccionarTodo('categoria', false);
  vm.alternarSeleccionIndividual('categoria', 'Equipo recepcion', true);
  vm.aplicarFiltro('categoria');

  assert.deepEqual(vm.inventariosFiltrados.map(it => it.id), [27]);
  assert.equal(vm.isFilterActive('sucursales'), true);
  assert.equal(vm.isFilterActive('categoria'), true);

  vm.limpiarFiltro('categoria');
  assert.deepEqual(vm.inventariosFiltrados.map(it => it.id), [27, 36]);
});


test('filtros cruzados: mouse + Villas del rey solo ofrece dos categorías disponibles', () => {
  const vm = crearComponente();
  vm.abrirMenuFiltro('sucursales');
  vm.seleccionarTodo('sucursales', false);
  vm.alternarSeleccionIndividual('sucursales', 'Villas del rey', true);
  vm.aplicarFiltro('sucursales');
  assert.deepEqual(vm.inventariosFiltrados.map(it => it.id), [27, 36]);

  vm.abrirMenuFiltro('categoria');
  assert.deepEqual(
    vm.obtenerOpcionesVisibles(vm.filtros.categoria).map(op => op.valor),
    ['Equipo recepcion', 'Equipo gerencia'],
  );
  assert.equal(vm.isTodoSeleccionado('categoria'), true);
  assert.equal(vm.filtros.categoria.opciones.length, 3,
    'el universo de opciones se conserva para futuros cambios');
});

test('al reabrir una columna filtrada se excluye a sí misma del cruce', () => {
  const vm = crearComponente();
  vm.seleccionarTodo('sucursales', false);
  vm.alternarSeleccionIndividual('sucursales', 'Villas del rey', true);
  vm.aplicarFiltro('sucursales');
  vm.abrirMenuFiltro('sucursales');

  assert.deepEqual(
    vm.obtenerOpcionesVisibles(vm.filtros.sucursales).map(op => op.valor),
    ['Villas del rey', 'Villa verde mexicali', 'Independencia'],
  );
  assert.equal(vm.isFilterActive('sucursales'), true);
});

test('filtro del menú por texto selecciona el valor correcto, no el índice visible', () => {
  const vm = crearComponente();
  vm.seleccionarTodo('sucursales', false);
  vm.alternarSeleccionIndividual('sucursales', 'Villas del rey', true);
  vm.aplicarFiltro('sucursales');

  vm.abrirMenuFiltro('categoria');
  vm.buscar('categoria', 'gerencia');
  assert.deepEqual(
    vm.obtenerOpcionesVisibles(vm.filtros.categoria).map(op => op.valor),
    ['Equipo gerencia'],
  );
  vm.seleccionarTodo('categoria', false);
  vm.alternarSeleccionIndividual('categoria', 'Equipo gerencia', true);
  vm.aplicarFiltro('categoria');

  assert.deepEqual(vm.inventariosFiltrados.map(it => it.id), [36]);
  assert.equal(vm.cantidadFiltrosActivos, 2);
  vm.limpiarFiltro('categoria');
  assert.deepEqual(vm.inventariosFiltrados.map(it => it.id), [27, 36]);
});

test('el cruce respeta búsqueda global, y al limpiarla muestra categorías adicionales', () => {
  const vm = crearComponente();
  vm.abrirMenuFiltro('categoria');
  assert.deepEqual(
    vm.obtenerOpcionesVisibles(vm.filtros.categoria).map(op => op.valor),
    ['Equipo recepcion', 'Equipo gerencia'],
  );
  vm.limpiarBusquedaGlobal();
  vm.abrirMenuFiltro('categoria');
  assert.deepEqual(
    vm.obtenerOpcionesVisibles(vm.filtros.categoria).map(op => op.valor),
    ['Equipo recepcion', 'Equipo gerencia', 'Cardio'],
  );
});

test('si se cierra sin aplicar, al reabrir se descartan cambios temporales', () => {
  const vm = crearComponente();
  vm.abrirMenuFiltro('sucursales');
  vm.seleccionarTodo('sucursales', false);
  vm.alternarSeleccionIndividual('sucursales', 'Villas del rey', true);

  vm.abrirMenuFiltro('sucursales');
  assert.equal(vm.isTodoSeleccionado('sucursales'), true);
  assert.equal(vm.inventariosFiltrados.length, 4);
});

test('todos los filtros se cruzan, no solo categoría y sucursal', () => {
  const vm = crearComponente();
  vm.seleccionarTodo('categoria', false);
  vm.alternarSeleccionIndividual('categoria', 'Equipo gerencia', true);
  vm.aplicarFiltro('categoria');

  vm.abrirMenuFiltro('sucursales');
  assert.deepEqual(
    vm.obtenerOpcionesVisibles(vm.filtros.sucursales).map(op => op.valor),
    ['Villas del rey'],
  );
  vm.abrirMenuFiltro('nombre');
  assert.deepEqual(
    vm.obtenerOpcionesVisibles(vm.filtros.nombre).map(op => op.valor),
    ['Mouse'],
  );
});
