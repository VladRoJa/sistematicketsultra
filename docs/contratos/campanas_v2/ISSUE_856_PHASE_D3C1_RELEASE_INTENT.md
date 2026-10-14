# Suite Ultra — Issue #856 / D3c1: elegibilidad e intención de liberación HELD

**Dependencias:** D1 #870 → D2a #873 → D2b #875 → D2c #878 → D3a #880 → D3b #881 → D3c1 (este corte).

## Problema de modelo

En D2a existe `uq_mkt_v2_approval_campaign`: una aprobación única por campaña. La aprobación, cotización y reservas caducan a los 15 minutos como máximo. D2b mantiene los children `HELD` intactos. **Prohibido** modificar el child histórico a READY, reutilizar la aprobación antigua, extender reservas o crear nuevos provider calls usando la huella anterior.

## Nuevo procedimiento, fase 1: intención auditable

- `GET /api/marketing/campaigns-v2/{campaign_id}/dispatch/held/{child_id}/release-preview`: evalúa exclusivamente un `HELD` original y no devuelve teléfonos ni datos personales. Requiere campaña con aprobación/manifest D2B, ejecución original `COMPLETE`, todos los READY anteriores `SUBMITTED` con ID externo, HELD sin intento, preflight actual completo y snapshot/recipients/channel binding intactos.
- La evidencia **nueva** debe tener atestaciones separadas `CHANNEL` y `PORTFOLIO` con timestamp observado posterior al último envío confirmado y a la aprobación original. Verifica recencia/vigencia y `assess_preflight_capacity` sin ignorar actividad anterior de la campaña; es cupo declarado por operador, no saldo garantizado por Meta.
- Genera `candidate_fingerprint` SHA256 del origen, snapshot, versión de preflight, cantidad y referencias de las nuevas atestaciones. Una variación exige repetir Preview.
- `POST /api/marketing/campaigns-v2/{campaign_id}/dispatch/held/{child_id}/release-intent`: requiere fingerprint exacto, cantidad confirmada, `source_reference`, motivo y actor autorizado. Bloquea campaña/approval/child, vuelve a evaluar y registra un solo evento de intención por child bajo la nueva migración `d856d3c01013`.
- Único estado persistido: `PENDING_FRESH_COHORT`. Siempre `send_authorized=false`, `held_released=false`, `quota_reserved=false`; la intención **no concede** ninguna autoridad para enviar o reintentar.
- Protecciones de backend: JWT, permisos globales de configuración y envío, campos desconocidos rechazados. No necesita activar kill switches; no crea proveedor.
- Historial append-only protegido por FKs, unicidad `source_child_id` y downgrade guard. Sin teléfonos dentro de `evidence_json`.

## Fase 2, aún NO implementada

Una operación **separada**, sometida a QA propio, materializará la nueva cohorte congelada vinculada al origen, solo con destinatarios autorizados después de volver a aplicar blacklist y deduplicación entre campañas. Esa cohorte tendrá su **propio campaign_id**, y recorrerá desde cero preflight, cotización, aprobación D2a, reserva, materialización D2b, autorización D2c y despacho ordenado. Ningún child histórico cambia de estado. Si la población ha cambiado, el sistema debe exigir un nuevo preview y decisión humana, no copiar silenciosamente datos obsoletos.

## Gates

CI de PostgreSQL 16 real para migración/unique/history, pruebas de snapshot modificado, evidencia anterior al envío, protección de permisos y cero llamadas a proveedor. PR permanece DRAFT, sin merge ni deploy. D3c1 es preparación, **no una liberación efectiva de HELD**.
