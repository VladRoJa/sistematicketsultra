const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const base = path.join(__dirname, '..', 'src', 'app', 'pantalla-ver-tickets');
const modal = fs.readFileSync(path.join(base, 'modals/tapizado-recepcion-modal.component.ts'), 'utf8');
const html = fs.readFileSync(path.join(base, 'modals/tapizado-recepcion-modal.component.html'), 'utf8');
const tickets = fs.readFileSync(path.join(base, 'pantalla-ver-tickets.component.ts'), 'utf8');

test('M4.4 usa estado actual de API, no solo estado de la fila', () => {
  assert.match(modal, /this\.estadoRecepcion = this\.data\.estado \|\| ''/);
  assert.match(modal, /this\.estadoRecepcion = result\.estado \|\| ''/);
  assert.match(modal, /result\.puede_editar === true && !this\.ticketAbierto/);
  assert.match(modal, /get ticketAbierto\(\): boolean/);
});

test('M4.4 muestra instrucción antes de recepción y bloquea checks abiertos', () => {
  assert.match(html, /\*ngIf="ticketAbierto && !cargandoRecepcion"/);
  assert.match(html, /Primero inicia el trabajo de tapizado/);
  assert.match(html, /utiliza la acción «En progreso»/);
  assert.match(html, /\[disabled\]="!puedeEditarRecepcion \|\| guardandoRecepciones \|\| cargandoRecepcion"/);
  assert.match(html, /!puedeEditarRecepcion && !cargandoRecepcion && !ticketAbierto/);
  assert.match(tickets, /cambiarEstadoEnProgreso\(ticket: Ticket\)/);
});

test('M4.4 mantiene selección temporal y guardado solo al pulsar Guardar cambios', () => {
  const change = modal.slice(modal.indexOf('  cambiarRecepcion('), modal.indexOf('  private recalcularCambios('));
  assert.match(change, /this\.borradorRecepciones\.set\(aparato\.id, event\.checked\)/);
  assert.doesNotMatch(change, /guardarRecepcionesTapizado/);
  assert.match(modal, /this\.ticketService\.guardarRecepcionesTapizado\(this\.data\.id, cambios\)/);
});
