"""Regresión: el histórico del Warehouse relaciona IDs de uploads y snapshots.

Pruebas de solo lectura, sin credenciales ni datos productivos.
"""
from datetime import date
from types import SimpleNamespace

from flask import Flask
from sqlalchemy import column

from app.routes import warehouse_routes as routes


class _FakeUploadQuery:
    def __init__(self, upload):
        self.upload = upload
        self.predicates = []

    def options(self, *args):
        return self

    def filter(self, predicate):
        self.predicates.append(predicate)
        return self

    def order_by(self, *args):
        return self

    def paginate(self, **kwargs):
        return SimpleNamespace(
            items=[self.upload],
            page=kwargs["page"],
            per_page=kwargs["per_page"],
            total=1,
            pages=1,
            has_next=False,
            has_prev=False,
        )


def test_numeric_search_matches_upload_or_snapshot_id(monkeypatch):
    upload = SimpleNamespace(
        id=20434,
        report_type=SimpleNamespace(key="kpi_desempeno"),
    )
    fake_query = _FakeUploadQuery(upload)
    fake_upload_model = SimpleNamespace(
        query=fake_query,
        id=column("warehouse_id"),
        original_filename=column("original_filename"),
        stored_filename=column("stored_filename"),
        created_at=column("created_at"),
        report_type=object(),
        source=object(),
        family=object(),
        operational_role=object(),
        uploader=object(),
    )
    fake_snapshot_model = SimpleNamespace(
        id=column("structured_snapshot_id"),
        warehouse_upload_id=column("warehouse_upload_id"),
    )
    monkeypatch.setattr(routes, "WarehouseUploadORM", fake_upload_model)
    monkeypatch.setattr(routes, "WAREHOUSE_UPLOAD_SNAPSHOT_MODELS", (fake_snapshot_model,))
    monkeypatch.setattr(routes, "joinedload", lambda *_: None)
    monkeypatch.setattr(routes, "require_warehouse_view", lambda: None)
    monkeypatch.setattr(
        routes,
        "_load_upload_snapshot_metadata",
        lambda ids: {
            (20434, "kpi_desempeno"): {
                "snapshot_id": 3969,
                "snapshot_is_canonical": True,
                "snapshot_business_date": "2026-09-30",
            }
        },
    )
    monkeypatch.setattr(
        routes,
        "_serialize_warehouse_upload_item",
        lambda item, snapshots: {
            "id": item.id,
            **routes._upload_snapshot_payload(item, snapshots),
        },
    )

    app = Flask(__name__)
    with app.test_request_context(
        "/api/warehouse/uploads?date_preset=all&search=3969"
    ):
        response, code = routes.warehouse_list_uploads.__wrapped__()

    assert code == 200
    item = response.get_json()["items"][0]
    assert item["id"] == 20434
    assert item["snapshot_id"] == 3969
    assert item["snapshot_is_canonical"] is True

    predicate_sql = str(fake_query.predicates[-1])
    assert "warehouse_id" in predicate_sql
    assert "structured_snapshot_id" in predicate_sql
    assert "warehouse_upload_id" in predicate_sql
    assert "original_filename" in predicate_sql


def test_snapshot_payload_is_independent_from_document_status():
    upload = SimpleNamespace(
        id=20434,
        status="ACTIVE",
        report_type=SimpleNamespace(key="kpi_desempeno"),
    )
    snapshots = {
        (20434, "kpi_desempeno"): {
            "snapshot_id": 3969,
            "snapshot_is_canonical": True,
            "snapshot_business_date": date(2026, 9, 30).isoformat(),
        }
    }
    assert routes._upload_snapshot_payload(upload, snapshots) == snapshots[
        (20434, "kpi_desempeno")
    ]

    other_upload = SimpleNamespace(
        id=20435,
        status="ACTIVE",
        report_type=SimpleNamespace(key="unstructured_file"),
    )
    assert routes._upload_snapshot_payload(other_upload, snapshots) == {
        "snapshot_id": None,
        "snapshot_is_canonical": None,
        "snapshot_business_date": None,
    }
