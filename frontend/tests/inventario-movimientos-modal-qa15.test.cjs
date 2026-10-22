'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const rx = require('rxjs');

const base = path.join(__dirname, '../src/app/inventario/movimientos');
const componentTs = fs.readFileSync(
  path.join(base, 'dialogo-registrar-movimiento/dialogo-registrar-movimiento.component.ts'), 'utf8'
);
const componentHtml = fs.readFileSync(
  path.join(base, 'dialogo-registrar-movimiento/dialogo-registrar-movimiento.component.html'), 'utf8'
);
const componentCss = fs.readFileSync(
  path.join(base, 'dialogo-registrar-movimiento/dialogo-registrar-movimiento.component.css'), 'utf8'
);
const parentTs = fs.readFileSync(path.join(base, 'movimientos.component.ts'), 'utf8');

const toasts = [];
const fakeRequire = name => {
  if (name === '@angular/core') return {
    Component: () => ctor => ctor,
    Inject: () => () => {},
  };
  if (name === '@angular/forms') return {
    Validators: {
      required: () => {},
      min: () => () => {},
      pattern: () => () => {},
    },
  };
  if (name === '@angular/common/http') return {
    HttpHeaders: class { set() { return this; } },
  };
  if (name === 'rxjs') return rx;
  if (name === 'src/environments/environment') {
    return { environment: { apiUrl: '/api' } };
  }
  if (name === 'src/app/utils/alertas') {
    return {
      mostrarAlertaToast: (...args) => toasts.push(args),
      mostrarAlertaStockInsuficiente: (...args) => toasts.push(args),
    };
  }
  return {};
};
const compiled = ts.transpileModule(componentTs, {
  compilerOptions: {
    target: ts.ScriptTarget.ES2020,
    module: ts.ModuleKind.CommonJS,
    experimentalDecorators: true,
  },
}).outputText;
const mod = { exports: {} };
new Function('require', 'module', 'exports', compiled)(fakeRequire, mod, mod.exports);
const { DialogoRegistrarMovimientoComponent } = mod.exports;

class Control {
  constructor(value) {
    this.value = value;
    this.valueChanges = new rx.Subject();
  }
  setValue(value, options) {
    this.value = value;
    if (options?.emitEvent !== false) this.valueChanges.next(value);
  }
}

class Group {
  constructor(controls) { this.controls = controls; }
  get(name) { return this.controls[name]; }
  get value() { return this.getRawValue(); }
  getRawValue() {
    const obj = {};
    for (const [key, value] of Object.entries(this.controls)) {
      obj[key] = value instanceof Control ? value.value :
        value instanceof ArrayGroup ? value.controls.map(c => c.getRawValue()) :
        value;
    }
    return obj;
  }
  get invalid() {
    if (this.get('sucursal_id')) {
      return !this.get('sucursal_id').value ||
        this.get('productos').controls.some(group => group.invalid);
    }
    return !this.get('inventario_id').value ||
      !this.get('inventarioControl').value ||
      !Number.isInteger(+this.get('cantidad').value) ||
      +this.get('cantidad').value < 1;
  }
  markAllAsTouched() {}
}
class ArrayGroup {
  controls = [];
  get length() { return this.controls.length; }
  push(group) { this.controls.push(group); }
  removeAt(i) { this.controls.splice(i, 1); }
  at(i) { return this.controls[i]; }
  getRawValue() { return this.controls.map(group => group.getRawValue()); }
}
class Builder {
  group(input) {
    return new Group(Object.fromEntries(
      Object.entries(input).map(([key, value]) => [
        key, value instanceof ArrayGroup ? value :
          new Control(Array.isArray(value) ? (
            typeof value[0] === 'object' && value[0] !== null && 'value' in value[0]
              ? value[0].value : value[0]
          ) : value),
      ]),
    ));
  }
  array() { return new ArrayGroup(); }
}

const catalog = ['11CCJW21','11CCJW22','11CCJW23','11CCJW24','11CCJW25']
  .map((codigo_interno, index) => ({
    id: 8000 + index, nombre: 'Caminadora', marca: 'Fitness',
    codigo_interno, tipo: 'aparatos', unidad_medida: 'pieza',
  }));
function crearVm() {
  const requests = [];
  const calls = [];
  const http = {
    post: (url, body) => {
      requests.push({ url, body });
      return { subscribe: ({ next }) => next() };
    },
  };
  const service = {
    listarSucursales: () => ({
      subscribe: ({ next }) => next([
        { sucursal_id: 12, sucursal: 'Santa Fe' },
        { sucursal_id: 99, sucursal: 'ULTRA DEMO' },
      ]),
    }),
  };
  global.localStorage = {
    getItem: key => key === 'user'
      ? JSON.stringify({ id: 91, rol: 'ADMINISTRADOR', sucursal_id: 99 })
      : 'jwt-example',
  };
  const vm = new DialogoRegistrarMovimientoComponent(
    new Builder(),
    { close: value => calls.push(value) },
    { inventariosDisponibles: catalog },
    service,
    http
  );
  vm.ngOnInit();
  return { vm, requests, calls };
}

test('administrador debe elegir sucursal, no se preselecciona ULTRA DEMO', () => {
  const { vm } = crearVm();
  assert.equal(vm.form.get('sucursal_id').value, null);
  assert.equal(vm.form.invalid, true);
  assert.equal(vm.nombreSucursalSeleccionada, 'Sucursal pendiente');
  vm.form.get('sucursal_id').setValue(12);
  assert.equal(vm.nombreSucursalSeleccionada, 'Santa Fe');
});

test('búsqueda por código distingue 5 caminadoras homónimas', async () => {
  const { vm } = crearVm();
  const result = await rx.firstValueFrom(vm.filteredInventarios(0).pipe(
    rx.map(() => vm.inventariosDisponibles.filter(x => x.codigo_interno === '11CCJW23')),
  ));
  assert.equal(result.length, 1);
  const grupo = vm.productosFormArray.at(0);
  grupo.get('inventarioControl').setValue('11CCJW23');
  const filtered = await rx.firstValueFrom(vm.filteredInventarios(0));
  assert.deepEqual(filtered.map(x => x.codigo_interno), ['11CCJW23']);
  assert.match(vm.displayInventario(filtered[0]), /11CCJW23 · Caminadora · Fitness/);
  vm.onInventarioSeleccionado(filtered[0], 0);
  assert.equal(grupo.get('inventario_id').value, 8002);
  assert.equal(vm.productosSeleccionados, 1);
});

test('teclear otro código invalida ID seleccionado para no guardar un artículo equivocado', () => {
  const { vm } = crearVm();
  const grupo = vm.productosFormArray.at(0);
  vm.onInventarioSeleccionado(catalog[0], 0);
  assert.equal(grupo.get('inventario_id').value, 8000);
  grupo.get('inventarioControl').setValue('11CCJW22');
  assert.equal(grupo.get('inventario_id').value, null);
  assert.equal(vm.form.invalid, true);
});

test('evita seleccionar el mismo código dos veces', () => {
  const { vm } = crearVm();
  vm.onInventarioSeleccionado(catalog[0], 0);
  vm.agregarProducto();
  vm.onInventarioSeleccionado(catalog[0], 1);
  assert.equal(vm.productosSeleccionados, 1);
  assert.equal(vm.productosFormArray.at(1).get('inventario_id').value, null);
  assert.ok(toasts.some(item => String(item[0]).includes('ya está seleccionado')));
});

test('cinco caminadoras → una sola entrada a Santa Fe sin alteración de cantidades', () => {
  const { vm, requests, calls } = crearVm();
  vm.form.get('sucursal_id').setValue(12);
  vm.form.get('observaciones').setValue('Alta inicial de caminadoras Santa Fe');
  for (let i = 0; i < 5; i++) {
    if (i > 0) vm.agregarProducto();
    vm.onInventarioSeleccionado(catalog[i], i);
  }
  assert.equal(vm.form.invalid, false);
  assert.equal(vm.productosSeleccionados, 5);
  vm.registrarMovimiento();
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, '/api/inventario/movimientos');
  assert.equal(requests[0].body.sucursal_id, 12);
  assert.equal(requests[0].body.tipo_movimiento, 'entrada');
  assert.equal(requests[0].body.inventarios.length, 5);
  assert.deepEqual(requests[0].body.inventarios.map(p => p.inventario_id), [8000,8001,8002,8003,8004]);
  assert.deepEqual(requests[0].body.inventarios.map(p => p.cantidad), [1,1,1,1,1]);
  assert.deepEqual(requests[0].body.inventarios.map(p => p.unidad_medida), ['pieza','pieza','pieza','pieza','pieza']);
  assert.deepEqual(calls, ['ok']);
});

test('filtro de tipo no borra equipo ya seleccionado', () => {
  const { vm } = crearVm();
  vm.onInventarioSeleccionado(catalog[0], 0);
  vm.cambiarTipoFiltro('otro');
  assert.equal(vm.productosSeleccionados, 1);
  vm.cambiarTipoFiltro('aparatos');
  assert.equal(vm.productosSeleccionados, 1);
});

test('el formulario es guiado y usa etiquetas externas; no conserva handler inexistente', () => {
  assert.match(componentHtml, /Datos del movimiento/);
  assert.match(componentHtml, /Equipos y cantidades/);
  assert.match(componentHtml, /formArrayName="productos"/);
  assert.match(componentHtml, /\[formGroupName\]="i"/);
  assert.match(componentHtml, /\(optionSelected\)="onInventarioSeleccionado/);
  assert.match(componentHtml, /inv\.codigo_interno/);
  assert.match(componentHtml, /Selecciona una opción|Elige una opción/);
  assert.match(componentHtml, /Registrar movimiento/);
  assert.doesNotMatch(componentHtml, /forzarObjetoEnFormArray/);
  assert.doesNotMatch(componentHtml, /style="/);
  assert.doesNotMatch(componentHtml, /<mat-card/);
  assert.match(componentCss, /movement-input:focus/);
  assert.match(parentTs, /maxHeight: '92vh'/);
});
