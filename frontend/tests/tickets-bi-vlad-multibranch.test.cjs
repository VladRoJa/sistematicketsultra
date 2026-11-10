const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');

const app = path.join(__dirname, '..', 'src', 'app');
const read = p => fs.readFileSync(path.join(app, p), 'utf8');
const createTs = read('pantalla-crear-ticket/crear-ticket-refactor.component.ts');
const createHtml = read('pantalla-crear-ticket/crear-ticket-refactor.component.html');
const listTs = read('pantalla-ver-tickets/pantalla-ver-tickets.component.ts');
const listHtml = read('pantalla-ver-tickets/pantalla-ver-tickets.component.html');
const helperFile = path.join(app, 'utils/ticket-utils.ts');

const compiled = ts.transpileModule(fs.readFileSync(helperFile, 'utf8'), {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
  },
}).outputText;
const mod = new Module(helperFile, module);
mod.filename = helperFile;
mod.paths = Module._nodeModulePaths(path.dirname(helperFile));
mod._compile(compiled, helperFile);

const { nombresSucursalesDeTicket, filtrarTicketsConFiltros } = mod.exports;
const scoped = {
  id: 3401, departamento: 'BI Vlad', sucursal: 'Corporativo',
  sucursales_alcance: [
    { sucursal_id: 4, sucursal: 'Villas del Rey' },
    { sucursal_id: 5, sucursal: 'Villa Verde' },
    { sucursal_id: 21, sucursal: 'Ixtapaluca' },
  ],
};
const normal = { id: 3400, departamento: 'Mantenimiento', sucursal: 'Villa Verde' };

test('depto se selecciona antes de la sucursal y lista BI Vlad es exclusiva', () => {
  assert.ok(createHtml.indexOf('let nivel of niveles') < createHtml.indexOf('Sucursal destino'));
  assert.match(createHtml, /nivel\.nivel === 1/);
  assert.match(createHtml, /\*ngIf="esAdmin\(\) && !esBiVladSeleccionado"/);
  assert.match(createHtml, /\*ngIf="esBiVladSeleccionado"/);
  assert.match(createHtml, /seleccionarTodasSucursalesBiVlad/);
  assert.match(createTs, /getSucursalesBiVladDisponibles\(\)/);
  assert.match(createTs, /body\.sucursales_alcance_ids =/);
  assert.match(createTs, /Selecciona al menos una sucursal para BI Vlad/);
});

test('un ticket, múltiples sucursales visibles y sin duplicados en filtro', () => {
  assert.deepEqual(nombresSucursalesDeTicket(scoped), [
    'Villas del Rey', 'Villa Verde', 'Ixtapaluca',
  ]);
  assert.deepEqual(nombresSucursalesDeTicket(normal), ['Villa Verde']);
  const tickets = [scoped, normal];
  assert.deepEqual(
    filtrarTicketsConFiltros(tickets, { sucursal: ['Ixtapaluca'] }).map(t => t.id),
    [3401],
  );
  assert.deepEqual(
    filtrarTicketsConFiltros(tickets, { sucursal: ['Villa Verde'] }).map(t => t.id),
    [3401, 3400],
  );
  assert.deepEqual(
    filtrarTicketsConFiltros(tickets, { sucursal: ['Villa Verde', 'Villas del Rey'] }).map(t => t.id),
    [3401, 3400],
  );
});

test('Ver tickets muestra alcance compacto y mantiene sucursal legacy', () => {
  assert.match(listHtml, /ticket\.sucursales_alcance\?\.length/);
  assert.match(listHtml, /matMenuTriggerFor]="menuSucursalesBI"/);
  assert.match(listHtml, /sucursalTicketTradicional/);
  assert.match(listTs, /nombresSucursalesDeTicket\(t\)/);
});
