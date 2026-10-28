'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const { webcrypto } = require('node:crypto');
globalThis.crypto ||= webcrypto;

const dir = path.join(__dirname, '../src/app/inventario/revision-correcciones');
const src = fs.readFileSync(path.join(dir,'revision-correcciones.component.ts'),'utf8');
const html = fs.readFileSync(path.join(dir,'revision-correcciones.component.html'),'utf8');
const css = fs.readFileSync(path.join(dir,'revision-correcciones.component.css'),'utf8');
const service = fs.readFileSync(path.join(__dirname,'../src/app/services/inventario.service.ts'),'utf8');
const layout = fs.readFileSync(path.join(__dirname,'../src/app/layout/layout.component.ts'),'utf8');
const routes = fs.readFileSync(path.join(__dirname,'../src/app/inventario/inventario.routes.ts'),'utf8');

function observable(value,error=false) {
  return { subscribe(observer) {
    if (error) observer.error(value); else observer.next(value);
    return { unsubscribe(){} };
  }};
}
function make({ fail=false }={}) {
  const js = ts.transpileModule(src,{compilerOptions:{
    module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,
    experimentalDecorators:true,
  }}).outputText;
  const mod={exports:{}};
  new Function('require','module','exports',js)(
    name=>name==='@angular/core'?{Component:()=>klass=>klass}:{},mod,mod.exports,
  );
  const items=[
    {id:1,tipo:'QUANTITY_DIFFERENCE',sucursal_id:7,estado:'PENDING',
      creado_por_usuario_id:98,baseline_canonico:{stock:3},
      valor_original:{stock:3},valor_propuesto:{cantidad_fisica:2},
      referencia_oficial:{nombre:'Caminadora',codigo_interno:'07CA01'},
      motivo:'Diferencia comprobada con conteo físico'},
    {id:2,tipo:'NOT_LOCATED',sucursal_id:7,estado:'PENDING',
      creado_por_usuario_id:98,baseline_canonico:{stock:3},
      valor_original:{stock:3},valor_propuesto:{no_localizado:true},
      referencia_oficial:{nombre:'Caminadora',codigo_interno:'07CA01'},
      motivo:'Equipo ausente tras revisión física',
      fecha_observacion_local:'2026-10-26',
      evidencia_descriptiva:'Búsqueda física total de referencia en almacén y piso'},
    {id:3,tipo:'UNREGISTERED_FIND',sucursal_id:7,estado:'PENDING',
      creado_por_usuario_id:98,baseline_canonico:{sucursal_id:7},
      hallazgo_provisional:{nombre:'Remo',tipo:'APARATOS',codigo_interno:'07RE01'},
      referencia_oficial:null,
      fecha_observacion_local:'2026-10-26',
      evidencia_descriptiva:'Cotejo de etiqueta física y conteo total del almacén'},
  ];
  const calls={lists:[],details:[],posts:[]};
  const api={
    contextoRevisionCorrecciones(){
      return observable({can_review:true,corporativo:false,
        sucursales:[{sucursal_id:7,sucursal:'Villas del Rey'}]});
    },
    listarRevisionCorrecciones(params){
      calls.lists.push(params);
      return observable({items,total:3,page:1,per_page:10});
    },
    detalleRevisionCorreccion(id){
      calls.details.push(id);
      return observable({solicitud:items.find(s=>s.id===id)});
    },
    decidirCorreccionesLote(payload){
      calls.posts.push(structuredClone(payload));
      return fail?observable({status:503},true):observable({
        lote_id:5,replayed:false,items:payload.solicitud_ids.map(id=>({solicitud_id:id})),
      });
    },
  };
  const vm=new mod.exports.RevisionCorreccionesComponent(api);
  vm.ngOnInit();
  return {vm,calls};
}

test('E3 muestra contexto en tarjetas y conserva solo el modal de decisión',()=>{
  assert.match(src,/standalone: true/);
  assert.match(src,/templateUrl: '.\/revision-correcciones.component.html'/);
  assert.match(src,/styleUrls: \['.\/revision-correcciones.component.css'\]/);
  assert.match(routes,/path: 'revision-correcciones'/);
  assert.match(layout,/inventario\/solicitudes\/revision\/contexto/);
  assert.match(layout,/if \(!response\?\.can_review\) return;/);
  assert.match(html,/cdkTrapFocus/);
  assert.equal((html.match(/class="revision-modal-overlay"/g) || []).length, 1);
  assert.doesNotMatch(html,/e3DetalleTitulo|consultarDetalle\(/);
  assert.match(html,/\{\{ solicitud\.motivo \}\}/);
  assert.match(html,/\{\{ solicitud\.evidencia_descriptiva/);
  assert.match(html,/\{\{ solicitud\.fecha_observacion_local/);
  assert.match(html,/\{\{ cambioPropuesto\(solicitud\) \}\}/);
  assert.match(html,/\{\{ nombreReferencia\(solicitud\) \}\}/);
  assert.match(html,/\{\{ codigoReferencia\(solicitud\) \}\}/);
  assert.match(css,/\.revision-fila__datos\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1\.3fr\)/s);
  assert.match(html,/Confirmar autorización/);
  assert.match(html,/Confirmar rechazo/);
  assert.match(html,/aprobacionEspecialIndividual/);
  assert.match(html,/Motivo original de la solicitud/);
  assert.match(html,/\*ngIf="!aprobacionEspecialIndividual"/);
  assert.match(css,/\.revision-acciones\s*\{[^}]*flex:\s*0 0 auto/s);
  assert.match(css,/\.revision-bandeja\s*\{[^}]*overflow-y:\s*auto/s);
  assert.match(service,/decidirCorreccionesLote\(payload: LoteDecisionesInventario\)/);
});

test('E3 consulta contextual, muestra cambios legibles y filtrar reinicia checks',()=>{
  const {vm,calls}=make();
  assert.equal(vm.contexto.can_review,true);
  assert.equal(calls.lists.length,1);
  assert.equal(vm.cambioPropuesto(vm.solicitudes[0]),
    'Stock oficial: 3 → 2 · Conteo físico');
  assert.equal(vm.cambioPropuesto(vm.solicitudes[1]),
    'Stock oficial: 3 → 0 · Ajuste solicitado');
  assert.match(vm.cambioPropuesto(vm.solicitudes[2]),/Código físico: 07RE01/);
  assert.equal(vm.nombreReferencia(vm.solicitudes[0]),'Caminadora');
  assert.equal(vm.codigoReferencia(vm.solicitudes[1]),'07CA01');
  assert.equal(vm.nombreReferencia(vm.solicitudes[2]),'Remo');
  assert.equal(vm.codigoReferencia(vm.solicitudes[2]),'07RE01');
  vm.solicitudes[0].referencia_oficial=null;
  assert.equal(vm.nombreReferencia(vm.solicitudes[0]),'Nombre no disponible');
  assert.equal(vm.codigoReferencia(vm.solicitudes[0]),'Sin código interno');
  assert.equal(calls.details.length,0); // No se consulta otro endpoint para leer.
  vm.marcar(1); assert.equal(vm.seleccionadas.length,1);
  vm.cambiarFiltros(); assert.equal(vm.seleccionadas.length,0);
});

test('E3 aprobación requiere confirmación y motivo con UUID de lote',()=>{
  const {vm,calls}=make();
  vm.marcar(1); vm.preparar('APPROVED');
  vm.motivo='Revisión formal con evidencia';
  assert.equal(vm.puedeConfirmar,false);
  vm.confirmo=true;
  assert.equal(vm.puedeConfirmar,true);
  vm.ejecutar();
  assert.equal(calls.posts.length,1);
  assert.equal(calls.posts[0].decision,'APPROVED');
  assert.deepEqual(calls.posts[0].solicitud_ids,[1]);
  assert.equal(calls.posts[0].idempotency_key.length,36);
  assert.equal(vm.seleccionadas.length,0);
});

test('E3 no localizado individual exige un fundamento y lo registra en ambos campos',()=>{
  const {vm,calls}=make();
  vm.marcar(2); vm.preparar('APPROVED');
  assert.equal(vm.aprobacionEspecialIndividual,true);
  vm.motivo='Insuficiente'; vm.confirmo=true;
  assert.equal(vm.puedeConfirmar,false);
  vm.motivo='Autorizo ajuste a cero tras verificar el reporte físico';
  assert.equal(vm.resoluciones[2].justificacion,''); // Sin segundo textarea.
  assert.equal(vm.puedeConfirmar,true);
  vm.ejecutar();
  assert.equal(calls.posts[0].resoluciones['2'].accion,'AJUSTAR_A_CERO');
  assert.equal(calls.posts[0].resoluciones['2'].stock_esperado,3);
  assert.equal(calls.posts[0].resoluciones['2'].justificacion,calls.posts[0].motivo);
});

test('E3 hallazgo requiere vínculo y cantidad física validada',()=>{
  const {vm,calls}=make();
  vm.marcar(3); vm.preparar('APPROVED');
  vm.motivo='Vinculación revisada';vm.confirmo=true;
  vm.resoluciones[3]={
    accion:'VINCULAR_EXISTENTE',inventario_id:502,stock_esperado:1,
    cantidad_fisica:2,justificacion:'Código físico cotejado con el maestro oficial',
  };
  assert.equal(vm.aprobacionEspecialIndividual,true);
  assert.equal(vm.puedeConfirmar,true);
  vm.ejecutar();
  assert.equal(calls.posts[0].resoluciones['3'].inventario_id,502);
  assert.equal(calls.posts[0].resoluciones['3'].justificacion,calls.posts[0].motivo);
});

test('E3 lotes de varias solicitudes conservan motivo general y justificaciones por registro',()=>{
  const {vm,calls}=make();
  vm.marcar(2);
  vm.marcar(3);
  vm.preparar('APPROVED');
  vm.confirmo=true;
  vm.motivo='Revisión formal de ambos casos';
  assert.equal(vm.aprobacionEspecialIndividual,false);
  assert.equal(vm.puedeConfirmar,false);
  vm.resoluciones[2].justificacion='Ausencia constatada y stock confirmado';
  vm.resoluciones[3]={
    accion:'VINCULAR_EXISTENTE', inventario_id:502, stock_esperado:1,
    cantidad_fisica:2, justificacion:'Identidad física del equipo verificada',
  };
  assert.equal(vm.puedeConfirmar,true);
  vm.ejecutar();
  assert.equal(calls.posts[0].motivo,'Revisión formal de ambos casos');
  assert.equal(calls.posts[0].resoluciones['2'].justificacion,'Ausencia constatada y stock confirmado');
  assert.equal(calls.posts[0].resoluciones['3'].justificacion,'Identidad física del equipo verificada');
});

test('E3 bloquea aprobar un PENDING incompleto, pero deja rechazar',()=>{
  const {vm,calls}=make();
  vm.marcar(2);vm.preparar('APPROVED');
  vm.motivo='Inspección incompleta que requiere nueva evidencia';
  vm.confirmo=true;
  vm.resoluciones[2].justificacion='El conteo requiere un registro documentado completo';
  const selected=vm.seleccionadas[0];
  selected.evidencia_descriptiva=null;
  assert.equal(vm.puedeConfirmar,false);
  selected.evidencia_descriptiva='Inspección física de todas las áreas de la sucursal';
  selected.fecha_observacion_local=null;
  assert.equal(vm.puedeConfirmar,false);
  vm.cerrarDecision();vm.preparar('REJECTED');
  vm.motivo='Rechazada por carecer de evidencia física fechada';vm.confirmo=true;
  assert.equal(vm.puedeConfirmar,true);
  vm.ejecutar();
  assert.equal(calls.posts[0].decision,'REJECTED');
});

test('E3 hallazgo sin código físico no permite autorizar',()=>{
  const {vm}=make();
  vm.marcar(3);vm.preparar('APPROVED');
  vm.motivo='Hallazgo cotejado con documentación';vm.confirmo=true;
  vm.resoluciones[3]={
    accion:'VINCULAR_EXISTENTE',inventario_id:502,stock_esperado:1,
    cantidad_fisica:2,justificacion:'Identidad física declarada y comprobada',
  };
  vm.seleccionadas[0].hallazgo_provisional.codigo_interno='';
  assert.equal(vm.puedeConfirmar,false);
});

test('E3 diferencia cero histórica exige no localizado',()=>{
  const {vm}=make();
  vm.marcar(1);vm.preparar('APPROVED');
  vm.motivo='Conteo físico total con ausencia de unidades';vm.confirmo=true;
  vm.seleccionadas[0].valor_propuesto={cantidad_fisica:0};
  assert.equal(vm.cantidadCeroRequiereNoLocalizado(vm.seleccionadas[0]),true);
  assert.equal(vm.puedeConfirmar,false);
});

test('E3 rechazo no adjunta resoluciones y reintento mantiene idempotencia',()=>{
  const {vm,calls}=make({fail:true});
  vm.marcar(3);vm.preparar('REJECTED');
  vm.motivo='Rechazo formal documentado';vm.confirmo=true;
  vm.ejecutar();
  assert.equal(calls.posts[0].resoluciones,undefined);
  vm.ejecutar();
  assert.equal(calls.posts[1].idempotency_key,calls.posts[0].idempotency_key);
});
