# Permissions Review — High Job / Import Routes

## Objetivo

Revisar rutas que ejecutan jobs, pipelines o importaciones antes de revisar escrituras comunes.

## Resultado

No se detectaron rutas `high_job_or_import` abiertas. Las 4 rutas revisadas tienen `@jwt_required()` y guard interno.

La observación principal queda en Inventario: la importación está protegida por permisos, pero sigue siendo una carga masiva directa al catálogo maestro. Esto se documenta como decisión futura de validación/auditoría, no como hotfix de seguridad inmediato.

## Rutas revisadas

| módulo | método | ruta | función | archivo | guard actual | scope esperado | estado | notas |
|---|---|---|---|---|---|---|---|---|
| Catálogos | POST | `/<string:catalogo>/importar` | `importar_catalogo` | `backend/app/routes/catalogos_routes.py` | `jwt_required` + `_validar_admin_catalogos()` | Admin catálogo global | ok_hardened | Import masivo protegido por admin. La importación de clasificaciones jerárquicas está bloqueada hasta tener validador dedicado. |
| Inventario | POST | `/importar` | `importar_inventario` | `backend/app/routes/inventarios.py` | `jwt_required` + `_require_inventory_global_write()` | Escritura global de inventario | needs_manual_decision | Guard correcto. Importa masivamente a `InventarioGeneral`; futuro recomendado: deduplicación, validación fuerte, auditoría/import batch o rollback controlado. |
| Track / BI | POST | `/run-daily-pipeline` | `run_track_daily_pipeline_endpoint` | `backend/app/routes/track_routes.py` | `jwt_required` + `_require_track_admin_role()` | Admin Track / BI | ok_hardened | Admin-only. Valida `track_date`, `generation_mode` y bloquea generación para fechas pasadas desde este flujo. |
| Track / BI | POST | `/run-agregadoras-integration` | `run_track_agregadoras_integration_endpoint` | `backend/app/routes/track_routes.py` | `jwt_required` + `_require_track_admin_role()` | Admin Track / BI | ok_hardened | Admin-only. Ejecuta integración manual de agregadoras para la fecha solicitada. |

## Conclusión

- No hay cambios funcionales urgentes derivados de la revisión `high_job_or_import`.
- Las rutas críticas de job/import tienen guard interno.
- Inventario queda como decisión futura de diseño: reforzar importación masiva con validación, deduplicación, auditoría y posible modelo de batch.
