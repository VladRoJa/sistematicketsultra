const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const base = path.join(__dirname, '..', 'src', 'app', 'pantalla-crear-ticket',
  'formularios-crear-ticket', 'mantenimiento-aparatos');
const html = fs.readFileSync(path.join(base, 'mantenimiento-aparatos.component.html'), 'utf8');
const css = fs.readFileSync(path.join(base, 'mantenimiento-aparatos.component.css'), 'utf8');
const ts = fs.readFileSync(path.join(base, 'mantenimiento-aparatos.component.ts'), 'utf8');

test('tres filtros y descripción usan Material fill con etiqueta flotante de Suite Ultra', () => {
  for (const cls of ['tapizado-buscador', 'tapizado-categoria', 'tapizado-familia']) {
    const tag = html.match(new RegExp('<mat-form-field[^>]*class="' + cls + '"[^>]*>'));
    assert.ok(tag, 'campo ' + cls);
    assert.match(tag[0], /appearance="fill"/);
    assert.match(tag[0], /floatLabel="always"/);
  }
  assert.match(html, /appearance="fill" floatLabel="always" class="form-group-description"/);
  assert.doesNotMatch(html, /appearance="outline"/);
});

test('layout muestra fila de búsqueda y filtros cruzados sin insertar lógica en HTML', () => {
  assert.match(html, /class="tapizado-campos"/);
  assert.match(css, /grid-template-columns: minmax\(0, 2fr\) minmax\(0, 1fr\) minmax\(0, 1fr\)/);
  assert.match(html, /\(selectionChange\)="cambiarCategoriaTapizado\(\$event\.value\)"/);
  assert.match(html, /\(selectionChange\)="cambiarFamiliaTapizado\(\$event\.value\)"/);
  assert.match(html, /\[formControl\]="filtroTapizado"/);
  assert.match(css, /@media \(max-width: 500px\)/);
});

test('selección conserva 50 equipos, controles seguros y listado compacto', () => {
  assert.match(html, /\[disabled\]="aparatosSeleccionados\.length >= 50"/);
  assert.match(html, /\(change\)="alternarAparatoTapizado\(equipo, \$event\.checked\)"/);
  assert.match(html, /\(click\)="eliminarAparatoTapizado\(seleccionado\)"/);
  assert.match(html, /<button type="button"/);
  assert.match(css, /max-height: 245px/);
  assert.match(css, /min-height: 46px/);
  assert.match(ts, /private actualizarOpcionesTapizado\(\): void/);
  assert.doesNotMatch(ts, /get familiasDisponiblesTapizado\(/);
});
