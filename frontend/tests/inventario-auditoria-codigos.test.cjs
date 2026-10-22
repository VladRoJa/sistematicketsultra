'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

function cargarTs(p, mocks = {}) {
  const source = fs.readFileSync(path.join(__dirname, '../src/app', p), 'utf8');
  const js = ts.transpileModule(source, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2020,
      module: ts.ModuleKind.CommonJS,
      experimentalDecorators: true,
    },
  }).outputText;
  const module = { exports: {} };
  const fakeRequire = (name) => {
    if (name === '@angular/core') {
      return { Component: () => klass => klass, ViewChild: () => () => {} };
    }
    return mocks[name] || {};
  };
  new Function('require', 'module', 'exports', js)(fakeRequire, module, module.exports);
  return module.exports;
}

const audit = cargarTs('inventario/helpers/auditoria-codigos.helper.ts');
const filters = cargarTs('utils/tabla-filtros.helper.ts');
const { InventarioComponent } = cargarTs('inventario/inventario.component.ts', {
  './helpers/auditoria-codigos.helper': audit,
  'src/app/utils/tabla-filtros.helper': filters,
  'src/app/utils/alertas': { mostrarAlertaToast: () => {} },
});

const html = fs.readFileSync(
  path.join(__dirname, '../src/app/inventario/inventario.component.html'), 'utf8',
);
const rows = [
  { id: 427, nombre: 'Escalera', marca: 'Matrix', codigo_interno: '01PIELF07', sucursales: 'Villas del rey' },
  { id: 717, nombre: 'Extension Espalda Baja', marca: 'Life Fitnes', codigo_interno: '01PIELF07', sucursales: 'Villas del rey' },
  { id: 3230, nombre: 'Banca Inclinada', marca: 'Star Trac', codigo_interno: '02PLST20', sucursales: 'Villa verde mexicali' },
  { id: 3231, nombre: 'Banca Inclinada', marca: 'Star Trac', codigo_interno: '02plst20 ', sucursales: 'Villa verde mexicali' },
  { id: 649, nombre: 'Glute Machine', marca: 'Excel', codigo_interno: '05PIPEX68', sucursales: 'Sendero mexicali' },
  { id: 2559, nombre: 'Pantorrilla Sentado', marca: 'Excel', codigo_interno: '05PIPEX68', sucursales: 'San luis' },
  { id: 650, nombre: 'Seated Leg Extension', marca: 'Excel', codigo_interno: '05PIPEX70', sucursales: 'Sendero mexicali' },
  { id: 2561, nombre: 'Seated Leg Extension', marca: 'Excel', codigo_interno: '05PIPEX70', sucursales: 'San luis' },
  { id: 652, nombre: 'Prone Leg Curl', marca: 'Excel', codigo_interno: '05PIPEX72', sucursales: 'Sendero mexicali' },
  { id: 3181, nombre: 'Prone Leg Curl', marca: 'Excel', codigo_interno: '05PIPEX72', sucursales: 'Tec mexicali' },
  { id: 9999, nombre: 'Caminadora', marca: 'Fitness', codigo_interno: '11CCJW21', sucursales: 'Sin asignación' },
  { id: 9998, nombre: 'Sin código', codigo_interno: '  ' },
  { id: 9997, nombre: 'Sin código', codigo_interno: null },
];

function componenteConRol(rol) {
  const service = {
    obtenerInventario: () => ({
      subscribe: handlers => handlers.next(rows.map(x => ({ ...x }))),
    }),
  };
  const component = new InventarioComponent(service, {}, { getRol: () => rol });
  component.ngOnInit();
  return component;
}

test('cinco códigos duplicados históricos, diez registros y cero escrituras', () => {
  const snapshot = JSON.stringify(rows);
  const grupos = audit.detectarCodigosDuplicados(rows);
  assert.equal(grupos.length, 5);
  assert.equal(grupos.reduce((n, grupo) => n + grupo.registros.length, 0), 10);
  assert.deepEqual(grupos.map(grupo => grupo.codigo), [
    '01PIELF07', '02PLST20', '05PIPEX68', '05PIPEX70', '05PIPEX72',
  ]);
  assert.deepEqual(grupos[0].registros.map(x => x.id), [427, 717]);
  assert.deepEqual(grupos[1].registros.map(x => x.id), [3230, 3231]);
  assert.equal(JSON.stringify(rows), snapshot, 'auditoría nunca modifica los datos');
});

test('botón administrador refleja todos los datos, sin depender de la búsqueda', () => {
  const vm = componenteConRol('ADMINISTRADOR');
  assert.equal(vm.gruposCodigosDuplicados.length, 5);
  assert.equal(vm.totalRegistrosConCodigoDuplicado, 10);
  assert.equal(vm.auditoriaCodigosAbierta, false);
  vm.busquedaGlobal = '11CCJW21';
  vm.aplicarBusquedaGlobal();
  assert.equal(vm.inventariosFiltrados.length, 1);
  assert.equal(vm.gruposCodigosDuplicados.length, 5);
  vm.alternarAuditoriaCodigos();
  assert.equal(vm.auditoriaCodigosAbierta, true);
  vm.alternarAuditoriaCodigos();
  assert.equal(vm.auditoriaCodigosAbierta, false);
});

test('usuarios sin permiso de administración no pueden abrir auditoría', () => {
  const vm = componenteConRol('GERENTE');
  assert.equal(vm.puedeAdministrarInventario, false);
  vm.alternarAuditoriaCodigos();
  assert.equal(vm.auditoriaCodigosAbierta, false);
  assert.match(html, /\*ngIf="puedeAdministrarInventario && !loading && !error"/);
  assert.match(html, /aria-label="Auditoría de códigos internos duplicados"/);
  assert.match(html, /grupo\.registros/);
});

test('sin códigos duplicados, devuelve vacío e informa cero', () => {
  const soloUnicos = rows.filter(x =>
    x.id === 9999 || x.id === 9998 || x.id === 9997
  );
  assert.deepEqual(audit.detectarCodigosDuplicados(soloUnicos), []);
  assert.match(html, /No se encontraron códigos internos duplicados/);
});
