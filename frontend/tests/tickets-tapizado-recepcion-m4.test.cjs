const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const app = path.join(__dirname, '..', 'src', 'app');
const read = file => fs.readFileSync(path.join(app, file), 'utf8');
const modal = read('pantalla-ver-tickets/modals/historial-fechas-modal.component.ts');
const html = read('pantalla-ver-tickets/modals/historial-fechas-modal.component.html');
const tickets = read('pantalla-ver-tickets/pantalla-ver-tickets.component.ts');
const service = read('services/ticket.service.ts');

test('seis aparatos visibles con checks y barra de progreso independiente del estado de ticket', () => {
  assert.match(modal, /get esTapizado\(\)/);
  assert.match(html, /\*ngFor="let aparato of aparatosTapizado"/);
  assert.match(html, /\[checked\]="aparato\.recibido"/);
  assert.match(html, /\[value\]="avanceTapizado\.porcentaje"/);
  assert.match(html, /Entrega parcial/);
  assert.match(html, /Recibido por/);
  assert.match(html, /Pendiente de recepción/);
  assert.match(modal, /consultarRecepcionTapizado\(this\.data\.id\)/);
});

test('reversión requiere motivo, no cambia check antes de confirmar servidor', () => {
  assert.match(modal, /event\.source\.checked = aparato\.recibido/);
  assert.match(modal, /this\.motivoReversion\.trim\(\)\.length === 0/);
  assert.match(html, /Confirmar corrección/);
  assert.match(html, /\[\(ngModel\)\]="motivoReversion"/);
  assert.match(modal, /registrarRecepcionTapizado\(this\.data\.id, aparato\.id, recibido, motivo\)/);
});

test('se muestra progreso en una fila de bandeja y se refresca al cerrar modal', () => {
  assert.match(tickets, /Tapizado · \$\{recibidos\}\/\$\{total\} recibidos/);
  assert.match(tickets, /afterClosed\(\)\.subscribe\(\(seActualizo: boolean\)/);
  assert.match(tickets, /this\.refrescarTicketsPreservandoFiltros\(\)/);
});

test('API usa JWT con helpers de autenticación, no HTML con lógica de negocios', () => {
  assert.match(service, /consultarRecepcionTapizado/);
  assert.match(service, /registrarRecepcionTapizado/);
  assert.match(service, /this\.authJsonHeaders\(\)/);
  assert.match(html, /\(change\)="cambiarRecepcion\(aparato, \$event\)"/);
});
