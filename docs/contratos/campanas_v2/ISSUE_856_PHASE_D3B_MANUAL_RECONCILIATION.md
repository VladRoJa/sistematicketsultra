# Suite Ultra — Issue #856 / D3b — Reconciliación gobernada manual

**Estado:** PR DRAFT apilado sobre D3a #880 y D2c #878. Ningún envío real, merge, despliegue o activación de flags.

## Motivo

Las campañas gobernadas no pueden usar el reconciliador heredado porque éste modifica solo el child, sin garantizar transición de la ejecución y una evidencia común. Queda bloqueado para campañas con aprobación gobernada, conservando el comportamiento histórico para otras campañas.

## Transacciones autorizadas

Ambas rutas requieren JWT, alcance global, `can_manage_dispatch_config` y `can_send_campaigns` en el backend, pero **no dependen de habilitar los kill switches de envío**.

1. `POST /api/marketing/campaigns-v2/{campaign_id}/dispatch/executions/{execution_id}/escalate`. Body: `child_id`, `expected_manifest_digest`, `source_reference`, `evidence_note`. Requiere ejecución `IN_FLIGHT`, claim del child correcto, huella íntegra y antigüedad mínima de **10 minutos**. Cambia ejecución a `REVIEW_REQUIRED`. Si child sigue `SUBMITTING`, pasa a `RECONCILIATION_REQUIRED` con **outcome UNKNOWN**; si ya es `SUBMITTED`, conserva identidad/éxito sin sobrescribir. No prueba que iVentas no creó campaña.
2. `POST /api/marketing/campaigns-v2/{campaign_id}/dispatch/executions/{execution_id}/resolve`. Body: los cuatro campos de arriba, además `resolution` y, si corresponde, `provider_campaign_id`. Solo se ejecuta sobre `REVIEW_REQUIRED` + child `RECONCILIATION_REQUIRED` sin resultado anterior:
   - `PROVIDER_CAMPAIGN_FOUND`: se requiere ID externo y referencia de evidencia; se registra `SUBMITTED` y el momento de **registro local** de la confirmación; no se inventa hora real de aceptación del proveedor.
   - `NOT_CREATED_CONFIRMED`: se prohíbe ID externo; child pasa a `PROVIDER_ERROR`, no a `RETRY_ELIGIBLE`.
3. Todas las acciones guardan child + execution + evento append-only en una transacción, con `source_reference`, nota, operador, estados anteriores/posteriores e identidad externa cuando exista. Migración `c856d3b01013`.
4. Ninguna acción deja execution como `AUTHORIZED`, ni renueva aprobación/cuotas, ni libera `HELD`, ni llama a iVentas. `send_authorized=false` y `may_auto_retry=false`. Toda continuación requiere otro contrato de autorización.

## Precondiciones

- Identidad de ruta, campaña, aprobación, ejecución y child congruente, bloqueo por filas `campaign → approval → execution → child`.
- Digest exacto, actor válido, fuente documental y nota obligatorias; identidad externa única.
- Operación de escalamiento deliberada **no antes de 10 minutos**, superior al umbral informativo de 5 minutos del monitor D3a; nunca marcar automáticamente por tarea programada.
- Reintento de la misma resolución falla por estado y restricción de unicidad; historial protegido ante downgrade.

## D3c pendiente

Liberación de `HELD`, renovación de evidencia de cupo y creación de nuevas autorizaciones requieren contrato separado. La aprobación D2a tiene unicidad por campaña y caduca en 15 minutos, por lo que reutilizarla o revivirla sería incorrecto. No se permite ninguna solución que ignore esas restricciones.
