'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const Module = require('node:module');
const path = require('node:path');
const ts = require('typescript');

const src = path.resolve(__dirname, '../src/app/shared/modal-submit-state.ts');
const compiled = ts.transpileModule(fs.readFileSync(src, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const mod = new Module(src, module);
mod.filename = src;
mod.paths = Module._nodeModulePaths(path.dirname(src));
mod._compile(compiled, src);
const { isModalSubmitDisabled } = mod.exports;

// Reasignar: motivo obligatorio, usuario interno requerido y cambio real.
assert.equal(isModalSubmitDisabled({
  requiredText: ['   '],
  requiredSelections: ['INTERNA', 68],
}), true, 'Motivo vacío bloquea confirmar');
assert.equal(isModalSubmitDisabled({
  requiredText: ['Corrección de sucursal'],
  requiredSelections: ['INTERNA', null],
}), true, 'Responsable interno sin seleccionar bloquea');
assert.equal(isModalSubmitDisabled({
  requiredText: ['Cambio a proveedor'],
  requiredSelections: ['EXTERNA'],
}), false, 'Proveedor con motivo habilita confirmar');
assert.equal(isModalSubmitDisabled({
  requiredText: ['Corrección de sucursal'],
  requiredSelections: ['INTERNA', 68],
}), false, 'Formulario interno completo habilita confirmar');
assert.equal(isModalSubmitDisabled({
  requiredText: ['Corrección de sucursal'],
  requiredSelections: ['INTERNA', 68],
  blocked: true,
}), true, 'Guardando o sin cambio bloquea');

// Fecha inicial: fecha/motivo obligatorios, además del responsable cuando aplica.
assert.equal(isModalSubmitDisabled({
  requiredText: ['Compromiso'],
  requiredSelections: [null, 'INTERNA', 68],
}), true, 'Sin fecha no se puede guardar');
assert.equal(isModalSubmitDisabled({
  requiredText: [''],
  requiredSelections: [new Date('2026-10-24'), 'INTERNA', 68],
}), true, 'Sin motivo no se puede guardar');
assert.equal(isModalSubmitDisabled({
  requiredText: ['Compromiso'],
  requiredSelections: [new Date('2026-10-24'), 'INTERNA', 68],
}), false, 'Fecha y responsable completos permiten guardar');

for (const rel of [
  '../src/app/shared/reasignar-responsable-modal/reasignar-responsable-modal.component.html',
  '../src/app/shared/asignar-fecha-modal/asignar-fecha-modal.component.html',
]) {
  const html = fs.readFileSync(path.resolve(__dirname, rel), 'utf8');
  assert.match(html, /ultra-modal-confirm/, rel + ' debe reutilizar la clase visual');
  assert.match(html, /\[disabled\]="guardarDeshabilitado"/, rel + ' debe usar disabled nativo');
}
const css = fs.readFileSync(path.resolve(__dirname, '../src/styles.scss'), 'utf8');
assert.match(css, /ultra-modal-confirm:disabled/, 'Debe existir estilo disabled visible');
assert.match(css, /ultra-modal-confirm:not\(:disabled\)/, 'Debe conservar naranja en enabled');
// Regresión Planner: el coordinador debe escoger responsable y guardar fecha + asignación
// mediante una sola transacción, no mediante la ruta de programación simple.
const plannerHtml = fs.readFileSync(path.resolve(__dirname,
  '../src/app/maintenance-planner/maintenance-planner-ticket-dialog.component.html'), 'utf8');
const plannerTs = fs.readFileSync(path.resolve(__dirname,
  '../src/app/maintenance-planner/maintenance-planner-ticket-dialog.component.ts'), 'utf8');
assert.match(plannerHtml, /\[permitirAsignacionMantenimiento\]="useCoordinatedAssignment"/,
  'Planner debe activar el selector del modal de mantenimiento');
assert.match(plannerHtml, /\[responsablesMantenimiento\]="responsablesMantenimiento"/,
  'Planner debe entregar el catálogo autorizado al modal compartido');
assert.match(plannerHtml, /\*ngIf="canShowInitialCommitmentForm"/,
  'Planner debe esperar el contexto de coordinación antes de mostrar el formulario');
assert.match(plannerTs, /getContext\(\)/,
  'Los responsables deben venir del endpoint de contexto autorizado');
assert.match(plannerTs, /this\.canRequestClosure && !this\.canCaptureDiagnosis/,
  'La coordinación no debe reemplazar el flujo técnico de diagnóstico');
assert.match(plannerTs, /this\.maintenanceCoordinationService\.coordinateTicket\(this\.ticket\.ticket_id/,
  'Planner debe guardar asignación y compromiso con el endpoint transaccional');
assert.match(plannerTs, /this\.plannerService\.assignInitialCommitmentFromForm\(/,
  'Planner debe conservar la programación anterior para otros perfiles');
assert.match(plannerTs, /!this\.coordinationReady/,
  'Un fallo del catálogo no debe habilitar un guardado sin asignación');
// Un SR puede consultar y terminar su trabajo, pero no fijar/mover compromisos.
// Las tres entradas visuales deben usar can_schedule del backend (no can_pm_execute).
const plannerBoardTs = fs.readFileSync(path.resolve(__dirname,
  '../src/app/maintenance-planner/maintenance-planner.component.ts'), 'utf8');
assert.match(plannerBoardTs, /canSchedule:\s*Boolean\(this\.board\?\.permissions\.can_schedule\)/,
  'El modal del Planner debe recibir can_schedule del backend');
assert.match(plannerTs, /get canAssignInitialCommitment\(\): boolean \{[\s\S]*?this\.canSchedule/,
  'La asignación inicial debe bloquearse sin can_schedule');
assert.match(plannerTs, /get canReprogramCommitment\(\): boolean \{[\s\S]*?this\.canSchedule/,
  'El botón Cambiar fecha debe bloquearse sin can_schedule');
assert.match(plannerBoardTs, /canDrag\(ticket:[\s\S]*?this\.board\?\.permissions\.can_schedule/,
  'Mover por drag & drop debe bloquearse sin can_schedule');
assert.match(plannerBoardTs, /if \(!this\.canDrag\(ticket\)\)/,
  'dropTicket debe volver a verificar el permiso antes de enviar el PUT');
const plannerBoardHtml = fs.readFileSync(path.resolve(__dirname,
  '../src/app/maintenance-planner/maintenance-planner.component.html'), 'utf8');
assert.match(plannerBoardHtml, /\[cdkDragDisabled\]="!canDrag\(ticket\)"/,
  'cdkDrag debe deshabilitarse sin canDrag');
// Recuperación de tickets legacy sin responsable: ejecutar los métodos reales
// aislados del componente, sin iniciar Angular ni tocar la base productiva.
const ticketsV1Ts = fs.readFileSync(path.resolve(__dirname,
  '../src/app/pantalla-ver-tickets/pantalla-ver-tickets.component.ts'), 'utf8');
const method = (name, returnType) => {
  const match = ticketsV1Ts.match(new RegExp(
    '^' + name + '\\(ticket: Ticket\\): ' + returnType + ' \\{[\\s\\S]*?^\\}', 'm',
  ));
  assert.ok(match, 'Debe existir el método de Tickets V1 ' + name);
  return match[0];
};
const ticketMethodsSource = [
  'class TestReassignment {',
  '  puedeCoordinarMantenimiento = false;',
  method('puedeCoordinarTicket', 'boolean'),
  method('puedeReasignarTicket', 'boolean'),
  method('etiquetaAccionResponsableTicket', 'string'),
  '}',
  'module.exports = { TestReassignment };',
].join('\n');
const ticketMethodsJs = ts.transpileModule(ticketMethodsSource, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const ticketMethodsModule = new Module('tickets-reassignment-qa', module);
ticketMethodsModule.filename = 'tickets-reassignment-qa.js';
ticketMethodsModule.paths = Module._nodeModulePaths(__dirname);
ticketMethodsModule._compile(ticketMethodsJs, 'tickets-reassignment-qa.js');
const assignment = new ticketMethodsModule.exports.TestReassignment();
const unassigned = {
  departamento_id: 1, estado: 'en progreso',
  asignado_a: null, tipo_atencion: null,
  fecha_solucion: '2026-08-28T07:00:00-07:00',
  estado_cierre: 'rechazado_por_gerente',
};
assignment.puedeCoordinarMantenimiento = true;
assert.equal(assignment.puedeReasignarTicket(unassigned), true,
  'Coordinación puede rescatar ticket antiguo en progreso sin responsable');
assert.equal(assignment.puedeReasignarTicket({ ...unassigned, estado: 'abierto' }), true,
  'Coordinación puede asignar ticket abierto sin responsable');
assert.equal(assignment.etiquetaAccionResponsableTicket(unassigned), 'Asignar responsable');
assert.equal(assignment.puedeReasignarTicket({ ...unassigned, asignado_a: 'SR_MANT' }), true,
  'La reasignación normal se conserva');
assert.equal(assignment.etiquetaAccionResponsableTicket({ ...unassigned, asignado_a: 'SR_MANT' }),
  'Reasignar responsable');
assert.equal(assignment.puedeReasignarTicket({
  ...unassigned, tipo_atencion: 'EXTERNA',
}), true, 'Proveedor externo sigue siendo reasignable');
for (const estado of ['por_validar', 'finalizado']) {
  assert.equal(assignment.puedeReasignarTicket({ ...unassigned, estado }), false,
    'No permitir asignación en estado ' + estado);
}
assert.equal(assignment.puedeReasignarTicket({ ...unassigned, departamento_id: 7 }), false,
  'Nunca extender coordinación a otro departamento');
assignment.puedeCoordinarMantenimiento = false;
assert.equal(assignment.puedeReasignarTicket(unassigned), false,
  'SR sin coordinación no puede asignar aunque el ticket esté huérfano');
const ticketTableHtml = fs.readFileSync(path.resolve(__dirname,
  '../src/app/pantalla-ver-tickets/pantalla-ver-tickets.component.html'), 'utf8');
assert.match(ticketTableHtml, /\*ngIf="puedeReasignarTicket\(ticket\)"/,
  'El icono debe respetar el permiso de coordinación');
assert.match(ticketTableHtml, /\[matTooltip\]="etiquetaAccionResponsableTicket\(ticket\)"/,
  'El botón debe indicar Asignar cuando el ticket nunca tuvo responsable');
console.log('PASS: tickets huérfanos de Mantenimiento asignables solo por coordinación');

console.log('PASS: Planner protege fecha inicial, botón Cambiar fecha y arrastre');

console.log('PASS: Planner exige asignación coordinada y conserva el flujo técnico');

console.log('PASS: habilitación reusable y estilo enabled/disabled en ambos modales');
