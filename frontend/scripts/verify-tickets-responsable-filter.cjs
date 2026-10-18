'use strict';

// Prueba sin navegador del mismo motor TypeScript que usa la tabla Tickets V1.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const Module = require('node:module');
const path = require('node:path');
const ts = require('typescript');

const file = path.resolve(__dirname, '../src/app/utils/ticket-utils.ts');
const compiled = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
    importsNotUsedAsValues: ts.ImportsNotUsedAsValues.Remove,
  },
}).outputText;

const mod = new Module(file, module);
mod.filename = file;
mod.paths = Module._nodeModulePaths(path.dirname(file));
mod._compile(compiled, file);

const { obtenerResponsableVisible, filtrarTicketsConFiltros } = mod.exports;

const tickets = [
  { id: 1, departamento_id: 1, tipo_atencion: 'INTERNA', asignado_a: 'SR_MANT_TIJ', estado: 'abierto' },
  { id: 2, departamento_id: 1, tipo_atencion: 'EXTERNA', asignado_a: null, estado: 'abierto' },
  { id: 3, departamento_id: 1, tipo_atencion: null, asignado_a: null, estado: 'en progreso' },
  { id: 4, departamento_id: 1, tipo_atencion: 'INTERNA', asignado_a: 'AUX_MANT_TJ', estado: 'en progreso' },
  { id: 5, departamento_id: 6, tipo_atencion: null, asignado_a: null, estado: 'abierto' },
  // Un asignado legacy sigue teniendo responsable aunque tipo_atencion sea NULL.
  { id: 6, departamento_id: 1, tipo_atencion: null, asignado_a: 'SR_MANT_TIJ', estado: 'abierto' },
];

function ids(filters) {
  return filtrarTicketsConFiltros(tickets, filters).map(t => t.id);
}

assert.equal(obtenerResponsableVisible(tickets[0]), 'SR_MANT_TIJ');
assert.equal(obtenerResponsableVisible(tickets[1]), 'Proveedor externo');
assert.equal(obtenerResponsableVisible(tickets[2]), 'Sin asignar');
assert.equal(obtenerResponsableVisible(tickets[4]), '—');
assert.deepEqual(ids({ responsable: ['SR_MANT_TIJ'] }), [1, 6]);
assert.deepEqual(ids({ responsable: ['Proveedor externo'] }), [2]);
assert.deepEqual(ids({ responsable: ['Sin asignar'] }), [3]);
assert.deepEqual(ids({ responsable: ['—'] }), [5]);
assert.deepEqual(ids({ responsable: ['SR_MANT_TIJ', 'Proveedor externo'] }), [1, 2, 6]);
assert.deepEqual(ids({ responsable: ['SR_MANT_TIJ', 'Proveedor externo'], estado: ['abierto'] }), [1, 2, 6]);
assert.deepEqual(ids({ responsable: ['SR_MANT_TIJ', 'Sin asignar'], estado: ['en progreso'] }), [3]);

console.log('PASS: filtro Responsable — interno, externo, sin asignar, legacy y cruce con Estado');
