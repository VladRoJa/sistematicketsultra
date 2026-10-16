# Suite Ultra — M3-C1: auditoría de invisibilidad de Track

**Versión de referencia auditada:** main `81ea0fda241cd370dea8024ee6326f107e54e22a`.
**Estado:** M3-C1 aislado, PR DRAFT; ningún staging F3 / M3-C2 autorizado.
**Alcance de búsqueda:** búsquedas GitHub Code en `TrackDailyMartORM`, `TrackDailyVersionORM`, `FROM/JOIN track_daily_mart` y `FROM/JOIN track_daily_versions`, revisión de los consumidores runtime relevantes; archivos de migración, pruebas y documentación excluidos de la clasificación de consumidores públicos.

## Contrato no negociable

1. Un candidato futuro `version_type = 'kpi_desempeno_candidato'` **nunca** entra en `PREFERRED_TRACK_VERSION_TYPES` ni en `resolve_track_daily_version_type_candidates()`. No se agrega dicho tipo a los flujos existentes durante M3-C1.
2. Una respuesta pública del mart debe partir de `resolve_preferred_track_daily_version()` o `resolve_effective_track_daily_version()` y usar **solo** `track_daily_version_id` de la versión resuelta. La precedencia se conserva `cierre_canonico > base_nocturna_canonica > preview_operativo` cuando aplica, incluido el fallback histórico válido de versión reemplazada con filas.
3. La exclusión **no** puede depender solo de `is_current=False`, `status='success'`, fecha o ID mayor. Si el candidato tuviera por error `is_current=True`, el contrato público igualmente debe excluir su `version_type`.
4. El scheduler de cierre solo reclama `cierre_canonico + pending/running + non-current`. Ni una petición manual ni las comprobaciones auxiliares deben interpretar el tipo reservado como cierre operativo.
5. Ninguna modificación de sources, KPI snapshots, Track rows reales, migraciones, canónicos o scheduler principal; M3-C1 solo corrige **lecturas**, excluyendo candidatos hipotéticos en CI.

## Auditoría de lectores — clasificación con evidencia

| Consumidor | Clasificación previo a M3-C1 | Evidencia / decisión |
|---|---|---|
| `app/routes/track_routes.py::get_track_daily_mart_endpoint` | **Seguro** | `resolve_effective_track_daily_version`; consultas por ID de versión resuelta |
| `app/routes/track_routes.py::export_track_daily_mart_xlsx_endpoint` | **Seguro** | misma resolución, XLSX solo filas del ID elegido |
| `app/routes/track_routes.py` historial: descubrimiento fechas | **Vulnerable menor** | fechas desde cualquier `track_daily_mart.track_daily_version_id IS NOT NULL`, aunque el detalle luego resolvía la versión; cambio a JOIN solo tipos públicos |
| `app/warehouse/services/planning_targets_service.py::_latest_track_mart_row_for_month` | **Vulnerable** | orden `track_date DESC, id DESC` sin resolver versión; cambio a helper de versión efectiva |
| `app/warehouse/services/planning_targets_service.py::get_branch_prefill` | **Vulnerable** | misma selección directa con `m2_sin_circulaciones IS NOT NULL`; cambio a helper |
| `app/warehouse/services/kpi_desempeno_query_service.py::_fetch_branch_capacity_targets_by_canon` | **Vulnerable** | misma selección directa; cambio a helper |
| `app/track_alerts/services/track_alert_rules_service.py::evaluate_track_alerts` | **Vulnerable** | seleccionaba todas las filas por `track_date + generation_mode`; ahora resuelve ID público antes de evaluar |
| `app/warehouse/services/track_forecast_service.py::load_first_store_income_dates_bulk` | **Vulnerable** | `MIN(track_date)` sobre todas las filas incluidas las de versiones no visibles; ahora reduce a IDs públicos resueltos |
| `app/warehouse/services/track_forecast_service.py::_get_track_daily_branch_version_candidates` | **Seguro** | filtros `is_current/status='success'` y allowlist de tipos; resolved cutoff seleccionado |
| `app/warehouse/services/track_forecast_service.py` SQL `selected_version` (cierre previo) | **Seguro respecto al candidato reservado** | `version_type='cierre_canonico'`, `status='success'`, orden de current/id; revisar consistencia de fallback separadamente si se cambia resolución global |
| `app/warehouse/services/track_forecast_center_service.py` | **Seguro con ID resuelto** | histórico: tipos allowlist y current-success; corte seleccionado recibe ID de resolved version |
| `app/warehouse/services/track_excel_export_service.py` | **Seguro** | resuelve versión por fecha y carga filas con IDs explícitos, también exportación sensibilizada |
| `app/warehouse/services/commercial_daily_reports_service.py` | **Seguro contra candidatos** | allowlist exclusiva cierre/base y `current+success`; MTD decreciente ya bloquea |
| `app/warehouse/services/commercial_sales_baseline_service.py` | **Seguro contra candidatos** | cierre/base `current+success` por fecha, luego consulta ID elegido |
| `app/control_center/retention.py` | **Seguro** | `resolve_effective_track_daily_version` + versión explícita |
| `app/control_center/operational_forecast.py` | **Seguro** | `resolve_preferred_track_daily_version` y consulta por ID |
| `app/track_alerts/services/track_alert_region_rules_service.py` | **Seguro** | `resolve_effective_track_daily_version` y loader con ID |
| `app/track_alerts/services/track_regional_operational_service.py` | **Seguro** | corte efectivo, históricos por `resolve_preferred`, carga por IDs |
| `app/track_alerts/services/track_branch_operational_detail_service.py` | **Seguro** | `resolve_preferred`, carga por version_ids resueltos |
| `app/warehouse/services/track_tienda_composition_service.py` | **Seguro** | `resolve_effective_track_daily_version` y query ID |
| `app/services/automation_control/track_base_sla_service.py` | **Seguro** | `version_type='base_nocturna_canonica'` current; solo su mart |
| `app/services/automation_control/track_coverage_service.py` | **Seguro** | `current+success` y tipo cierre/base |
| `app/services/automation_control/freshness_service.py` | **Seguro** | `current+success` y tipo cierre/base |
| `app/warehouse/services/scheduler_priority_service.py::has_active_track_work` | **Vulnerable menor** | `current+pending/running` sin filtro tipo; ahora allowlist de trabajo operativo |
| `app/warehouse/scheduler/track_scheduler_worker.py` | **Seguro** | el claim manual usa `claim_next_pending_track_canonical_close`; automáticos filtran por tipo cierre/base |
| `app/warehouse/services/track_daily_version_service.py::claim_next_pending_track_canonical_close` | **Seguro** | exclusión por `version_type='cierre_canonico'` + estados `pending/running` + noncurrent; `FOR UPDATE SKIP LOCKED` |
| `app/warehouse/services/track_daily_query_version_service.py` | **Seguro; helper añadido** | allowlist de tres tipos, prioridad y fallback; nuevo helper busca última fila por versión publicada efectiva |
| `app/warehouse/services/track_daily_mart_service.py` | **No consumidor público** | builder/refresco escriben DB; prohibido invocar para M3-C1 |
| `app/warehouse/services/track_daily_pipeline_service.py` | **No consumidor público** | pipeline y cierre hacen ingesta/refrescos; prohibido invocar |
| `app/warehouse/backfill/rebuild_track_from_sources.py` | **No consumidor público** | backfill operacional con escrituras; prohibido invocar |
| `app/services/automation_control/timeline_service.py`, `job_read_service.py`, `diagnostic_service.py` | **Metadatos operativos** | no consumen directamente filas de mart; el acceso a versiones requiere distinguir salud de procesos de visibilidad pública; no activan candidatos |
| `app/warehouse/services/scheduler_priority_service.py`, `app/services/automation_control/track_base_sla_service.py` | **Workload/estado** | filtrado por tipos explícitos descrito arriba |

La clasificación **seguro** significa seguro respecto al candidato reservado y al contrato de acceso usado hoy; no certifica todos los aspectos del histórico, relecturas directas por ID privilegiado ni un futuro contrato de publicación multi-fecha. Este documento deberá volver a auditarse si aparece un nuevo lector SQL o frontend/endpoint sin selección autoritativa.

## Pruebas de gate (PostgreSQL 16 exclusivamente sintético)

- Insertar versiones del mismo día: cierre current success, base current success, cierre histórico replaced, candidato success noncurrent, y candidato hipotético con current=true.
- Demostrar resolución `cierre > base` y fallback válido, incluso si el candidato tiene ID más reciente.
- Asegurar que `planning_targets`, KPI capacidad y alertas solo leen el ID efectivo; candidatos con valores intencionalmente enormes no alteran respuesta.
- Demostrar primera venta de tienda inalterada si el único dato positivo de una fecha proviene de candidato.
- Pruebas de scheduler (claim canónico y prioridad de trabajo) no tratan tipo reservado como cierre; historial no descubre fechas cuyo único mart es de candidato.
- No escribir ni copiar candidatos reales. Fixture aislada a esquema aleatorio con DROP solo de ese esquema en PostgreSQL CI.

## Fuera de M3-C1
- No habilitar `kpi_desempeno_candidato` en `create_track_daily_version`, no crear servicio staging F3, no ajustar `TrackDailyMartORM`, no migración.
- No promover, reconstruir, cambiar fuentes, preparar raw KPI productivo ni tocar otros indicadores.
- Todo cambio de semántica de seguridad deberá validarse por revisión independiente antes de M3-C2.
