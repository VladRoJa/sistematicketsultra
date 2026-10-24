const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '..', 'src', 'app');
const read = relative => fs.readFileSync(path.join(root, relative), 'utf8');

const child = read('pantalla-crear-ticket/formularios-crear-ticket/mantenimiento-aparatos/mantenimiento-aparatos.component.ts');
const form = read('pantalla-crear-ticket/crear-ticket-refactor.component.ts');
const html = read('pantalla-crear-ticket/formularios-crear-ticket/mantenimiento-aparatos/mantenimiento-aparatos.component.html');
const tickets = read('pantalla-ver-tickets/pantalla-ver-tickets.component.ts');
const ticketsHtml = read('pantalla-ver-tickets/pantalla-ver-tickets.component.html');

test('el backend gobierna la activación, nunca el frontend unilateralmente', () => {
  assert.match(child, /tapizadoHabilitado = false/);
  assert.match(child, /\/tickets\/tapizado-disponible/);
  assert.match(child, /result\.habilitado === true/);
  assert.match(html, /\*ngIf="tapizadoHabilitado"/);
});

test('selección múltiple acotada, validada y sincronizada con campos legacy', () => {
  assert.match(child, /maxAparatosTapizado = 50/);
  assert.match(child, /Validators\.minLength\(1\)/);
  assert.match(child, /aparatosSeleccionados\.map\(equipo => equipo\.id\)/);
  assert.match(child, /get\('aparato_id'\)\?\.setValue\(ids\[0\] \?\? null\)/);
  assert.match(form, /body\.aparatos_ids = this\.form\.value\.aparatos_ids/);
});

test('filtros cruzados de sucursal, familia y categoría', () => {
  assert.match(child, /filtroCategoriaTapizado/);
  assert.match(child, /filtroFamiliaTapizado/);
  assert.match(child, /equiposReqSub\?\.unsubscribe/);
  assert.match(html, /categoriasDisponiblesTapizado/);
  assert.match(html, /familiasDisponiblesTapizado/);
});

test('v1 de un aparato conserva selector clásico y payload intacto', () => {
  assert.match(html, /\*ngIf="!modoTapizado"/);
  assert.match(form, /this\.form\.value\.tipo_trabajo === 'TAPIZADO'/);
  assert.match(form, /body\.tipo_trabajo = 'TAPIZADO'/);
  assert.match(child, /this\.parentForm\.get\('tipo_trabajo'\)\?\.setValue\(null/);
});

test('bandeja muestra número de aparatos sin crear filas nuevas', () => {
  assert.match(tickets, /Tapizado · \$\{recibidos\}\/\$\{total\} recibidos/);
  assert.match(tickets, /getResumenTapizado\(ticket: Ticket\)/);
  assert.match(ticketsHtml, /\[matTooltip\]="getResumenTapizado\(ticket\)/);
});
