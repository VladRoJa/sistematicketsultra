from types import SimpleNamespace

import pytest
from flask import Flask

import app.routes.track_routes as routes


def _build_app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


def _call_unwrapped_daily_mart_endpoint():
    endpoint = routes.get_track_daily_mart_endpoint
    wrapped = getattr(endpoint, "__wrapped__", None)

    if wrapped is None:
        raise AssertionError(
            "Se esperaba @jwt_required() sobre el endpoint."
        )

    return wrapped()


class _FakeTrackDailyMartQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter_by(self, **kwargs):
        assert kwargs == {"track_daily_version_id": 3659}
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        return list(self._rows)


def test_daily_mart_operational_only_preserves_raw_default_and_filters_operational_view(
    monkeypatch: pytest.MonkeyPatch,
):
    app = _build_app()

    active_row = SimpleNamespace(sucursal_canon="ACTIVA_1")
    opening_row = SimpleNamespace(sucursal_canon="EN_APERTURA_1")
    rows = [active_row, opening_row]

    resolved_version = SimpleNamespace(
        id=3659,
        version_type="cierre_canonico",
        status="success",
        generated_at_utc=None,
        started_at_utc=None,
        finished_at_utc=None,
    )

    fake_model = SimpleNamespace(
        query=_FakeTrackDailyMartQuery(rows),
        sucursal_canon=SimpleNamespace(
            asc=lambda: "sucursal_canon ASC",
        ),
    )

    monkeypatch.setattr(
        routes,
        "_require_track_read_role",
        lambda: None,
    )
    monkeypatch.setattr(
        routes,
        "resolve_effective_track_daily_version",
        lambda **_kwargs: resolved_version,
    )
    monkeypatch.setattr(
        routes,
        "TrackDailyMartORM",
        fake_model,
    )
    monkeypatch.setattr(
        routes,
        "_serialize_track_daily_mart_row",
        lambda row: {"sucursal_canon": row.sucursal_canon},
    )

    # Este símbolo todavía no existe en producción.
    # Se define aquí para fijar el contrato esperado del siguiente cambio.
    monkeypatch.setattr(
        routes,
        "load_operational_track_branch_canons",
        lambda: {"ACTIVA_1"},
        raising=False,
    )

    with app.test_request_context(
        "/api/track/daily-mart"
        "?track_date=2026-09-06"
        "&generation_mode=official_closed_day",
        method="GET",
    ):
        response, status_code = _call_unwrapped_daily_mart_endpoint()

    payload = response.get_json()

    assert status_code == 200
    assert payload["total_rows"] == 2
    assert [row["sucursal_canon"] for row in payload["rows"]] == [
        "ACTIVA_1",
        "EN_APERTURA_1",
    ]

    with app.test_request_context(
        "/api/track/daily-mart"
        "?track_date=2026-09-06"
        "&generation_mode=official_closed_day"
        "&operational_only=true",
        method="GET",
    ):
        response, status_code = _call_unwrapped_daily_mart_endpoint()

    payload = response.get_json()

    assert status_code == 200
    assert payload["total_rows"] == 1
    assert [row["sucursal_canon"] for row in payload["rows"]] == [
        "ACTIVA_1",
    ]

def _call_unwrapped_daily_mart_export_endpoint():
    endpoint = routes.export_track_daily_mart_xlsx_endpoint
    wrapped = getattr(endpoint, "__wrapped__", None)

    if wrapped is None:
        raise AssertionError(
            "Se esperaba @jwt_required() sobre el endpoint."
        )

    return wrapped()


def test_daily_mart_export_operational_only_preserves_raw_default_and_filters_operational_view(
    monkeypatch: pytest.MonkeyPatch,
):
    app = _build_app()

    active_row = SimpleNamespace(sucursal_canon="ACTIVA_1")
    opening_row = SimpleNamespace(sucursal_canon="EN_APERTURA_1")
    rows = [active_row, opening_row]

    resolved_version = SimpleNamespace(id=3659)
    captured_exports = []

    fake_model = SimpleNamespace(
        query=_FakeTrackDailyMartQuery(rows),
        sucursal_canon=SimpleNamespace(
            asc=lambda: "sucursal_canon ASC",
        ),
    )

    monkeypatch.setattr(
        routes,
        "_require_track_read_role",
        lambda: None,
    )
    monkeypatch.setattr(
        routes,
        "resolve_effective_track_daily_version",
        lambda **_kwargs: resolved_version,
    )
    monkeypatch.setattr(
        routes,
        "TrackDailyMartORM",
        fake_model,
    )
    monkeypatch.setattr(
        routes,
        "load_operational_track_branch_canons",
        lambda: {"ACTIVA_1"},
    )

    def fake_build_excel(**kwargs):
        captured_exports.append(
            [row.sucursal_canon for row in kwargs["rows"]]
        )
        return b"fake-xlsx"

    monkeypatch.setattr(
        routes,
        "build_track_daily_mart_excel",
        fake_build_excel,
    )
    monkeypatch.setattr(
        routes,
        "send_file",
        lambda *_args, **_kwargs: "fake-response",
    )

    with app.test_request_context(
        "/api/track/daily-mart/export-xlsx"
        "?track_date=2026-09-06"
        "&generation_mode=official_closed_day",
        method="GET",
    ):
        response = _call_unwrapped_daily_mart_export_endpoint()

    assert response == "fake-response"
    assert captured_exports[-1] == [
        "ACTIVA_1",
        "EN_APERTURA_1",
    ]

    with app.test_request_context(
        "/api/track/daily-mart/export-xlsx"
        "?track_date=2026-09-06"
        "&generation_mode=official_closed_day"
        "&operational_only=true",
        method="GET",
    ):
        response = _call_unwrapped_daily_mart_export_endpoint()

    assert response == "fake-response"
    assert captured_exports[-1] == [
        "ACTIVA_1",
    ]