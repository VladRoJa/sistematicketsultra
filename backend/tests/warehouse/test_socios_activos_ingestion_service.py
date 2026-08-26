from datetime import date, datetime, timezone

from flask import Flask
import pytest

from app.warehouse.services import (
    socios_activos_ingestion_service as service,
)


def _upload_payload(
    *,
    report_type_key="socios_activos",
    period_type="diario",
    cutoff_date=date(2026, 8, 25),
):
    return {
        "warehouse_upload_id": 123,
        "report_type_key": report_type_key,
        "original_filename": (
            "Reporte Socios Activos.xlsx"
        ),
        "storage_path": None,
        "file_bytes": b"fake-xlsx",
        "captured_at": datetime(
            2026,
            8,
            25,
            10,
            0,
            tzinfo=timezone.utc,
        ),
        "period_type": period_type,
        "cutoff_date": cutoff_date,
        "metadata": {},
    }


def _app_with_hooks(
    *,
    loader,
    parser,
    repository,
):
    app = Flask(__name__)

    app.config[
        "WAREHOUSE_UPLOAD_LOADER"
    ] = loader

    app.config[
        "WAREHOUSE_SOCIOS_ACTIVOS_PARSER"
    ] = parser

    app.config[
        "WAREHOUSE_SOCIOS_ACTIVOS_REPOSITORY"
    ] = repository

    return app


def test_ingestion_connects_upload_parser_and_repository():
    observed = {}

    def loader(
        *,
        warehouse_upload_id,
    ):
        observed[
            "loader_upload_id"
        ] = warehouse_upload_id

        return _upload_payload()

    def parser(
        *,
        file_path,
        file_bytes,
    ):
        observed[
            "parser_file_path"
        ] = file_path

        observed[
            "parser_file_bytes"
        ] = file_bytes

        return {
            "rows": [
                {"row_index": 0},
            ],
            "row_count_detected": 1,
            "row_count_valid": 1,
            "row_count_rejected": 0,
            "data_quality_counts": {
                "aplica_kpi_no": 0,
            },
        }

    def repository(
        *,
        warehouse_upload_id,
        report_type_key,
        cutoff_date,
        captured_at,
        snapshot_kind,
        is_canonical,
        parsed_snapshot,
    ):
        observed[
            "repository_upload_id"
        ] = warehouse_upload_id

        observed[
            "repository_report_type"
        ] = report_type_key

        observed[
            "repository_cutoff"
        ] = cutoff_date

        observed[
            "repository_captured_at"
        ] = captured_at

        observed[
            "repository_snapshot_kind"
        ] = snapshot_kind

        observed[
            "repository_is_canonical"
        ] = is_canonical

        observed[
            "repository_parsed_snapshot"
        ] = parsed_snapshot

        return {
            "status": "ingested",
            "was_idempotent": False,
            "snapshot_id": 55,
            "warehouse_upload_id": (
                warehouse_upload_id
            ),
            "report_type_key": (
                report_type_key
            ),
            "cutoff_date": (
                cutoff_date.isoformat()
            ),
            "snapshot_kind": (
                snapshot_kind
            ),
            "is_canonical": (
                is_canonical
            ),
            "row_count_detected": 1,
            "row_count_valid": 1,
            "row_count_rejected": 0,
            "rows_inserted": 1,
        }

    app = _app_with_hooks(
        loader=loader,
        parser=parser,
        repository=repository,
    )

    with app.app_context():
        result = (
            service.ingest_socios_activos_upload(
                warehouse_upload_id=123,
                ingestion_source="unit_test",
            )
        )

    assert observed[
        "loader_upload_id"
    ] == 123

    assert observed[
        "parser_file_path"
    ] is None

    assert observed[
        "parser_file_bytes"
    ] == b"fake-xlsx"

    assert observed[
        "repository_upload_id"
    ] == 123

    assert observed[
        "repository_report_type"
    ] == "socios_activos"

    assert observed[
        "repository_cutoff"
    ] == date(2026, 8, 25)

    assert observed[
        "repository_snapshot_kind"
    ] == "daily"

    assert observed[
        "repository_is_canonical"
    ] is False

    assert result[
        "status"
    ] == "ingested"

    assert result[
        "data_quality_counts"
    ] == {
        "aplica_kpi_no": 0,
    }


def test_upload_document_rejects_wrong_report_type():
    document = (
        service._normalize_upload_document(
            expected_upload_id=123,
            raw_result=_upload_payload(
                report_type_key="socios_vencidos",
            ),
        )
    )

    with pytest.raises(
        service.SociosActivosUploadLoadError,
        match=(
            "no corresponde a socios_activos"
        ),
    ):
        document.validate()


def test_upload_document_rejects_wrong_period_type():
    document = (
        service._normalize_upload_document(
            expected_upload_id=123,
            raw_result=_upload_payload(
                period_type="rango",
            ),
        )
    )

    with pytest.raises(
        service.SociosActivosUploadLoadError,
        match="period_type='diario'",
    ):
        document.validate()


def test_normalize_upload_requires_cutoff_date():
    payload = _upload_payload()

    payload[
        "cutoff_date"
    ] = None

    with pytest.raises(
        ValueError,
        match="cutoff_date es obligatorio",
    ):
        service._normalize_upload_document(
            expected_upload_id=123,
            raw_result=payload,
        )


def test_parser_failure_is_wrapped():
    def loader(
        *,
        warehouse_upload_id,
    ):
        return _upload_payload()

    def parser(
        *,
        file_path,
        file_bytes,
    ):
        raise RuntimeError(
            "parser failure"
        )

    def repository(**kwargs):
        raise AssertionError(
            "repository no debe ejecutarse"
        )

    app = _app_with_hooks(
        loader=loader,
        parser=parser,
        repository=repository,
    )

    with app.app_context():
        with pytest.raises(
            service.SociosActivosParseError,
            match=(
                "Falló el parser "
                "de Socios Activos"
            ),
        ):
            service.ingest_socios_activos_upload(
                warehouse_upload_id=123
            )
