from __future__ import annotations

from typing import Any, Callable

from flask import current_app

from app.warehouse.services.resumen_ventas_ingestion_service import (
    RESUMEN_VENTAS_REPORT_TYPE_KEY,
    ingest_resumen_ventas_upload,
)


class ResumenVentasManualDispatcherError(RuntimeError):
    pass


def register_resumen_ventas_manual_dispatcher_extension(app) -> None:
    base_dispatcher = app.config.get(
        "WAREHOUSE_MANUAL_INGESTION_DISPATCHER"
    )
    if not callable(base_dispatcher):
        raise ResumenVentasManualDispatcherError(
            "El dispatcher manual base debe registrarse antes de Resumen Ventas."
        )

    def dispatch_with_resumen_ventas(
        *,
        warehouse_upload_id: int,
        requested_by: str | None = None,
        ingestion_source: str | None = None,
    ) -> dict[str, Any]:
        base_result = base_dispatcher(
            warehouse_upload_id=warehouse_upload_id,
            requested_by=requested_by,
            ingestion_source=ingestion_source,
        )
        report_type_key = str(
            base_result.get("report_type_key") or ""
        ).strip()
        if report_type_key != RESUMEN_VENTAS_REPORT_TYPE_KEY:
            return base_result

        ingestor = _resolve_ingestor()
        result = ingestor(
            warehouse_upload_id=warehouse_upload_id,
            requested_by=requested_by,
            ingestion_source=ingestion_source,
        )
        if not isinstance(result, dict):
            raise ResumenVentasManualDispatcherError(
                "El ingestor de resumen_ventas debe devolver dict."
            )
        return {
            "ingestion_status": result.get("status", "ingested"),
            "warehouse_upload_id": warehouse_upload_id,
            "report_type_key": report_type_key,
            "structured_result": result,
        }

    app.config["WAREHOUSE_MANUAL_INGESTION_DISPATCHER"] = (
        dispatch_with_resumen_ventas
    )


def _resolve_ingestor() -> Callable[..., Any]:
    configured = current_app.config.get(
        "WAREHOUSE_RESUMEN_VENTAS_INGESTOR"
    )
    return (
        configured
        if callable(configured)
        else ingest_resumen_ventas_upload
    )
