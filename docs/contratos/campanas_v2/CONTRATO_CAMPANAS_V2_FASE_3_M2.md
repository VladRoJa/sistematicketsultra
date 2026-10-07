# Contrato Campañas V2 — Fase 3 / M2
## Controlled Submit

Estado: IMPLEMENTADO / PENDIENTE DE ACCEPTANCE LIVE — 2026-10-07
Gate de entrada: CUMPLIDO — `CONTRATO_CAMPANAS_V2_FASE_3_M1.md` está ACCEPTED en main.
Gate de salida: PENDIENTE únicamente del primer caso live controlado con autorización explícita. La implementación, mocks y regresión están cerrados.

## 0. Uso de este contrato

Este archivo es autosuficiente para una conversación nueva.

La conversación debe implementar **únicamente F3-M2**.

No empezar si M1 no está ACCEPTED.

Antes de tocar código:

1. leer este contrato;
2. inspeccionar main;
3. confirmar el modelo 1:N provider campaigns;
4. confirmar preflight/fingerprint;
5. confirmar sendable projection compartida;
6. confirmar dos descargas manuales;
7. confirmar permiso explícito y channel/template resolution.

## 1. Objetivo

Agregar el primer submit real a iVentas de forma controlada.

M2 debe permitir:

- enviar inmediatamente una Campaign V2 congelada;
- usar exclusivamente el plan aprobado por M1;
- dividir en N provider campaigns por channel/sucursal;
- persistir cada resultado inmediatamente;
- impedir doble submit;
- detenerse si cambió el plan;
- conservar estado parcial si un batch falla;
- tratar resultados ambiguos sin retry ciego.

M2 no incluye:

- scheduling `sendAt`;
- retries automáticos;
- reconciliación automática compleja;
- aceptación productiva multísucursal final;
- eliminación de exports manuales;
- eliminación de legacy histórico.

## 2. Guardas previas obligatorias

Antes de cualquier provider POST:

- campaign existe;
- usuario tiene permiso explícito de enviar;
- kill switch backend habilitado;
- campaign tiene recipients congelados;
- preflight vigente;
- expected dispatch fingerprint coincide;
- sendable projection reconstruida coincide;
- ningún batch tiene channel sin resolver;
- template activo/válido;
- variables requeridas completas;
- no existe operación concurrente incompatible;
- provider campaign child no está ya SUBMITTED/SUBMITTING de forma incompatible.

Si cualquiera falla: **0 provider calls**.

## 3. Feature flag / kill switch

Debe existir configuración backend/entorno.

Ejemplo conceptual:

`CAMPAIGN_V2_PROVIDER_SEND_ENABLED=false`

Default: OFF.

Reglas:

- frontend no controla el valor;
- endpoint real responde bloqueado si OFF;
- tests deben cubrir OFF/ON;
- cambiarlo no modifica datos históricos;
- OFF no cancela broadcasts ya aceptados por provider.

No usar el flag como sustituto de permisos.

## 4. Provider adapter

Implementar una abstracción explícita para creación.

Conceptualmente:

```
CampaignProvider.create_campaign(dispatch_batch) -> ProviderCreateResult
```

iVentas es un adapter.

El core M2 no debe construir headers HTTP ni interpretar errores iVentas en rutas Flask.

El adapter debe encapsular:

- URL;
- Authorization;
- timeout;
- request body;
- parse de respuesta;
- errores provider;
- supportRef sanitizado.

No loggear Authorization.

## 5. Request iVentas

Endpoint conocido:

`POST https://rest.iventas.mx/v2/broadcast`

Usar:

- integration key;
- channelId resuelto backend;
- templateName resuelto backend;
- leads construidos backend.

No usar token legacy salvo decisión contractual posterior.

M2 envía **sin sendAt**.

## 6. Leads

Cada lead debe provenir del batch preflight.

Nunca aceptar desde Angular:

- phones;
- vars;
- urlVars;
- channelId.

Angular puede seleccionar template/configuración autorizada y confirmar fingerprint.

Backend reconstruye todo.

## 7. Confirmación y TOCTOU

La UI primero ejecuta preflight.

Usuario ve:

- frozen_count;
- suppressions;
- sendable_count;
- batches;
- channels;
- template;
- variables/bloqueos;
- fingerprint.

Submit recibe el fingerprint esperado.

En submit backend:

1. reconstruye sendable projection;
2. reconstruye channel/template/vars;
3. recalcula fingerprint;
4. compara;
5. si difiere -> 409 / PRECONDITION FAILED;
6. no hace POST.

Esto protege cambios de blacklist/config entre revisión y envío.

## 8. Idempotencia Suite

No confiar en dedupe provider.

Debe existir estado/constraint para impedir:

- doble click;
- retry manual simultáneo;
- dos workers;
- misma operación dos veces.

La implementación puede usar:

- unique idempotency key;
- row lock;
- transición atómica;
- combinación de los anteriores.

Requisito:

dos requests concurrentes no pueden producir dos broadcasts para el mismo batch/configuración.

## 9. Estados M2

Cada provider campaign child debe distinguir al menos:

- READY;
- SUBMITTING;
- SUBMITTED;
- PROVIDER_ERROR;
- RECONCILIATION_REQUIRED.

Opcionalmente BLOCKED permanece de M1.

Reglas:

### READY -> SUBMITTING

Transición atómica antes del POST.

### SUBMITTING -> SUBMITTED

Solo con respuesta válida que contenga provider campaign id.

Persistir inmediatamente:

- provider_campaign_id;
- submitted_at;
- submitted_by;
- respuesta mínima sanitizada;
- deduplicated si provider lo reporta.

### SUBMITTING -> PROVIDER_ERROR

Solo cuando el fallo es determinísticamente no creado/configuración, por ejemplo 4xx conocido que garantiza rechazo.

### SUBMITTING -> RECONCILIATION_REQUIRED

Para resultados ambiguos:

- timeout;
- conexión cortada después de posible submit;
- 5xx sin garantía de no creación;
- respuesta inválida tras posible aceptación.

No reintentar automáticamente estos casos.

## 10. Errores iVentas

Mapear al menos:

- FORBIDDEN;
- INVALID_CHANNEL_TOKEN;
- MISSING_CHANNEL;
- TEMPLATE_NOT_FOUND;
- DUPLICATE_BROADCAST_IN_PROGRESS;
- supportRef;
- timeout;
- 5xx;
- respuesta sin campaign id.

Reglas:

- error configuración: no retry ciego;
- ambiguity: RECONCILIATION_REQUIRED;
- no inventar campaign id;
- no transformar ambiguity en FAILED definitivo sin evidencia;
- no esconder supportRef operativo, pero sanitizarlo.

## 11. Persistencia por batch

Multisucursal puede producir N POST.

Cada batch se persiste de forma independiente.

Si:

- batch A SUBMITTED;
- batch B falla;

no hacer rollback lógico de A.

Resultado Campaign V2 debe poder mostrar estado parcial.

No borrar provider ID exitoso porque otro batch falló.

## 12. Orden de submit multibatch

La implementación debe ser determinística.

No se requiere paralelismo en M2.

Preferible:

- ordenar batches por clave canónica;
- enviar secuencialmente;
- persistir resultado de cada uno;
- detener o continuar según política explícita.

Política inicial recomendada:

**detener nuevos batches al primer resultado ambiguo**.

Para un error determinístico de configuración, también detener por seguridad hasta revisión.

No seguir "a ver cuáles pasan" por default.

## 13. No scheduling en M2

M2 no envía `sendAt`.

La UI no ofrece fecha/hora real.

Si existen campos preparados en modelo, quedan inactivos.

Scheduling pertenece a M3.

## 14. UI de confirmación

Debe existir confirmación final.

Mostrar:

- campaña;
- propósito;
- frozen_count;
- blacklist/supresiones;
- sendable_count;
- sucursal(es);
- channels resueltos;
- template;
- batches;
- modo = Inmediato;
- fingerprint/version.

Botón real:

- oculto/deshabilitado si kill switch OFF;
- deshabilitado si plan no ready;
- requiere acción explícita del usuario.

No usar confirmaciones ambiguas tipo "Continuar" sin decir que se enviarán mensajes.

## 15. Regla de primer envío live

La implementación puede completarse con mocks sin aprobación especial.

Pero el **primer POST real** requiere que el usuario autorice explícitamente en esa conversación.

Antes del POST real:

1. crear/identificar campaña QA pequeña;
2. descargar cohorte congelada;
3. descargar lista para envío;
4. revisar teléfonos;
5. ejecutar preflight;
6. demostrar igualdad del phone set entre lista para envío y batch;
7. mostrar template/channel/count;
8. pedir/recibir autorización explícita;
9. solo entonces enviar.

No interpretar "prueba", "va" o una aprobación anterior como permiso permanente para futuros sends reales.

## 16. Tamaño del primer caso live

Usar la mínima población útil.

Preferencias:

- 1 sucursal;
- pocos recipients;
- teléfonos controlados/esperados;
- template conocido.

No usar una campaña masiva como primera prueba.

No probar multisucursal live todavía salvo instrucción explícita extraordinaria.

## 17. Observabilidad M2

Registrar sin PII innecesaria:

- campaign_v2_id;
- provider_campaign_child_id;
- provider;
- sucursal/channel binding id;
- recipient_count;
- operation;
- state transition;
- duration;
- HTTP class;
- error code;
- supportRef sanitizado.

No registrar:

- bearer token;
- teléfonos completos en logs generales;
- vars completos;
- payload entero.

## 18. Provider campaign id

Respuesta exitosa conocida:

```json
{
  "campaign": "<provider campaign id>"
}
```

No marcar SUBMITTED antes de persistir un ID válido.

Si provider reporta `deduplicated=true`:

- conservar flag;
- validar que exista campaign id utilizable;
- no asumir éxito sin identidad provider.

## 19. Relación con Fase 2

M2 persiste provider IDs de child rows.

No es obligatorio todavía adaptar todo Reporting consolidado a N children; eso se termina en M3.

Sí debe quedar una interfaz clara para que M3/Fase 2 puedan consultar cada provider campaign.

No bloquear submit esperando analytics.

## 20. Exports manuales

M2 no elimina ni oculta:

- Descargar cohorte congelada;
- Descargar lista para envío.

Después de un submit siguen disponibles.

La lista para envío no se convierte en "histórico enviado"; es una proyección vigente.

El registro exacto de qué batch se intentó enviar vive en provider campaign/config snapshot.

## 21. Seguridad ante blacklist posterior

Si un teléfono entra a blacklist:

### antes del submit

fingerprint cambia -> submit se bloquea y exige nueva revisión.

### después de SUBMITTED

no se reescribe el provider campaign ya enviado.

Blacklist no puede des-enviar un mensaje ya aceptado por provider.

La auditoría debe distinguir el momento de submit.

## 22. Pruebas mínimas M2

### Kill switch

- OFF -> 0 provider calls;
- ON + sin permiso -> 0 calls;
- ON + plan invalid -> 0 calls.

### Fingerprint

- coincide -> puede avanzar;
- blacklist cambió -> 409, 0 calls;
- template cambió -> 409;
- channel cambió -> 409.

### Idempotencia

- doble click;
- requests concurrentes;
- batch ya SUBMITTED;
- batch SUBMITTING huérfano según política.

### Provider

- éxito + campaign id;
- deduplicated + campaign id;
- template not found;
- invalid channel;
- forbidden;
- timeout;
- 500 + supportRef;
- 2xx sin campaign id;
- JSON inválido.

### Multibatch

- dos batches mockeados;
- primer éxito, segundo error;
- éxito queda persistido;
- no rollback;
- ambiguity detiene restantes.

### Seguridad

- browser phone injection imposible;
- browser channel injection imposible;
- secretos fuera de responses;
- logs sanitizados.

## 23. Criterio de aceptación M2

M2 puede marcarse ACCEPTED solo si:

1. M1 permanece intacto;
2. kill switch backend default OFF;
3. provider client está aislado;
4. submit requiere fingerprint vigente;
5. idempotencia/concurrencia están protegidas;
6. N provider campaigns se soportan;
7. provider IDs se persisten inmediatamente;
8. ambiguities terminan en RECONCILIATION_REQUIRED;
9. no hay retries ciegos;
10. exports manuales permanecen;
11. suite específica y regresión Campaign V2 están verdes;
12. se ejecutó al menos un caso live controlado **con autorización explícita** y phone set revisado.

Si no se realiza el caso live, M2 queda IMPLEMENTADO / PENDIENTE DE ACCEPTANCE LIVE, no ACCEPTED.

## 24. Cierre documental M2

Al aceptar:

- actualizar estado a ACCEPTED;
- documentar provider payload real observado;
- documentar error behavior real;
- registrar campaign id QA;
- no guardar PII/secretos en docs;
- desbloquear M3.

No empezar M3 en la misma conversación.

### 24.1 Cierre de implementación — 2026-10-07

Implementación completada, sin ejecutar todavía el primer POST live.

Decisiones finales:

- **Kill switch:** `CAMPAIGN_V2_PROVIDER_SEND_ENABLED` existe en backend y su default es `false`. El endpoint de submit se bloquea antes de construir el provider cuando está OFF.
- **Credencial write-only:** el submit usa únicamente `IVENTAS_CAMPAIGN_SEND_API_KEY`; no existe fallback al token legacy. Se exige integration key con prefijo `ivk_live_`.
- **Base URL:** `IVENTAS_CAMPAIGN_SEND_API_BASE_URL`, default `https://rest.iventas.mx`.
- **Provider adapter:** `IVentasBroadcastProvider` encapsula URL, Authorization, timeout, payload y clasificación de errores. `POST /v2/broadcast` vive únicamente en ese adapter.
- **Sin retry automático:** create campaign hace un solo POST. Timeout, 5xx, 409 ambiguo, JSON inválido o 2xx sin `campaign` terminan en `RECONCILIATION_REQUIRED` y no se reintentan automáticamente.
- **Payload inmediato:** `templateName`, `leads[{phone, vars}]`, `channelId`, `name`; M2 omite `sendAt`.
- **Phone:** `marketing_phone.normalize_phone()` sigue siendo la única normalización; `format_mexico_international_phone()` es únicamente la proyección de transporte `MX10 -> 52+MX10` para iVentas.
- **TOCTOU:** submit recibe solo `template_id` + `expected_dispatch_fingerprint`, reconstruye el preflight completo en backend y responde conflicto si el fingerprint cambió.
- **Autoridad del browser:** Angular no puede enviar phones, vars, urlVars, channelId, provider ID ni `sendAt`.
- **Idempotencia/concurrencia:** child rows se preparan con `idempotency_key` única y cada batch hace transición atómica `READY -> SUBMITTING` antes del provider POST. Un segundo request ante `SUBMITTING`, `SUBMITTED` o estado incompatible hace 0 provider calls.
- **Política multibatch:** orden determinístico y secuencial. Se persiste cada éxito inmediatamente. Al primer error determinístico o resultado ambiguo se detienen los batches restantes; no se revierte un batch ya `SUBMITTED`.
- **Auditoría child:** se agregan `submit_started_at`, `provider_deduplicated`, `request_snapshot_json` y `provider_response_json`; se conserva `provider_campaign_id`, `submitted_at`, `submitted_by`, `error_code` y `support_ref`.
- **Observabilidad:** logs de transición contienen campaign id, child id, provider, sucursal, channel binding id, recipient count, operación, estado, duración, clase HTTP, error code y supportRef sanitizado. No se loggean teléfonos, vars, payload completo ni bearer token.
- **UI:** el detalle muestra gate de Controlled Submit, estado de provider campaigns y confirmación explícita `Sí, enviar mensajes ahora`. La confirmación incluye campaña, purpose, frozen count, blacklist vigente, sendable count, sucursales/channels, template, batches, modo inmediato, fingerprint y versión.
- **Exports:** `Descargar cohorte congelada` y `Descargar lista para envío` permanecen disponibles.

Persistencia / migración:

- `d2f8a4c6b1e7_extend_campaign_v2_m2_submit_audit.py`
- `down_revision = c1f7e9a4b6d2`
- Heads Alembic finales:
  - Campaign V2: `d2f8a4c6b1e7`
  - Requisiciones: `e1a7c4d2b9f6`

Endpoint M2:

- `POST /api/marketing/campaigns-v2/<campaign_id>/submit`
- body permitido: `template_id`, `expected_dispatch_fingerprint`
- `can_send_campaigns` es obligatorio y separado de preflight/gestión.

Variables de despliegue backend (`.env.docker` en producción):

- `CAMPAIGN_V2_PROVIDER_SEND_ENABLED=false` por defecto.
- `IVENTAS_CAMPAIGN_SEND_API_KEY=<integration key>`.
- `IVENTAS_CAMPAIGN_SEND_API_BASE_URL=https://rest.iventas.mx` salvo override explícito.

Evidencia de implementación:

- Suite Campaign V2 + iVentas + phone: **579 passed**.
- Suite enfocada M2 tras observabilidad: **39 passed**.
- Frontend Campaign V2 node tests: **47/47 passed**.
- Angular template/type compilation (`ngc`): **exit code 0**.
- `ng build` del worktree no llegó a bundle por bloqueo del entorno al compartir `node_modules`; no emitió error de TypeScript/template. `ngc` sí compiló completamente el frontend M2.
- Alembic: grafo válido, sin colisiones/ciclos; head Campaign V2 `d2f8a4c6b1e7`.
- Primer POST real a iVentas en esta implementación: **0 ejecutados**.

Estado de salida actual:

`F3-M2 — IMPLEMENTADO / PENDIENTE DE ACCEPTANCE LIVE`

Para cambiar a `ACCEPTED` todavía falta exclusivamente el procedimiento de §15–16: seleccionar campaña QA pequeña, revisar cohorte y lista para envío, demostrar paridad del phone set, mostrar template/channel/count y recibir autorización explícita en esta conversación antes del POST real.

`F3-M3 — BLOQUEADO HASTA M2 ACCEPTED`

## 25. Prompt de arranque para una conversación nueva

```
Estamos implementando únicamente Campañas V2 Fase 3 / M2 — Controlled Submit.

Lee docs/contratos/campanas_v2/CONTRATO_CAMPANAS_V2_FASE_3_M2.md y verifica que M1 esté ACCEPTED en main antes de tocar código.

Reglas críticas:
- preservar cohorte congelada y lista para envío;
- no aceptar phones/channelId desde frontend como autoridad;
- submit exige dispatch fingerprint vigente;
- kill switch backend default OFF;
- sin scheduling;
- sin retry automático de timeout/5xx ambiguo;
- N provider campaigns por Campaign V2;
- el primer POST real a iVentas requiere autorización explícita del usuario en esta conversación.

Trabaja un cambio/prueba a la vez y no adelantes M3.
```
