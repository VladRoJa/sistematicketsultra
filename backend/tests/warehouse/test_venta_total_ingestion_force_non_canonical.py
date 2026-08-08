from datetime import date, datetime, timezone

import pytest

import app.warehouse.services.venta_total_ingestion_service as service


def _build_upload_document():
    return service.WarehouseUploadDocument(
        warehouse_upload_id=501,
        report_type_key="venta_total",
        original_filename="venta_total.xlsx",
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        file_path="fake.xlsx",
        captured_at=datetime(
            2026,
            8,
            7,
            18,
            0,
            tzinfo=timezone.utc,
        ),
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
        metadata={},
    )


def _parsed_snapshot():
    return {
        "rows": [{"row_index": 1}],
        "row_count": 1,
        "row_count_valid": 1,
        "row_count_rejected": 0,
    }


def _repository_result(*, is_canonical):
    return {
        "status": "ingested",
        "was_idempotent": False,
        "snapshot_id": 777,
        "warehouse_upload_id": 501,
        "report_type_key": "venta_total",
        "business_date": "2026-07-31",
        "captured_at": "2026-08-07T18:00:00+00:00",
        "snapshot_kind": "daily",
        "is_canonical": is_canonical,
        "row_count_detected": 1,
        "row_count_valid": 1,
        "row_count_rejected": 0,
        "rows_inserted": 1,
        "metadata": {},
    }


def test_force_non_canonical_overrides_global_canonicality_resolver(
    monkeypatch: pytest.MonkeyPatch,
):
    captured = {}

    def global_resolver(**_kwargs):
        return {
            "is_canonical": True,
            "replace_existing_canonical": True,
            "reason": "global_wants_canonical",
        }

    def fake_repository(
        *,
        canonicality_resolver,
        **_kwargs,
    ):
        decision = canonicality_resolver(
            business_date=date(2026, 7, 31),
            snapshot_kind="daily",
            existing_canonical_snapshot=None,
            report_type_key="venta_total",
            captured_at=datetime(
                2026,
                8,
                7,
                18,
                0,
                tzinfo=timezone.utc,
            ),
            row_count_valid=1,
            row_count_rejected=0,
        )

        captured["decision"] = decision

        return _repository_result(
            is_canonical=bool(decision["is_canonical"])
        )

    monkeypatch.setattr(
        service,
        "_load_upload_document",
        lambda **_kwargs: _build_upload_document(),
    )
    monkeypatch.setattr(
        service,
        "_parse_upload_document",
        lambda **_kwargs: _parsed_snapshot(),
    )
    monkeypatch.setattr(
        service,
        "_resolve_repository",
        lambda: fake_repository,
    )
    monkeypatch.setattr(
        service,
        "_resolve_optional_canonicality_resolver",
        lambda: global_resolver,
    )
    monkeypatch.setattr(
        service,
        "_resolve_optional_advisory_lock_key",
        lambda **_kwargs: None,
    )

    result = service.ingest_venta_total_upload(
        warehouse_upload_id=501,
        snapshot_kind="daily",
        requested_by="admin_test",
        ingestion_source="manual_canonical_close",
        force_non_canonical=True,
    )

    assert captured["decision"] == {
        "is_canonical": False,
        "replace_existing_canonical": False,
        "reason": "explicit_force_non_canonical",
    }

    assert result["snapshot_id"] == 777
    assert result["business_date"] == "2026-07-31"
    assert result["is_canonical"] is False


def test_default_ingestion_keeps_normal_canonicality_resolver(
    monkeypatch: pytest.MonkeyPatch,
):
    captured = {}

    def global_resolver(**_kwargs):
        return {
            "is_canonical": True,
            "replace_existing_canonical": True,
            "reason": "normal_canonicality",
        }

    def fake_repository(
        *,
        canonicality_resolver,
        **_kwargs,
    ):
        decision = canonicality_resolver(
            business_date=date(2026, 7, 31),
            snapshot_kind="daily",
            existing_canonical_snapshot=None,
            report_type_key="venta_total",
            captured_at=datetime(
                2026,
                8,
                7,
                18,
                0,
                tzinfo=timezone.utc,
            ),
            row_count_valid=1,
            row_count_rejected=0,
        )

        captured["decision"] = decision

        return _repository_result(
            is_canonical=bool(decision["is_canonical"])
        )

    monkeypatch.setattr(
        service,
        "_load_upload_document",
        lambda **_kwargs: _build_upload_document(),
    )
    monkeypatch.setattr(
        service,
        "_parse_upload_document",
        lambda **_kwargs: _parsed_snapshot(),
    )
    monkeypatch.setattr(
        service,
        "_resolve_repository",
        lambda: fake_repository,
    )
    monkeypatch.setattr(
        service,
        "_resolve_optional_canonicality_resolver",
        lambda: global_resolver,
    )
    monkeypatch.setattr(
        service,
        "_resolve_optional_advisory_lock_key",
        lambda **_kwargs: None,
    )

    result = service.ingest_venta_total_upload(
        warehouse_upload_id=501,
        snapshot_kind="daily",
        requested_by="normal_test",
        ingestion_source="normal_ingestion",
    )

    assert captured["decision"] == {
        "is_canonical": True,
        "replace_existing_canonical": True,
        "reason": "normal_canonicality",
    }

    assert result["snapshot_id"] == 777
    assert result["is_canonical"] is True
