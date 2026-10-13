# Issue #856 — D3c2: cohorte derivada desde HELD (sin enviar)

**Dependencias:** D1 #870 → D2a #873 → D2b #875 → D2c #878 → D3a #880 → D3b #881 → D3c1 #882 → D3c2 (este PR).

## Qué hace

`POST /api/marketing/campaigns-v2/{source_campaign_id}/dispatch/held/{source_child_id}/freeze-derived`

Body exacto: `intent_id`, `expected_candidate_fingerprint`, `expected_recipient_count`. Requiere JWT, acceso global, `can_manage_dispatch_config` y `can_send_campaigns` en backend. El frontend nunca habilita el envío desde aquí.

1. Usa PostgreSQL con lock global de cohortes derivadas y bloqueos del origen. Revalida solicitud D3c1 `PENDING_FRESH_COHORT`, fingerprint/identidad, aprobación, child `HELD` sin intentos, ejecución original `COMPLETE`, demás READY `SUBMITTED`, snapshot exacto, evidencia nueva de canal/portafolio y población completa.
2. Rechaza listas negras o exclusiones actuales que alteren la población; **no excluye silenciosamente destinatarios** de un lote aprobado. Rechaza contactos ya incluidos en otra cohorte derivada o en snapshots de envíos de otras campañas con estado aceptado/en curso/ambiguo. Si la identidad externa es ilegible, falla cerrado.
3. Crea una **nueva** `marketing_campaign_v2_campaigns` con `source=HELD_RELEASE_DERIVED`, su propio ID y una copia exacta de los destinatarios y evidencias de origen. Conserva el `filters.allowed_sucursal_keys` de la campaña original y enlaza `intent_id`, approval/digest/candidate de origen en `audience_definition_json.derived_release` sin exponer teléfonos en el endpoint.
4. Actualiza en la misma transacción la intención a `FROZEN_DERIVED`, `derived_campaign_id` y `materialized_at`. Alembic `e856d3c21013` exige vínculo único y protege el downgrade con historial. Reintentos de materialización son conflicto.
5. En el **preflight normal** de campañas con `source=HELD_RELEASE_DERIVED` se exige intención materializada válida, audiencia congelada completa (sin supresión silenciosa), lista negra vigente y ausencia de contactos anteriores potencialmente enviados, porque un congelamiento aprobado ayer no garantiza seguridad mañana. Los D2a/D2b/D2c reutilizan ese preflight.

## Límites de autoridad

- La nueva campaña no tiene aprobación D2a, reserva, child D2b ni ejecución D2c. No invoca iVentas, no activa switches y no altera el `HELD` original.
- `send_authorized=false`, `quota_reserved=false`, `provider_calls=0` siempre al congelar.
- Antes de cualquier envío deben repetirse **preflight → cotización MXN → cuota → aprobación independiente D2a → materialización D2b → autorización D2c**, cada uno con sus controles y vencimientos.
- La evidencia de cupo es manual del operador, nunca Meta-verificada. La deduplicación solo puede demostrar lo persistido en Suite Ultra, no contactos externos desconocidos al sistema.
- Una carrera externa donde otro proceso envíe sin respetar los locks de campaña/cupo sigue siendo un riesgo operativo; la revisión de liberación debe validar los caminos efectivos de envío. No prometer ausencia absoluta de duplicados en plataformas ajenas.

## QA antes de merge

Tests de batch HELD original, copia de destinatarios/evidencias, lista negra, overlap con snapshots enviados, malformaciones, permiso backend, intent distinto o ya materializado, unicidad PostgreSQL y downgrade, CI de cuota/reconciliación/Winback. Todas las pruebas sintéticas. PR DRAFT, sin merge/despliegue/envíos reales.
