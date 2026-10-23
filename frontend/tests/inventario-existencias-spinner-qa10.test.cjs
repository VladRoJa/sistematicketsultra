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

test('E1: GERENTE no participa en piloto, ni por URL directa a la pantalla', () => {
  const { vm, peticiones } = fixture('GERENTE');
  vm.ngOnInit();
  assert.equal(vm.puedeConsultarVista, false);
  assert.equal(peticiones.length, 0);
  assert.match(vm.error, /no está habilitada/);
  vm.cargarExistencias();
  assert.equal(peticiones.length, 0);
  assert.match(html, /\*ngIf="puedeConsultarVista"/);
  assert.doesNotMatch(html, /Solicitar corrección/);
  assert.doesNotMatch(html, /Verificado/);
});

test('E1: un perfil operativo permitido no ofrece selector global y respeta alcance backend', () => {
  const { vm, peticiones } = fixture('SR_MANTENIMIENTO');
  vm.ngOnInit();
  assert.equal(vm.puedeVerGlobal, false);
  assert.equal(vm.puedeConsultarVista, true);
  assert.equal(peticiones[0].opts, undefined);
  peticiones[0].observer.next(rows.slice(0, 1));
  assert.equal(vm.totalReferencias, 1);
  assert.match(html, /\*ngIf="puedeVerGlobal"/);
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


test('E1 familias: categorias de catalogo prevalecen sobre Maquinas/Cardio heredados', () => {
  const { vm, peticiones } = fixture();
  const equipos = [
    { ...rows[0], inventario_id: 201, nombre: 'Caminadora', tipo: 'Aparatos',
      categoria: 'Maquinas', subcategoria: 'Cardio', categoria_catalogo: 'Cardio',
      familia_equipo_id: 1, familia_equipo: { id: 1, key: 'CAMINADORA', nombre: 'Caminadora' } },
    { ...rows[0], inventario_id: 202, nombre: 'Bicicleta Vertical', tipo: 'Aparatos',
      categoria: 'Maquinas', subcategoria: 'Cardio', categoria_catalogo: 'Cardio',
      familia_equipo_id: null, familia_equipo: null },
    { ...rows[0], inventario_id: 203, nombre: 'Peso Integrado', tipo: 'Aparatos',
      categoria: 'Maquinas', subcategoria: 'Selectorizado', categoria_catalogo: 'Selectorizado',
      familia_equipo_id: 6, familia_equipo: { id: 6, key: 'PESO_INTEGRADO', nombre: 'Peso Integrado' } },
    { ...rows[0], inventario_id: 204, nombre: 'Caminadora', tipo: 'Aparatos',
      categoria: 'Cardio', subcategoria: '', categoria_catalogo: null,
      familia_equipo_id: null, familia_equipo: null },
    { ...rows[0], inventario_id: 205, nombre: 'Monitor', tipo: 'Dispositivos',
      categoria: 'Equipo recepción', categoria_catalogo: 'Equipo recepción',
      familia_equipo_id: null, familia_equipo: null },
  ];
  const original = JSON.stringify(equipos);
  vm.ngOnInit();
  peticiones[0].observer.next(equipos);

  assert.equal(vm.totalReferencias, 5);
  assert.equal(vm.totalEquiposGimnasio, 4);
  assert.equal(vm.equiposSinFamilia, 2); // NO cuenta el monitor sin familia.
  assert.equal(vm.totalCategorias, 4);
  assert.equal(vm.composicion.reduce((total, c) => total + c.cantidad, 0), 5);
  assert.deepEqual(vm.categorias,
    ['Cardio', 'Equipo recepción', 'Selectorizado', 'Sin categoría de catálogo']);
  assert.equal(vm.composicionFamilias.reduce((total, f) => total + f.cantidad, 0), 4);
  assert.equal(vm.composicionFamilias.at(-1).nombre, 'Sin familia');
  assert.deepEqual(vm.familias, ['Caminadora', 'Peso Integrado', 'Sin familia']);
  assert.equal(vm.nombreCategoria(equipos[0]), 'Cardio');
  assert.equal(vm.nombreCategoria(equipos[3]), 'Sin categoría de catálogo');
  assert.equal(vm.nombreFamilia(equipos[4]), null);
  assert.equal(JSON.stringify(equipos), original); // No hay reclasificación ni escritura.

  vm.familiaSeleccionada = 'Sin familia';
  vm.categoriaSeleccionada = 'Cardio';
  vm.aplicarFiltros();
  assert.deepEqual(vm.existenciasFiltradas.map(e => e.inventario_id), [202]);
  assert.equal(vm.totalReferencias, 5); // Filtros sólo afectan tabla.

  vm.categoriaSeleccionada = 'Sin categoría de catálogo';
  vm.aplicarFiltros();
  assert.deepEqual(vm.existenciasFiltradas.map(e => e.inventario_id), [204]);

  vm.limpiarFiltros();
  assert.equal(vm.existenciasFiltradas.length, 5);
  assert.equal(vm.familiaSeleccionada, 'todas');
  assert.equal(vm.hayFiltros, false);

  vm.familiaSeleccionada = 'Caminadora';
  assert.equal(vm.hayFiltros, true);
  vm.onSucursalChange(1);
  assert.equal(vm.familiaSeleccionada, 'todas');
  assert.equal(peticiones[1].opts.sucursal_id, 1);
});

test('E1 familias: dispositivos no generan pendientes y los porcentajes pequenos son legibles', () => {
  const { vm, peticiones } = fixture();
  vm.ngOnInit();
  peticiones[0].observer.next(rows);
  assert.equal(vm.totalEquiposGimnasio, 0);
  assert.equal(vm.equiposSinFamilia, 0);
  assert.deepEqual(vm.familias, []);
  assert.equal(vm.formatoPorcentaje(0.25), '<1%');
  assert.equal(vm.formatoPorcentaje(25.8), '26%');
  assert.equal(vm.formatoPorcentaje(0), '0%');
  assert.match(html, /familiaSeleccionada/);
  assert.match(html, /nombreCategoria\(e\)/);
  assert.match(html, /nombreFamilia\(e\)/);
  assert.match(html, /equiposSinFamilia/);
  assert.match(html, /formatoPorcentaje\(categoria.porcentaje\)/);
  assert.match(css, /\.family-summary \{/);
});


test('E1 filtros cruzados: Cardio sólo ofrece sus familias y no Peso Libre', () => {
  const { vm, peticiones } = fixture();
  const aparato = { ...rows[0], tipo: 'Aparatos', categoria: 'Maquinas', stock: 1 };
  const registros = [
    { ...aparato, inventario_id: 1, nombre: 'Caminadora', categoria_catalogo: 'Cardio',
      familia_equipo: { id: 1, key: 'CAMINADORA', nombre: 'Caminadora' } },
    { ...aparato, inventario_id: 2, nombre: 'Elíptica', categoria_catalogo: 'Cardio',
      familia_equipo: { id: 2, key: 'ELIPTICA', nombre: 'Elíptica' } },
    { ...aparato, inventario_id: 3, nombre: 'Bicicleta Vertical', categoria_catalogo: 'Cardio',
      familia_equipo: null },
    { ...aparato, inventario_id: 4, nombre: 'Mancuerna', categoria_catalogo: 'Peso Libre',
      familia_equipo: { id: 7, key: 'PESO_LIBRE', nombre: 'Peso Libre' } },
    { ...aparato, inventario_id: 5, nombre: 'Peso Integrado', categoria_catalogo: 'Selectorizado',
      familia_equipo: { id: 6, key: 'PESO_INTEGRADO', nombre: 'Peso Integrado' } },
    { ...rows[0], inventario_id: 6, categoria_catalogo: 'Equipo recepción',
      familia_equipo: null },
  ];

  vm.ngOnInit();
  peticiones[0].observer.next(registros);
  assert.equal(vm.totalReferencias, 6);
  assert.deepEqual(vm.familiasDisponibles,
    ['Caminadora', 'Elíptica', 'Peso Integrado', 'Peso Libre', 'Sin familia']);
  assert.deepEqual(vm.categoriasDisponibles, vm.categorias);

  vm.onCategoriaChange('Cardio');
  assert.deepEqual(vm.familiasDisponibles, ['Caminadora', 'Elíptica', 'Sin familia']);
  assert.equal(vm.familiasDisponibles.includes('Peso Libre'), false);
  assert.equal(vm.familiasDisponibles.includes('Peso Integrado'), false);
  assert.deepEqual(vm.existenciasFiltradas.map(e => e.inventario_id), [1, 2, 3]);

  vm.onFamiliaChange('Caminadora');
  assert.deepEqual(vm.categoriasDisponibles, ['Cardio']);
  assert.deepEqual(vm.existenciasFiltradas.map(e => e.inventario_id), [1]);

  // Si se cambia de categoría, no se conserva una familia imposible.
  vm.onCategoriaChange('Peso Libre');
  assert.equal(vm.familiaSeleccionada, 'todas');
  assert.deepEqual(vm.familiasDisponibles, ['Peso Libre']);
  assert.equal(vm.mostrarFiltroFamilia, false); // Redundante con categoría.
  assert.deepEqual(vm.existenciasFiltradas.map(e => e.inventario_id), [4]);

  // También funciona al seleccionar primero familia y después categoría.
  vm.onFamiliaChange('Peso Integrado');
  assert.equal(vm.categoriaSeleccionada, 'Selectorizado'); // Autoselección segura.
  assert.equal(vm.familiaSeleccionada, 'todas'); // Evita filtro redundante oculto.
  assert.equal(vm.mostrarFiltroFamilia, false);
  assert.deepEqual(vm.existenciasFiltradas.map(e => e.inventario_id), [5]);

  vm.onFamiliaChange('todas');
  vm.onCategoriaChange('Equipo recepción');
  assert.deepEqual(vm.familiasDisponibles, []); // Sin familias para dispositivos.
  assert.equal(vm.mostrarFiltroFamilia, false);
  assert.deepEqual(vm.existenciasFiltradas.map(e => e.inventario_id), [6]);

  vm.limpiarFiltros();
  assert.deepEqual(vm.categoriasDisponibles, vm.categorias);
  assert.deepEqual(vm.familiasDisponibles, vm.familias);
  assert.equal(vm.totalReferencias, 6);
  assert.equal(vm.equiposSinFamilia, 1);
  assert.equal(vm.referenciasConStock, 6);

  vm.onSucursalChange(1);
  assert.deepEqual(vm.familiasDisponibles, []);
  assert.deepEqual(vm.categoriasDisponibles, []);
  peticiones[1].observer.next(registros.slice(0, 1));
  assert.deepEqual(vm.familiasDisponibles, ['Caminadora']);
  assert.deepEqual(vm.categoriasDisponibles, ['Cardio']);
  assert.equal(vm.totalReferencias, 1);
  assert.match(html, /\*ngFor="let familia of familiasDisponibles"/);
  assert.match(html, /\*ngFor="let categoria of categoriasDisponibles"/);
  assert.match(html, /onCategoriaChange\(\$event\)/);
  assert.match(html, /onFamiliaChange\(\$event\)/);
  assert.match(html, /\*ngIf="mostrarFiltroFamilia"/);
});

test('E1 UX: familia seleccionada primero autocompleta categoría solo cuando es única', () => {
  const { vm, peticiones } = fixture();
  const aparato = { ...rows[0], tipo: 'Aparatos', categoria: 'Maquinas', stock: 1 };
  vm.ngOnInit();
  peticiones[0].observer.next([
    { ...aparato, inventario_id: 1, categoria_catalogo: 'Cardio',
      familia_equipo: { nombre: 'Caminadora' } },
    { ...aparato, inventario_id: 2, categoria_catalogo: 'Cardio',
      familia_equipo: { nombre: 'Elíptica' } },
    { ...aparato, inventario_id: 3, categoria_catalogo: 'Cardio', familia_equipo: null },
    { ...aparato, inventario_id: 4, categoria_catalogo: 'Peso Libre',
      familia_equipo: { nombre: 'Peso Libre' } },
    { ...aparato, inventario_id: 5, categoria_catalogo: 'Selectorizado',
      familia_equipo: { nombre: 'Peso Integrado' } },
    { ...aparato, inventario_id: 6, categoria_catalogo: null, familia_equipo: null },
    { ...rows[0], inventario_id: 7, categoria_catalogo: 'Equipo recepción' },
  ]);
  vm.onFamiliaChange('Caminadora');
  assert.equal(vm.categoriaSeleccionada, 'Cardio');
  assert.equal(vm.familiaSeleccionada, 'Caminadora');
  assert.equal(vm.mostrarFiltroFamilia, true); // Cardio sí tiene varias familias.
  assert.deepEqual(vm.existenciasFiltradas.map(e => e.inventario_id), [1]);

  vm.limpiarFiltros();
  vm.onFamiliaChange('Peso Libre');
  assert.equal(vm.categoriaSeleccionada, 'Peso Libre');
  assert.equal(vm.familiaSeleccionada, 'todas');
  assert.equal(vm.mostrarFiltroFamilia, false);
  assert.deepEqual(vm.existenciasFiltradas.map(e => e.inventario_id), [4]);

  vm.limpiarFiltros();
  vm.onFamiliaChange('Sin familia');
  assert.equal(vm.categoriaSeleccionada, 'todas'); // Ambigua en 2 categorías.
  assert.equal(vm.familiaSeleccionada, 'Sin familia');
  assert.equal(vm.mostrarFiltroFamilia, true);
  assert.deepEqual(vm.existenciasFiltradas.map(e => e.inventario_id), [3, 6]);

  vm.onCategoriaChange('Sin categoría de catálogo');
  assert.equal(vm.familiaSeleccionada, 'todas');
  assert.equal(vm.mostrarFiltroFamilia, false);
  assert.deepEqual(vm.existenciasFiltradas.map(e => e.inventario_id), [6]);
});

test('E1 UX: una sola familia visible puede ser útil si hay referencias sin familia', () => {
  const { vm, peticiones } = fixture();
  const aparato = { ...rows[0], tipo: 'Aparatos', categoria_catalogo: 'Cardio' };
  vm.ngOnInit();
  peticiones[0].observer.next([
    { ...aparato, inventario_id: 11, familia_equipo: { nombre: 'Caminadora' } },
    { ...aparato, inventario_id: 12, familia_equipo: null },
  ]);
  vm.onCategoriaChange('Cardio');
  assert.deepEqual(vm.familiasDisponibles, ['Caminadora', 'Sin familia']);
  assert.equal(vm.mostrarFiltroFamilia, true);
  vm.onFamiliaChange('Caminadora');
  assert.equal(vm.mostrarFiltroFamilia, true);
  assert.deepEqual(vm.existenciasFiltradas.map(e => e.inventario_id), [11]);

  vm.limpiarFiltros();
  vm.onCategoriaChange('Cardio');
  assert.equal(vm.familiaSeleccionada, 'todas');
  assert.deepEqual(vm.existenciasFiltradas.map(e => e.inventario_id), [11, 12]);
});
