from datetime import datetime, timezone
from types import SimpleNamespace

from flask import Flask

import app.routes.warehouse_routes as routes


class _FakeQuery:
    def __init__(self, upload):
        self.upload = upload

    def options(self, *_):
        return self

    def filter_by(self, **_):
        return self

    def first(self):
        return self.upload


def _call_download(monkeypatch, upload):
    app = Flask(__name__)
    app.config["TESTING"] = True
    fake_model = SimpleNamespace(
        query=_FakeQuery(upload),
        report_type=object(),
    )
    monkeypatch.setattr(routes, "WarehouseUploadORM", fake_model)
    monkeypatch.setattr(routes, "joinedload", lambda *_: None)
    monkeypatch.setattr(routes, "require_warehouse_view", lambda: None)

    endpoint = routes.warehouse_download_upload
    unwrapped = getattr(endpoint, "__wrapped__", None)
    assert unwrapped is not None

    with app.test_request_context("/api/warehouse/uploads/5/download"):
        return unwrapped(5)


def test_deleted_structured_source_returns_explicit_410(monkeypatch):
    deleted_at = datetime(2026, 8, 27, 12, tzinfo=timezone.utc)
    upload = SimpleNamespace(source_file_deleted_at=deleted_at)

    response, status_code = _call_download(monkeypatch, upload)
    payload = response.get_json()

    assert status_code == 410
    assert payload["retention_status"] == (
        "SOURCE_DELETED_AFTER_STRUCTURED_SUCCESS"
    )
    assert payload["source_file_deleted_at"] == deleted_at.isoformat()


def test_missing_unmarked_source_keeps_generic_404(monkeypatch):
    upload = SimpleNamespace(
        source_file_deleted_at=None,
        stored_path="warehouse/missing",
        stored_filename="missing.xlsx",
    )

    response, status_code = _call_download(monkeypatch, upload)

    assert status_code == 404
    assert response.get_json()["error"] == "Archivo no encontrado"
