from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from flask import Flask

import app.routes.track_routes as routes


def _build_app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


def _call_unwrapped_endpoint():
    endpoint = routes.request_track_canonical_close_endpoint
    wrapped = getattr(endpoint, "__wrapped__", None)

    if wrapped is None:
        raise AssertionError(
            "Se esperaba @jwt_required() sobre el endpoint."
        )

    return wrapped()


def test_request_canonical_close_accepts_past_ready_date(
    monkeypatch: pytest.MonkeyPatch,
):
    app = _build_app()
    calls = []

    monkeypatch.setattr(
        routes,
        "_require_track_admin_role",
        lambda: None,
    )

    monkeypatch.setattr(
        routes,
        "_today_tijuana",
        lambda: date(2026, 8, 7),
    )

    monkeypatch.setattr(
        routes,
        "get_jwt_identity",
        lambda: 123,
    )

    def fake_readiness(*, business_date):
        assert business_date == date(2026, 7, 31)
        calls.append(("readiness", business_date))

        return {
            "is_ready": True,
            "business_date": "2026-07-31",
        }

    monkeypatch.setattr(
        routes,
        "resolve_exact_agregadoras_snapshot_status_for_date",
        fake_readiness,
    )

    request_version = SimpleNamespace(
        id=777,
        version_type="cierre_canonico",
        status="pending",
        is_current=False,
        base_version_id=700,
        replaces_version_id=650,
        retry_count=0,
        requested_by="123",
        trigger_source="api_manual_canonical_close",
    )

    def fake_request_close(
        *,
        track_date,
        requested_by,
        trigger_source,
        auto_commit,
    ):
        assert track_date == date(2026, 7, 31)
        assert requested_by == "123"
        assert trigger_source == "api_manual_canonical_close"
        assert auto_commit is True

        calls.append(
            (
                "request",
                track_date,
                requested_by,
                trigger_source,
                auto_commit,
            )
        )

        return request_version

    monkeypatch.setattr(
        routes,
        "request_track_canonical_close",
        fake_request_close,
    )

    with app.test_request_context(
        "/api/track/request-canonical-close",
        method="POST",
        json={"track_date": "2026-07-31"},
    ):
        response, status_code = _call_unwrapped_endpoint()

    payload = response.get_json()

    assert status_code == 202
    assert payload["status"] == "accepted"
    assert payload["track_date"] == "2026-07-31"

    assert payload["request"] == {
        "id": 777,
        "version_type": "cierre_canonico",
        "status": "pending",
        "is_current": False,
        "base_version_id": 700,
        "replaces_version_id": 650,
        "retry_count": 0,
        "requested_by": "123",
        "trigger_source": "api_manual_canonical_close",
    }

    assert calls == [
        ("readiness", date(2026, 7, 31)),
        (
            "request",
            date(2026, 7, 31),
            "123",
            "api_manual_canonical_close",
            True,
        ),
    ]


@pytest.mark.parametrize(
    "track_date",
    [
        "2026-08-07",
        "2026-08-08",
    ],
)
def test_request_canonical_close_rejects_today_and_future(
    monkeypatch: pytest.MonkeyPatch,
    track_date: str,
):
    app = _build_app()

    monkeypatch.setattr(
        routes,
        "_require_track_admin_role",
        lambda: None,
    )

    monkeypatch.setattr(
        routes,
        "_today_tijuana",
        lambda: date(2026, 8, 7),
    )

    def forbidden_readiness(**_kwargs):
        raise AssertionError(
            "No debe consultar agregadoras para hoy/futuro."
        )

    def forbidden_request(**_kwargs):
        raise AssertionError(
            "No debe crear solicitud para hoy/futuro."
        )

    monkeypatch.setattr(
        routes,
        "resolve_exact_agregadoras_snapshot_status_for_date",
        forbidden_readiness,
    )

    monkeypatch.setattr(
        routes,
        "request_track_canonical_close",
        forbidden_request,
    )

    with app.test_request_context(
        "/api/track/request-canonical-close",
        method="POST",
        json={"track_date": track_date},
    ):
        response, status_code = _call_unwrapped_endpoint()

    payload = response.get_json()

    assert status_code == 400
    assert payload["status"] == "error"
    assert (
        "solo aplica a fechas pasadas"
        in payload["message"]
    )


def test_request_canonical_close_returns_conflict_when_agregadoras_not_ready(
    monkeypatch: pytest.MonkeyPatch,
):
    app = _build_app()

    monkeypatch.setattr(
        routes,
        "_require_track_admin_role",
        lambda: None,
    )

    monkeypatch.setattr(
        routes,
        "_today_tijuana",
        lambda: date(2026, 8, 7),
    )

    monkeypatch.setattr(
        routes,
        "resolve_exact_agregadoras_snapshot_status_for_date",
        lambda **_kwargs: {
            "is_ready": False,
            "business_date": "2026-07-31",
            "reason": "missing_exact_snapshot",
        },
    )

    def forbidden_request(**_kwargs):
        raise AssertionError(
            "No debe crear solicitud sin agregadoras exactas."
        )

    monkeypatch.setattr(
        routes,
        "request_track_canonical_close",
        forbidden_request,
    )

    with app.test_request_context(
        "/api/track/request-canonical-close",
        method="POST",
        json={"track_date": "2026-07-31"},
    ):
        response, status_code = _call_unwrapped_endpoint()

    payload = response.get_json()

    assert status_code == 409
    assert payload["status"] == "not_ready"
    assert payload["track_date"] == "2026-07-31"


def test_request_canonical_close_returns_forbidden_for_non_admin(
    monkeypatch: pytest.MonkeyPatch,
):
    app = _build_app()

    def deny():
        raise PermissionError(
            "No autorizado para ejecutar procesos del Track."
        )

    monkeypatch.setattr(
        routes,
        "_require_track_admin_role",
        deny,
    )

    def forbidden_request(**_kwargs):
        raise AssertionError(
            "No debe crear solicitud sin permiso admin."
        )

    monkeypatch.setattr(
        routes,
        "request_track_canonical_close",
        forbidden_request,
    )

    with app.test_request_context(
        "/api/track/request-canonical-close",
        method="POST",
        json={"track_date": "2026-07-31"},
    ):
        response, status_code = _call_unwrapped_endpoint()

    payload = response.get_json()

    assert status_code == 403
    assert payload["status"] == "error"
    assert "No autorizado" in payload["message"]


def _call_unwrapped_status_endpoint():
    endpoint = routes.get_track_canonical_close_status_endpoint
    wrapped = getattr(endpoint, "__wrapped__", None)

    if wrapped is None:
        raise AssertionError(
            "Se esperaba @jwt_required() sobre el endpoint GET."
        )

    return wrapped()


def _fake_close_version(
    *,
    version_id,
    status,
    is_current,
    error_message=None,
):
    timestamp = datetime(
        2026,
        8,
        7,
        12,
        0,
        tzinfo=timezone.utc,
    )

    return SimpleNamespace(
        id=version_id,
        track_date=date(2026, 7, 31),
        version_type="cierre_canonico",
        status=status,
        is_current=is_current,
        base_version_id=700,
        replaces_version_id=650,
        retry_count=1,
        requested_by="123",
        trigger_source="api_manual_canonical_close",
        error_message=error_message,
        generated_at_utc=(
            timestamp
            if status in {"success", "replaced"}
            else None
        ),
        started_at_utc=timestamp,
        finished_at_utc=(
            timestamp
            if status in {"success", "failed", "replaced"}
            else None
        ),
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_canonical_close_status_keeps_current_while_latest_is_running(
    monkeypatch: pytest.MonkeyPatch,
):
    app = _build_app()

    current_close = _fake_close_version(
        version_id=650,
        status="success",
        is_current=True,
    )

    latest_attempt = _fake_close_version(
        version_id=777,
        status="running",
        is_current=False,
    )

    monkeypatch.setattr(
        routes,
        "_require_track_admin_role",
        lambda: None,
    )

    monkeypatch.setattr(
        routes,
        "_today_tijuana",
        lambda: date(2026, 8, 7),
    )

    def fake_current(*, track_date, version_type):
        assert track_date == date(2026, 7, 31)
        assert version_type == "cierre_canonico"
        return current_close

    monkeypatch.setattr(
        routes,
        "get_current_track_daily_version",
        fake_current,
    )

    monkeypatch.setattr(
        routes,
        "get_latest_track_canonical_close_version",
        lambda **_kwargs: latest_attempt,
    )

    with app.test_request_context(
        "/api/track/canonical-close-status"
        "?track_date=2026-07-31",
        method="GET",
    ):
        response, status_code = (
            _call_unwrapped_status_endpoint()
        )

    payload = response.get_json()

    assert status_code == 200
    assert payload["status"] == "ok"

    assert payload["current_close"]["id"] == 650
    assert payload["current_close"]["status"] == "success"
    assert payload["current_close"]["is_current"] is True

    assert payload["latest_attempt"]["id"] == 777
    assert payload["latest_attempt"]["status"] == "running"
    assert payload["latest_attempt"]["is_current"] is False

    assert payload["has_active_request"] is True
    assert payload["can_request_close"] is False


@pytest.mark.parametrize(
    "active_status",
    [
        "pending",
        "running",
    ],
)
def test_canonical_close_status_blocks_new_request_for_active_attempt(
    monkeypatch: pytest.MonkeyPatch,
    active_status: str,
):
    app = _build_app()

    latest_attempt = _fake_close_version(
        version_id=800,
        status=active_status,
        is_current=False,
    )

    monkeypatch.setattr(
        routes,
        "_require_track_admin_role",
        lambda: None,
    )

    monkeypatch.setattr(
        routes,
        "_today_tijuana",
        lambda: date(2026, 8, 7),
    )

    monkeypatch.setattr(
        routes,
        "get_current_track_daily_version",
        lambda **_kwargs: None,
    )

    monkeypatch.setattr(
        routes,
        "get_latest_track_canonical_close_version",
        lambda **_kwargs: latest_attempt,
    )

    with app.test_request_context(
        "/api/track/canonical-close-status"
        "?track_date=2026-07-31",
        method="GET",
    ):
        response, status_code = (
            _call_unwrapped_status_endpoint()
        )

    payload = response.get_json()

    assert status_code == 200
    assert payload["current_close"] is None
    assert payload["latest_attempt"]["status"] == active_status
    assert payload["has_active_request"] is True
    assert payload["can_request_close"] is False


def test_canonical_close_status_failed_attempt_allows_retry_and_keeps_current(
    monkeypatch: pytest.MonkeyPatch,
):
    app = _build_app()

    current_close = _fake_close_version(
        version_id=650,
        status="success",
        is_current=True,
    )

    failed_attempt = _fake_close_version(
        version_id=801,
        status="failed",
        is_current=False,
        error_message="Venta Total falló",
    )

    monkeypatch.setattr(
        routes,
        "_require_track_admin_role",
        lambda: None,
    )

    monkeypatch.setattr(
        routes,
        "_today_tijuana",
        lambda: date(2026, 8, 7),
    )

    monkeypatch.setattr(
        routes,
        "get_current_track_daily_version",
        lambda **_kwargs: current_close,
    )

    monkeypatch.setattr(
        routes,
        "get_latest_track_canonical_close_version",
        lambda **_kwargs: failed_attempt,
    )

    with app.test_request_context(
        "/api/track/canonical-close-status"
        "?track_date=2026-07-31",
        method="GET",
    ):
        response, status_code = (
            _call_unwrapped_status_endpoint()
        )

    payload = response.get_json()

    assert status_code == 200

    assert payload["current_close"]["id"] == 650
    assert payload["current_close"]["status"] == "success"

    assert payload["latest_attempt"]["id"] == 801
    assert payload["latest_attempt"]["status"] == "failed"
    assert (
        payload["latest_attempt"]["error_message"]
        == "Venta Total falló"
    )

    assert payload["has_active_request"] is False
    assert payload["can_request_close"] is True


def test_canonical_close_status_returns_empty_when_no_close_exists(
    monkeypatch: pytest.MonkeyPatch,
):
    app = _build_app()

    monkeypatch.setattr(
        routes,
        "_require_track_admin_role",
        lambda: None,
    )

    monkeypatch.setattr(
        routes,
        "_today_tijuana",
        lambda: date(2026, 8, 7),
    )

    monkeypatch.setattr(
        routes,
        "get_current_track_daily_version",
        lambda **_kwargs: None,
    )

    monkeypatch.setattr(
        routes,
        "get_latest_track_canonical_close_version",
        lambda **_kwargs: None,
    )

    with app.test_request_context(
        "/api/track/canonical-close-status"
        "?track_date=2026-07-31",
        method="GET",
    ):
        response, status_code = (
            _call_unwrapped_status_endpoint()
        )

    payload = response.get_json()

    assert status_code == 200
    assert payload["current_close"] is None
    assert payload["latest_attempt"] is None
    assert payload["has_active_request"] is False
    assert payload["can_request_close"] is True


def test_canonical_close_status_rejects_today(
    monkeypatch: pytest.MonkeyPatch,
):
    app = _build_app()

    monkeypatch.setattr(
        routes,
        "_require_track_admin_role",
        lambda: None,
    )

    monkeypatch.setattr(
        routes,
        "_today_tijuana",
        lambda: date(2026, 8, 7),
    )

    def forbidden_query(**_kwargs):
        raise AssertionError(
            "No debe consultar versiones para fecha de hoy."
        )

    monkeypatch.setattr(
        routes,
        "get_current_track_daily_version",
        forbidden_query,
    )

    monkeypatch.setattr(
        routes,
        "get_latest_track_canonical_close_version",
        forbidden_query,
    )

    with app.test_request_context(
        "/api/track/canonical-close-status"
        "?track_date=2026-08-07",
        method="GET",
    ):
        response, status_code = (
            _call_unwrapped_status_endpoint()
        )

    payload = response.get_json()

    assert status_code == 400
    assert payload["status"] == "error"
    assert (
        "solo aplica a fechas pasadas"
        in payload["message"]
    )


def test_canonical_close_status_returns_forbidden_for_non_admin(
    monkeypatch: pytest.MonkeyPatch,
):
    app = _build_app()

    def deny():
        raise PermissionError(
            "No autorizado para ejecutar procesos del Track."
        )

    monkeypatch.setattr(
        routes,
        "_require_track_admin_role",
        deny,
    )

    with app.test_request_context(
        "/api/track/canonical-close-status"
        "?track_date=2026-07-31",
        method="GET",
    ):
        response, status_code = (
            _call_unwrapped_status_endpoint()
        )

    payload = response.get_json()

    assert status_code == 403
    assert payload["status"] == "error"
    assert "No autorizado" in payload["message"]
