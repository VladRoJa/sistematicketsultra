# M1-F6 — Etapa 2: captura automática del universo Track por versión

Estado: **PR de código + pruebas; sin deploy ni certificación de SLA**.

## Punto de integración real

`backend/app/warehouse/services/track_daily_mart_service.py`:
- `refresh_track_daily_mart_for_date()` obtiene **una sola lista** del
  catálogo Track activo, no-demo, usando el loader ya existente.
- `build_track_daily_mart_for_date(active_branches=...)` consume exactamente
  esa lista sin releerla; los lectores directos conservan su comportamiento.
- Si hay `track_daily_version_id`, antes del commit del mart captura:
  código canónico e ID operativo en ese instante, número esperado,
  SHA-256 determinístico y sello irrevocable por versión. Valida que todos
  los códigos, fecha y modo del mart coincidan con ese mismo universo.
- **Una sola transacción**: filas del mart + snapshot + miembros + sello.
  Error del catálogo, duplicados, digest, FK o guard DB provoca rollback
  y el caller de Track marca la versión fallida. No se silencian errores.
- Si no hay `track_daily_version_id` (legacy sin versión) el mart no
  pretende certificar linaje de versiones y no crea snapshot.
- El commit del mart existente es preservado: no se introduce otro commit
  ni se cambia la promoción atómica de Venta Total y cierre canónico.

Abarca las llamadas actuales a `refresh_track_daily_mart_for_date` desde:
1. `run_track_daily_pipeline_for_date`: preview y base nocturna;
2. `run_requested_track_canonical_close`: cierre pendiente/running
   promovido al final, sin marcar green;
3. `run_track_agregadoras_integration_for_date` cuando crea otro
   cierre versionado;
4. `rebuild_track_from_sources._rebuild_one_date`: si se crea **una nueva
   versión** en fecha antigua, conserva explícitamente el catálogo de la
   **fecha de generación**, no se representa como catálogo histórico efectivo
   del día antiguo.

## Conservadurismo de frescura

- `source_kind=LIVE_TRACK_CATALOG_NON_DEMO_AT_CAPTURE` significa
  **catalogo observado al construir el mart**, NO catálogo vigente en D.
- `historical_roster_verified=FALSE` permanece impuesto por la base
  de datos. Un hash correcto y sello no prueban fechas efectivas ni
  puntualidad del SLA.
- NO se crean datos para versiones `success` anteriores a la implantación.
  La ejecución contra una versión con snapshot existente falla explícitamente.
- `freshness_service.py`, `track_base_sla_service.py`,
  `funnel_operational_sla_service.py`, Angular y sus reason_codes no
  se alteran. Ningún semáforo pasa a verde.
- La etapa futura de **vigencia efectiva** necesita fuente de verdad para
  altas/bajas/cambios por fecha/sucursal, historial auditado, y contrato de
  certificación del SLA independiente del cierre canónico.

## Operación y despliegue

**No desplegar código stage 2 sin haber aplicado previamente**
`f6roster1014` (aprobada en PR #906). El esquema no existe aún en
producción hasta que se ejecute Alembic. La compatibilidad debe validarse
en entorno aislado primero; no tocar scheduler productivo durante el PR.

Verificaciones antes de deployment (futuro):
- `flask --app app.wsgi:app db current` = `f6roster1014 (head)`;
- prueba de un pipeline sintético aislado: version `running`, mart y
  snapshot del mismo ID, sello y 1:1; simular fallo y verificar rollback;
- comprobar que un reporte de freshness sigue UNKNOWN;
- supervisar latidos de workers; no desencadenar jobs históricos de prueba
  en producción.

## CI

PostgreSQL 15/16 con datos sintéticos para trigger/version/fecha/digest/
inmutabilidad y escritura real con ORM; pruebas unitarias negativas
(incluye branch mismatch) y regresión de mart y cierre solicitado.
