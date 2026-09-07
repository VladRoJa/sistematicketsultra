from __future__ import annotations

from datetime import date
from typing import Any, Callable

from app.warehouse.services.gasca_job_orchestrator import run_gasca_report_job
from app.warehouse.services.socios_activos_repository import (
    promote_socios_activos_snapshot_canonical,
)


SOCIOS_ACTIVOS_REPORT_TYPE_KEY = "socios_activos"


def sync_socios_activos_daily(
    *,
    business_date: date,
    requested_by: str | None = None,
    job_runner: Callable[..., dict[str, Any]] = run_gasca_report_job,
    canonical_promoter: Callable[..., dict[str, Any]] = (
        promote_socios_activos_snapshot_canonical
    ),
) -> dict[str, Any]:
    result = job_runner(
        report_type_key=SOCIOS_ACTIVOS_REPORT_TYPE_KEY,
        run_mode="scheduled_daily",
        snapshot_kind="daily",
        requested_by=requested_by,
        trigger_source="socios_activos_daily_sync",
        target_business_date=business_date,
        force_ingestion=True,
    )

    ingestion_status = result.get("ingestion_status")
    if ingestion_status not in {"ingested", "already_ingested"}:
        raise RuntimeError(
            "El pipeline Gasca no confirmó la ingesta estructurada "
            "de Socios Activos."
        )

    snapshot_id = result.get("snapshot_id")
    if not isinstance(snapshot_id, int) or snapshot_id <= 0:
        raise RuntimeError(
            "La ingesta de Socios Activos no devolvió snapshot_id válido."
        )

    promotion = canonical_promoter(
        snapshot_id=snapshot_id,
        expected_cutoff_date=business_date,
        expected_snapshot_kind="daily",
        auto_commit=True,
    )

    if promotion.get("is_canonical") is not True:
        raise RuntimeError(
            "La promoción de Socios Activos no confirmó is_canonical=True."
        )

    return {**result, "canonical_promotion": promotion}
