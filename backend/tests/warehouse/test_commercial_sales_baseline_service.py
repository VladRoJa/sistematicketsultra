from datetime import date
from io import BytesIO

import pytest
from openpyxl import load_workbook

from app.warehouse.services import commercial_sales_baseline_service as service


class FakeCatalogQuery:
    def filter_by(self, **kwargs):
        return self
    def all(self):
        return []


def _render(monkeypatch, cutoff, data=None):
    monkeypatch.setattr(service.TrackBranchCatalogORM, "query", FakeCatalogQuery())
    monkeypatch.setattr(service, "_fetch_new_data", lambda cutoff, keys: data or {})
    return load_workbook(BytesIO(service.build_sales_from_baseline(cutoff=cutoff)), data_only=True)


def test_original_history_unchanged(monkeypatch):
    original = service._load_source()
    output = _render(monkeypatch, date(2026, 10, 4))
    for name, first_row, last_row, last_col in [
        ("Semanal", 3, 41, 36),
        ("Totales Mensuales", 3, 32, 22),
    ]:
        for row in range(first_row, last_row + 1):
            for col in range(1, last_col + 1):
                assert output[name].cell(row, col).value == original[name].cell(row, col).value
    assert output["DIARIO 04 OCT"]["C31"].value == original["DIARIO 04 OCT"]["C31"].value


def test_new_daily_cut_requires_previous_mtd(monkeypatch):
    with pytest.raises(service.SalesBaselineError, match="No previous MTD"):
        _render(monkeypatch, date(2026, 10, 5), {date(2026, 10, 5): {"VILLASDELREY": 1}})


def test_baseline_hash_matches_original():
    assert service._load_source()["Semanal"]["A1"].value is not None
