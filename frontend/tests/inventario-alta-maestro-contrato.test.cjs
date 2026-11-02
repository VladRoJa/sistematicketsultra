const fs = require('fs');
const path = require('path');
const assert = require('node:assert/strict');

const root = path.join(__dirname, '..', 'src', 'app', 'inventario', 'dialogo-inventario');
const component = fs.readFileSync(path.join(root, 'dialogo-inventario.component.ts'), 'utf8');
const view = fs.readFileSync(path.join(root, 'dialogo-inventario.component.html'), 'utf8');
const backend = fs.readFileSync(
  path.join(__dirname, '..', '..', 'backend', 'app', 'routes', 'inventarios.py'), 'utf8',
);

// Campos que usa el selector de equipos de Tickets y la identidad del maestro.
for (const field of [
  'nombre', 'tipo', 'codigo_interno', 'no_equipo', 'marca',
  'categoria_inventario_id', 'familia_equipo_id', 'grupo_muscular',
  'subcategoria', 'unidad', 'proveedor', 'unidad_compra', 'factor_compra',
]) {
  assert.match(view, new RegExp('formControlName="' + field + '"'),
    'El campo ' + field + ' debe existir visualmente');
}
assert.match(view, /formControlName="categoria_inventario_id"/);
assert.match(view, /\[value\]="c\.id"/, 'La categoría debe seleccionarse por ID oficial.');
assert.doesNotMatch(view, /categoriaEsNueva\(\)|usarCategoriaNuevaDesdeFiltro/,
  'No permitir categorías fantasma creadas solo en memoria.');
assert.match(component, /categoriaOficialSeleccionada/);
assert.match(component, /familiaCtrl\?\.setValidators\(\[Validators\.required\]\)/);
assert.doesNotMatch(component, /gmCtrl\?\.setValidators\(\[Validators\.required\]\)/,
  'Grupo muscular no es obligatorio en todos los aparatos.');
assert.match(component, /categoria_inventario_id:\s*categoriaOficial\?\.id/);
assert.match(component, /if \(this\.guardando\) return;/);
assert.match(backend, /categoria_inventario_id=\(categoria_oficial\.id/);
assert.match(backend, /unidad_compra=normalizar_campo\(data\.get\('unidad_compra'\)\)/);
assert.match(backend, /factor_compra=factor_compra/);
assert.match(view, /La asignación[\s\S]*?a sucursales y sus existencias/);
assert.doesNotMatch(view, /formControlName="stock_actual"/,
  'Alta de catálogo no modifica existencias.');

console.log('inventory master ticket-ready form contract: PASS');
