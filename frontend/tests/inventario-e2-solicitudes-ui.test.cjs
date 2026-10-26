'use strict';

// QA E2: contrato frontend con API sin writes V1; probar estado TS aislado.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const ts = require('typescript');
const { webcrypto } = require('node:crypto');
globalThis.crypto ||= webcrypto;

const base = path.join(__dirname, '../src/app/inventario/solicitudes');
const src = fs.readFileSync(path.join(base, 'solicitudes-correccion.component.ts'), 'utf8');
const html = fs.readFileSync(path.join(base, 'solicitudes-correccion.component.html'), 'utf8');
const css = fs.readFileSync(path.join(base, 'solicitudes-correccion.component.css'), 'utf8');
const parentDir = path.join(__dirname, '../src/app/inventario/existencias');
const parent = fs.readFileSync(path.join(parentDir, 'existencias.component.ts'), 'utf8');
const parentHtml = fs.readFileSync(path.join(parentDir, 'existencias.component.html'), 'utf8');
const service = fs.readFileSync(path.join(__dirname, '../src/app/services/inventario.service.ts'), 'utf8');

function createComponent() {
  const js = ts.transpileModule(src, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2020,
      module: ts.ModuleKind.CommonJS,
      experimentalDecorators: true,
    },
  }).outputText;
  const module = { exports: {} };
  const decorator = () => () => {};
  const angular = {
    Component: () => klass => klass,
    Input: decorator,
    Output: decorator,
    EventEmitter: class {
      constructor() { this.values = []; }
      emit(value) { this.values.push(value); }
    },
  };
  new Function('require', 'module', 'exports', js)(
    name => name === '@angular/core' ? angular : {},
    module,
    module.exports,
  );
  return module.exports.SolicitudesCorreccionComponent;
}

function observable(valueOrError, fail = false) {
  return {
    subscribe(observer) {
      if (fail) observer.error(valueOrError);
      else observer.next(valueOrError);
      return { unsubscribe() {} };
    },
  };
}

function fixture({
  referencia = {
    inventario_id: 502, sucursal_id: 7, sucursal_nombre: 'Villas del Rey',
    nombre: 'Caminadora', codigo_interno: '07CA001', tipo: 'Aparatos',
    marca: 'Star Trac', unidad_medida: 'Pieza', stock: 3,
    categoria_inventario_id: 1, familia_equipo_id: 1,
  },
  vistaInicial = 'solicitud',
  guardarError = null,
} = {}) {
  const calls = { posts: [], gets: [], details: [] };
  const api = {
    crearSolicitudCorreccion(data) {
      calls.posts.push(data);
      return guardarError
        ? observable(guardarError, true)
        : observable({
          solicitud: { id: 25, estado: 'PENDING', ...data },
          replayed: false, possible_pending_duplicate: false,
        });
    },
    listarSolicitudesCorreccion(params) {
      calls.gets.push(params);
      return observable({
        items: [{ id: 7, tipo: 'NOT_LOCATED', estado: 'PENDING',
          sucursal_id: 7, inventario_id: 502, creado_en_utc: '2026-10-23T20:00:00Z' }],
        total: 1, page: params.page, per_page: params.per_page,
      });
    },
    obtenerSolicitudCorreccion(id) {
      calls.details.push(id);
      return observable({
        solicitud: { id, tipo: 'NOT_LOCATED', estado: 'PENDING',
          sucursal_id: 7, inventario_id: 502 },
      });
    },
  };
  const vm = new (createComponent())(api);
  vm.referencia = referencia;
  vm.visible = true;
  vm.vistaInicial = vistaInicial;
  vm.sucursales = [{ sucursal_id: 7, sucursal: 'Villas del Rey' },
    { sucursal_id: 8, sucursal: 'Villa Verde' }];
  vm.sucursalPreferida = 7;
  vm.ngOnChanges({ visible: {} });
  return { vm, calls };
}

test('E2: estructura Angular separada y botones disponibles sin editar inventario', () => {
  assert.match(src, /standalone: true/);
  assert.match(src, /templateUrl: '\.\/solicitudes-correccion.component.html'/);
  assert.match(src, /styleUrls: \['\.\/solicitudes-correccion.component.css'\]/);
  assert.match(parentHtml, /Solicitar corrección de/);
  assert.match(parentHtml, /Reportar sin registro/);
  assert.match(parentHtml, /Seguimiento de solicitudes/);
  assert.match(parentHtml, /\[referencia\]="referenciaSolicitud"/);
  assert.match(parent, /cerrarSolicitudes\(\)/);
  assert.match(css, /\.solicitud-panel\s*\{/);
  assert.match(html, /no se modifica/);
  assert.match(html, /class="solicitud-bandeja__autorizar" disabled/);
  assert.match(html, /class="solicitud-bandeja__rechazar" disabled/);
  assert.doesNotMatch(html, /\(click\)="aprobar/);
  assert.doesNotMatch(html, /\(click\)="rechazar/);
  assert.match(service, /crearSolicitudCorreccion/);
  assert.match(service, /listarSolicitudesCorreccion/);
  assert.match(service, /obtenerSolicitudCorreccion/);
  assert.doesNotMatch(src, /\.registrarMovimiento\(|\.editarInventario\(|\.corregirCodigoInterno\(/);
});

test('E2: cantidad física con baseline oficial crea solo propuesta PENDING', () => {
  const { vm, calls } = fixture();
  vm.cantidadFisica = 2;
  vm.motivo = 'Faltó una caminadora en conteo físico';
  assert.equal(vm.puedeEnviar, true);
  vm.enviar();
  assert.equal(calls.posts.length, 1);
  const payload = calls.posts[0];
  assert.equal(payload.tipo, 'QUANTITY_DIFFERENCE');
  assert.equal(payload.sucursal_id, 7);
  assert.equal(payload.inventario_id, 502);
  assert.deepEqual(payload.valor_original, { stock: 3 });
  assert.deepEqual(payload.valor_propuesto, { cantidad_fisica: 2 });
  assert.match(payload.idempotency_key, /^[0-9a-f-]{36}$/);
  assert.equal('estado' in payload, false);
  assert.equal('creado_por_usuario_id' in payload, false);
  assert.equal('baseline_canonico' in payload, false);
  assert.equal(vm.guardado.estado, 'PENDING');
  assert.equal(vm.puedeEnviar, false);
});

test('E2: un reintento de red conserva UUID; cambiar formulario lo invalida', () => {
  const { vm, calls } = fixture({ guardarError: { status: 503 } });
  vm.motivo = 'Discrepancia física validada en inventario';
  vm.cantidadFisica = 1;
  vm.enviar();
  const old = calls.posts[0].idempotency_key;
  assert.match(vm.errorGuardar, /reintentar/);
  vm.enviar();
  assert.equal(calls.posts[1].idempotency_key, old);
  vm.cantidadFisica = 2;
  vm.modificado();
  vm.enviar();
  assert.notEqual(calls.posts[2].idempotency_key, old);
});

test('E2: master muestra valor oficial y propone sin alterarlo', () => {
  const { vm, calls } = fixture();
  vm.seleccionarTipo('MASTER_FIELD');
  vm.campo = 'codigo_interno';
  vm.nuevoTexto = '07CA002';
  vm.motivo = 'Código físico revisado y diferente al oficial';
  assert.equal(vm.valorOficial, '07CA001');
  vm.enviar();
  assert.equal(calls.posts[0].campo, 'codigo_interno');
  assert.equal(calls.posts[0].valor_original, '07CA001');
  assert.equal(calls.posts[0].valor_propuesto, '07CA002');
});

test('E2: hallazgo no registrado no inventa inventario_id', () => {
  const { vm, calls } = fixture({ referencia: null, vistaInicial: 'hallazgo' });
  assert.equal(vm.tipo, 'UNREGISTERED_FIND');
  vm.sucursalId = 8;
  vm.hallazgoNombre = 'Remo sin etiqueta';
  vm.hallazgoTipo = 'APARATOS';
  vm.motivo = 'Hallado en almacén sin registro en sistema';
  vm.enviar();
  assert.equal(calls.posts[0].tipo, 'UNREGISTERED_FIND');
  assert.equal('inventario_id' in calls.posts[0], false);
  assert.deepEqual(calls.posts[0].hallazgo_provisional,
    { nombre: 'Remo sin etiqueta', tipo: 'APARATOS' });
});

test('E2: impide enviar formulario incompleto, stock igual y fecha no válida sin servidor', () => {
  const { vm, calls } = fixture();
  vm.motivo = 'Ok';
  vm.cantidadFisica = 3;
  assert.equal(vm.puedeEnviar, false);
  vm.enviar();
  assert.equal(calls.posts.length, 0);
  vm.motivo = 'Motivo del conteo físico revisado';
  assert.equal(vm.puedeEnviar, false);
  vm.cantidadFisica = 2;
  assert.equal(vm.puedeEnviar, true);
  vm.enviar();
  assert.equal(calls.posts.length, 1);
});

test('E2: seguimiento filtra en backend por alcance, estado y tipo', () => {
  const { vm, calls } = fixture({ referencia: null, vistaInicial: 'seguimiento' });
  assert.equal(vm.modo, 'seguimiento');
  assert.equal(calls.gets[0].sucursal_id, 7);
  vm.filtroSucursal = 'todas';
  vm.filtroEstado = 'PENDING';
  vm.filtroTipo = 'NOT_LOCATED';
  vm.cambiarFiltros();
  assert.equal(calls.gets[1].sucursal_id, undefined);
  assert.equal(calls.gets[1].estado, 'PENDING');
  assert.equal(calls.gets[1].tipo, 'NOT_LOCATED');
  assert.equal(calls.gets[1].per_page, 10);
  vm.consultarDetalle(7);
  assert.deepEqual(calls.details, [7]);
  assert.equal(vm.detalle.id, 7);
});

test('E2: mensaje de conflicto no finge guardado', () => {
  const { vm } = fixture({ guardarError: { status: 409 } });
  vm.cantidadFisica = 1;
  vm.motivo = 'El inventario físico presenta discrepancia';
  vm.enviar();
  assert.equal(vm.guardado, null);
  assert.match(vm.errorGuardar, /datos oficiales cambiaron/);
});

test('E2 UX: modal centrado y compacto conserva scroll accesible en pantallas bajas', () => {
  assert.match(css, /\.solicitud-overlay\s*\{[^}]*justify-content:\s*center;/s);
  assert.match(css, /\.solicitud-overlay\s*\{[^}]*align-items:\s*center;/s);
  assert.match(css, /\.solicitud-panel\s*\{[^}]*width:\s*min\(920px,\s*100%\);/s);
  assert.match(css, /\.solicitud-panel\s*\{[^}]*max-height:\s*min\(88dvh,\s*820px\);/s);
  assert.match(css, /\.solicitud-grid--hallazgo\s*\{[^}]*repeat\(3,/s);
  assert.match(css, /\.solicitud-grid--details\s*\{[^}]*grid-template-columns:/s);
  assert.match(css, /\.solicitud-content\s*\{[^}]*overflow-y:\s*auto;/s);
  assert.match(css, /@media \(max-width:\s*640px\)/);
  assert.match(css, /@media \(max-height:\s*700px\)/);
  assert.match(html, /class="solicitud-grid solicitud-grid--hallazgo"/);
  assert.match(html, /class="solicitud-grid solicitud-grid--details"/);
  // En un hallazgo ya seleccionado no repetir el botón que activa ese mismo tipo.
  assert.match(html, /\*ngIf="!referencia && !esHallazgo" class="solicitud-kind-switch"/);
  assert.match(html, /\(click\)="enviar\(\)"/);
  assert.match(html, /\(click\)="abrirSeguimiento\(\)"/);
});

test('E2 UX: bandeja con selección por página, detalles por fila y decisiones E3 bloqueadas', () => {
  assert.match(html, /class="solicitud-grid solicitud-filtros"/);
  assert.match(html, /class="solicitud-bandeja__barra"/);
  assert.match(html, /\[checked\]="todosSeleccionadosPagina"/);
  assert.match(html, /\[indeterminate\]="algunosSeleccionadosPagina"/);
  assert.match(html, /\(change\)="alternarPagina\(\)"/);
  assert.match(html, /\(change\)="alternarSeleccion\(solicitud\.id\)"/);
  assert.match(html, /\[disabled\]="solicitud\.estado !== 'PENDING'"/);
  assert.match(html, /\(click\)="toggleDetalle\(solicitud\.id, \$event\)"/);
  assert.match(html, /aria-haspopup="dialog"/);
  assert.match(html, /Autorizar seleccionadas/);
  assert.match(html, /Rechazar seleccionadas/);
  assert.match(html, /class="solicitud-bandeja__autorizar" disabled/);
  assert.match(html, /class="solicitud-bandeja__rechazar" disabled/);
  assert.match(css, /\.solicitud-bandeja__lista\s*\{[^}]*overflow:\s*visible;/s);
  assert.doesNotMatch(html, /class="solicitud-bandeja__expandido"/);
  assert.match(html, /class="solicitud-detalle-overlay"/);
  assert.match(html, /class="solicitud-detalle-dialog" role="dialog" aria-modal="true"/);
  assert.match(html, /cdkTrapFocus/);
  assert.match(html, /\(keydown\.escape\)="cerrarDetalle\(\)"/);
  assert.match(css, /\.solicitud-detalle-contenido\s*\{[^}]*overflow-y:\s*auto;/s);
  assert.match(css, /\.solicitud-filtros\s*\{[^}]*repeat\(3,/s);
  assert.doesNotMatch(html, /aprobarSolicitud\(|rechazarSolicitud\(|aplicarCorreccion\(/);
  assert.doesNotMatch(src, /\.(aprobarSolicitud|rechazarSolicitud|aplicarCorreccion)\(/);
});

test('E2: solo PENDING se seleccionan y seleccionar página nunca incluye otras páginas', () => {
  const { vm } = fixture({ referencia: null, vistaInicial: 'seguimiento' });
  vm.solicitudes = [
    { id: 11, estado: 'PENDING', tipo: 'MASTER_FIELD', sucursal_id: 7 },
    { id: 12, estado: 'REJECTED', tipo: 'NOT_LOCATED', sucursal_id: 7 },
    { id: 13, estado: 'PENDING', tipo: 'QUANTITY_DIFFERENCE', sucursal_id: 8 },
  ];
  vm.totalSolicitudes = 200;
  vm.alternarSeleccion(12);
  assert.equal(vm.totalSeleccionados, 0);
  vm.alternarPagina();
  assert.equal(vm.totalSeleccionados, 2);
  assert.equal(vm.estaSeleccionada(11), true);
  assert.equal(vm.estaSeleccionada(13), true);
  assert.equal(vm.estaSeleccionada(12), false);
  assert.equal(vm.todosSeleccionadosPagina, true);
  vm.alternarPagina();
  assert.equal(vm.totalSeleccionados, 0);
});

test('E2: filtros y páginas limpian selección para evitar aprobar fuera del contexto visible', () => {
  const { vm, calls } = fixture({ referencia: null, vistaInicial: 'seguimiento' });
  vm.alternarSeleccion(7);
  assert.equal(vm.totalSeleccionados, 1);
  vm.cambiarFiltros();
  assert.equal(vm.totalSeleccionados, 0);
  vm.alternarSeleccion(7);
  vm.totalSolicitudes = 26;
  vm.cambiarPagina(1);
  assert.equal(vm.totalSeleccionados, 0);
  assert.equal(calls.gets.at(-1).page, 2);
});

test('E2: detalles abren un segundo modal sin alterar la selección', () => {
  const { vm, calls } = fixture({ referencia: null, vistaInicial: 'seguimiento' });
  vm.alternarSeleccion(7);
  vm.toggleDetalle(7);
  assert.deepEqual(calls.details, [7]);
  assert.equal(vm.detalleIdAbierto, 7);
  assert.equal(vm.detalle.id, 7);
  assert.equal(vm.totalSeleccionados, 1);
  vm.toggleDetalle(7);
  assert.equal(vm.detalle, null);
  assert.equal(vm.detalleIdAbierto, null);
  assert.equal(vm.totalSeleccionados, 1);
});

test('E2: detalle conserva checks y devuelve foco al botón al cerrarlo', async () => {
  const { vm } = fixture({ referencia: null, vistaInicial: 'seguimiento' });
  vm.alternarSeleccion(7);
  let focusCount = 0;
  const boton = { isConnected: true, focus() { focusCount++; } };
  vm.toggleDetalle(7, { currentTarget: boton });
  assert.equal(vm.detalleIdAbierto, 7);
  assert.equal(vm.totalSeleccionados, 1);
  vm.cerrarDetalle();
  await Promise.resolve();
  assert.equal(vm.detalleIdAbierto, null);
  assert.equal(vm.totalSeleccionados, 1);
  assert.equal(focusCount, 1);
});

test('E2: filtrar mientras detalle abierto cancela modal y limpia selección', () => {
  const { vm } = fixture({ referencia: null, vistaInicial: 'seguimiento' });
  vm.alternarSeleccion(7);
  vm.toggleDetalle(7);
  assert.equal(vm.detalleIdAbierto, 7);
  vm.cambiarFiltros();
  assert.equal(vm.detalleIdAbierto, null);
  assert.equal(vm.totalSeleccionados, 0);
});

test('E2 UX: segundo modal no aumenta altura de la lista ni agrega doble scroll', () => {
  assert.match(css, /\.solicitud-detalle-dialog\s*\{[^}]*max-height:\s*min\(82dvh,\s*720px\)/s);
  assert.match(css, /\.solicitud-bandeja__lista\s*\{[^}]*overflow:\s*visible;/s);
  assert.match(css, /\.solicitud-bandeja__acciones--fijas\s*\{[^}]*flex:\s*0 0 auto;/s);
  const barra = html.indexOf('solicitud-bandeja__acciones--fijas');
  const pie = html.indexOf('<footer class="solicitud-footer">');
  assert.ok(barra > 0 && pie > barra, 'Las acciones deben aparecer antes del pie fijo');
  assert.ok(barra > html.indexOf('</section>\n      </section>'), 'Las acciones no deben estar en la lista');
  assert.match(html, /\*ngIf="modo === 'seguimiento' && !cargandoListado && !errorListado"/);
  assert.match(html, /\*ngIf="detalleIdAbierto !== null && modo === 'seguimiento'"/);
  assert.match(html, /\[attr\.inert\]="detalleIdAbierto !== null \? '' : null"/);
  assert.match(html, /\(click\)="cerrarDetalle\(\)"/);
  assert.doesNotMatch(html, /\*ngIf="detalleIdAbierto === solicitud\.id"/);
  assert.match(html, /class="solicitud-bandeja__autorizar" disabled/);
  assert.match(html, /class="solicitud-bandeja__rechazar" disabled/);
});
