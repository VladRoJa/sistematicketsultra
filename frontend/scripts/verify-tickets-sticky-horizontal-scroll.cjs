'use strict';

// QA en aislamiento de los métodos TS originales. No requiere navegador ni DB.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');

const base = path.resolve(__dirname, '../src/app/pantalla-ver-tickets');
const source = fs.readFileSync(path.join(base, 'pantalla-ver-tickets.component.ts'), 'utf8');
const template = fs.readFileSync(path.join(base, 'pantalla-ver-tickets.component.html'), 'utf8');
const css = fs.readFileSync(path.join(base, 'pantalla-ver-tickets.component.css'), 'utf8');

function extract(name) {
  const match = source.match(new RegExp(
    '^  ' + name + '\\(\\): void \\{[\\s\\S]*?^  \\}', 'm',
  ));
  assert.ok(match, 'Método original faltante: ' + name);
  return match[0];
}

const code = [
  'class TicketsHorizontalScrollTest {',
  '  ticketsScrollContainer: any = null;',
  '  anchoContenidoScrollTickets = 0;',
  '  mostrarBarraHorizontalTickets = false;',
  '  changeDetectorRef = { detectChanges() {} };',
  extract('sincronizarTablaDesdeBarraTickets'),
  extract('sincronizarBarraDesdeTablaTickets'),
  '  ' + source.match(/private actualizarBarraHorizontalTickets\(\): void \{[\s\S]*?^  \}/m)?.[0],
  '}',
  'module.exports = { TicketsHorizontalScrollTest };',
].join('\n');
assert.ok(!code.includes('undefined'), 'Debe existir el método de medición');
const js = ts.transpileModule(code, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const mod = new Module('ticket-horizontal-scroll-qa', module);
mod.filename = 'ticket-horizontal-scroll-qa.js';
mod.paths = Module._nodeModulePaths(__dirname);
mod._compile(js, mod.filename);

const instance = new mod.exports.TicketsHorizontalScrollTest();
const table = { scrollWidth: 2486 };
const rail = { scrollLeft: 0, clientWidth: 1200 };
const viewport = {
  scrollLeft: 0,
  querySelector(selector) {
    return selector === '.tickets-table-rail' ? rail : table;
  },
};
instance.ticketsScrollContainer = viewport;
instance.actualizarBarraHorizontalTickets();
assert.equal(instance.mostrarBarraHorizontalTickets, true, 'Debe habilitar el riel si hay desborde');
assert.equal(instance.anchoContenidoScrollTickets, 2486, 'El riel usa ancho real de la tabla');

rail.scrollLeft = 600;
instance.sincronizarTablaDesdeBarraTickets();
assert.equal(viewport.scrollLeft, 600, 'Arrastrar la barra superior mueve la tabla');
viewport.scrollLeft = 1150;
instance.sincronizarBarraDesdeTablaTickets();
assert.equal(rail.scrollLeft, 1150, 'Arrastrar barra inferior mueve la superior');

rail.clientWidth = 2900;
instance.actualizarBarraHorizontalTickets();
assert.equal(instance.mostrarBarraHorizontalTickets, false,
  'El riel desaparece si la tabla cabe en el viewport');

assert.match(template, /#ticketsScrollContainer/, 'Tabla necesita referencia de contenedor');
assert.match(template, /\(scroll\)="sincronizarTablaDesdeBarraTickets\(\)"/,
  'El riel debe enviar los cambios a la tabla');
assert.match(template, /\(scroll\)="sincronizarBarraDesdeTablaTickets\(\)"/,
  'La tabla debe actualizar el riel');
assert.match(template, /\[style\.width\.px\]="anchoContenidoScrollTickets"/,
  'El spacer reproduce el ancho real de tabla');
assert.doesNotMatch(template, /\(wheel\)=/, 'La rueda vertical NO debe secuestrarse');
assert.match(css, /\.tickets-table-rail\s*\{[\s\S]*?position:\s*sticky;[\s\S]*?top:\s*0;/,
  'El riel debe permanecer visible al desplazarse verticalmente');
assert.match(css, /\.tickets-table-card\s*\{[\s\S]*?box-sizing:\s*border-box;/,
  'El contenedor no puede desbordar la ventana por sumar padding');
assert.match(css, /\.tickets-page\s*\{[\s\S]*?overflow-x:\s*clip;/,
  'La página no debe crear scroll horizontal independiente');

console.log('PASS: barra horizontal superior sincronizada y página sin overflow horizontal extra');
