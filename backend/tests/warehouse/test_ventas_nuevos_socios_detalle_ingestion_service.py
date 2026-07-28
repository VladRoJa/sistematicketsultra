from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from flask import Flask

import app.warehouse.services.ventas_nuevos_socios_detalle_ingestion_service as ingestion


CAPTURED_AT = datetime(
    2026,
    7,
    27,
    15,
    30,
    tzinfo=timezone.utc,
)

def _app() -> Flask:
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


def _upload_payload(
    **overrides,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "warehouse_upload_id": 12134,
        "report_type_key": (
            "ventas_nuevos_socios_detalle"
        ),
        "original_filename": (
            "gasca-new-members.xlsx"
        ),
        "content_type": (
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        ),
        "file_bytes": b"xlsx-placeholder",
        "captured_at": CAPTURED_AT,
        "period_type": "rango",
        "cutoff_date": date(2026, 7, 27),
        "date_from": date(2026, 7, 1),
        "date_to": date(2026, 7, 27),
        "metadata": {
            "source": "routine_control",
        },
    }

    payload.update(overrides)
    return payload


def _repository_result() -> dict[str, object]:
    return {
        "status": "ingested",
        "was_idempotent": False,
        "snapshot_id": 91,
        "warehouse_upload_id": 12134,
        "report_type_key": (
            "ventas_nuevos_socios_detalle"
        ),
        "business_date": "2026-07-27",
        "date_from": "2026-07-01",
        "date_to": "2026-07-27",
        "captured_at": (
            "2026-07-27T15:30:00+00:00"
        ),
        "snapshot_kind": "month_to_date",
        "is_canonical": False,
        "row_count_detected": 1942,
        "row_count_valid": 1942,
        "row_count_rejected": 0,
        "rows_inserted": 1942,
        "metadata": {},
    }


def test_ingest_coordinates_loader_parser_and_repository():
    app = _app()

    parser_calls: list[dict[str, object]] = []
    repository_calls: list[dict[str, object]] = []

    def loader(
        *,
        warehouse_upload_id: int,
    ):
        assert warehouse_upload_id == 12134
        return _upload_payload()

    def branch_resolver(
        sucursal_raw: str,
    ) -> int | None:
        assert sucursal_raw
        return 7

    def parser(**kwargs):
        parser_calls.append(dict(kwargs))

        return {
            "rows": [
                {
                    "id_socio": "123456",
                }
            ],
            "row_count": 1,
            "row_count_valid": 1,
            "row_count_rejected": 0,
        }

    def repository(**kwargs):
        repository_calls.append(dict(kwargs))
        return _repository_result()

    app.config[
        "WAREHOUSE_UPLOAD_LOADER"
    ] = loader

    app.config[
        "WAREHOUSE_VENTAS_NUEVOS_SOCIOS_DETALLE_PARSER"
    ] = parser

    app.config[
        "WAREHOUSE_VENTAS_NUEVOS_SOCIOS_DETALLE_REPOSITORY"
    ] = repository

    app.config[
        "WAREHOUSE_VENTAS_NUEVOS_SOCIOS_DETALLE_BRANCH_RESOLVER"
    ] = branch_resolver

    with app.app_context():
        result = (
            ingestion
            .ingest_ventas_nuevos_socios_detalle_upload(
                warehouse_upload_id=12134,
                snapshot_kind="month_to_date",
                requested_by="routine-control",
                ingestion_source=(
                    "automated_pipeline"
                ),
            )
        )

    assert result["status"] == "ingested"
    assert result["snapshot_id"] == 91
    assert result["rows_inserted"] == 1942

    assert len(parser_calls) == 1
    assert parser_calls[0]["file_bytes"] == (
        b"xlsx-placeholder"
    )

    assert (
        parser_calls[0]["branch_resolver"]
        is branch_resolver
    )

    assert len(repository_calls) == 1

    repository_call = repository_calls[0]

    assert (
        repository_call["warehouse_upload_id"]
        == 12134
    )

    assert (
        repository_call["report_type_key"]
        == "ventas_nuevos_socios_detalle"
    )

    assert repository_call["business_date"] == date(
        2026,
        7,
        27,
    )

    assert repository_call["date_from"] == date(
        2026,
        7,
        1,
    )

    assert repository_call["date_to"] == date(
        2026,
        7,
        27,
    )

    assert (
        repository_call["snapshot_kind"]
        == "month_to_date"
    )

    assert (
        repository_call["requested_by"]
        == "routine-control"
    )

    assert (
        repository_call["ingestion_source"]
        == "automated_pipeline"
    )


def test_invalid_snapshot_kind_is_rejected_before_loader():
    app = _app()
    loader_calls = 0

    def loader(**_kwargs):
        nonlocal loader_calls
        loader_calls += 1
        return _upload_payload()

    app.config[
        "WAREHOUSE_UPLOAD_LOADER"
    ] = loader

    with app.app_context():
        with pytest.raises(
            ingestion
            .VentasNuevosSociosDetalleIngestionError,
            match="snapshot_kind inválido",
        ):
            (
                ingestion
                .ingest_ventas_nuevos_socios_detalle_upload(
                    warehouse_upload_id=12134,
                    snapshot_kind="daily",
                )
            )

    assert loader_calls == 0


def test_wrong_report_type_is_rejected():
    app = _app()

    app.config[
        "WAREHOUSE_UPLOAD_LOADER"
    ] = lambda **_: _upload_payload(
        report_type_key="venta_total"
    )

    with app.app_context():
        with pytest.raises(
            ingestion
            .VentasNuevosSociosDetalleUploadLoadError,
            match="no corresponde",
        ):
            (
                ingestion
                .ingest_ventas_nuevos_socios_detalle_upload(
                    warehouse_upload_id=12134,
                    snapshot_kind="month_to_date",
                )
            )


def test_date_from_must_be_first_day_of_month():
    app = _app()

    app.config[
        "WAREHOUSE_UPLOAD_LOADER"
    ] = lambda **_: _upload_payload(
        date_from=date(2026, 7, 2)
    )

    with app.app_context():
        with pytest.raises(
            ingestion
            .VentasNuevosSociosDetalleUploadLoadError,
            match="primer día del mes",
        ):
            (
                ingestion
                .ingest_ventas_nuevos_socios_detalle_upload(
                    warehouse_upload_id=12134,
                    snapshot_kind="month_to_date",
                )
            )


def test_parser_failure_is_wrapped():
    app = _app()

    def failing_parser(**_kwargs):
        raise ValueError("invalid xlsx")

    app.config[
        "WAREHOUSE_UPLOAD_LOADER"
    ] = lambda **_: _upload_payload()

    app.config[
        "WAREHOUSE_VENTAS_NUEVOS_SOCIOS_DETALLE_PARSER"
    ] = failing_parser

    with app.app_context():
        with pytest.raises(
            ingestion
            .VentasNuevosSociosDetalleParseError,
            match="Falló el parser",
        ):
            (
                ingestion
                .ingest_ventas_nuevos_socios_detalle_upload(
                    warehouse_upload_id=12134,
                    snapshot_kind="month_to_date",
                )
            )


def test_repository_failure_is_wrapped():
    app = _app()

    def parser(**_kwargs):
        return {
            "rows": [
                {
                    "id_socio": "123456",
                }
            ],
            "row_count": 1,
            "row_count_valid": 1,
            "row_count_rejected": 0,
        }

    def failing_repository(**_kwargs):
        raise RuntimeError("database unavailable")

    app.config[
        "WAREHOUSE_UPLOAD_LOADER"
    ] = lambda **_: _upload_payload()

    app.config[
        "WAREHOUSE_VENTAS_NUEVOS_SOCIOS_DETALLE_PARSER"
    ] = parser

    app.config[
        "WAREHOUSE_VENTAS_NUEVOS_SOCIOS_DETALLE_REPOSITORY"
    ] = failing_repository

    with app.app_context():
        with pytest.raises(
            ingestion
            .VentasNuevosSociosDetallePersistError,
            match="Falló la persistencia",
        ):
            (
                ingestion
                .ingest_ventas_nuevos_socios_detalle_upload(
                    warehouse_upload_id=12134,
                    snapshot_kind="month_to_date",
                )
            )
