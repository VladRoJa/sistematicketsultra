"""ADMICORP scheduler alert: real evidence only, no historical SMS noise."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes.automation_control_routes import automation_control_bp
from app.services.automation_control import scheduler_alert_service as alerts


NOW = datetime(2026, 10, 20, 23, 0, tzinfo=timezone.utc)


def _worker(status="HEALTHY", reason="RECENT_HEARTBEAT"):
    return {
        "worker_key": "track-scheduler", "status": status,
        "reason_code": reason, "last_seen_at_utc": NOW.isoformat(),
    }


def _read(*, worker=None, pulse="HEALTHY", jobs=(), run_rows=None, now=NOW):
    worker = worker or _worker()
    run_rows = run_rows or {}
    with (
        patch.object(alerts, "read_worker_health", return_value={"workers": [worker]}),
        patch.object(alerts, "read_pulse_health", return_value={
            "state": pulse, "last_attempt_at_utc": NOW.isoformat(),
        }),
        patch.object(
            alerts, "get_job_catalog",
            return_value=tuple(SimpleNamespace(key=key, label=key) for key in jobs),
        ),
        patch.object(alerts, "has_run_source", side_effect=lambda key: True),
        patch.object(alerts, "has_completion_marker_source", side_effect=lambda key: key.startswith("reports.")),
        patch.object(
            alerts, "list_job_runs",
            side_effect=lambda key, **kwargs: {"rows": run_rows.get(key, [])},
        ) as listing,
    ):
        result = alerts.read_scheduler_alert_summary(now)
    return result, listing


def _run(status, *, when=NOW):
    return {
        "status_raw": status,
        "finished_at_utc": when.isoformat(),
        "started_at_utc": (when - timedelta(minutes=10)).isoformat(),
    }


def test_healthy_and_unknown_without_failure_do_not_raise_alert():
    clean, _ = _read(jobs=("marketing.iventas_sync",), run_rows={
        "marketing.iventas_sync": [_run("COMPLETED")],
    })
    assert clean["state"] == "CLEAR"
    assert clean["issue_count"] == 0
    no_beat, _ = _read(worker=_worker("UNKNOWN", "NO_HEARTBEAT"), pulse="UNKNOWN")
    assert no_beat["issue_count"] == 0
    disabled, _ = _read(worker=_worker("DISABLED", "WORKER_DISABLED"))
    assert disabled["issue_count"] == 0


def test_worker_expired_and_pulse_failed_trigger_critical_alert():
    result, _ = _read(worker=_worker("UNREACHABLE", "HEARTBEAT_EXPIRED"), pulse="FAILED")
    assert result["state"] == "CRITICAL"
    assert result["issue_count"] == 2
    assert {item["kind"] for item in result["issues"]} == {"WORKER", "SMS_PULSE"}
    assert all(item["severity"] == "CRITICAL" for item in result["issues"])


def test_worker_degraded_and_pulse_late_are_warning_only():
    result, _ = _read(worker=_worker("DEGRADED", "HEARTBEAT_LATE"), pulse="LATE")
    assert result["state"] == "WARNING"
    assert result["critical_count"] == 0
    assert result["warning_count"] == 2


def test_last_instrumented_failed_run_is_included_but_old_failure_expires():
    key = "marketing.iventas_sync"
    failed, _ = _read(jobs=(key,), run_rows={key: [_run("FAILED")]})
    assert failed["issue_count"] == 1
    assert failed["issues"][0]["key"] == "job:" + key
    assert failed["issues"][0]["reason_code"] == "LATEST_RUN_FAILED"
    past, _ = _read(jobs=(key,), run_rows={
        key: [_run("FAILED", when=NOW - timedelta(hours=37))],
    })
    assert past["issue_count"] == 0


def test_last_run_success_clears_old_failure_and_partial_warns():
    key = "track.base_nocturna_canonica"
    success, _ = _read(jobs=(key,), run_rows={key: [_run("COMPLETED")]})
    assert success["state"] == "CLEAR"
    partial, _ = _read(jobs=(key,), run_rows={key: [_run("PARTIAL")]})
    assert partial["state"] == "WARNING"


def test_sms_customer_history_and_completion_only_never_count_as_scheduler_error():
    result, listing = _read(
        jobs=("gasca.sms_dispatch", "reports.commercial_daily_reports"),
        run_rows={
            "gasca.sms_dispatch": [_run("FAILED")],
            "reports.commercial_daily_reports": [_run("FAILED")],
        },
    )
    assert result["issue_count"] == 0
    listing.assert_not_called()


def test_future_or_naive_timestamp_is_not_claimed_as_recent_failure():
    key = "marketing.meta_sync"
    for when in ("2026-10-20T23:10:00+00:00", "2026-10-20T22:10:00"):
        result, _ = _read(jobs=(key,), run_rows={
            key: [{"status_raw": "FAILED", "finished_at_utc": when}],
        })
        assert result["issue_count"] == 0


def test_alert_endpoint_is_get_only_with_jwt_and_admicorp_permissions():
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="scheduler-alert-test")
    JWTManager(app)
    app.register_blueprint(automation_control_bp, url_prefix="/api/automation-control")
    client = app.test_client()
    url = "/api/automation-control/alerts/summary"
    assert client.get(url).status_code == 401
    with app.app_context():
        token = create_access_token(identity="47")
    headers = {"Authorization": f"Bearer {token}"}
    with patch(
        "app.routes.automation_control_routes.UserORM.get_by_id",
        return_value=SimpleNamespace(username="SISTEMAS", rol="SISTEMAS"),
    ):
        assert client.get(url, headers=headers).status_code == 403
    with (
        patch(
            "app.routes.automation_control_routes.UserORM.get_by_id",
            return_value=SimpleNamespace(username="ADMICORP", rol="ADMINISTRADOR"),
        ),
        patch(
            "app.routes.automation_control_routes.read_scheduler_alert_summary",
            return_value={"issue_count": 0, "state": "CLEAR", "issues": []},
        ),
    ):
        response = client.get(url, headers=headers)
        assert response.status_code == 200
        assert response.get_json()["issue_count"] == 0
        assert client.post(url, headers=headers).status_code == 405
