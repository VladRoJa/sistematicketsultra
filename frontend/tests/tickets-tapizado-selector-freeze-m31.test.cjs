const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const typescript = require('typescript');

const sourcePath = path.join(
  __dirname, '..', 'src', 'app', 'pantalla-crear-ticket',
  'formularios-crear-ticket', 'mantenimiento-aparatos',
  'mantenimiento-aparatos.component.ts'
);

const source = fs.readFileSync(sourcePath, 'utf8');
const code = typescript.transpileModule(source, {
  compilerOptions: {
    target: typescript.ScriptTarget.ES2020,
    module: typescript.ModuleKind.CommonJS,
    experimentalDecorators: true,
  },
}).outputText;

class Control {
  constructor(value) {
    this.value = value;
    this.subscribers = [];
    this.valueChanges = {
      subscribe: fn => {
        this.subscribers.push(fn);
        return { unsubscribe: () => {
          this.subscribers = this.subscribers.filter(item => item !== fn);
        } };
      },
    };
  }
  setValue(value, opts = {}) {
    this.value = value;
    if (opts.emitEvent !== false) {
      this.subscribers.forEach(fn => fn(value));
    }
  }
  reset() { this.setValue(null); }
  setValidators() {}
  clearValidators() {}
  updateValueAndValidity() {}
}

const identityDecorator = () => target => target;
const propertyDecorator = () => () => undefined;
const noop = class {};
const stubRequire = name => {
  if (name === '@angular/core') {
    return { Component: identityDecorator, Input: propertyDecorator,
      Output: propertyDecorator, EventEmitter: class { emit() {} } };
  }
  if (name === '@angular/forms') {
    return { FormControl: Control, Validators: {
      required: noop,
      minLength: () => noop,
    }, ReactiveFormsModule: noop, FormsModule: noop };
  }
  if (name === 'src/environments/environment') {
    return { environment: { apiUrl: '/api' } };
  }
  if (name.includes('formularios.helper')) {
    return { limpiarCamposDependientes: () => {},
      emitirPayloadFormulario: () => {},
      DEPARTAMENTO_IDS: { mantenimiento: 1 } };
  }
  return new Proxy({}, { get: () => noop });
};

const moduleRef = { exports: {} };
vm.runInNewContext(code, {
  require: stubRequire,
  module: moduleRef,
  exports: moduleRef.exports,
  console, Set, Map, Number, String,
}, { filename: sourcePath });

const { MantenimientoAparatosComponent } = moduleRef.exports;

function crearFormulario() {
  const controles = new Map([
    ['tipo_trabajo', new Control(null)],
    ['aparatos_ids', new Control([])],
    ['aparato_id', new Control(null)],
    ['detalle', new Control(null)],
    ['subcategoria', new Control(null)],
  ]);
  return { get: campo => controles.get(campo) };
}

function crearComponente(cantidad = 2500) {
  const componente = new MantenimientoAparatosComponent(null, null, null, null);
  componente.parentForm = crearFormulario();
  componente.tapizadoHabilitado = true;
  componente.equipos = Array.from({ length: cantidad }, (_, i) => ({
    id: i + 1,
    nombre: i % 2 ? 'Caminadora' : 'Banco',
    codigo_interno: 'DEMO-' + String(i + 1).padStart(5, '0'),
    marca: 'Ultra',
    categoria: i % 2 ? 'Cardio' : 'Peso libre',
    familia_equipo_id: i % 2 ? 1 : 2,
    familia_equipo: { nombre: i % 2 ? 'Caminadora' : 'Bancos' },
  }));
  return componente;
}

test('activar Tapizado con miles de equipos conserva listas estables', () => {
  assert.doesNotMatch(source, /get familiasDisponiblesTapizado\s*\(/);
  assert.doesNotMatch(source, /get aparatosDisponiblesTapizado\s*\(/);
  assert.doesNotMatch(source, /get categoriasDisponiblesTapizado\s*\(/);

  const comp = crearComponente();
  comp.cambiarModoTapizado(true);
  assert.equal(comp.parentForm.get('tipo_trabajo').value, 'TAPIZADO');
  assert.equal(comp.aparatosDisponiblesTapizado.length, 25);
  assert.equal(comp.familiasDisponiblesTapizado.length, 2);

  const familias = comp.familiasDisponiblesTapizado;
  const aparatos = comp.aparatosDisponiblesTapizado;
  const categorias = comp.categoriasDisponiblesTapizado;
  for (let i = 0; i < 1000; i++) {
    assert.strictEqual(comp.familiasDisponiblesTapizado, familias);
    assert.strictEqual(comp.aparatosDisponiblesTapizado, aparatos);
    assert.strictEqual(comp.categoriasDisponiblesTapizado, categorias);
  }
});

test('filtros cruzados actualizan opciones sólo al cambiar estado', () => {
  const comp = crearComponente(300);
  comp.cambiarModoTapizado(true);
  comp.cambiarCategoriaTapizado('Cardio');
  assert.equal(comp.familiasDisponiblesTapizado.length, 1);
  assert.equal(comp.familiasDisponiblesTapizado[0].nombre, 'Caminadora');
  assert.ok(comp.aparatosDisponiblesTapizado.every(eq => eq.categoria === 'Cardio'));

  const opciones = comp.aparatosDisponiblesTapizado;
  assert.strictEqual(comp.aparatosDisponiblesTapizado, opciones);
  comp.cambiarCategoriaTapizado('Peso libre');
  assert.notStrictEqual(comp.aparatosDisponiblesTapizado, opciones);
  assert.equal(comp.filtroFamiliaTapizado.value, '');
  assert.ok(comp.aparatosDisponiblesTapizado.every(eq => eq.categoria === 'Peso libre'));
});

test('seleccionar y quitar equipo sincroniza principal, IDs y lista', () => {
  const comp = crearComponente(100);
  comp.cambiarModoTapizado(true);
  const primero = comp.aparatosDisponiblesTapizado[0];
  const segundo = comp.aparatosDisponiblesTapizado[1];
  comp.alternarAparatoTapizado(primero, true);
  comp.alternarAparatoTapizado(segundo, true);
  assert.equal(comp.parentForm.get('aparato_id').value, primero.id);
  assert.deepEqual(Array.from(comp.parentForm.get('aparatos_ids').value),
    [primero.id, segundo.id]);
  assert.equal(comp.aparatosDisponiblesTapizado.some(eq => eq.id === primero.id), false);

  comp.eliminarAparatoTapizado(primero);
  assert.equal(comp.parentForm.get('aparato_id').value, segundo.id);
  assert.deepEqual(Array.from(comp.parentForm.get('aparatos_ids').value), [segundo.id]);
  comp.cambiarModoTapizado(false);
  assert.equal(comp.parentForm.get('tipo_trabajo').value, null);
  assert.equal(comp.aparatosDisponiblesTapizado.length, 0);
});
