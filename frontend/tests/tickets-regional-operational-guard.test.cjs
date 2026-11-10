const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const component = fs.readFileSync(
  path.join(__dirname, '..', 'src', 'app', 'pantalla-ver-tickets',
            'pantalla-ver-tickets.component.ts'), 'utf8',
);
const template = fs.readFileSync(
  path.join(__dirname, '..', 'src', 'app', 'pantalla-ver-tickets',
            'pantalla-ver-tickets.component.html'), 'utf8',
);

function methodBody(name) {
  const start = component.indexOf(name);
  assert.ok(start >= 0, 'Missing: ' + name);
  return component.slice(start, start + 740);
}

test('Regional has read-only access without changing shared AuthService', () => {
  assert.match(methodBody('get puedeEditarTickets(): boolean'), /getUserMaintenanceRole\(\) !== 'GERENTE_REGIONAL'/);
  assert.match(methodBody('puedeMostrarBotonEnProgreso(ticket: Ticket)'), /getUserMaintenanceRole\(\) === 'GERENTE_REGIONAL'/);
  assert.match(methodBody('puedeMostrarEditarFechaSolucion(ticket: Ticket)'), /getUserMaintenanceRole\(\) === 'GERENTE_REGIONAL'/);
});

test('Direct UI handlers cannot open operational dialogs if action is forbidden', () => {
  assert.match(methodBody('cambiarEstadoEnProgreso(ticket: Ticket)'), /if \(!this\.puedeMostrarBotonEnProgreso\(ticket\)\) return;/);
  assert.match(methodBody('abrirEditarFechaSolucion(ticket: Ticket)'), /if \(!this\.puedeMostrarEditarFechaSolucion\(ticket\)\) return;/);
});

test('Existing creator conformity remains separate from state transition', () => {
  assert.match(template, /\*ngIf="puedeMostrarBotonEnProgreso\(ticket\)"/);
  assert.match(methodBody('puedeMostrarBotonesValidarCierre(ticket: Ticket)'), /esCreador\(ticket\)/);
});
