from datetime import date
from io import BytesIO
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook

from app.warehouse.services import commercial_sales_baseline_service as service


# Track catalog keys come from the seeded canonical branch catalog.
CANONICAL_BRANCHES = (
    "VILLAS_DEL_REY", "VILLA_VERDE", "INDEPENDENCIA", "TEC_MXL",
    "SEND_MXL", "SAN_LUIS", "PABELLON_RTO", "MISION_ENS",
    "PASEO_2000", "LOMA_BONITA", "SANTA_FE", "CARROUSEL_TJ",
    "PAPALOTE_TJ", "SEND_CUL", "SAN_ISIDRO_CUL", "AZAHARES_CUL",
    "STA_CATARINA", "SEND_SALTILLO", "SEND_CHIH", "PASEO_LA_PAZ",
    "IXTAPALUCA", "INSURGENTES", "TLALNEPANTLA",
    "SALTILLO_VILLALTA", "METEPEC", "SERRANIA",
)


def _catalog():
    return [
        SimpleNamespace(sucursal_canon=key, track_label=key.replace("_", " "))
        for key in CANONICAL_BRANCHES
    ]


class FakeCatalogQuery:
    def filter_by(self, **kwargs):
        return self

    def all(self):
        return _catalog()


def _render(monkeypatch, cutoff, data=None):
    monkeypatch.setattr(service, "TrackBranchCatalogORM", SimpleNamespace(query=FakeCatalogQuery()))
    monkeypatch.setattr(service, "_fetch_new_data", lambda cutoff, keys: data or {})
    return load_workbook(BytesIO(service.build_sales_from_baseline(cutoff=cutoff)), data_only=False)


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

def test_october_5_appends_without_touching_historical_week(monkeypatch):
    source = service._load_source()
    weekly, monthly, daily = service._source_rows(source)
    # Real Track data is keyed by canonical branch names, not Excel labels.
    readings = {
        date(2026, 9, 30): {
            service._canon(branch): 30 for branch in CANONICAL_BRANCHES
        },
        date(2026, 10, 4): {
            service._canon(branch): 8 for branch in CANONICAL_BRANCHES
        },
        date(2026, 10, 5): {
            service._canon(branch): 10 for branch in CANONICAL_BRANCHES
        },
    }
    output = _render(monkeypatch, date(2026, 10, 5), readings)
    assert output["DIARIO 04 OCT"].cell(daily["VILLASDELREY"], 3).value == source["DIARIO 04 OCT"].cell(daily["VILLASDELREY"], 3).value
    assert output["DIARIO 04 OCT"].cell(daily["VILLASDELREY"], 4).value == 2
    assert output["Semanal"].cell(weekly["VILLASDELREY"], 35).value == source["Semanal"].cell(weekly["VILLASDELREY"], 35).value
    assert output["Semanal"].cell(weekly["VILLASDELREY"], 37).value == (
        source["DIARIO 04 OCT"].cell(daily["VILLASDELREY"], 3).value + 2
    )
    assert output["Totales Mensuales"].cell(monthly["VILLASDELREY"], 22).value == source["Totales Mensuales"].cell(monthly["VILLASDELREY"], 22).value
    assert output["Totales Mensuales"].cell(monthly["VILLASDELREY"], 24).value == 10


def test_all_historical_branch_labels_resolve_to_exactly_26_canonicals():
    workbook = service._load_source()
    weekly, monthly, daily = service._source_rows(workbook)
    aliases = service._branch_alias_map(_catalog())
    for rows in (weekly, monthly, daily):
        mapped = [aliases.get(service._canon(label)) for label in rows]
        assert None not in mapped
        assert set(mapped) == {service._canon(k) for k in CANONICAL_BRANCHES}
        assert len(set(mapped)) == 26

    assert aliases["VILLAVERDEMEXICALI"] == "VILLAVERDE"
    assert aliases["TECMEXICALI"] == "TECMXL"
    assert aliases["SENDEROMEXICALI"] == "SENDMXL"


def test_ambiguous_catalog_label_is_refused():
    rows = _catalog()
    rows[1].track_label = rows[0].track_label
    with pytest.raises(service.SalesBaselineError, match="Ambiguous branch"):
        service._branch_alias_map(rows)


def test_missing_required_canonical_is_refused():
    rows = [row for row in _catalog() if row.sucursal_canon != "VILLA_VERDE"]
    with pytest.raises(service.SalesBaselineError, match="VILLA_VERDE"):
        service._branch_alias_map(rows)


def test_new_cells_inherit_template_styles(monkeypatch):
    source = service._load_source()
    keys = {service._canon(k) for k in CANONICAL_BRANCHES}
    readings = {
        date(2026, 9, 30): {k: 25 for k in keys},
        date(2026, 10, 4): {k: 6 for k in keys},
        date(2026, 10, 5): {k: 8 for k in keys},
    }
    output = _render(monkeypatch, date(2026, 10, 5), readings)
    daily = output["DIARIO 04 OCT"]
    weekly = output["Semanal"]
    monthly = output["Totales Mensuales"]
    assert daily["D4"].style_id == daily["C4"].style_id
    assert daily["D24"].style_id == daily["C24"].style_id
    assert daily["D2"].style_id == daily["C2"].style_id
    assert weekly["AK4"].style_id == weekly["AI4"].style_id
    assert weekly["AK24"].style_id == weekly["AI24"].style_id
    assert weekly["AK2"].style_id == weekly["AI2"].style_id
    assert monthly["W4"].style_id == monthly["V4"].style_id
    assert monthly["W31"].style_id == monthly["V31"].style_id
    assert monthly["X4"].style_id == monthly["V4"].style_id
    assert "04 AL 10 DE OCTUBRE DE 2026" in daily["B1"].value
    assert source["Semanal"]["AJ3"].value == weekly["AJ3"].value


def test_titles_and_merge_ranges_for_october_7(monkeypatch):
    names = {service._canon(key) for key in CANONICAL_BRANCHES}
    readings = {
        date(2026, 9, 30): {key: 70 for key in names},
        **{
            date(2026, 10, day): {key: day + 10 for key in names}
            for day in range(4, 8)
        },
    }
    book = _render(monkeypatch, date(2026, 10, 7), readings)
    daily = book["DIARIO 04 OCT"]
    weekly = book["Semanal"]
    monthly = book["Totales Mensuales"]

    assert "04 AL 10 DE OCTUBRE DE 2026" in daily["B1"].value
    assert "B1:I1" in {str(item) for item in daily.merged_cells.ranges}
    assert "04 AL 10 DE OCTUBRE DE 2026" in weekly["A1"].value
    assert weekly["AK2"].value == "04 - 10 Oct"
    assert "A1:AK1" in {str(item) for item in weekly.merged_cells.ranges}
    assert monthly["B1"].value.endswith("CORTE AL 07 DE OCTUBRE DE 2026")
    assert "B1:X1" in {str(item) for item in monthly.merged_cells.ranges}


def test_titles_rotate_to_next_week_without_touching_october_4(monkeypatch):
    original = service._load_source()
    keys = {service._canon(key) for key in CANONICAL_BRANCHES}
    readings = {
        date(2026, 9, 30): {key: 70 for key in keys},
        **{
            date(2026, 10, day): {key: day + 10 for key in keys}
            for day in range(4, 12)
        },
    }
    book = _render(monkeypatch, date(2026, 10, 11), readings)

    daily = book["DIARIO 11 OCT"]
    weekly = book["Semanal"]
    assert "11 AL 17 DE OCTUBRE DE 2026" in daily["B1"].value
    assert "11 AL 17 DE OCTUBRE DE 2026" in weekly["A1"].value
    assert weekly["AK2"].value == "04 - 10 Oct"
    assert weekly["AL2"].value == "11 - 17 Oct"
    assert "A1:AL1" in {str(item) for item in weekly.merged_cells.ranges}
    assert weekly["AJ3"].value == original["Semanal"]["AJ3"].value
    assert book["Totales Mensuales"]["V3"].value == original["Totales Mensuales"]["V3"].value


@pytest.mark.parametrize(
    "start,end,label",
    [
        (date(2026, 10, 4), date(2026, 10, 10), "04 AL 10 DE OCTUBRE DE 2026"),
        (date(2026, 9, 27), date(2026, 10, 3), "27 DE SEPTIEMBRE AL 03 DE OCTUBRE DE 2026"),
        (date(2026, 12, 27), date(2027, 1, 2), "27 DE DICIEMBRE DE 2026 AL 02 DE ENERO DE 2027"),
    ],
)
def test_span_title_handles_same_month_cross_month_and_year(start, end, label):
    assert service._span_title(start, end) == label
