# Suite Ultra — Issue #856 / D3a — Observabilidad gobernada (solo lectura)

**Dependencia:** PR #878 (D2c) → D3a. La implementación se conserva DRAFT, sin merge/despliegue ni autorización de campaña real.

## Contrato

`GET /api/marketing/campaigns-v2/{campaign_id}/dispatch/monitor`

- Solo JWT con **`is_global`, `can_manage_dispatch_config` y `can_send_campaigns`** verificados en backend.
- Sin parámetros de consulta. Ninguna llamada al proveedor, escritura, commit, renovación de evidencia, cambio de estado o procesamiento de cola.
- Respuesta derivada exclusivamente de PostgreSQL: aprobación, ejecución, últimos reclamos, children, conteo por estado, referencia de proveedor y reservas/evidencias existentes.
- Toda cuota se declara `OPERATOR_ATTESTED_NOT_META_VERIFIED`. `quota.all_current` únicamente indica que **las evidencias persistidas** y ventanas de reserva siguen vigentes, no que Meta garantice el saldo.
- `send_authorized=false`, `may_auto_retry=false`, `may_auto_release_held=false` siempre. Este endpoint **no es un permiso de envío**.
- `IN_FLIGHT` reciente: `DO_NOT_RESEND`. Cuando han transcurrido 5 minutos desde el último reclamo sin cierre, se **muestra** `IN_FLIGHT_STALE` y `VERIFY_PROVIDER_OUTCOME_MANUALLY`; **nunca modifica** la fila original ni la convierte en error. Una pausa, caída o timeout no demuestra que iVentas no creó una campaña.
- `REVIEW_REQUIRED`, `RECONCILIATION_REQUIRED` y `PROVIDER_ERROR` requieren revisión humana; no autorizan retry.
- `HELD` se muestra retenido con su motivo y hora. Sin liberación implícita. `APPROVAL_EXPIRED` no permite reutilizar la aprobación.
- No se incluyen teléfonos, datos personales de destinatarios o cuerpos de mensaje en la salida.

## Separación de D3

- **D3a:** monitor interno persistido, read-only.
- **D3b:** reconciliación de ejecuciones gobernadas detenidas/ambiguas con evidencia externa obligatoria, auditoría y estado explícito; sin retry automático.
- **D3c:** liberación de HELD con nueva política de cupo y aprobación/manifest versionado, considerando la unicidad de aprobación por campaña. Sin reutilización de reservas caducadas.
- **D3d:** QA extremo a extremo sintético, cobertura de permisos y revisión de liberación. Fusionar PRs en orden si se autoriza; no habilitar flags por accidente.

## Regresiones exigidas

- Stale vs reciente; fuente de cuota vigente/caducada; estados de ejecución y HELD conservados.
- Respuesta con autorización siempre falsa; sin `session.add`, `commit`, `flush`, `execute`.
- GET 403 para alcance no global o `can_send_campaigns=false`; rechazo de `?auto_retry=true`; no instancia iVentas.
- Suite PostgreSQL 16 D2c y otras regresiones existentes sin cambios.
