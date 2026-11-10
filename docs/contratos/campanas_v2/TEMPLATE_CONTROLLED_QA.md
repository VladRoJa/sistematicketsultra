# Campañas V2 — Pruebas controladas de plantilla por canal emisor

Base: main `9dd54eb97a7380d23c6cf3600b72914a7cbbb8cf`, 2026-11-09.
Rama: `codex/campaign-template-controlled-qa`. Solo Campañas V2.

## Operación

1. En el Centro de envío de la campaña comercial, seleccionar la plantilla.
2. Abrir **Comprobar plantillas mediante envíos de prueba** y consultar la matriz.
   Se usa el preflight real, no el inventario ni una lista fija de sucursales.
3. Indicar nombre, teléfono autorizado y referencia rastreable de su autorización.
   Confirmar expresamente que se autoriza probar todos los canales indicados.
   Backend rechaza teléfonos presentes en la cohorte comercial, incluso si están
   excluidos del envío. No se copian sus destinatarios a QA.
4. **Preparar pruebas QA (todavía no envía)** congela exactamente una cohorte
   QA_MANUAL de un destinatario por canal emisor único. INDEPENDENCIA y TEC_MXL
   comparten prueba cuando el snapshot vigente resuelve el mismo emisor TEC_MXL;
   la matriz conserva ambos orígenes. No se cambia el snapshot de campañas viejas.
5. Abrir **Revisar QA / confirmar envío** para cada fila. Se reutiliza el Centro
   de envío gobernado: revisión de destinatario, costo y cuota, aprobación,
   materialización, autorización y confirmación explícita de envío con los
   controles existentes. La plantilla queda fijada. Preparar o consultar la
   matriz nunca llama al proveedor. Tampoco se envía al abrir esta consola.
6. Volver a consultar la matriz después de cada QA. Resultado, fecha, actor,
   campaña QA, child e identificador iVentas quedan separados de la entrega.
7. La campaña comercial requiere su propia revisión, presupuesto, cuota,
   aprobación y confirmación. Ninguna prueba inicia su despacho.

Los campos QA disponibles son los del flujo existente (nombre, teléfono y
sucursal del emisor). Una plantilla con variables que esos datos no satisfacen
queda bloqueada por el preflight; no se inventan valores ni se toman datos de
destinatarios comerciales. La compatibilidad local de plantilla/canal, blacklist
y demás validaciones también siguen vigentes: la prueba no las elude.

## Resultados y vigencia

| Estado | Significado |
| --- | --- |
| PENDIENTE | Cohorte sin intento iniciado, o aún sin preparar. |
| ACEPTADA POR IVENTAS | Child SUBMITTED/SCHEDULED con identificador de campaña y fecha de aceptación persistidos. No demuestra entrega ni facturación. |
| RECHAZADA | Rechazo confirmado por el validador estricto existente: actualmente HTTP 400, TEMPLATE_NOT_FOUND y referencia de soporte, sin campaña aceptada ni reintentos. |
| INCIERTA | Timeout, SUBMITTING, error ambiguo, configuración fallida, respuesta incompleta, rechazo no acreditado o evidencia desactualizada. Requiere revisión. |

No se amplía especulativamente la lista de rechazos confirmados. Un nuevo código
solo puede clasificarse como rechazo después de ampliar el contrato y sus pruebas.
La entrega se muestra como **NO VERIFICADA**; para acreditarla siguen siendo
necesarias las estadísticas/observaciones existentes de iVentas.

Una certificación QA aceptada para la misma plantilla/versión y canal emisor es reutilizable entre campañas sin volver a enviar. No caduca automáticamente a las 24 horas; esa vigencia continúa aplicando por separado a la evidencia manual del proveedor del PR #1225. Un cambio en la firma de la plantilla genera una nueva versión de certificación. La disponibilidad externa no está garantizada indefinidamente.

Para recuperación fallida, una QA aceptada puede satisfacer únicamente
`PROVIDER_TEMPLATE_UNVERIFIED` de su canal. No reutiliza las 24 horas de vigencia de
la evidencia manual: se valida por versión y canal. Se exigen firma de plantilla/variables/compatibilidad/media,
binding emisor exacto, actor, snapshot de un único teléfono autorizado,
identificador provider y aceptación persistida. No basta la existencia de una QA.
Un cambio de plantilla/media/ruta, rechazo o incertidumbre no concede
el pase. El resto de bloqueos, cuota, presupuesto y autorizaciones permanece.
Se conserva compatibilidad con la evidencia manual ya existente del PR #1225.

## Persistencia y protección contra duplicados

- No hay modelos ni migraciones nuevos. Se reutilizan Campaign V2, destinatarios,
  evidencias QA y provider children. `source_metadata.template_probe_v1` registra
  campaña comercial, plantilla y su firma, canal/binding, sucursales de origen,
  teléfono autorizado, referencia, actor y fecha de autorización.
- Nombre QA determinístico por **campaña comercial + template_id + canal real**.
  Un lock transaccional PostgreSQL por plantilla serializa preparaciones entre campañas;
  todas las cohortes y sus metadatos se confirman en una sola transacción. El
  helper QA existente admite flush sin commit para esta orquestación interna;
  sus consumidores anteriores conservan el comportamiento por defecto.
- Reintentar la preparación desde otra campaña devuelve las mismas cohortes. Cambiar el teléfono
  no crea otra prueba para la misma versión/canal. Un intento duradero de cualquier
  resultado impide otro POST para esa cohorte, incluso mediante retry legado.
  Expirar la evidencia tampoco habilita reenvíos.
- El gate compartido de contactos valida contrato y snapshot antes del claim
  SUBMITTING. La prueba necesita aprobación gobernada; no introduce una vía
  alternativa a `IVentasBroadcastProvider` ni un segundo motor de envío.
- JWT y capacidad global/configuración + gestión + preflight + envío son
  obligatorios para preparar/consultar. El envío mantiene todos los checks D2c,
  reautenticación, cuotas y ambos kill switches. No se cambian sus defaults.
- El teléfono se enmascara en la matriz; la autorización y los datos completos
  quedan en la trazabilidad protegida de QA, como el destinatario ya persistido.

## API Suite

`GET /api/marketing/campaigns-v2/{campaign_id}/dispatch/template-probes?template_id=...`
consulta la matriz. El POST a la misma ruta recibe exclusivamente `template_id`,
`recipient_name`, `phone`, `authorization_reference`, `confirmed_authorized`.
No admite actor, canales, destinatarios comerciales ni instrucciones de envío
aportados por el cliente. El actor procede del JWT y los emisores del preflight.
Ambas rutas son distintas de cualquier API de inventario iVentas: aquí no se
usa `/whatsappTemplate/...` ni credenciales del navegador.

## Verificación de desarrollo

- Backend final: **183 passed, 2 skipped**. Las omitidas necesitan PostgreSQL
  sintético local (`quota_ci`), ausente en este entorno; CI las ejecuta con
  PostgreSQL 16. Se cubren preparación idempotente, autorización del teléfono,
  deduplicación TEC/Independencia, exclusión comercial, contrato alterado, estados,
  prueba vigente/expirada, HTTP/JWT/global, preflight y regresiones de envío.
- Angular: `ngc -p tsconfig.app.json --noEmit`, correcto.
- Interfaz: **3 pruebas Node correctas** para autorización explícita, doble clic,
  ausencia de retry automático y descarte de respuestas de otra plantilla.
- Workflow `campaign-v2-template-probes-ci.yml`: backend focal y concurrencia
  PostgreSQL real, claim D2c con proveedor falso y compilación/pruebas Angular.
  Ningún job necesita claves iVentas; ambos flags de envío están OFF.
- `git diff --check`: correcto. `graphify update .` no pudo ejecutarse porque
  graphify no está instalado; tampoco existe `graphify-out/graph.json`.
- Instalación local aislada en `artifacts/qa-deps` y `frontend/node_modules`,
  ignorados por Git. No se modificaron dependencias fijadas ni archivos de entorno.

Comandos de validación desde backend (Python empaquetado, PYTHONPATH a los paquetes
aislados y claves JWT/SECRET sintéticas, sin credenciales iVentas):

```text
python -m pytest -q --tb=short
  tests/marketing/test_campaign_v2_template_probes.py
  tests/marketing/test_campaign_v2_template_probes_http.py
  tests/marketing/test_campaign_v2_template_probes_pg.py
  tests/marketing/test_campaign_v2_template_evidence.py
  tests/marketing/test_marketing_campaign_v2_qa_http.py
  tests/marketing/test_marketing_campaign_v2_qa_manual_service.py
  tests/marketing/test_marketing_campaign_v2_preflight_service.py
  tests/marketing/test_campaign_v2_channel_routing.py
  tests/marketing/test_campaign_v2_confirmed_failures.py
  tests/marketing/test_issue_856_stage_e_gates.py
  tests/marketing/test_marketing_permissions_p26_9_integral_inventory.py
  tests/marketing/test_marketing_campaign_v2_quota_dispatch_real_pg.py
  tests/integrations/test_iventas_broadcast_provider.py
```

Desde frontend:

```text
npm ci --ignore-scripts --no-audit --no-fund
node node_modules/@angular/compiler-cli/bundles/src/bin/ngc.js -p tsconfig.app.json --noEmit
node node_modules/esbuild/bin/esbuild src/app/marketing-campaign-v2/marketing-campaign-v2-template-probes.component.node-test.ts --bundle --platform=node --format=esm --external:@angular/* --external:rxjs --external:rxjs/* --outfile=node_modules/.cache/template-probes-tests.mjs
node node_modules/.cache/template-probes-tests.mjs
```

Incidencias del entorno resueltas antes del resultado final: venv no pudo ejecutar
ensurepip; se usó instalación en directorio aislado. Primeras colecciones pytest
fallaron por ruta de importación y dependencias faltantes (pytz/playwright); se
completaron y repitieron las pruebas focales. El primer bundle Node incluyó
Angular y falló durante su inicialización; el ejecutor final deja sus paquetes
externos y las tres pruebas pasan. No se alteró código productivo para esos fallos.

## Primer canario

Este PR no habilita flags ni ejecuta mensajes reales, merge o despliegue.
Tras un despliegue autorizado y validación de controles, el propietario deberá
autorizar expresamente el primer canario para un teléfono, plantilla y canal
concretos. Preparar la cohorte y revisar su plan no equivalen a esa autorización.

## Ajuste de alcance: certificación reutilizable (2026-11-09)

- Una prueba QA aceptada acredita el par **versión local de plantilla + canal iVentas**, independientemente de la campaña desde la que se preparó originalmente.
- Una campaña posterior con el mismo par ve **VALIDADA** sin otro envío ni necesidad de preparar una QA nueva. El preflight comercial conserva sus propias aprobaciones y restricciones.
- La validez se liga a la firma del contrato de plantilla, media y binding emisor. Al cambiar la firma se prepara una versión nueva; el historial anterior permanece.
- **Sin caducidad automática** para certificaciones QA. La atestación manual del PR #1225 conserva su vigencia de 24 horas.
- El sistema no detecta cambios externos en iVentas: una revocación o rechazo posterior requiere revisión operativa y corrección de la configuración local. No confundir certificación histórica con garantía de disponibilidad externa actual.
- Este ajuste todavía se presenta desde el Centro de envío de una campaña, como punto de consulta/alta; no añade de momento una pantalla propia en el catálogo administrativo de plantillas.

## Certificación directa desde catálogo (continuación)

Desde **Plantillas, canales y tarifas · iVentas**, el operador puede seleccionar
**Certificar canales** sobre una plantilla activa. La matriz obtiene los bindings
iVentas activos/default y resuelve los emisores efectivos sin exigir una campaña
comercial congelada. INDEPENDENCIA → TEC_MXL se agrupa bajo el emisor TEC_MXL.
La compatibilidad de la plantilla filtra los canales aplicables.

`GET /api/marketing/campaigns-v2/dispatch/template-certifications/{template_id}`
consulta el estado. El POST a la misma ruta recibe `recipient_name`, `phone`,
`authorization_reference`, `confirmed_authorized` y prepara solo QA faltantes.
No acepta canales arbitrarios, actor, destinatarios comerciales ni instrucciones
de envío del cliente. Conserva JWT/global/gestión/preflight/envío, bloqueo de
reintentos, aprobación, cuota, presupuesto y ambos kill switches OFF.
La revisión y confirmación de cada envío QA sigue utilizando el Centro de envío
gobernado existente. Preparar o consultar nunca envía mensajes.

La certificación permanece por plantilla/versión + canal efectivo entre campañas.
Agregar un canal compatible nuevo **no invalida los anteriores**: la firma QA
solo cambia cuando cambian el nombre exacto, variables o media de plantilla.
Si hay una alteración externa en iVentas, la certificación histórica no garantiza
su disponibilidad actual y requiere intervención operativa.

La preparación desde catálogo utiliza únicamente el teléfono expresamente
autorizado para QA; no extrae destinatarios de ninguna campaña comercial.
No altera el mecanismo de evidencia manual con vigencia de 24 horas.

Validación: compilación Angular y cinco tests Node focales correctos; pruebas
backend focales de catálogo/JWT/duplicados y PostgreSQL serán verificadas por CI.


## Reconocimiento de entregas comerciales (extensión)

La matriz de certificación también aprovecha **evidencia comercial ya persistida**
en `marketing_campaign_v2_provider_campaigns`,
`marketing_campaign_v2_provider_stats_snapshots` y
`marketing_campaign_v2_provider_recipient_observations`.

- Coincidencia obligatoria: `template_id`, nombre exacto, media, binding
  emisor real y `provider_channel_id`; child `SUBMITTED` con identificador
  externo, fecha y actor. No se infiere por sucursal de origen.
- Se exige snapshot iVentas posterior al envío, ligado por campaña e ID del
  proveedor, con observación `SUCCESSFUL` y `DELIVERED`/`VIEWED` de un
  destinatario que también figura en el request congelado del child. Un
  `SUBMITTED` sin entrega asociada **no** certifica.
- Para childs históricos que no almacenaban firma de plantilla, se exige que
  el registro local de la plantilla **no haya cambiado después de enviar**;
  la ausencia de prueba suficiente se considera `PENDIENTE`. No se
  reescriben ni se marcan retrospectivamente registros productivos.
- Un rechazo determinístico posterior `TEMPLATE_NOT_FOUND` revoca la prueba
  previa hasta que exista una entrega nueva verificada; los estados ambiguos
  no autorizan certificación. No se ignora un rechazo porque otra sucursal
  del mismo lote haya funcionado.
- La evidencia en la matriz muestra `COMMERCIAL_DELIVERY`, ID de campaña
  comercial, child, snapshot y momento de captura. Los teléfonos no se exponen.
- Las campañas futuras se reconocen automáticamente cuando el proceso ya
  existente guarda un snapshot que satisface el contrato. No se crea job,
  endpoint externo, WhatsApp ni lectura live a iVentas desde la matriz.
- Se mantienen los controles de envío comercial: esta evidencia **no**
  concede aprobación ni activa flags.
- La certificación QA `QA_MANUAL` sigue funcionando de forma independiente;
  las nuevas pruebas se omiten para pares con evidencia comercial suficiente.
- Sin migraciones: toda la evaluación es de solo lectura sobre estructuras
  ya existentes. Podrían persistir canales pendientes si no hay observaciones
  históricas de entrega o la versión local no puede verificarse.


## Selección focal de canales QA (extensión)

- **Consultar matriz** no crea QA ni llama al proveedor. El operador marca
  únicamente los canales pendientes/rechazados comerciales/expirados que desea
  comprobar, y puede desmarcarlos antes de preparar.
- **Preparar pruebas QA** exige selección no vacía, nombre, teléfono autorizado,
  referencia y confirmación nueva tras cualquier cambio en la selección.
  Solicita \`selected_channel_ids\` (identificadores efectivos del proveedor,
  no alias ni sucursales de origen) tanto desde el catálogo como desde una campaña.
- El endpoint del catálogo **rechaza** omitir \`selected_channel_ids\`. Backend
  comprueba estrictamente tipo lista, longitud, duplicados y pertenencia a
  \`_context(...)\` dentro del lock transaccional. Solo recorre canales elegidos;
  nunca amplía el conjunto a todos los pendientes.
- Si una combinación ya estaba certificada o tenía una QA preparada, se reutiliza
  y no se duplica. Los intentos inciertos siguen sin autorizar reenvíos.
- Los errores \`TEMPLATE_NOT_FOUND\` provenientes de un child comercial
  se rotulan **Rechazo comercial confirmado**, con campaña y lote originales;
  no se falsifica un identificador QA inexistente.
- Seleccionar y preparar **no envía WhatsApps**. El envío real conserva la
  aprobación, revisión de cuota/costo, confirmación y guards existentes.
- Uso focal: para VILLA_VERDE y SEND_CUL marcar solo sus dos filas;
  VILLAS_DEL_REY es otra sucursal distinta y no se incluye.
