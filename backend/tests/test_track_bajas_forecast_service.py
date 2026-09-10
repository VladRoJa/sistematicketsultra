from datetime import date
from decimal import Decimal

from app.warehouse.services import track_bajas_forecast_service as service


class _FakeMappings:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return _FakeMappings(self._rows)


def test_build_bajas_historical_progress_curve_uses_complete_prior_months(monkeypatch):
    captured = {}

    def fake_execute(query, params):
        captured["query"] = str(query)
        captured["params"] = params
        return _FakeResult(
            [
                {
                    "dia_mes": 7,
                    "meses_disponibles": 39,
                    "pct_cierre_p25": Decimal("0.291"),
                    "pct_cierre_mediana": Decimal("0.338"),
                    "pct_cierre_p75": Decimal("0.375"),
                },
                {
                    "dia_mes": 14,
                    "meses_disponibles": 40,
                    "pct_cierre_p25": Decimal("0.519"),
                    "pct_cierre_mediana": Decimal("0.558"),
                    "pct_cierre_p75": Decimal("0.624"),
                },
            ]
        )

    monkeypatch.setattr(service.db.session, "execute", fake_execute)

    curve = service.build_bajas_historical_progress_curve(
        target_month=date(2026, 9, 10),
    )

    assert captured["params"] == {"target_month": date(2026, 9, 1)}
    assert "business_date < :target_month" in captured["query"]
    assert "is_canonical = TRUE" in captured["query"]
    assert "snapshot_kind = 'daily'" in captured["query"]
    assert "UPPER(TRIM(r.sucursal)) <> 'BECA'" in captured["query"]

    assert curve["status"] == "available"
    assert curve["method"] == "chain_daily_median_share_of_month_close"
    assert curve["target_month"] == date(2026, 9, 1)
    assert curve["history_end_exclusive"] == date(2026, 9, 1)

    assert curve["points"][7] == {
        "day": 7,
        "samples_count": 39,
        "p25": Decimal("0.291"),
        "median": Decimal("0.338"),
        "p75": Decimal("0.375"),
    }
    assert curve["points"][14]["median"] == Decimal("0.558")


def test_build_bajas_historical_progress_curve_returns_no_history(monkeypatch):
    monkeypatch.setattr(
        service.db.session,
        "execute",
        lambda *_args, **_kwargs: _FakeResult([]),
    )

    curve = service.build_bajas_historical_progress_curve(
        target_month=date(2026, 9, 1),
    )

    assert curve["status"] == "no_history"
    assert curve["points"] == {}
