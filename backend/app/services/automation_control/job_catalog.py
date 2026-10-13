"""Catálogo M1-A: qué se ejecuta y de dónde proviene la evidencia.

Metadatos versionados obtenidos de los workers y de los modelos existentes.
No consulta DB/Docker, no determina si un worker está vivo ni dispara jobs.
Los horarios de este catálogo son referencias de código, NO configuración efectiva.
"""
from __future__ import annotations

from dataclasses import dataclass


TIMEZONE = "America/Tijuana"


@dataclass(frozen=True)
class JobSpec:
    key: str
    worker_key: str
    domain: str
    label: str
    schedule_kind: str
    schedule_reference: str
    schedule_env_keys: tuple[str, ...]
    evidence_tables: tuple[str, ...]
    priority_policy: str
    dataset_keys: tuple[str, ...] = ()
    enabled_default: bool | None = None
    manual_run_supported: bool = False
    timezone: str = TIMEZONE


@dataclass(frozen=True)
class DatasetSourceSpec:
    key: str
    evidence_table: str
    business_date_column: str
    selection_contract: str
    producing_job_key: str | None = None


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    label: str
    sources: tuple[DatasetSourceSpec, ...]
    completion_contract: str
    cutoff_reader: str | None
    expected_cutoff_policy: str | None = None
    timezone: str = TIMEZONE


# Los nombres de los trabajos son estables y distintos a los nombres Docker.
# "enabled_default=None" significa que NO se ha leído la configuración efectiva.
_JOBS = (
    JobSpec(
        key="marketing.iventas_sync",
        worker_key="marketing-scheduler",
        domain="marketing",
        label="Sincronización iVentas",
        schedule_kind="DAILY_SLOTS",
        schedule_reference="08:20,12:20,16:20,20:20",
        schedule_env_keys=("MARKETING_SCHEDULER_RUN_TIMES",),
        evidence_tables=("marketing_iventas_sync_runs",),
        priority_policy="SECONDARY_TRACK_WINDOW",
        dataset_keys=("marketing.sales_funnel",),
    ),
    JobSpec(
        key="marketing.meta_sync",
        worker_key="marketing-scheduler",
        domain="marketing",
        label="Sincronización Meta Ads",
        schedule_kind="DAILY_SLOTS",
        schedule_reference="08:20,12:20,16:20,20:20",
        schedule_env_keys=("MARKETING_SCHEDULER_RUN_TIMES",),
        evidence_tables=("marketing_meta_sync_runs",),
        priority_policy="SECONDARY_TRACK_WINDOW",
        dataset_keys=("marketing.sales_funnel",),
    ),
    JobSpec(
        key="marketing.campaign_v2_provider_stats",
        worker_key="marketing-scheduler",
        domain="marketing",
        label="Estadísticas de proveedor Campaign V2",
        schedule_kind="OPTIONAL_INTERVAL",
        schedule_reference="Intervalo condicionado a configuración explícita",
        schedule_env_keys=(
            "CAMPAIGN_V2_PROVIDER_STATS_AUTO_CAPTURE_ENABLED",
            "CAMPAIGN_V2_PROVIDER_STATS_INTERVAL_SECONDS",
        ),
        evidence_tables=("marketing_campaign_v2_provider_stats_snapshots",),
        priority_policy="SECONDARY_TRACK_WINDOW",
        enabled_default=False,
    ),
    JobSpec(
        key="track.preview_operativo",
        worker_key="track-scheduler",
        domain="track",
        label="Track preview operativo",
        schedule_kind="HOURLY_WINDOW",
        schedule_reference="HH:00, 05:00–23:00 (defaults)",
        schedule_env_keys=("TRACK_PREVIEW_START_HOUR", "TRACK_PREVIEW_END_HOUR"),
        evidence_tables=("track_daily_versions", "track_daily_mart"),
        priority_policy="TRACK_PRIMARY",
        dataset_keys=("track.daily",),
    ),
    JobSpec(
        key="track.base_nocturna_canonica",
        worker_key="track-scheduler",
        domain="track",
        label="Track base nocturna",
        schedule_kind="DAILY_TIME",
        schedule_reference="23:30 (default)",
        schedule_env_keys=("TRACK_NIGHTLY_BASE_HOUR", "TRACK_NIGHTLY_BASE_MINUTE"),
        evidence_tables=("track_daily_versions", "track_daily_mart"),
        priority_policy="TRACK_PRIMARY",
        dataset_keys=("track.daily",),
    ),
    JobSpec(
        key="track.base_nocturna_retry",
        worker_key="track-scheduler",
        domain="track",
        label="Reintento de base nocturna",
        schedule_kind="CONDITIONAL_DAILY_TIME",
        schedule_reference="00:30, si falló la base anterior (default)",
        schedule_env_keys=("TRACK_NIGHTLY_RETRY_HOUR", "TRACK_NIGHTLY_RETRY_MINUTE"),
        evidence_tables=("track_daily_versions",),
        priority_policy="TRACK_PRIMARY",
        dataset_keys=("track.daily",),
    ),
    JobSpec(
        key="track.request_cierre_canonico",
        worker_key="track-scheduler",
        domain="track",
        label="Solicitud automática de cierre canónico",
        schedule_kind="CONDITIONAL",
        schedule_reference="Según disponibilidad de agregadoras y lookback",
        schedule_env_keys=("TRACK_CLOSE_LOOKBACK_DAYS",),
        evidence_tables=("track_daily_versions",),
        priority_policy="TRACK_PRIMARY",
        dataset_keys=("track.daily",),
    ),
    JobSpec(
        key="track.pending_manual_canonical_close",
        worker_key="track-scheduler",
        domain="track",
        label="Reclamo de cierres canónicos pendientes",
        schedule_kind="PENDING_REQUEST",
        schedule_reference="Atiende solicitud existente cuando no hay decisión horaria",
        schedule_env_keys=(),
        evidence_tables=("track_daily_versions",),
        priority_policy="TRACK_PRIMARY",
        dataset_keys=("track.daily",),
    ),
    JobSpec(
        key="track.agregadoras_consolidado_export",
        worker_key="track-scheduler",
        domain="track",
        label="Consolidado agregadoras",
        schedule_kind="INTERVAL_CHECK",
        schedule_reference="Chequeo cada 5 minutos (default), publicación condicional",
        schedule_env_keys=("AGREGADORAS_EXPORT_CHECK_MINUTE_STEP",),
        evidence_tables=("warehouse_uploads",),
        priority_policy="TRACK_PRIMARY",
    ),
    JobSpec(
        key="track.warehouse_retention",
        worker_key="track-scheduler",
        domain="warehouse",
        label="Retención Warehouse",
        schedule_kind="DAILY_TIME",
        schedule_reference="01:10 (default)",
        schedule_env_keys=("WAREHOUSE_RETENTION_HOUR", "WAREHOUSE_RETENTION_MINUTE"),
        evidence_tables=(),
        priority_policy="TRACK_PRIMARY",
    ),
    JobSpec(
        key="reports.reactivation_sources_daily",
        worker_key="reports-scheduler",
        domain="reports",
        label="Reactivaciones: fuentes diarias",
        schedule_kind="DAILY_TIME_OPTIONAL",
        schedule_reference="09:00 (default; deshabilitado por defecto)",
        schedule_env_keys=(
            "REACTIVATION_SOURCES_ENABLED",
            "REACTIVATION_SOURCES_RUN_HOUR",
            "REACTIVATION_SOURCES_RUN_MINUTE",
        ),
        evidence_tables=("warehouse_audit_logs",),
        priority_policy="SECONDARY_TRACK_WINDOW",
        enabled_default=False,
    ),
    JobSpec(
        key="reports.reactivation_outcomes_daily",
        worker_key="reports-scheduler",
        domain="reports",
        label="Reactivaciones: resultados diarios",
        schedule_kind="DAILY_TIME_OPTIONAL",
        schedule_reference="09:15 (default; depende de fuentes diarias; deshabilitado por defecto)",
        schedule_env_keys=(
            "REACTIVATION_SOURCES_ENABLED",
            "REACTIVATION_OUTCOMES_RUN_HOUR",
            "REACTIVATION_OUTCOMES_RUN_MINUTE",
        ),
        evidence_tables=("warehouse_audit_logs",),
        priority_policy="SECONDARY_TRACK_WINDOW",
        enabled_default=False,
    ),
    JobSpec(
        key="reports.cobranza_recurrente_rechazados",
        worker_key="reports-scheduler",
        domain="reports",
        label="Cobranza recurrente: rechazados",
        schedule_kind="DAILY_TIME_OPTIONAL",
        schedule_reference="08:00 (default; deshabilitado por defecto)",
        schedule_env_keys=(
            "COBRANZA_RECURRENTE_ENABLED",
            "COBRANZA_RECURRENTE_RUN_HOUR",
            "COBRANZA_RECURRENTE_RUN_MINUTE",
        ),
        evidence_tables=("warehouse_audit_logs",),
        priority_policy="SECONDARY_TRACK_WINDOW",
        enabled_default=False,
    ),
    JobSpec(
        key="reports.commercial_daily_reports",
        worker_key="reports-scheduler",
        domain="reports",
        label="Reportes comerciales diarios",
        schedule_kind="DAILY_TIME_OPTIONAL_GATED",
        schedule_reference=(
            "01:20 nominal (default); primera ventana secundaria posible 05:20 "
            "(HH:20–HH:44 hasta 22:44); corte cerrado del día anterior; "
            "deshabilitado por defecto"
        ),
        schedule_env_keys=(
            "COMMERCIAL_DAILY_REPORTS_ENABLED",
            "COMMERCIAL_DAILY_REPORTS_RUN_HOUR",
            "COMMERCIAL_DAILY_REPORTS_RUN_MINUTE",
        ),
        evidence_tables=("warehouse_audit_logs",),
        priority_policy="SECONDARY_TRACK_WINDOW",
        enabled_default=False,
    ),
    JobSpec(
        key="reports.reporte_direccion_daily_capture",
        worker_key="reports-scheduler",
        domain="reports",
        label="Captura nocturna Reporte de Dirección",
        schedule_kind="NIGHTLY_WINDOW_OPTIONAL",
        schedule_reference="23:20–23:24 (ventana exclusiva; deshabilitado por defecto)",
        schedule_env_keys=("REPORTE_DIRECCION_DAILY_CAPTURE_ENABLED",),
        evidence_tables=("reporte_direccion_snapshots",),
        priority_policy="NIGHTLY_TRACK_WINDOW",
        enabled_default=False,
    ),
    JobSpec(
        key="reports.attendance_daily_capture",
        worker_key="reports-scheduler",
        domain="reports",
        label="Captura diaria de asistencia",
        schedule_kind="DAILY_TIME_OPTIONAL",
        schedule_reference="06:20 (default; deshabilitado por defecto)",
        schedule_env_keys=(
            "ATTENDANCE_DAILY_CAPTURE_ENABLED",
            "ATTENDANCE_DAILY_CAPTURE_RUN_HOUR",
            "ATTENDANCE_DAILY_CAPTURE_RUN_MINUTE",
        ),
        evidence_tables=("warehouse_attendance_runs",),
        priority_policy="SECONDARY_TRACK_WINDOW",
        enabled_default=False,
    ),
    JobSpec(
        key="routine_control.scheduled_pipeline",
        worker_key="routine-control-scheduler",
        domain="routine_control",
        label="Pipeline programado Control de Rutinas",
        schedule_kind="DAILY_SLOTS",
        schedule_reference="09:20, 13:20, 17:20, 21:20 (defaults)",
        schedule_env_keys=(
            "ROUTINE_CONTROL_SCHEDULER_ENABLED",
            "ROUTINE_CONTROL_RUN_TIMES",
            "ROUTINE_CONTROL_TIMEZONE",
        ),
        evidence_tables=("routine_control_pipeline_runs",),
        priority_policy="SECONDARY_TRACK_WINDOW",
        enabled_default=True,
    ),
    JobSpec(
        key="tickets.attachment_cleanup",
        worker_key="ticket-attachment-cleanup",
        domain="tickets",
        label="Limpieza de adjuntos expirados",
        schedule_kind="DAILY_TIME",
        schedule_reference="02:20 (default; puede diferirse si Track está activo)",
        schedule_env_keys=(
            "TICKET_ATTACHMENT_CLEANUP_RUN_TIME",
            "TICKET_ATTACHMENT_CLEANUP_TIMEZONE",
        ),
        evidence_tables=(),
        priority_policy="DEFER_WHEN_TRACK_ACTIVE",
    ),
)


_DATASETS = (
    DatasetSpec(
        key="marketing.sales_funnel",
        label="Funnel Venta Nueva",
        sources=(
            DatasetSourceSpec(
                "iventas",
                "marketing_iventas_sync_runs",
                "date_to",
                "period_key IVENTAS-YYYY-MM; date_from = inicio del mes; status COMPLETED",
                "marketing.iventas_sync",
            ),
            DatasetSourceSpec(
                "meta",
                "marketing_meta_sync_runs",
                "date_to",
                "period_key META-YYYY-MM; date_from = inicio del mes; status COMPLETED",
                "marketing.meta_sync",
            ),
            DatasetSourceSpec(
                "venta_total",
                "venta_total_snapshots",
                "business_date",
                "report_type_key venta_total; snapshot_kind daily; is_canonical",
            ),
            DatasetSourceSpec(
                "ventas_nuevos_socios",
                "ventas_nuevos_socios_detalle_snapshots",
                "business_date",
                "report_type_key ventas_nuevos_socios_detalle; snapshot_kind month_to_date; is_canonical; date_from = inicio del mes",
            ),
            DatasetSourceSpec(
                "kpi_desempeno",
                "kpi_desempeno_snapshots",
                "business_date",
                "report_type_key kpi_desempeno; snapshot_kind daily; is_canonical",
            ),
        ),
        completion_contract="INTERSECTION_OF_REQUIRED_SOURCE_DATES",
        cutoff_reader=(
            "app.services.marketing_sales_funnel_cutoff_service."
            "list_available_funnel_cutoffs"
        ),
        # La regla de SLA/exigibilidad NO está ratificada aún.
        expected_cutoff_policy=None,
    ),
    DatasetSpec(
        key="track.daily",
        label="Track Daily",
        sources=(
            DatasetSourceSpec(
                "track_version",
                "track_daily_versions",
                "track_date",
                "Verificar version_type, status e is_current antes de considerar un cierre",
            ),
            DatasetSourceSpec(
                "track_mart",
                "track_daily_mart",
                "track_date",
                "Validar track_daily_version_id, generation_mode y cobertura por sucursal",
            ),
        ),
        completion_contract="TRACK_VERSION_AND_MART_RECONCILIATION_PENDING",
        cutoff_reader=None,
        expected_cutoff_policy=None,
    ),
)


def get_job_catalog() -> tuple[JobSpec, ...]:
    """Retorna inventario estático sin atribuir salud o habilitación efectiva."""
    return _JOBS


def get_dataset_catalog() -> tuple[DatasetSpec, ...]:
    """Retorna dependencias de los datasets; no inventa un SLA."""
    return _DATASETS


def validate_catalog() -> None:
    """Rechaza claves repetidas y referencias rotas durante QA, sin consultar DB."""
    job_keys = [job.key for job in _JOBS]
    dataset_keys = [dataset.key for dataset in _DATASETS]
    if len(job_keys) != len(set(job_keys)):
        raise ValueError("job_key duplicado")
    if len(dataset_keys) != len(set(dataset_keys)):
        raise ValueError("dataset_key duplicado")

    known_jobs = set(job_keys)
    known_datasets = set(dataset_keys)

    for job in _JOBS:
        if job.manual_run_supported:
            raise ValueError("M1-A no autoriza ejecución manual")
        if not set(job.dataset_keys).issubset(known_datasets):
            raise ValueError(f"dataset desconocido en {job.key}")

    for dataset in _DATASETS:
        source_keys = [source.key for source in dataset.sources]
        if len(source_keys) != len(set(source_keys)):
            raise ValueError(f"source_key duplicado en {dataset.key}")
        for source in dataset.sources:
            if source.producing_job_key and source.producing_job_key not in known_jobs:
                raise ValueError(f"job desconocido en {dataset.key}")
