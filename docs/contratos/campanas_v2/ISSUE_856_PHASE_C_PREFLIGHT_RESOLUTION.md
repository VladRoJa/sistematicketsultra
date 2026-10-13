# Issue #856 — Fase C: centro de preparación y exclusiones auditadas

## Garantías fundamentales

- El preflight y los diagnósticos no envían mensajes, no modifican la audiencia congelada y no editan la blacklist global.
- La fuente para deduplicar campañas es el payload JSON de cada lote confirmado `SUBMITTED`, nunca la audiencia original. Los lotes `HELD` correctamente auditados prueban cero contactos y no son considerados como enviados. Cualquier lote READY, SUBMITTING, PROVIDER_ERROR o RECONCILIATION_REQUIRED bloquea el origen completo por seguridad.
- Se puede revisar una o varias campañas anteriores (hasta 20). En cruces repetidos, se atribuye una sola fuente anterior, ordenada por ID de campaña, y se conserva la primera auditoría ya existente.
- El diagnóstico clasifica sucursal ausente con evidencia contradictoria (2+ claves), sin evidencia (0 claves) o una sola evidencia pendiente de consolidar. No se infiere una sucursal a partir de conjeturas ni se relabelan recipients históricos.
- El UI muestra resultados paginados (máximo 100 filas por petición) y el resumen completo. Exclusiones auditadas se crean solo para evidencias conflictivas 2+, usando la validación histórica del helper de exclusión.
- Toda mutación exige permiso backend global `can_manage_dispatch_config`, campaña sin provider children, hash de revisión y cantidad exacta. Desde 10 exclusiones se requiere `allow_bulk=true`. La confirmación visible exige teclear `EXCLUIR N` también para volúmenes menores.
- La operación lockea campaña destino antes de recomputar el manifest. Si cambia el hash, la cantidad o la evidencia, se rechaza la operación antes de cualquier inserción.
- No se modifica schema: reusa `marketing_campaign_v2_recipient_dispatch_exclusions` (`reason`, `related_campaign_id`, actor, fecha). Ninguna migración Alembic adicional.
- Después de una mutación el frontend descarta preflight/fingerprint anterior. Se requiere revisar de nuevo antes de enviar.

## API

- GET /api/marketing/campaigns-v2/{id}/preparation/branches?page=1&page_size=25 — read-only, acceso preflight
- POST /api/marketing/campaigns-v2/{id}/preparation/branches/exclude — admin, fingerprint/cantidad/bulk
- POST /api/marketing/campaigns-v2/{id}/preparation/previous/review — read-only, source_campaign_ids
- POST /api/marketing/campaigns-v2/{id}/preparation/previous/exclude — admin, source_campaign_ids y manifest aprobado

## Pruebas requeridas

- 1, 9, 10, 11, 626 evidencias ambiguas; cero/single, paginación, revisión read-only, bulk explícito.
- Rechazo si existen provider children en destino; hash stale, mismatch de conteos, cambio de razón ya auditada, pertenencia a campaña diferente, origen posterior o con payload inconsistente.
- Origen parcial 23 SUBMITTED + 2 HELD: contar solo aceptados y rechazar HELD sin auditoría o con inicio de POST. Cruces varios orígenes sin doble exclusión.
- Flask JWT/403, Angular TypeScript/Node y build de producción, regresiones de campañas #8/#14/#15.

## Fuera de Fase C

No se habilita envío, liberación de HELD ni saldo Meta; cuotas y aprobación presupuestaria son Fase D. No se introducen scripts que editen producción.