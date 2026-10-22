'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const inventoryDir = path.join(__dirname, '../src/app/inventario');
const dialogDir = path.join(inventoryDir, 'dialogo-inventario');
const html = fs.readFileSync(path.join(dialogDir, 'dialogo-inventario.component.html'), 'utf8');
const css = fs.readFileSync(path.join(dialogDir, 'dialogo-inventario.component.css'), 'utf8');
const componentTs = fs.readFileSync(path.join(dialogDir, 'dialogo-inventario.component.ts'), 'utf8');
const parentTs = fs.readFileSync(path.join(inventoryDir, 'inventario.component.ts'), 'utf8');

test('QA-11A: etiquetas visibles independientes de floating labels MDC compactas', () => {
  assert.match(html, /class="form-item__label"/);
  assert.doesNotMatch(html, /<mat-label>/);
  assert.match(html, /<label for="inv-nombre"/);
  assert.match(html, /<input matInput id="inv-nombre"/);
  assert.match(html, /formControlName="nombre"/);
  assert.match(html, /formControlName="marca"/);
  assert.match(html, /formControlName="categoria"/);
  assert.match(css, /\.form-item__label/);
  assert.match(css, /grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/);
  assert.match(css, /@media \(max-width: 700px\)/);
});

test('QA-11A: cuerpo desplazable y acciones separadas, sin estilos inline', () => {
  assert.match(html, /mat-dialog-content/);
  assert.match(html, /mat-dialog-actions/);
  assert.match(html, /class="inventory-dialog__content"/);
  assert.match(html, /class="botones"/);
  assert.match(html, /Datos del artículo en el catálogo maestro/);
  assert.match(html, /Las existencias por sucursal se registran por separado/);
  assert.doesNotMatch(html, /\bstyle="/);
  assert.match(parentTs, /width:\s*'780px'/);
  assert.match(parentTs, /maxWidth:\s*'96vw'/);
});

test('QA-11A: Aparatos, Sistemas y Dispositivos muestran código requerido', () => {
  assert.match(componentTs, /get requiereCodigoInterno\(\): boolean/);
  for (const tipo of ['aparato', 'aparatos', 'sistema', 'sistemas', 'dispositivo', 'dispositivos']) {
    assert.ok(componentTs.includes("'" + tipo + "'"), 'falta ' + tipo);
  }
  assert.match(html, /\*ngIf="requiereCodigoInterno"/);
  assert.match(html, /formControlName="codigo_interno"/);
  assert.match(html, /\*ngIf="esTipoAparato"/);
  assert.match(componentTs, /get detalleConversionCompra\(\): string/);
  assert.match(html, /\*ngIf="detalleConversionCompra"/);
});
