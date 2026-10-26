const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const dir = path.join(__dirname, '..', 'src', 'app', 'pantalla-ver-tickets', 'modals');
const ts = fs.readFileSync(path.join(dir, 'tapizado-recepcion-modal.component.ts'), 'utf8');
const html = fs.readFileSync(path.join(dir, 'tapizado-recepcion-modal.component.html'), 'utf8');
const scss = fs.readFileSync(path.join(dir, 'tapizado-recepcion-modal.component.scss'), 'utf8');

test('M4.2 elimina segunda confirmación; Guardar cambios es acción definitiva', () => {
  assert.match(html, /\(click\)="guardarCambios\(\)"/);
  assert.match(ts, /guardarCambios\(\): void/);
  assert.doesNotMatch(ts, /confirmarGuardadoVisible|prepararGuardado\(|cancelarConfirmacion\(|confirmarGuardado\(/);
  assert.doesNotMatch(html, /¿Confirmar los cambios|Confirmar y registrar|Volver a revisar/);
  assert.equal((html.match(/\(click\)="guardarCambios\(\)"/g) || []).length, 1);
});

test('M4.2 respeta borrador local y controla errores de guardado', () => {
  const change = ts.slice(ts.indexOf('  cambiarRecepcion('), ts.indexOf('  private recalcularCambios('));
  assert.match(change, /borradorRecepciones\.set\(aparato\.id, event\.checked\)/);
  assert.doesNotMatch(change, /guardarRecepcionesTapizado|registrarRecepcionTapizado/);
  const save = ts.slice(ts.indexOf('  guardarCambios('), ts.indexOf('  cancelarDescarte('));
  assert.match(save, /if \(!this\.puedeEditarRecepcion/);
  assert.match(save, /this\.guardandoRecepciones = true/);
  assert.match(save, /this\.ticketService\.guardarRecepcionesTapizado\(this\.data\.id, cambios\)/);
  assert.match(save, /this\.actualizarDatosRecepcion\(result\)/);
  assert.match(save, /this\.errorRecepcion = err\?\.error\?\.mensaje/);
  assert.match(html, /Descartar selección/);
  assert.match(ts, /confirmarDescarteVisible = true/);
});

test('M4.2 aumenta visibilidad de Guardar con botón primario y barra sticky', () => {
  assert.match(html, /class="tapizado-avance__barra-acciones"/);
  assert.match(html, /class="tapizado-avance__btn-guardar"/);
  assert.match(html, /class="tapizado-avance__btn-descartar"/);
  assert.match(html, /\[disabled\]="!cambiosValidos \|\| guardandoRecepciones \|\| cargandoRecepcion"/);
  assert.match(scss, /\.tapizado-avance__barra-acciones\s*\{[^}]*position:\s*sticky/s);
  assert.match(scss, /\.tapizado-avance__btn-guardar\s*\{[^}]*background:\s*var\(--ultra-orange/s);
  assert.match(scss, /:focus-visible/);
  assert.doesNotMatch(scss, /\.tapizado-avance__confirmacion/);
});
