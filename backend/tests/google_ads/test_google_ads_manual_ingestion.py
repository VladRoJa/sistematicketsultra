"""Tests the importer does not double-count or overwrite silently."""
from decimal import Decimal
from types import SimpleNamespace
import pytest

from app.warehouse.services import google_ads_daily_ingestion_service as service
from app.warehouse.services.google_ads_daily_xlsx_parser import (
    parse_google_ads_daily_xlsx,
)
from tests.google_ads.test_google_ads_manual_warehouse_import import make_export


def test_reimport_and_conflict(monkeypatch):
    parsed = parse_google_ads_daily_xlsx(make_export())
    upload = SimpleNamespace(id=1, date_from=parsed.date_from,
                             date_to=parsed.date_to, uploaded_by_user_id=7)

    class Session:
        rows = []
        commits = 0

        def query(self, model):
            return self

        def filter(self, *args):
            return self

        def all(self):
            return self.rows

        def add_all(self, rows):
            self.rows.extend(rows)

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rows = []

    session = Session()
    monkeypatch.setattr(service, "db", SimpleNamespace(session=session))
    monkeypatch.setattr(service, "_upload_content", lambda uid: (upload, b"x"))
    monkeypatch.setattr(service, "parse_google_ads_daily_xlsx", lambda raw: parsed)
    monkeypatch.setattr(service, "_customer_id", lambda: "2739125201")
    monkeypatch.setattr(service, "log_warehouse_audit", lambda **kw: None)

    assert service.import_google_ads_warehouse_upload(
        warehouse_upload_id=1)["created_rows"] == 4
    assert service.import_google_ads_warehouse_upload(
        warehouse_upload_id=1)["unchanged_rows"] == 4
    assert len(session.rows) == 4
    session.rows[0].cost = Decimal("999.00")
    with pytest.raises(service.GoogleAdsDailyIngestionError, match="Conflicto"):
        service.import_google_ads_warehouse_upload(warehouse_upload_id=1)
    assert session.commits == 2
