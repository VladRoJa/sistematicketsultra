const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '..', 'src', 'app');
const component = fs.readFileSync(
  path.join(root, 'pantalla-ver-tickets/pantalla-ver-tickets.component.ts'),
  'utf8',
);
const template = fs.readFileSync(
  path.join(root, 'pantalla-ver-tickets/pantalla-ver-tickets.component.html'),
  'utf8',
);
const helper = name => {
  const pos = component.indexOf(name + '(ticket: Ticket)');
  assert.notEqual(pos, -1, 'Missing method ' + name);
  return component.slice(pos, pos + 850);
};

test('BI Vlad requires the assigned operator, not a general edit permission', () => {
  assert.match(helper('puedeGestionarBiVlad'), /ticket\?\.asignado_a/);
  assert.match(helper('puedeGestionarBiVlad'), /this\.user\?\.username/);
  assert.match(helper('puedeGestionarBiVlad'), /responsable === usuario/);
});

test('requester sees no management actions but retains final conformity', () => {
  for (const method of [
    'puedeMostrarBotonEnProgreso',
    'puedeMostrarEditarFechaSolucion',
    'puedeMostrarBotonFinalizar',
    'puedeMostrarBotonCerrarDesdeCero',
  ]) {
    assert.match(helper(method), /this\.puedeGestionarBiVlad\(ticket\)/, method);
  }
  assert.match(helper('solicitarCierre'), /this\.puedeGestionarBiVlad\(ticket\)/);
  assert.match(helper('puedeMostrarBotonesValidarCierre'), /this\.esCreador\(ticket\)/);
  assert.match(template, /\*ngIf="puedeMostrarBotonFinalizar\(ticket\)"/);
});
