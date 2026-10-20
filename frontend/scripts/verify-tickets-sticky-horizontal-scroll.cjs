'use strict';

// Regresión CSS / Angular de Tickets V1. Conserva el nombre de script en CI,
// pero comprueba que solo exista el scrollbar horizontal nativo inferior.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const base = path.resolve(__dirname, '../src/app/pantalla-ver-tickets');
const source = fs.readFileSync(path.join(base, 'pantalla-ver-tickets.component.ts'), 'utf8');
const template = fs.readFileSync(path.join(base, 'pantalla-ver-tickets.component.html'), 'utf8');
const css = fs.readFileSync(path.join(base, 'pantalla-ver-tickets.component.css'), 'utf8');
const layoutCss = fs.readFileSync(path.resolve(__dirname,
  '../src/app/layout/layout.component.css'), 'utf8');

function cssRule(selector) {
  const start = css.indexOf(selector + ' {');
  assert.ok(start >= 0, 'Regla CSS faltante: ' + selector);
  const open = css.indexOf('{', start);
  const end = css.indexOf('}', open);
  return css.slice(open + 1, end);
}

// Una sola barra horizontal, nativa y debajo de las filas.
assert.match(template, /class="tickets-table-card table-container"/,
  'El contenedor de la tabla debe conservar su scrollbar nativo');
assert.doesNotMatch(template, /tickets-table-rail|ticketsScrollContainer|sincronizarBarraDesdeTablaTickets/,
  'No debe existir el riel horizontal superior ni su listener');
assert.doesNotMatch(source, /ticketsScrollContainer|sincronizarTablaDesdeBarraTickets|sincronizarBarraDesdeTablaTickets|anchoContenidoScrollTickets|mostrarBarraHorizontalTickets|ticketsScrollResizeObserver/,
  'Eliminar código de sincronización y ResizeObserver que ya no se usa');
assert.doesNotMatch(css, /tickets-table-rail|tickets-horizontal-rail-height|::-webkit-scrollbar:horizontal/,
  'No debe ocultarse el scrollbar nativo inferior ni reservar altura al superior');
assert.match(cssRule('.tickets-table-card'), /overflow-x:\s*auto;/,
  'El scroll horizontal nativo debe seguir funcionando');
assert.match(cssRule('.tickets-table-card'), /overflow-y:\s*auto;/,
  'Conservar el scroll vertical dentro de la tabla');
assert.match(cssRule('.tabla-tickets th'), /position:\s*sticky;\s*top:\s*0;/,
  'Encabezado sticky al inicio de la tabla, sin espacio para el riel superior');
assert.doesNotMatch(template, /\(wheel\)=/,
  'La rueda vertical conserva su comportamiento nativo');

// Layout corregido en PR 977: no introducir una segunda barra en la ventana
// ni volver a ocultar paginación/exportación.
const hostRule = cssRule(':host');
const pageRule = cssRule('.tickets-page');
const tableRule = cssRule('.tickets-table-card');
const footerRule = cssRule('.pagination-export-container');
assert.match(hostRule, /height:\s*100%;/,
  'El componente toma la altura real asignada por el layout');
assert.match(hostRule, /overflow:\s*hidden;/,
  'La ventana no debe volver a desplazarse por el componente');
assert.match(pageRule, /display:\s*flex;[\s\S]*?flex-direction:\s*column;/,
  'La página debe tener un layout vertical flexible');
assert.match(pageRule, /height:\s*100%;[\s\S]*?overflow:\s*hidden;/,
  'El scroll global exterior permanece bloqueado');
assert.match(tableRule, /flex:\s*1 1 0;/,
  'La tabla toma solo el espacio disponible');
assert.match(footerRule, /flex:\s*0 0 auto;/,
  'La paginación se mantiene visible fuera de la tabla');
assert.match(layoutCss,
  /:host:has\(app-pantalla-ver-tickets\)\s*\{[^}]*display:\s*flex;[^}]*flex-direction:\s*column;[^}]*height:\s*100dvh;/,
  'El layout descuenta dinámicamente la altura real del header');
assert.match(layoutCss,
  /\.suite-main-content:has\(app-pantalla-ver-tickets\)\s*\{[^}]*flex:\s*1 1 0;[^}]*min-height:\s*0;[^}]*overflow:\s*hidden;/,
  'Ver Tickets no aumenta la altura total del documento');
assert.match(css, /@media \(max-width: 768px\), \(max-height: 560px\)/,
  'Las ventanas pequeñas deben conservar acceso a controles');

console.log('PASS: única barra horizontal inferior, scroll vertical interno y paginación visible');
