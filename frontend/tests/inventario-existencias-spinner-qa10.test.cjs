'use strict';

// Inventarios V2 E1: compatibilidad de carga QA-10 y coherencia dashboard/listado.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const ts = require('typescript');

const base = path.join(__dirname, '../src/app/inventario/existencias');
const source = fs.readFileSync(path.join(base, 'existencias.component.ts'), 'utf8');
const html = fs.readFileSync(path.join(base, 'existencias.component.html'), 'utf8');
const css = fs.readFileSync(path.join(base, 'existencias.component.css'), 'utf8');
const serviceSource = fs.readFileSync(path.join(__dirname, '../src/app/services/inventario.service.ts'), 'utf8');

function componente() {
  const js = ts.transpileModule(source, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2020,
      module: ts.ModuleKind.CommonJS,
      experimentalDecorators: true,
    },
  }).outputText;
  const mod = { exports: {} };
  new Function('require', 'module', 'exports', js)(
    name => name === '@angular/core'
      ? { Component: () => klass => klass }
      : {},
    mod,
    mod.exports,
  );
  return mod.exports.ExistenciasComponent;
}

function fixture(rol = 'ADMINISTRADOR') {
  const peticiones = [];
  const servicio = {
    listarSucursales: () => ({
      subscribe: observer => {
        observer.next([{ sucursal_id: 1, sucursal: 'Santa Fe' }]);
        return { unsubscribe() {} };
      },
    }),
    verExistencias: opts => ({
      subscribe: observer => {
        const peticion = {
          opts,
          observer,
          cancelada: false,
        };
        peticiones.push(peticion);
        return { unsubscribe: () => { peticion.cancelada = true; } };
      },
    }),
  };
  const session = { getRol: () => rol };
  const vm = new (componente())(servicio, session);
  return { vm, peticiones };
}

const rows = [
  { inventario_id: 25, sucursal_id: 1, sucursal_nombre: 'Santa Fe',
    nombre: 'CPU', codigo_interno: 'SF-025', tipo: 'Dispositivos', marca: 'Dell',
    proveedor: 'Proveedor A', categoria: 'Equipo recepción', unidad_medida: 'Pieza', stock: 1 },
  { inventario_id: 26, sucursal_id: 1, sucursal_nombre: 'Santa Fe',
    nombre: 'Monitor', codigo_interno: 'SF-026', tipo: 'Dispositivos', marca: 'HP',
    proveedor: 'Proveedor B', categoria: 'Equipo gerencia', unidad_medida: 'Pieza', stock: 0 },
  { inventario_id: 27, sucursal_id: 1, sucursal_nombre: 'Santa Fe',
    nombre: 'Impresora', codigo_interno: 'SF-027', tipo: 'Impresora', marca: null,
    proveedor: null, categoria: 'Equipo recepción', unidad_medida: 'Pieza', stock: 2 },
];

test('QA-10: spinner y plantilla externa siguen presentes', () => {
  assert.match(source, /MatProgressSpinnerModule/);
  assert.match(source, /SessionService/);
  assert.match(source, /templateUrl: '\.\/existencias\.component\.html'/);
  assert.match(source, /styleUrls: \['\.\/existencias\.component\.css'\]/);
  assert.match(html, /\*ngIf="loading" class="existencias-loading"/);
  assert.match(html, /<mat-spinner/);
  assert.match(html, /Cargando existencias\.\.\./);
  assert.match(css, /\.existencias-loading \{/);
});

test('E1: rol global inicia en Global y consulta su sucursal en backend, no filtra globalmente en Angular', () => {
  const { vm, peticiones } = fixture();
  vm.ngOnInit();
  assert.equal(vm.puedeVerGlobal, true);
  assert.equal(vm.sucursalSeleccionada, 'global');
  assert.equal(vm.loading, true);
  assert.equal(peticiones[0].opts, undefined);

  peticiones[0].observer.next(rows);
  assert.equal(vm.loading, false);
  assert.equal(vm.totalReferencias, 3);
  assert.equal(vm.referenciasConStock, 2);
  assert.equal(vm.referenciasSinStock, 1);
  assert.equal(vm.totalCategorias, 2);

  vm.onSucursalChange(1);
  assert.deepEqual(peticiones[1].opts, { sucursal_id: 1 });
  assert.equal(peticiones[0].cancelada, true);
  assert.equal(vm.loading, true);
  assert.equal(vm.totalReferencias, 0);
  peticiones[1].observer.next(rows.slice(0, 1));
  assert.equal(vm.totalReferencias, 1);
  assert.equal(vm.existenciasFiltradas.length, 1);
  assert.equal(vm.filasPagina[0].codigo_interno, 'SF-025');
  assert.match(serviceSource, /verExistencias\(opts\?: \{ sucursal_id\?: number \}\)/);
});

test('E1: un rol de sucursal no ve selector global y el backend define sus filas', () => {
  const { vm, peticiones } = fixture('GERENTE');
  vm.ngOnInit();
  assert.equal(vm.puedeVerGlobal, false);
  assert.equal(peticiones[0].opts, undefined);
  peticiones[0].observer.next(rows.slice(0, 1));
  assert.equal(vm.totalReferencias, 1);
  assert.match(html, /\*ngIf="puedeVerGlobal"/);
  assert.doesNotMatch(html, /Solicitar corrección/);
  assert.doesNotMatch(html, /Verificado/);
});

test('E1: búsqueda sin acentos, categoría y estado stock filtran la tabla sin alterar el resumen', () => {
  const { vm, peticiones } = fixture();
  vm.ngOnInit();
  peticiones[0].observer.next(rows);

  vm.busqueda = 'recepcion';
  vm.aplicarFiltros();
  assert.deepEqual(vm.existenciasFiltradas.map(e => e.inventario_id), [25, 27]);
  assert.equal(vm.totalReferencias, 3);

  vm.busqueda = '';
  vm.categoriaSeleccionada = 'Equipo gerencia';
  vm.estadoStock = 'sin-stock';
  vm.aplicarFiltros();
  assert.deepEqual(vm.existenciasFiltradas.map(e => e.inventario_id), [26]);
  assert.equal(vm.totalReferencias, 3);

  vm.limpiarFiltros();
  assert.equal(vm.existenciasFiltradas.length, 3);
  assert.equal(vm.composicion.reduce((n, cat) => n + cat.cantidad, 0), 3);
  assert.match(html, /e\.unidad_medida \|\| '—'/);
  assert.match(html, /e\.codigo_interno \|\| '—'/);
});

test('E1: paginación no renderiza miles de filas y conserva total filtrado', () => {
  const { vm, peticiones } = fixture();
  vm.ngOnInit();
  peticiones[0].observer.next(Array.from({ length: 85 }, (_, i) => ({
    ...rows[0],
    inventario_id: i + 1,
  })));
  assert.equal(vm.totalReferencias, 85);
  assert.equal(vm.filasPagina.length, 40);
  assert.equal(vm.totalPaginas, 3);
  vm.irPagina(2);
  assert.equal(vm.filasPagina.length, 5);
  assert.equal(vm.rangoInicio, 81);
  assert.equal(vm.rangoFin, 85);
  vm.irPagina(3);
  assert.equal(vm.paginaActual, 2);
  vm.busqueda = 'no-existe';
  vm.aplicarFiltros();
  assert.equal(vm.paginaActual, 0);
  assert.equal(vm.filasPagina.length, 0);
});

test('QA-10: error y respuesta tardía no dejan spinner ni cifras obsoletas', () => {
  const { vm, peticiones } = fixture();
  vm.ngOnInit();
  vm.onSucursalChange(1);
  peticiones[0].observer.next(rows);
  assert.equal(vm.totalReferencias, 0); // Ignorar respuesta de consulta anterior.
  peticiones[1].observer.error({ status: 403 });
  assert.equal(vm.loading, false);
  assert.equal(vm.totalReferencias, 0);
  assert.match(vm.error, /permiso/);
  vm.cargarExistencias();
  assert.equal(vm.loading, true);
  peticiones[2].observer.next(rows);
  assert.equal(vm.loading, false);
  assert.equal(vm.error, '');
});
