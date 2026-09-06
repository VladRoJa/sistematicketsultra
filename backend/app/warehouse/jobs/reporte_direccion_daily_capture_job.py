from __future__ import annotations

import logging
from datetime import date
from typing import Any

from app.extensions import db
from app.models.warehouse import (
    ReporteDireccionSnapshotORM,
)
from app.warehouse.services.gasca_job_orchestrator import (
    run_gasca_report_job,
)


logger = logging.getLogger(__name__)


JOB_REQUESTED_BY = "reports_scheduler"
JOB_TRIGGER_SOURCE = "reporte_direccion_daily_capture"


class ReporteDireccionDailyCaptureError(RuntimeError):
    """Error base del job diario de Reporte Dirección."""


class ReporteDireccionBusinessDateMismatchError(
    ReporteDireccionDailyCaptureError
):
    """La fecha persistida por el archivo no coincide con la solicitada."""


def _load_persisted_business_date(
    snapshot_id: int,
) -> date:
    snapshot = db.session.get(
        ReporteDireccionSnapshotORM,
        snapshot_id,
    )

    if snapshot is None:
        raise ReporteDireccionDailyCaptureError(
            "No se encontró el snapshot persistido de "
            f"Reporte Dirección id={snapshot_id}."
        )

    return snapshot.business_date


def run_job(
    *,
    business_date: date,
) -> dict[str, Any]:
    """
    Obtiene e ingiere el Reporte Dirección para una fecha de negocio.

    Este job es deliberadamente independiente de Track:
    - no ejecuta el pipeline Track;
    - no modifica versiones Track;
    - no compara métricas;
    - no envía notificaciones.

    La auditoría se construirá sobre el snapshot persistido por este job.
    """
    if not isinstance(business_date, date):
        raise TypeError(
            "business_date debe ser datetime.date."
        )

    logger.info(
        "Reporte Dirección daily capture iniciado. business_date=%s",
        business_date.isoformat(),
    )

    gasca_result = run_gasca_report_job(
        report_type_key="reporte_direccion",
        run_mode="manual_retry",
        snapshot_kind="daily",
        requested_by=JOB_REQUESTED_BY,
        trigger_source=JOB_TRIGGER_SOURCE,
        target_business_date=business_date,
        report_types=(
            "reporte_direccion",
        ),
        force_ingestion=True,
    )

    snapshot_id = gasca_result.get(
        "snapshot_id"
    )

    if not isinstance(snapshot_id, int):
        raise ReporteDireccionDailyCaptureError(
            "La ingesta de Reporte Dirección no devolvió "
            "un snapshot_id válido."
        )

    persisted_business_date = (
        _load_persisted_business_date(
            snapshot_id
        )
    )

    if persisted_business_date != business_date:
        raise ReporteDireccionBusinessDateMismatchError(
            "La fecha persistida por Reporte Dirección "
            "no coincide con la fecha solicitada. "
            f"expected={business_date.isoformat()} "
            f"actual={persisted_business_date.isoformat()} "
            f"snapshot_id={snapshot_id}"
        )

    result = {
        "status": "completed",
        "business_date": (
            persisted_business_date.isoformat()
        ),
        "report_type_key": "reporte_direccion",
        "warehouse_upload_id": gasca_result.get(
            "warehouse_upload_id"
        ),
        "snapshot_id": snapshot_id,
        "ingestion_status": gasca_result.get(
            "ingestion_status"
        ),
        "gasca_job": gasca_result,
    }

    logger.info(
        "Reporte Dirección daily capture terminado. "
        "business_date=%s upload_id=%s snapshot_id=%s "
        "ingestion_status=%s",
        persisted_business_date.isoformat(),
        result["warehouse_upload_id"],
        result["snapshot_id"],
        result["ingestion_status"],
    )

    return result
