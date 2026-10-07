# Contrato Campañas V2 — Fase 3 / M3
## Productionization & Final Acceptance

Estado: BLOQUEADO HASTA M2 ACCEPTED  
Gate de entrada: `CONTRATO_CAMPANAS_V2_FASE_3_M2.md` marcado ACCEPTED en main.  
Gate de salida: Fase 3 ACCEPTED para operación productiva controlada.

## 0. Uso de este contrato

Este archivo es autosuficiente para una conversación nueva.

La conversación debe implementar únicamente F3-M3.

No comenzar si M2 no está ACCEPTED.

Antes de tocar código:

1. inspeccionar `main`;
2. confirmar M1/M2;
3. confirmar provider child rows 1:N;
4. confirmar controlled submit ya probado;
5. confirmar exports manuales;
6. confirmar kill switch;
7. revisar stats/history Fase 2 existentes.

## 1. Objetivo

Convertir el submit controlado de M2 en una capacidad productiva segura.

M3 agrega:

- scheduling explícito;
- reconciliación de estados ambiguos;
- retries limitados cuando exista evidencia de seguridad;
- integración completa de N provider campaigns con stats/costo;
- observabilidad;
- estados agregados Campaign V2;
- multisucursal live;
- UX final;
- acceptance productiva.

M3 no modifica la semántica de Freeze ni Audience Builder.

## 2. Invariantes heredadas

Se mantienen sin excepción:

- cohorte congelada exacta e inmutable;
- descarga de cohorte congelada;
- lista para envío con supresiones vigentes;
- preflight/fingerprint antes de submit;
- channel/template backend-authoritative;
- phones nunca vienen del navegador como autoridad;
- provider campaign 1:N;
- kill switch backend;
- no retry ciego ante resultado ambiguo;
- no secretos en frontend;
- no recálculo de Activos/Vencidos/Funnel/Histórico al enviar.

## 3. Scheduling

M3 puede usar `sendAt` si el contrato real del provider está confirmado.

UX:

- usuario selecciona fecha/hora local;
- timezone se muestra explícitamente;
- default de negocio: `America/Tijuana` cuando corresponda a la operación actual, nunca por inferencia silenciosa.

Backend persiste como mínimo:

- timezone de origen;
- datetime local confirmado;
- valor normalizado/enviado a provider;
- created_by/scheduled_by;
- timestamp de submit.

No mezclar `America/Tijuana` y `America/Mexico_City`.

## 4. Scheduling y fingerprint

La fecha/hora programada forma parte del dispatch fingerprint.

Si cambia:

- sendAt;
- template;
- channel;
- blacklist/sendable set;
- variables;

el fingerprint cambia y requiere nueva confirmación.

## 5. Estado SCHEDULED

Una respuesta provider válida para envío programado debe persistir:

- provider_campaign_id;
- scheduled_for;
- provider payload mínimo;
- estado SCHEDULED o equivalente.

No marcar SENT solo porque quedó programada.

El estado agregado debe distinguir:

- programada;
- aceptada;
- observada posteriormente;
- fallida.

## 6. Reconciliación

M2 introdujo `RECONCILIATION_REQUIRED`.

M3 debe definir cómo salir de ese estado sin duplicar mensajes.

Antes de implementar reconciliación automática, investigar capacidades reales de iVentas:

- lookup por provider campaign id;
- list/search por nombre/tag/idempotency metadata;
- deduplicated response;
- campaign listing;
- soporte para identificar un create que pudo haber ocurrido tras timeout.

No inventar endpoint.

Si no hay evidencia suficiente para reconciliar automáticamente:

- mantener estado manual;
- permitir registrar resolución auditada por operador;
- no reintentar create.

## 7. Retries

Clasificar fallos:

### Retryable seguro

Solo si existe evidencia de que provider no creó la campaña o si la operación consultada es idempotente/read-only.

### No retryable

Errores de configuración:

- template inválido;
- channel inválido;
- forbidden;
- payload inválido.

### Ambiguo

- timeout tras envío;
- connection reset después de request;
- 5xx sin garantía;
- respuesta inválida tras posible aceptación.

Ambiguo -> reconciliar, no recrear.

Definir:

- máximo de intentos;
- backoff;
- auditoría;
- criterio de cierre.

## 8. Background jobs

Usar jobs separados si se requiere:

- sync stats;
- reconciliación;
- retries seguros;
- backfill.

No mantener loops dentro de Gunicorn.

Si se usa un scheduler infinito:

- seguir patrón de `track-scheduler` o worker dedicado;
- `db.session.remove()` por ciclo;
- no dejar conexiones `idle in transaction`.

No reutilizar el scheduler Track si mezcla dominios de forma impropia; puede existir worker específico.

## 9. Integración con Fase 2 stats

Fase 2 hoy conoce provider stats/reporting.

M3 debe adaptar la lectura a:

```
Campaign V2
  -> N ProviderCampaign
      -> provider stats snapshots
```

Cada child puede tener:

- provider_campaign_id;
- successful;
- failed;
- sent;
- delivered;
- viewed;
- interactions;
- cost;
- analyticsStatus.

No perder detalle por sucursal/channel.

## 10. Agregación Campaign V2

Para una campaña lógica:

```
total recipients submitted
= suma de recipients de provider batches efectivamente submitidos
```

Las métricas agregadas deben distinguir:

- batches SUBMITTED/SCHEDULED;
- batches FAILED;
- batches RECONCILIATION_REQUIRED;
- batches sin stats;
- stats parciales.

No asumir que missing = 0.

## 11. Costos

Costo total:

`sum(provider campaign costs válidos)`

Si un child:

- no tiene cost;
- analytics está not_synced;
- está reconciliando;

el total debe marcarse incompleto/parcial.

No mostrar costo exacto cuando hay children pendientes.

## 12. Reporting

Actualizar reporting individual/consolidado sin romper Fase 2.

Debe poder mostrar:

- total Campaign V2;
- breakdown por provider campaign/sucursal;
- estado de submit;
- estado analytics;
- costo parcial/completo.

No hacer provider HTTP dentro de generación de Excel/reporting si el patrón Fase 2 es evidencia persistida.

Sync provider y reporting permanecen separados.

## 13. Estado agregado de Campaign V2

Definir una proyección clara.

Ejemplos conceptuales:

- READY;
- PARTIALLY_SUBMITTED;
- SUBMITTED;
- SCHEDULED;
- PARTIALLY_FAILED;
- RECONCILIATION_REQUIRED;
- COMPLETED/OBSERVED según negocio.

No mezclar estado de Campaign V2 padre con un único child.

Un child fallido no debe borrar estado exitoso de otros.

## 14. Multisucursal live

M3 debe probar operación real multisucursal si Campaign V2 permite campañas multisucursal.

Antes del live:

1. frozen export;
2. sendable export;
3. preflight;
4. breakdown por channel;
5. fingerprint;
6. revisión manual;
7. autorización explícita.

Preferir caso pequeño de 2 sucursales.

No usar campaña masiva como primera validación multisucursal.

## 15. Política de fallos parciales

Ejemplo:

- A: SUBMITTED;
- B: PROVIDER_ERROR;
- C: no intentado.

Suite debe mostrar exactamente eso.

No:

- marcar toda la campaña FAILED ocultando A;
- volver a enviar A;
- asumir que C fue enviado.

La reanudación, si se permite, opera solo sobre children elegibles y con fingerprint/config coherente.

## 16. Reanudación segura

Si un operador corrige channel/template después de fallo:

- crear nueva revisión/config del child o una nueva operación auditada;
- no sobrescribir silenciosamente la configuración con la que falló;
- no tocar children ya SUBMITTED.

La política exacta debe quedar probada.

## 17. Blacklist después de submit parcial

Si blacklist cambia entre batches de una operación multisucursal:

la política inicial segura es:

- reconstruir plan antes de cada nuevo submit o usar snapshot transaccional explícito;
- si diverge del plan confirmado, detener restantes;
- no modificar batches ya submitidos.

No continuar con un fingerprint obsoleto.

## 18. Confirmación para scheduled

Mostrar:

- campaña;
- frozen count;
- sendable count;
- suppressions;
- batches;
- template;
- channel;
- fecha/hora local;
- timezone;
- fingerprint;
- kill switch.

Backend vuelve a validar.

## 19. UX de estados

La UI debe distinguir al menos:

- Preparado;
- Enviando;
- Programado;
- Enviado/aceptado;
- Error de configuración;
- Requiere conciliación;
- Parcial.

No usar solo verde/rojo sin texto.

El usuario debe poder identificar sucursal/batch problemático.

## 20. Observabilidad

Además de M2:

- scheduled_for;
- sync/reconciliation attempts;
- last_provider_check;
- analytics status;
- provider child cost status.

Logs estructurados sin PII.

Debe poder rastrearse un incidente por:

- campaign_v2_id;
- child id;
- provider campaign id;
- supportRef.

## 21. Alertas operativas

Considerar alertas para:

- child atrapado en SUBMITTING;
- RECONCILIATION_REQUIRED;
- scheduled campaign sin transición esperada;
- stats sin sincronizar por demasiado tiempo;
- provider errors repetidos.

No crear notificaciones ruidosas sin umbral.

## 22. Scheduler / frecuencia

La frecuencia debe responder al SLA real.

No consultar stats por segundo.

Preferir:

- batch;
- backoff;
- ventanas razonables.

Las lecturas no deben bloquear requests web.

## 23. Export manual permanece

Incluso con Fase 3 ACCEPTED:

- Descargar cohorte congelada permanece;
- Descargar lista para envío permanece.

No son temporales.

Sirven para:

- auditoría;
- contingencia;
- QA;
- comparación con provider;
- operación manual si el envío automático se desactiva.

## 24. Kill switch en producción

Debe seguir disponible.

Escenario de incidente:

1. desactivar nuevos sends;
2. conservar consulta/reporting;
3. investigar children afectados;
4. no cancelar automáticamente provider campaigns ya aceptados;
5. reconciliar antes de reanudar.

Probar que OFF no rompe lectura/reporting/export.

## 25. Seguridad de secretos

Revalidar:

- integration key solo backend/env;
- no secrets en DB si no están cifrados/justificados;
- no secrets en Angular;
- no secrets en logs;
- no support dumps con Authorization;
- errores frontend sanitizados.

## 26. Pruebas mínimas M3

### Scheduling

- immediate vs scheduled;
- timezone;
- DST cuando aplique;
- fingerprint cambia con schedule;
- provider scheduled success;
- provider scheduled error.

### Reconciliation

- timeout;
- 500;
- provider campaign encontrado;
- provider campaign no encontrado;
- capacidad provider insuficiente -> manual;
- nunca duplicar create.

### Retry

- error retryable probado;
- límite;
- backoff;
- error configuración sin retry;
- ambiguous sin retry de create.

### Stats

- 1 child;
- N children;
- child not_synced;
- child missing cost;
- aggregate parcial;
- aggregate completo.

### Multisucursal

- N batches;
- fallo parcial;
- reanudación solo elegible;
- cambio blacklist entre confirmación y batch restante;
- no duplicar exitosos.

### Scheduler

- session cleanup;
- exceptions aisladas;
- no bloqueo web.

### Kill switch

- OFF bloquea send/schedule;
- OFF permite export/reporting;
- ON requiere permisos.

## 27. Acceptance live final

Antes:

- campaign QA;
- mínimo volumen;
- exports revisados;
- channels revisados;
- templates revisados;
- fingerprint vigente;
- explicit approval.

Casos live:

### Caso A — single branch

Debe demostrar ciclo completo:

Freeze -> preflight -> submit/schedule -> provider id -> stats persistidas -> reporting.

### Caso B — multi branch

Debe demostrar:

- al menos 2 batches/channels;
- N provider ids;
- no duplicados;
- breakdown correcto;
- stats agregadas;
- costo status correcto.

Si no existe ambiente/destinatarios seguros para live multibranch, M3 no se declara ACCEPTED; queda pendiente de acceptance operativa.

## 28. Criterio de aceptación Fase 3

Fase 3 es ACCEPTED solo si:

1. M1 ACCEPTED;
2. M2 ACCEPTED;
3. scheduling seguro implementado o explícitamente descartado por decisión documentada si negocio no lo requiere;
4. reconciliation definida;
5. retries seguros;
6. N provider campaigns integrados a stats/reporting;
7. multisucursal probada;
8. kill switch probado;
9. exports manuales conservados;
10. suite completa relevante verde;
11. casos live aprobados ejecutados sin divergencias;
12. documentación final actualizada.

## 29. Después de Fase 3

No borrar legacy histórico automáticamente.

El siguiente trabajo, si se desea, debe tener contrato separado para:

- cleanup de V1;
- migración histórica;
- retiro de jobs;
- consolidación de modelos compartidos.

También puede abrirse una fase posterior para optimización/automatización avanzada.

## 30. Cierre documental M3

Al aceptar:

- marcar este contrato ACCEPTED;
- marcar paraguas Fase 3 ACCEPTED;
- actualizar GLOBAL;
- documentar arquitectura final;
- documentar kill switch;
- documentar procedimiento de incidente;
- documentar pruebas live sin PII/secretos.

## 31. Prompt de arranque para una conversación nueva

```
Estamos implementando únicamente Campañas V2 Fase 3 / M3 — Productionization & Final Acceptance.

Lee docs/contratos/campanas_v2/CONTRATO_CAMPANAS_V2_FASE_3_M3.md y verifica que M2 esté ACCEPTED en main.

Preserva obligatoriamente:
- cohorte congelada;
- lista para envío;
- fingerprint/preflight;
- modelo 1:N provider campaigns;
- kill switch;
- no retry ciego de creates ambiguos.

M3 agrega scheduling, reconciliación/retries seguros, integración N-child con stats/costo, observabilidad, multisucursal live y acceptance final.

No ejecutes ningún caso live sin autorización explícita del usuario en esta conversación.
Trabaja un cambio/prueba a la vez.
```
