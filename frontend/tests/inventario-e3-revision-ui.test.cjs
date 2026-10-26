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
      creado_por_usuario_id:98,baseline_canonico:{stock:3}},
    {id:2,tipo:'NOT_LOCATED',sucursal_id:7,estado:'PENDING',
      creado_por_usuario_id:98,baseline_canonico:{stock:3}},
    {id:3,tipo:'UNREGISTERED_FIND',sucursal_id:7,estado:'PENDING',
      creado_por_usuario_id:98,baseline_canonico:{sucursal_id:7}},
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

test('E3 standalone, backend-first menu, ruta y dos modales confirmados',()=>{
  assert.match(src,/standalone: true/);
  assert.match(src,/templateUrl: '.\/revision-correcciones.component.html'/);
  assert.match(src,/styleUrls: \['.\/revision-correcciones.component.css'\]/);
  assert.match(routes,/path: 'revision-correcciones'/);
  assert.match(layout,/inventario\/solicitudes\/revision\/contexto/);
  assert.match(layout,/if \(!response\?\.can_review\) return;/);
  assert.match(html,/cdkTrapFocus/);
  assert.match(html,/Confirmar autorización/);
  assert.match(html,/Confirmar rechazo/);
  assert.match(css,/\.revision-acciones\s*\{[^}]*flex:\s*0 0 auto/s);
  assert.match(css,/\.revision-bandeja\s*\{[^}]*overflow-y:\s*auto/s);
  assert.match(service,/decidirCorreccionesLote\(payload: LoteDecisionesInventario\)/);
});

test('E3 consulta contextual, seleccionar y filtrar reinicia checks',()=>{
  const {vm,calls}=make();
  assert.equal(vm.contexto.can_review,true);
  assert.equal(calls.lists.length,1);
  vm.marcar(1); assert.equal(vm.seleccionadas.length,1);
  vm.consultarDetalle(1); assert.equal(vm.detalle.id,1);
  vm.cerrarDetalle(); assert.equal(vm.seleccionadas.length,1);
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

test('E3 no localizado exige justificación para ajustar a cero',()=>{
  const {vm,calls}=make();
  vm.marcar(2); vm.preparar('APPROVED');
  vm.motivo='Inspección documentada'; vm.confirmo=true;
  assert.equal(vm.puedeConfirmar,false);
  vm.resoluciones[2].justificacion='Revisión física y evidencia cruzada suficientes';
  assert.equal(vm.puedeConfirmar,true);
  vm.ejecutar();
  assert.equal(calls.posts[0].resoluciones['2'].accion,'AJUSTAR_A_CERO');
  assert.equal(calls.posts[0].resoluciones['2'].stock_esperado,3);
});

test('E3 hallazgo requiere vínculo y cantidad física validada',()=>{
  const {vm,calls}=make();
  vm.marcar(3); vm.preparar('APPROVED');
  vm.motivo='Vinculación revisada';vm.confirmo=true;
  vm.resoluciones[3]={
    accion:'VINCULAR_EXISTENTE',inventario_id:502,stock_esperado:1,
    cantidad_fisica:2,justificacion:'Código físico cotejado con el maestro oficial',
  };
  assert.equal(vm.puedeConfirmar,true);
  vm.ejecutar();
  assert.equal(calls.posts[0].resoluciones['3'].inventario_id,502);
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
