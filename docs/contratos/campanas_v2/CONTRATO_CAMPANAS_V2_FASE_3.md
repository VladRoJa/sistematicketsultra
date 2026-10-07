# Contrato Campañas V2 — Fase 3

Estado: DESBLOQUEADA / DIVIDIDA EN TRES MILESTONES  
Dependencia: Fase 2 ACCEPTED mediante M32.  
Regla de ejecución: **este archivo es paraguas; no se implementa Fase 3 directamente desde aquí**. Cada conversación nueva debe trabajar exactamente uno de los contratos M1, M2 o M3.

## 0. Estado real de partida

Antes de iniciar cualquier milestone se debe inspeccionar `main` y revalidar este estado:

- Fase 1 congela audiencias Campaign V2.
- Fase 2 está ACCEPTED: iVentas/histórico recipient-level, Funnel, Historical Targeting y Campaign BI/Reporting.
- Existe lista negra global incremental de Campaign V2.
- La lista negra aplica a Vencidos, Activos y Funnel y también a la proyección operativa de envío.
- La **cohorte congelada** y la **lista para envío** son conceptos distintos:
  - cohorte congelada = evidencia histórica exacta persistida al Freeze;
  - lista para envío = proyección de esa cohorte con supresiones de seguridad vigentes.
- Ambos archivos se pueden descargar por separado.
- Campañas V1 fue retirada de la superficie operativa de frontend/API, pero persisten datos, modelos, jobs históricos e infraestructura compartida que no deben borrarse por implicación.
- No existe todavía envío automático Campaign V2 por `POST /v2/broadcast`.

## 1. Principio de seguridad rector

Un error de Fase 3 puede enviar mensajes reales a destinatarios incorrectos. Por tanto:

1. **Freeze nunca se recalcula.**
2. **La cohorte congelada nunca se muta ni se reescribe por blacklist, cambios de socio, Funnel, tarifa o historial.**
3. **La descarga de cohorte congelada se conserva aun después de habilitar envío automático.**
4. **La descarga de lista para envío también se conserva como respaldo operativo y oráculo de QA.**
5. El plan de envío se construye únicamente desde recipients congelados más supresiones de seguridad explícitas vigentes.
6. Actualmente la supresión dinámica aprobada es la blacklist global. Agregar otra exige contrato explícito.
7. Antes de cualquier POST real, backend reconstruye el plan y compara un fingerprint de dispatch confirmado por el usuario.
8. Si cambió el plan entre confirmación y submit, se aborta sin enviar nada.
9. El navegador nunca puede suministrar una lista arbitraria de teléfonos, channelId o provider_campaign_id como autoridad.
10. Un timeout/5xx ambiguo en creación de campaña **no autoriza retry ciego**.

## 2. Distinción canónica: histórico vs operativo

### 2.1 Cohorte congelada

Fuente exclusiva:

`marketing_campaign_v2_recipients` y su evidence persistida.

Propiedades:

- inmutable;
- descargable;
- auditable;
- no consulta blacklist;
- no consulta Activos/Vencidos/Funnel;
- no consulta provider;
- representa exactamente lo aprobado en Freeze.

### 2.2 Lista para envío

Fuente:

`cohorte congelada -> supresiones de seguridad vigentes -> sendable recipients`

Propiedades:

- no recalcula fuentes;
- puede variar si cambia una supresión de seguridad;
- debe mostrar diferencias respecto a Freeze;
- es la población máxima que un dispatch puede intentar enviar;
- debe poder descargarse antes del envío.

### 2.3 Plan de dispatch

El plan agrega a la lista para envío:

- template;
- variables;
- sucursal;
- channel binding;
- agrupación por provider channel;
- estado de resolución;
- fingerprint/idempotencia.

El plan **no puede agregar teléfonos** que no estén en lista para envío.

## 3. Cardinalidad obligatoria del proveedor

iVentas `POST /v2/broadcast` recibe un solo `channelId`.

Por tanto el modelo debe soportar:

```
Campaign V2
    1
    |
    N ProviderCampaign / DispatchBatch
```

Cada provider campaign debe conservar como mínimo:

- Campaign V2 padre;
- provider;
- sucursal/canal;
- template;
- recipient_count;
- dispatch fingerprint/idempotency key;
- estado;
- provider_campaign_id cuando exista;
- submitted/scheduled metadata;
- resultado/error sanitizado.

No usar el campo histórico `campaign_v2.provider_campaign_id` como única relación de Fase 3 si impide multisucursal.

## 4. API iVentas conocida

Creación:

`POST https://rest.iventas.mx/v2/broadcast`

Autenticación backend:

`Authorization: Bearer <integration key>`

Respuesta exitosa conocida:

```json
{
  "campaign": "<provider campaign id>"
}
```

Puede existir `deduplicated = true` en escenarios soportados por proveedor.

Fase 3 usa integration key + channelId. No mover credenciales a Angular.

## 5. Tres milestones obligatorios

### F3-M1 — Foundation & Preflight

Contrato:

`CONTRATO_CAMPANAS_V2_FASE_3_M1.md`

Objetivo:

construir toda la base segura de dispatch, resolución de canales/templates, modelo 1:N, permisos, sendable projection reutilizable, preflight y fingerprint.

**Prohibido hacer POST /v2/broadcast.**

Estado inicial: PENDIENTE.

Gate de salida:

un plan de envío determinístico y auditable puede construirse para campañas mono y multisucursal y coincide exactamente con la lista para envío.

### F3-M2 — Controlled Submit

Contrato:

`CONTRATO_CAMPANAS_V2_FASE_3_M2.md`

Objetivo:

implementar submit inmediato real con provider adapter, idempotencia, feature flag, estados seguros y persistencia inmediata de provider IDs.

No incluye scheduling ni retry automático de resultados ambiguos.

Estado inicial: BLOQUEADO por M1.

Gate de salida:

un envío controlado explícitamente aprobado puede ejecutarse sin divergencia entre preflight y payload enviado, y queda completamente auditado.

### F3-M3 — Productionization & Final Acceptance

Contrato:

`CONTRATO_CAMPANAS_V2_FASE_3_M3.md`

Objetivo:

scheduling, conciliación/retries seguros, integración N provider campaigns con stats/costo de Fase 2, observabilidad, multisucursal real y acceptance final.

Estado inicial: BLOQUEADO por M2.

Gate de salida:

Fase 3 ACCEPTED para operación productiva controlada.

## 6. Gates entre conversaciones

Una conversación de M2 debe detenerse si M1 no está marcado ACCEPTED en `main`.

Una conversación de M3 debe detenerse si M2 no está marcado ACCEPTED en `main`.

No basta con que exista código parcial. El contrato del milestone previo debe declarar su acceptance y las pruebas exigidas deben estar verdes.

## 7. Capacidades que deben reutilizarse

Inspeccionar antes de crear piezas nuevas:

- `backend/app/services/marketing_phone.py`
- `backend/app/services/marketing_iventas_service.py`
- `backend/app/services/marketing_iventas_branch_service.py`
- modelos `MarketingIventas*`
- infraestructura de permisos de Marketing;
- Campaign V2 recipients/evidence;
- blacklist Campaign V2;
- export de cohorte congelada;
- export de lista para envío;
- provider stats/history de Fase 2;
- patrones scheduler/jobs si M3 los necesita.

No crear un tercer normalizador de teléfono ni un diccionario paralelo branch -> sucursal.

## 8. Invariantes que ningún milestone puede romper

- No volver a consultar Vencidos/Activos/Funnel al enviar.
- No reevaluar Historical Targeting.
- No modificar recipients congelados.
- No retirar las dos descargas manuales.
- No enviar con teléfono inválido.
- No inventar channelId.
- No aceptar channelId desde Angular como autoridad.
- No aceptar teléfonos desde Angular como autoridad.
- No hardcodear templates en Angular.
- No loggear credenciales ni payloads completos con PII.
- No bloquear Gunicorn esperando analytics.
- No borrar legacy histórico ni infraestructura compartida.
- No asumir costo cero cuando provider no tiene costo disponible.
- No marcar enviado sin provider ID válido o estado explícitamente conciliable.

## 9. Regla de confirmación antes de cualquier envío real

La UI debe mostrar como mínimo:

- campaña;
- propósito;
- cohorte congelada;
- supresiones vigentes;
- destinatarios enviables;
- sucursal(es);
- channel(s) resueltos;
- template;
- variables;
- inmediato/programado;
- fingerprint de dispatch o versión equivalente.

Backend reconstruye y valida de nuevo.

Si el fingerprint no coincide, responde conflicto y obliga a revisar de nuevo.

## 10. Kill switch

La capacidad de enviar debe tener un control backend/entorno default OFF durante M2.

Desactivar el kill switch:

- impide nuevos submits;
- no modifica campañas ya enviadas;
- no cancela campañas ya aceptadas por iVentas.

Nunca colocar este control únicamente en frontend.

## 11. Regla de acceptance real

Ninguna conversación debe ejecutar un POST real a iVentas sin aprobación explícita del usuario en ese momento.

Las pruebas unitarias/mockeadas pueden avanzar sin esa aprobación.

Los casos live deben usar una campaña QA deliberada, pequeña y revisada manualmente contra su lista para envío.

## 12. Retiro de legacy

El decommission operativo de V1 ya ocurrió antes de esta subdivisión.

Fase 3 **no autoriza**:

- drop de tablas legacy;
- borrado de histórico;
- eliminación de jobs históricos;
- eliminación de servicios iVentas compartidos.

Cualquier limpieza física posterior requiere contrato/PR separado.

## 13. Cómo iniciar una conversación nueva

No pegar este paraguas como único contrato para implementar.

Usar exactamente el archivo del milestone activo:

- M1: `CONTRATO_CAMPANAS_V2_FASE_3_M1.md`
- M2: `CONTRATO_CAMPANAS_V2_FASE_3_M2.md`
- M3: `CONTRATO_CAMPANAS_V2_FASE_3_M3.md`

La primera acción de la conversación debe ser inspeccionar `main` y confirmar que el gate previo sigue vigente.
