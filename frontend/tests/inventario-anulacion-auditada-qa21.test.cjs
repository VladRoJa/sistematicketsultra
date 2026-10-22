'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const base = path.join(__dirname, '../src/app/inventario/movimientos');
const read = rel => fs.readFileSync(path.join(base, rel), 'utf8');
const listaTs = read('movimientos.component.ts');
const listaHtml = read('movimientos.component.html');
const listaCss = read('movimientos.component.css');
const detalleHtml = read('dialogo-detalle-movimiento/dialogo-detalle-movimiento.component.html');
const detalleTs = read('dialogo-detalle-movimiento/dialogo-detalle-movimiento.component.ts');
const anularTs = read('dialogo-anular-movimiento/dialogo-anular-movimiento.component.ts');
const anularHtml = read('dialogo-anular-movimiento/dialogo-anular-movimiento.component.html');

test('QA-21 no queda ninguna llamada DELETE para movimientos', () => {
  assert.doesNotMatch(listaTs, /http\.delete\(/);
  assert.doesNotMatch(listaTs, /eliminarMovimiento/);
  assert.match(listaTs, /http\.post\(/);
  assert.match(listaTs, /\/inventario\/movimientos\/\$\{mov\.id\}\/anular/);
  assert.match(listaTs, /\{ motivo \}/);
});

test('QA-21 acción Anular oculta para anulados y exige un solo envío pendiente', () => {
  assert.match(listaHtml, /\*ngIf="!mov\.anulado"/);
  assert.match(listaHtml, /\(click\)="anularMovimiento\(mov\)"/);
  assert.match(listaHtml, /\[disabled\]="anulandoMovimientoId !== null"/);
  assert.match(listaHtml, /mov\.anulado/);
  assert.match(listaHtml, />Anulado</);
  assert.match(listaCss, /\.movimientos-anulado/);
  assert.match(listaTs, /if \(mov\.anulado \|\| this\.anulandoMovimientoId !== null\) return/);
});

test('QA-21 motivo obligatorio con validación cliente; cancelar no envía', () => {
  assert.match(anularTs, /Validators\.minLength\(10\)/);
  assert.match(anularTs, /Validators\.maxLength\(1000\)/);
  assert.match(anularTs, /this\.dialogRef\.close\(null\)/);
  assert.match(anularTs, /this\.dialogRef\.close\(motivoLimpio\)/);
  assert.match(anularHtml, /\[formControl\]="motivo"/);
  assert.match(anularHtml, /\[disabled\]="motivo\.invalid \|\| motivo\.value\.trim\(\)\.length < 10"/);
  assert.match(anularHtml, /Se revertirán las existencias/);
  assert.match(anularHtml, /historial/);
});

test('QA-21 detalle histórico incluye usuario, fecha UTC y motivo sin ocultar artículos', () => {
  assert.match(detalleHtml, /data\.movimiento\.anulado/);
  assert.match(detalleHtml, /usuarioAnulacion/);
  assert.match(detalleTs, /data\.movimiento\.usuario_anulacion/);
  assert.match(detalleHtml, /anulado_en_utc/);
  assert.match(detalleHtml, /motivo_anulacion/);
  assert.match(detalleHtml, /\*ngFor="let articulo of articulos"/);
});
