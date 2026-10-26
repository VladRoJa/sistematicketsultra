const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '..', 'src', 'app', 'pantalla-ver-tickets');
const read = p => fs.readFileSync(path.join(root, p), 'utf8');
const tickets = read('pantalla-ver-tickets.component.ts');
const html = read('pantalla-ver-tickets.component.html');
const css = read('pantalla-ver-tickets.component.css');
const historial = read('modals/historial-fechas-modal.component.html');
const historialTs = read('modals/historial-fechas-modal.component.ts');
const recepcion = read('modals/tapizado-recepcion-modal.component.ts');
const recepcionHtml = read('modals/tapizado-recepcion-modal.component.html');

test('acción directa está junto al QR y sólo en tickets Tapizado', () => {
  assert.match(html, /class="btn-tapizado-recepcion"/);
  assert.match(html, /\*ngIf="ticket\.tipo_trabajo === 'TAPIZADO'"/);
  assert.match(html, /\(click\)="abrirRecepcionTapizado\(ticket, \$event\)"/);
  assert.match(html, /matTooltip="Gestionar recepción de tapizado"/);
  assert.match(tickets, /event\?\.stopPropagation\(\)/);
  assert.match(tickets, /this\.dialog\.open\(TapizadoRecepcionModalComponent/);
  assert.match(css, /\.btn-tapizado-recepcion/);
});

test('resumen histórico es sólo lectura y conserva lista y auditoría', () => {
  assert.match(historial, /Estado de tapizado/);
  assert.match(historial, /\*ngFor="let aparato of aparatosTapizado"/);
  assert.match(historial, /mat-progress-bar/);
  assert.match(historialTs, /consultarRecepcionTapizado/);
  assert.doesNotMatch(historial, /<mat-checkbox/);
  assert.doesNotMatch(historial, /Guardar cambios|Descartar selección/);
  assert.doesNotMatch(historialTs, /guardarRecepcionesTapizado/);
  assert.match(historial, /Historial de solución/);
});

test('modal dedicado conserva permisos backend, borrador, motivo y guardado único', () => {
  assert.match(recepcion, /result\.puede_editar === true/);
  assert.match(recepcion, /this\.borradorRecepciones\.set\(aparato\.id, event\.checked\)/);
  assert.match(recepcion, /this\.ticketService\.guardarRecepcionesTapizado\(this\.data\.id, cambios\)/);
  assert.match(recepcionHtml, /Guardar cambios/);
  assert.match(recepcionHtml, /Descartar selección/);
  assert.match(recepcionHtml, /motivosReversion\[aparato\.id\]/);
  assert.doesNotMatch(recepcionHtml, /Confirmar y registrar/);
});

test('refresca bandeja sólo cuando se guardaron recepciones', () => {
  const fn = tickets.slice(tickets.indexOf('  abrirRecepcionTapizado('), tickets.indexOf('  inicializarCategoriaTemp()'));
  assert.match(fn, /afterClosed\(\)\.subscribe\(\(seActualizo: boolean\)/);
  assert.match(fn, /if \(seActualizo === true\)/);
  assert.match(fn, /this\.refrescarTicketsPreservandoFiltros\(\)/);
  assert.match(recepcion, /this\.huboCambioRecepcion = true/);
});
