const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const app = path.join(__dirname, '..', 'src', 'app');
const read = file => fs.readFileSync(path.join(app, file), 'utf8');
const modal = read('pantalla-ver-tickets/modals/tapizado-recepcion-modal.component.ts');
const html = read('pantalla-ver-tickets/modals/tapizado-recepcion-modal.component.html');
const tickets = read('pantalla-ver-tickets/pantalla-ver-tickets.component.ts');
const service = read('services/ticket.service.ts');

test('seis aparatos visibles con checks y barra de progreso independiente del estado de ticket', () => {
  assert.match(modal, /get esTapizado\(\)/);
  assert.match(html, /\*ngFor="let aparato of aparatosTapizado"/);
  assert.match(html, /\[checked\]="estaMarcado\(aparato\)"/);
  assert.match(html, /\[value\]="avanceTapizado\.porcentaje"/);
  assert.match(html, /Entrega parcial/);
  assert.match(html, /Recibido por/);
  assert.match(html, /Pendiente de recepción/);
  assert.match(modal, /consultarRecepcionTapizado\(this\.data\.id\)/);
});

test('check sólo cambia borrador local; nunca dispara escritura ni historial', () => {
  const change = modal.slice(modal.indexOf('  cambiarRecepcion('), modal.indexOf('  private recalcularCambios('));
  assert.match(change, /this\.borradorRecepciones\.set\(aparato\.id, event\.checked\)/);
  assert.doesNotMatch(change, /registrarRecepcionTapizado|guardarRecepcionesTapizado/);
  assert.match(modal, /this\.dialogRef\.disableClose = this\.cambiosPendientes\.length > 0/);
  assert.match(html, /Descartar selección/);
  assert.match(html, /Guardar cambios/);
  assert.match(html, /\(click\)="guardarCambios\(\)"/);
  assert.doesNotMatch(html, /Confirmar y registrar|Volver a revisar|confirmarGuardadoVisible/);
  assert.doesNotMatch(modal, /prepararGuardado\(|confirmarGuardadoVisible/);
  assert.match(modal, /this\.ticketService\.guardarRecepcionesTapizado\(this\.data\.id, cambios\)/);
});

test('reversión requiere motivo y nadie registra con solo un clic', () => {
  assert.match(modal, /this\.motivosReversion\[cambio\.inventario_id\]/);
  assert.match(modal, /cambio\.recibido \|\|/);
  assert.match(html, /\[\(ngModel\)\]="motivosReversion\[aparato\.id\]"/);
  assert.match(html, /Guardar cambios/);
  assert.match(html, /\[disabled\]="!cambiosValidos \|\| guardandoRecepciones \|\| cargandoRecepcion"/);
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
