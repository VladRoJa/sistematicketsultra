-- WSO-01 / Solo lectura: referencias entrantes a los 2,061 uploads Corte de Caja.
-- Ejecutar en DBeaver antes de autorizar la limpieza de warehouse_uploads.
-- No contiene DML, no recorre las filas de corte_caja_snapshot_rows.
-- Refleja las 23 FKs obtenidas en pg_constraint al 2026-11-02.
-- Si cualquiera de los BLOCKER tiene referencias > 0, DETENER eliminación de uploads.
-- Audits y corte_caja_snapshots se esperan: requieren tratamiento explícito.
WITH target AS MATERIALIZED (
    SELECT u.id
    FROM public.warehouse_uploads u
    JOIN public.warehouse_report_types rt ON rt.id = u.report_type_id
    WHERE rt.key = 'corte_caja'
), refs AS (
    SELECT 'warehouse_audit_logs.upload_id' AS dependencia,
           'EXPECTED_AUDIT' AS tipo,
           COUNT(*)::bigint AS referencias
    FROM target t
    JOIN public.warehouse_audit_logs d ON d.upload_id = t.id
    UNION ALL
    SELECT 'reporte_direccion_snapshots.warehouse_upload_id' AS dependencia,
           'BLOCKER' AS tipo,
           COUNT(*)::bigint AS referencias
    FROM target t
    JOIN public.reporte_direccion_snapshots d ON d.warehouse_upload_id = t.id
    UNION ALL
    SELECT 'kpi_desempeno_snapshots.warehouse_upload_id' AS dependencia,
           'BLOCKER' AS tipo,
           COUNT(*)::bigint AS referencias
    FROM target t
    JOIN public.kpi_desempeno_snapshots d ON d.warehouse_upload_id = t.id
    UNION ALL
    SELECT 'kpi_ventas_nuevos_socios_snapshots.warehouse_upload_id' AS dependencia,
           'BLOCKER' AS tipo,
           COUNT(*)::bigint AS referencias
    FROM target t
    JOIN public.kpi_ventas_nuevos_socios_snapshots d ON d.warehouse_upload_id = t.id
    UNION ALL
    SELECT 'corte_caja_snapshots.warehouse_upload_id' AS dependencia,
           'EXPECTED_BEFORE_MIGRATION' AS tipo,
           COUNT(*)::bigint AS referencias
    FROM target t
    JOIN public.corte_caja_snapshots d ON d.warehouse_upload_id = t.id
    UNION ALL
    SELECT 'cargos_recurrentes_snapshots.warehouse_upload_id' AS dependencia,
           'BLOCKER' AS tipo,
           COUNT(*)::bigint AS referencias
    FROM target t
    JOIN public.cargos_recurrentes_snapshots d ON d.warehouse_upload_id = t.id
    UNION ALL
    SELECT 'venta_total_snapshots.warehouse_upload_id' AS dependencia,
           'BLOCKER' AS tipo,
           COUNT(*)::bigint AS referencias
    FROM target t
    JOIN public.venta_total_snapshots d ON d.warehouse_upload_id = t.id
    UNION ALL
    SELECT 'planning_target_batches.source_upload_id' AS dependencia,
           'BLOCKER' AS tipo,
           COUNT(*)::bigint AS referencias
    FROM target t
    JOIN public.planning_target_batches d ON d.source_upload_id = t.id
    UNION ALL
    SELECT 'internal_document_versions.warehouse_upload_id' AS dependencia,
           'BLOCKER' AS tipo,
           COUNT(*)::bigint AS referencias
    FROM target t
    JOIN public.internal_document_versions d ON d.warehouse_upload_id = t.id
    UNION ALL
    SELECT 'opening_task_document_links.warehouse_upload_id' AS dependencia,
           'BLOCKER' AS tipo,
           COUNT(*)::bigint AS referencias
    FROM target t
    JOIN public.opening_task_document_links d ON d.warehouse_upload_id = t.id
    UNION ALL
    SELECT 'routine_control_provider_runs.raw_warehouse_upload_id' AS dependencia,
           'BLOCKER' AS tipo,
           COUNT(*)::bigint AS referencias
    FROM target t
    JOIN public.routine_control_provider_runs d ON d.raw_warehouse_upload_id = t.id
    UNION ALL
    SELECT 'ventas_nuevos_socios_detalle_snapshots.warehouse_upload_id' AS dependencia,
           'BLOCKER' AS tipo,
           COUNT(*)::bigint AS referencias
    FROM target t
    JOIN public.ventas_nuevos_socios_detalle_snapshots d ON d.warehouse_upload_id = t.id
    UNION ALL
    SELECT 'socios_vencidos_snapshots.warehouse_upload_id' AS dependencia,
           'BLOCKER' AS tipo,
           COUNT(*)::bigint AS referencias
    FROM target t
    JOIN public.socios_vencidos_snapshots d ON d.warehouse_upload_id = t.id
    UNION ALL
    SELECT 'socios_activos_snapshots.warehouse_upload_id' AS dependencia,
           'BLOCKER' AS tipo,
           COUNT(*)::bigint AS referencias
    FROM target t
    JOIN public.socios_activos_snapshots d ON d.warehouse_upload_id = t.id
    UNION ALL
    SELECT 'google_ads_daily_metrics.source_upload_id' AS dependencia,
           'BLOCKER' AS tipo,
           COUNT(*)::bigint AS referencias
    FROM target t
    JOIN public.google_ads_daily_metrics d ON d.source_upload_id = t.id
    UNION ALL
    SELECT 'google_ads_ad_group_daily_metrics.source_upload_id' AS dependencia,
           'BLOCKER' AS tipo,
           COUNT(*)::bigint AS referencias
    FROM target t
    JOIN public.google_ads_ad_group_daily_metrics d ON d.source_upload_id = t.id
    UNION ALL
    SELECT 'google_ads_branch_identity_mappings.source_upload_id' AS dependencia,
           'BLOCKER' AS tipo,
           COUNT(*)::bigint AS referencias
    FROM target t
    JOIN public.google_ads_branch_identity_mappings d ON d.source_upload_id = t.id
    UNION ALL
    SELECT 'google_ads_branch_approval_versions.source_ad_group_upload_id' AS dependencia,
           'BLOCKER' AS tipo,
           COUNT(*)::bigint AS referencias
    FROM target t
    JOIN public.google_ads_branch_approval_versions d ON d.source_ad_group_upload_id = t.id
    UNION ALL
    SELECT 'google_ads_branch_approval_versions.source_campaign_upload_id' AS dependencia,
           'BLOCKER' AS tipo,
           COUNT(*)::bigint AS referencias
    FROM target t
    JOIN public.google_ads_branch_approval_versions d ON d.source_campaign_upload_id = t.id
    UNION ALL
    SELECT 'google_ads_m6_daily_publications.ad_group_upload_id' AS dependencia,
           'BLOCKER' AS tipo,
           COUNT(*)::bigint AS referencias
    FROM target t
    JOIN public.google_ads_m6_daily_publications d ON d.ad_group_upload_id = t.id
    UNION ALL
    SELECT 'google_ads_m6_daily_publications.campaign_upload_id' AS dependencia,
           'BLOCKER' AS tipo,
           COUNT(*)::bigint AS referencias
    FROM target t
    JOIN public.google_ads_m6_daily_publications d ON d.campaign_upload_id = t.id
    UNION ALL
    SELECT 'google_ads_m6_correction_cases.ad_group_upload_id' AS dependencia,
           'BLOCKER' AS tipo,
           COUNT(*)::bigint AS referencias
    FROM target t
    JOIN public.google_ads_m6_correction_cases d ON d.ad_group_upload_id = t.id
    UNION ALL
    SELECT 'google_ads_m6_correction_cases.campaign_upload_id' AS dependencia,
           'BLOCKER' AS tipo,
           COUNT(*)::bigint AS referencias
    FROM target t
    JOIN public.google_ads_m6_correction_cases d ON d.campaign_upload_id = t.id
)
SELECT dependencia, tipo, referencias,
       CASE
           WHEN tipo = 'BLOCKER' AND referencias > 0 THEN 'BLOQUEA_RETIRO'
           WHEN tipo = 'BLOCKER' THEN 'SIN_REFERENCIAS'
           ELSE 'REQUIERE_TRATAMIENTO'
       END AS decision
FROM refs
ORDER BY CASE WHEN tipo = 'BLOCKER' AND referencias > 0 THEN 0
              WHEN tipo != 'BLOCKER' THEN 1 ELSE 2 END,
         dependencia;
