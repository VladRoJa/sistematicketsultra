const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const app = path.join(__dirname, '..', 'src', 'app');
const read = rel => fs.readFileSync(path.join(app, rel), 'utf8');

const tickets = read('pantalla-ver-tickets/pantalla-ver-tickets.component.ts');
const ticketsHtml = read('pantalla-ver-tickets/pantalla-ver-tickets.component.html');
const planner = read('maintenance-planner/maintenance-planner-ticket-dialog.component.ts');
const plannerHtml = read('maintenance-planner/maintenance-planner-ticket-dialog.component.html');
const plannerDto = read('maintenance-planner/maintenance-planner.service.ts');

const ticket = (recibidos, total = 6, tipo = 'TAPIZADO') => ({
  tipo_trabajo: tipo,
  estado: 'en progreso',
  avance_tapizado: { total, recibidos, pendientes: total - recibidos, completo: total > 0 && recibidos === total },
});

function extractMethod(src, name, nextMarker) {
  const start = src.indexOf(name);
  const end = src.indexOf(nextMarker, start);
  assert.ok(start >= 0 && end > start, 'Método no encontrado: ' + name);
  return src.slice(start, end).trim().replaceAll('ticket: Ticket', 'ticket').replaceAll(': boolean', '');
}

test('M4.5 5/6 bloquea, 6/6 habilita, 0/0 y dato ausente bloquean', () => {
  const method = extractMethod(tickets, 'tapizadoListoParaCierre(ticket: Ticket)', '\n\nmensajeTapizadoPendiente');
  const policy = new Function('return ({ ' + method + ' }).tapizadoListoParaCierre')();
  assert.equal(policy(ticket(5)), false);
  assert.equal(policy(ticket(6)), true);
  assert.equal(policy(ticket(0, 0)), false);
  assert.equal(policy({ tipo_trabajo: 'TAPIZADO' }), false);
  assert.equal(policy(ticket(0, 0, null)), true, 'Ticket normal no cambia');
  assert.equal(policy(ticket(0, 0, 'NORMAL')), true);
  assert.equal(policy(ticket(5)), false, 'Revertir de 6/6 a 5/6 revoca cierre');
});

test('M4.5 aplica misma regla a las tres acciones de Tickets, y protege apertura del modal', () => {
  assert.match(tickets, /puedeSolicitarCierreMantenimiento\(ticket: Ticket\): boolean \{[^}]*tapizadoListoParaCierre\(ticket\)/s);
  assert.match(tickets, /puedeMostrarBotonCerrarDesdeCero\(ticket: Ticket\): boolean \{[^}]*tapizadoListoParaCierre\(ticket\)/s);
  assert.match(tickets, /puedeMostrarBotonFinalizar\(ticket: Ticket\): boolean \{[^}]*tapizadoListoParaCierre\(ticket\)/s);
  assert.match(tickets, /async solicitarCierre\(ticket: Ticket\) \{[\s\S]*?tapizadoListoParaCierre\(ticket\)/);
  assert.match(ticketsHtml, /\*ngIf="puedeMostrarAvisoTapizadoPendiente\(ticket\)"/);
  assert.match(ticketsHtml, /resumenAvisoCierreTapizado\(ticket\)/);
  assert.match(ticketsHtml, /detalleAvisoCierreTapizado\(ticket\)/);
});

test('M4.6 muestra aviso en dos renglones sin alterar la regla de cierre', () => {
  assert.match(ticketsHtml, /class="ticket-tapizado-cierre-pendiente__texto"/);
  assert.match(ticketsHtml, /<span>\{\{ resumenAvisoCierreTapizado\(ticket\) \}\}<\/span>/);
  assert.match(ticketsHtml, /<span>\{\{ detalleAvisoCierreTapizado\(ticket\) \}\}<\/span>/);
  assert.match(tickets, /resumenAvisoCierreTapizado\(ticket: Ticket\): string/);
  assert.match(tickets, /detalleAvisoCierreTapizado\(ticket: Ticket\): string/);
  assert.match(ticketsHtml, /\[matTooltip\]="mensajeTapizadoPendiente\(ticket\)"/);
  const css = read('pantalla-ver-tickets/pantalla-ver-tickets.component.css');
  assert.match(css, /\.ticket-tapizado-cierre-pendiente__texto \{[\s\S]*?flex-direction: column/);
});

test('M4.5 Planner recibe avance del backend, oculta cierre y explica motivo', () => {
  assert.match(plannerDto, /avance_tapizado: \{/);
  assert.match(plannerDto, /tipo_trabajo: string \| null/);
  assert.match(planner, /get tapizadoBloqueaCierre\(\): boolean/);
  assert.match(planner, /!avance \|\| avance\.total < 1 \|\| avance\.completo !== true/);
  assert.match(planner, /get canFinalizeTicket\(\): boolean \{[\s\S]*?!this\.tapizadoBloqueaCierre/);
  assert.match(plannerHtml, /\*ngIf="mostrarAvisoTapizadoIncompleto"/);
  assert.match(plannerHtml, /\*ngIf="canFinalizeTicket"/);
});
