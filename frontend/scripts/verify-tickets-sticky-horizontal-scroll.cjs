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
// Contrato desktop: solo la tabla se desplaza, sin cortar paginación.
// Leer la regla específica evita aceptar reglas parecidas en otros módulos.
function cssRule(selector) {
  const start = css.indexOf(selector + ' {');
  assert.ok(start >= 0, 'Regla CSS faltante: ' + selector);
  const open = css.indexOf('{', start);
  const end = css.indexOf('}', open);
  return css.slice(open + 1, end);
}
const hostRule = cssRule(':host');
const pageRule = cssRule('.tickets-page');
const tableRule = cssRule('.tickets-table-card');
const footerRule = cssRule('.pagination-export-container');
assert.match(hostRule, /height:\s*calc\(100dvh - 72px\);/,
  'Ver Tickets ocupa el viewport menos los 72px de cabecera');
assert.match(hostRule, /overflow:\s*hidden;/,
  'Sin scroll duplicado en el host');
assert.match(pageRule, /display:\s*flex;[\s\S]*?flex-direction:\s*column;/,
  'Layout vertical de KPIs + tabla + paginación');
assert.match(pageRule, /height:\s*100%;[\s\S]*?overflow:\s*hidden;/,
  'Sin scroll horizontal/vertical exterior a la tabla');
assert.match(tableRule, /flex:\s*1 1 0;/,
  'Tabla utiliza el espacio restante de la ventana');
assert.match(tableRule, /overflow-y:\s*auto;/,
  'Scroll vertical conservado dentro de la tabla');
assert.match(tableRule, /min-height:\s*0;[\s\S]*?max-height:\s*none;/,
  'Eliminar tope fijo de altura de tabla');
assert.match(css, /\.tickets-table-card::-webkit-scrollbar:horizontal\s*\{\s*height:\s*0;/,
  'Ocultar únicamente scrollbar horizontal nativo inferior');
assert.match(footerRule, /flex:\s*0 0 auto;/,
  'Paginación siempre visible fuera del scroll de la tabla');
assert.match(css, /@media \(max-width: 768px\), \(max-height: 560px\)/,
  'Móvil o ventana reducida usa layout sin recortar controles');
assert.doesNotMatch(css, /html\s*,\s*body\s*\{[\s\S]*?overflow:\s*hidden;/,
  'No desactivar scroll global de la aplicación');
console.log('PASS: barra superior sticky, scroll vertical de tabla y viewport sin doble scroll');
