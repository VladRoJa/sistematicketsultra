from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable, Iterator

from app.extensions import db
from app.warehouse.services.gasca_job_orchestrator import run_gasca_report_job


SOCIOS_VENCIDOS_REPORT_TYPE_KEY = "socios_vencidos"


class SociosVencidosCarteraSyncError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        last_successful_range: tuple[date, date] | None,
        failed_range: tuple[date, date],
    ) -> None:
        super().__init__(message)
        self.last_successful_range = last_successful_range
        self.failed_range = failed_range


@dataclass(frozen=True, slots=True)
class SociosVencidosBackfillFailure:
    date_from: date
    date_to: date
    error: str


@dataclass(frozen=True, slots=True)
class SociosVencidosBackfillDownload:
    date_from: date
    date_to: date
    warehouse_upload_id: int
    ingestion_status: str
    original_filename: str | None
    file_path: str | None


@dataclass(frozen=True, slots=True)
class SociosVencidosBackfillResult:
    date_from: date
    date_to: date
    chunks_processed: int
    last_successful_range: tuple[date, date] | None
    cleanup_warnings: tuple[str, ...]
    chunks_failed: int = 0
    failed_ranges: tuple[SociosVencidosBackfillFailure, ...] = ()
    downloaded_chunks: tuple[SociosVencidosBackfillDownload, ...] = ()


def iter_calendar_month_ranges(
    *,
    date_from: date,
    date_to: date,
) -> Iterator[tuple[date, date]]:
    if date_from > date_to:
        raise ValueError("date_from no puede ser posterior a date_to.")

    chunk_start = date_from
    while chunk_start <= date_to:
        month_end = date(
            chunk_start.year,
            chunk_start.month,
            monthrange(chunk_start.year, chunk_start.month)[1],
        )
        chunk_end = min(month_end, date_to)
        yield chunk_start, chunk_end
        chunk_start = chunk_end + timedelta(days=1)


def sync_socios_vencidos_period(
    *,
    date_from: date,
    date_to: date,
    run_mode: str,
    requested_by: str | None = None,
    trigger_source: str | None = None,
    download_only: bool = False,
    job_runner: Callable[..., dict[str, Any]] = run_gasca_report_job,
) -> dict[str, Any]:
    if date_from > date_to:
        raise ValueError("date_from no puede ser posterior a date_to.")

    result = job_runner(
        report_type_key=SOCIOS_VENCIDOS_REPORT_TYPE_KEY,
        run_mode=run_mode,
        snapshot_kind="daily",
        requested_by=requested_by,
        trigger_source=trigger_source,
        date_from=date_from,
        date_to=date_to,
        force_ingestion=not download_only,
    )
    if download_only:
        if result.get("ingestion_status") != "skipped":
            raise RuntimeError(
                "El pipeline Gasca no confirmó la descarga sin ingesta del rango."
            )
        if result.get("warehouse_upload_id") is None:
            raise RuntimeError(
                "La descarga sin ingesta no devolvió warehouse_upload_id."
            )
        return result

    if result.get("ingestion_status") not in {"ingested", "already_ingested"}:
        raise RuntimeError(
            "El pipeline Gasca no confirmó la ingesta estructurada del rango."
        )
    if result.get("snapshot_id") is None:
        raise RuntimeError("La ingesta no devolvió snapshot_id de auditoría.")
    return result


def sync_socios_vencidos_daily(
    *,
    business_date: date,
    requested_by: str | None = None,
    job_runner: Callable[..., dict[str, Any]] = run_gasca_report_job,
) -> dict[str, Any]:
    return sync_socios_vencidos_period(
        date_from=business_date,
        date_to=business_date,
        run_mode="scheduled_daily",
        requested_by=requested_by,
        trigger_source="socios_vencidos_daily_sync",
        job_runner=job_runner,
    )


def backfill_socios_vencidos_cartera(
    *,
    date_from: date,
    date_to: date,
    requested_by: str | None = None,
    continue_on_error: bool = False,
    download_only: bool = False,
    job_runner: Callable[..., dict[str, Any]] = run_gasca_report_job,
) -> SociosVencidosBackfillResult:
    last_successful_range: tuple[date, date] | None = None
    cleanup_warnings: list[str] = []
    failed_ranges: list[SociosVencidosBackfillFailure] = []
    downloaded_chunks: list[SociosVencidosBackfillDownload] = []
    chunks_processed = 0

    for chunk_from, chunk_to in iter_calendar_month_ranges(
        date_from=date_from,
        date_to=date_to,
    ):
        try:
            result = sync_socios_vencidos_period(
                date_from=chunk_from,
                date_to=chunk_to,
                run_mode="manual_backfill",
                requested_by=requested_by,
                trigger_source="socios_vencidos_monthly_backfill",
                download_only=download_only,
                job_runner=job_runner,
            )
        except Exception as exc:
            if not continue_on_error:
                raise SociosVencidosCarteraSyncError(
                    str(exc),
                    last_successful_range=last_successful_range,
                    failed_range=(chunk_from, chunk_to),
                ) from exc
            failed_ranges.append(
                SociosVencidosBackfillFailure(
                    date_from=chunk_from,
                    date_to=chunk_to,
                    error=str(exc),
                )
            )
            try:
                db.session.rollback()
            finally:
                db.session.remove()
            continue

        if download_only:
            artifact = result.get("artifact")
            artifact = artifact if isinstance(artifact, dict) else {}
            downloaded_chunks.append(
                SociosVencidosBackfillDownload(
                    date_from=chunk_from,
                    date_to=chunk_to,
                    warehouse_upload_id=result["warehouse_upload_id"],
                    ingestion_status=result["ingestion_status"],
                    original_filename=artifact.get("original_filename"),
                    file_path=artifact.get("file_path"),
                )
            )

        warning = (result.get("ingestion_metadata") or {}).get(
            "cleanup_warning"
        )
        if warning:
            cleanup_warnings.append(
                f"{chunk_from.isoformat()}..{chunk_to.isoformat()}: {warning}"
            )
        last_successful_range = (chunk_from, chunk_to)
        chunks_processed += 1

    return SociosVencidosBackfillResult(
        date_from=date_from,
        date_to=date_to,
        chunks_processed=chunks_processed,
        last_successful_range=last_successful_range,
        cleanup_warnings=tuple(cleanup_warnings),
        chunks_failed=len(failed_ranges),
        failed_ranges=tuple(failed_ranges),
        downloaded_chunks=tuple(downloaded_chunks),
    )
