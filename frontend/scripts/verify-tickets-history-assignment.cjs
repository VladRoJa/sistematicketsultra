'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const Module = require('node:module');
const path = require('node:path');
const ts = require('typescript');

const source = path.resolve(
  __dirname,
  '../src/app/pantalla-ver-tickets/modals/historial-fechas-display.ts',
);
const js = ts.transpileModule(fs.readFileSync(source, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const script = new Module(source, module);
script.filename = source;
script.paths = Module._nodeModulePaths(path.dirname(source));
script._compile(js, source);

const { esEventoReasignacion, esEventoCoordinacion, obtenerCambioResponsableHistorial } =
  script.exports;

const reasignacion = {
  tipo: 'maintenance_reassignment_v1',
  asignado_anterior: 'SR_MANT_MXLI',
  asignado_nuevo: 'SR_MANT_TIJ',
  tipo_atencion_anterior: 'INTERNA',
  tipo_atencion_nuevo: 'INTERNA',
  motivo: 'Prueba de reasignación',
};
assert.equal(esEventoReasignacion(reasignacion), true);
assert.equal(esEventoCoordinacion(reasignacion), false);
assert.deepEqual(obtenerCambioResponsableHistorial(reasignacion), {
  anterior: 'SR_MANT_MXLI',
  nuevo: 'SR_MANT_TIJ',
});

assert.deepEqual(obtenerCambioResponsableHistorial({
  tipo: 'maintenance_coordination_v1',
  tipo_atencion_anterior: null,
  asignado_anterior: null,
  tipo_atencion_nuevo: 'INTERNA',
  asignado_nuevo: 'SR_MANT_TIJ',
}), {
  anterior: 'Sin asignar',
  nuevo: 'SR_MANT_TIJ',
});

assert.deepEqual(obtenerCambioResponsableHistorial({
  tipo: 'maintenance_reassignment_v1',
  tipo_atencion_anterior: 'INTERNA',
  asignado_anterior: 'SR_MANT_MXLI',
  tipo_atencion_nuevo: 'EXTERNA',
  asignado_nuevo: null,
}), {
  anterior: 'SR_MANT_MXLI',
  nuevo: 'Proveedor externo',
});

assert.deepEqual(obtenerCambioResponsableHistorial({
  tipo: 'maintenance_reassignment_v1',
  tipo_atencion_anterior: 'EXTERNA',
  asignado_anterior: null,
  tipo_atencion_nuevo: 'INTERNA',
  asignado_nuevo: 'SR_MANT_TIJ',
}), {
  anterior: 'Proveedor externo',
  nuevo: 'SR_MANT_TIJ',
});

// No presentar asignaciones inventadas para eventos legacy o sin cambio.
assert.equal(obtenerCambioResponsableHistorial({
  tipo: 'legacy',
  motivo: 'Cambio de fecha',
}), null);
assert.equal(obtenerCambioResponsableHistorial({
  motivo: 'Reasignado manualmente',
}), null);
assert.equal(obtenerCambioResponsableHistorial({
  tipo: 'maintenance_coordination_v1',
  tipo_atencion_anterior: 'INTERNA',
  asignado_anterior: 'SR_MANT_TIJ',
  tipo_atencion_nuevo: 'INTERNA',
  asignado_nuevo: 'SR_MANT_TIJ',
}), null);

// El resumen representa el cambio en una sola fila y no inventa una fecha de solución.
const html = fs.readFileSync(
  path.resolve(__dirname, '../src/app/pantalla-ver-tickets/modals/historial-fechas-modal.component.html'),
  'utf8',
);
assert.match(html, /getCambioResponsableItem\(item\) as cambio/);
assert.match(html, /cambio\.anterior/);
assert.match(html, /cambio\.nuevo/);
assert.match(html, /historial-responsable-inline/);
assert.match(html, /Compromiso:/);
assert.match(html, /\*ngIf="getCambioResponsableItem\(item\) as cambio; else soloSolucion"/);
assert.doesNotMatch(html, /historial-cambio-responsable/, 'No regresar a la franja extra');

const scss = fs.readFileSync(
  path.resolve(__dirname, '../src/app/pantalla-ver-tickets/modals/historial-fechas-modal.component.scss'),
  'utf8',
);
assert.match(scss, /\.historial-compact-row\s*\{[^}]*grid-template-columns: 128px/s);
assert.match(scss, /\.contenido-modal\s*\{[^}]*overflow-y: auto/s);
assert.doesNotMatch(scss, /\.historial-cambio-responsable\s*\{/);

console.log('PASS: historial legible en una fila, scroll de contenido y eventos legacy');
