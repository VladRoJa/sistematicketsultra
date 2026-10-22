'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const base = path.join(__dirname, '../src/app/inventario/movimientos');
const load = name => fs.readFileSync(path.join(base, name), 'utf8');
const transpiled = ts.transpileModule(load('movimientos-vista.helper.ts'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const mod = { exports: {} };
new Function('module', 'exports', 'require', transpiled)(mod, mod.exports, () => {});
const vista = mod.exports;

const catalogo = [
  { id: 11, nombre: 'Caminadora', marca: 'Fitness', proveedor: 'Proveedor A',
    categoria: 'Cardio', codigo_interno: '11CCJW21' },
  { id: 22, nombre: 'Arc Trainer', marca: 'Cybex', proveedor: 'Proveedor B',
    categoria: 'Cardio', codigo_interno: '01CESMT01' },
];
const mov = {
  id: 85, fecha: '22/10/2026 12:30', tipo: 'entrada',
  inventarios: [
    { inventario_id: 11, cantidad: 1, unidad_medida: 'pieza',
      codigo_interno: '11CCJW21' },
    { inventario_id: 22, cantidad: 2, unidad_medida: 'unidad',
      codigo_interno: '01CESMT01' },
  ],
};

test('resumen muestra renglones, no concatena productos ni suma unidades incompatibles', () => {
  assert.equal(vista.cantidadArticulosMovimiento(mov), 2);
  assert.equal(vista.primerArticuloMovimiento(mov, catalogo), 'Caminadora');
});

test('detalle conserva ID, código, unidad y cantidad por artículo', () => {
  const registros = vista.detallesMovimiento(mov, catalogo);
  assert.deepEqual(registros.map(r => [
    r.inventarioId, r.nombre, r.codigoActual, r.cantidad, r.unidadMedida,
  ]), [
    ['11', 'Caminadora', '11CCJW21', 1, 'pieza'],
    ['22', 'Arc Trainer', '01CESMT01', 2, 'unidad'],
  ]);
  assert.equal(registros[0].marca, 'Fitness');
  assert.equal(registros[1].proveedor, 'Proveedor B');
});

test('un movimiento de 75 renglones permanece íntegro para consulta detallada', () => {
  const grande = {
    ...mov,
    inventarios: Array.from({ length: 75 }, (_, index) => ({
      inventario_id: index + 1000,
      cantidad: index + 1,
      codigo_interno: 'COD-' + index,
      unidad_medida: 'pieza',
    })),
  };
  const snapshot = JSON.stringify(grande);
  assert.equal(vista.cantidadArticulosMovimiento(grande), 75);
  assert.equal(vista.detallesMovimiento(grande, []).length, 75);
  assert.equal(vista.detallesMovimiento(grande, [])[74].cantidad, 75);
  assert.equal(JSON.stringify(grande), snapshot, 'el detalle nunca muta el historial');
});

test('funciona con detalle ausente y catálogo aún no cargado', () => {
  assert.equal(vista.cantidadArticulosMovimiento({ id: 5 }), 0);
  assert.equal(vista.primerArticuloMovimiento({ id: 5 }, []), 'Sin artículos');
  assert.deepEqual(vista.detallesMovimiento({ id: 5 }, []), []);
  assert.equal(vista.primerArticuloMovimiento(mov, []), '11CCJW21');
  assert.equal(vista.detallesMovimiento(mov, [])[0].nombre, 'Inventario #11');
});

test('tabla mantiene sólo resumen y abre detalle sin renderizar códigos gigantes', () => {
  const html = load('movimientos.component.html');
  const typescript = load('movimientos.component.ts');
  const detalleHtml = load('dialogo-detalle-movimiento/dialogo-detalle-movimiento.component.html');

  assert.match(html, /matColumnDef="articulos"/);
  assert.match(html, /cantidadArticulos\(mov\)/);
  assert.match(html, /primerArticulo\(mov\)/);
  assert.match(html, /\(click\)="abrirDetalleMovimiento\(mov\)"/);
  assert.match(html, /Ver detalle/);
  assert.match(html, /displayedColumns/);
  assert.doesNotMatch(html, /matColumnDef="Codigo"/);
  assert.doesNotMatch(html, /matColumnDef="detalles"/);
  assert.doesNotMatch(html, /\*ngFor="let p of mov\.inventarios"/);
  assert.match(typescript, /this\.dialog\.open\(DialogoDetalleMovimientoComponent/);
  assert.match(typescript, /anularMovimiento\(mov: MovimientoInventarioVista\)/);
  assert.match(typescript, /this\.filtrar\(texto, tipo, sucursal, usuario, fecha\)/);
  assert.match(detalleHtml, /\*ngFor="let articulo of articulos"/);
  assert.match(detalleHtml, /articulo\.codigoActual/);
  assert.match(detalleHtml, /articulo\.cantidad/);
  assert.match(detalleHtml, /Los códigos y datos descriptivos corresponden al catálogo actual/);
});

test('QA-22 detalle muestra estado, trazabilidad y secciones bien jerarquizadas', () => {
  const html = load('dialogo-detalle-movimiento/dialogo-detalle-movimiento.component.html');
  const css = load('dialogo-detalle-movimiento/dialogo-detalle-movimiento.component.css');
  const component = load('dialogo-detalle-movimiento/dialogo-detalle-movimiento.component.ts');

  assert.match(html, /mat-dialog-title>Movimiento #/);
  assert.match(html, /etiquetaEstado/);
  assert.match(html, /\[class\.movement-detail__status--annulled\]="data\.movimiento\.anulado"/);
  assert.match(html, /Fecha original/);
  assert.match(html, /Registrado por/);
  assert.match(html, /usuarioRegistro/);
  assert.match(html, /nombreSucursal/);
  assert.match(html, /\*ngIf="data\.movimiento\.anulado"/);
  assert.match(html, /Auditoría de anulación/);
  assert.match(html, /usuarioAnulacion/);
  assert.match(html, /anulado_en_utc/);
  assert.match(html, /motivo_anulacion/);
  assert.match(html, /etiquetaCantidadArticulos/);
  assert.match(html, /Registro histórico · Solo lectura/);
  assert.match(html, /\(click\)="cerrar\(\)"/);
  assert.match(css, /\.movement-detail__meta\s*\{/);
  assert.match(css, /grid-template-columns: repeat\(4, minmax\(0, 1fr\)\)/);
  assert.match(css, /@media \(max-width: 760px\)/);
  assert.match(css, /\.movement-detail__scroll/);
  assert.match(css, /position: sticky/);
  assert.match(component, /MatIconModule/);
  assert.match(component, /this\.etiquetaEstado = data\.movimiento\.anulado/);
  assert.match(component, /this\.usuarioAnulacion = this\.etiquetaRegistro/);
});

test('QA-22 no pierde los detalles ni convierte registros anulados en existencias activas', () => {
  const html = load('dialogo-detalle-movimiento/dialogo-detalle-movimiento.component.html');
  const cancelado = {
    ...mov,
    anulado: true,
    usuario_anulacion: 'ADMICORP',
    motivo_anulacion: 'QA-21: anulacion controlada de prueba',
  };
  assert.equal(vista.detallesMovimiento(cancelado, catalogo).length, 2);
  assert.equal(vista.detallesMovimiento(cancelado, catalogo)[0].cantidad, 1);
  assert.match(html, /Datos originales de cantidades y unidades, sin modificaciones/);
  assert.match(html, /Los códigos y datos descriptivos corresponden al catálogo actual/);
  assert.doesNotMatch(html, /style="/);
});
