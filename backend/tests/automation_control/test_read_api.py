"""M1-B: contrato HTTP seguro y semántica de lecturas de dominio."""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes.automation_control_routes import automation_control_bp
from app.services.automation_control import job_read_service


@pytest.fixture
def api():
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="test-only-read-api")
    JWTManager(app)
    app.register_blueprint(automation_control_bp, url_prefix="/api/automation-control")
    with app.app_context():
        token = create_access_token(identity="47")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def _actor(*, username="ADMICORP", role="ADMINISTRADOR"):
    return SimpleNamespace(id=47, username=username, rol=role)


@pytest.mark.parametrize("path", [
    "/api/automation-control/summary",
    "/api/automation-control/jobs",
    "/api/automation-control/datasets",
    "/api/automation-control/jobs/marketing.iventas_sync",
    "/api/automation-control/jobs/marketing.iventas_sync/runs",
])
def test_all_endpoints_require_jwt(api, path):
    client, _ = api
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("role,username", [
    ("ADMINISTRADOR", "other_admin"),
    ("GERENTE", "branch_user"),
    ("LECTOR_GLOBAL", "reader"),
    ("MARKETING", "marketer"),
    ("SISTEMAS", "other_systems"),
])
def test_non_authorized_roles_rejected_even_with_valid_jwt(api, role, username):
    client, headers = api
    with patch("app.routes.automation_control_routes.UserORM.get_by_id",
               return_value=_actor(username=username, role=role)):
        for path in ("/summary", "/jobs", "/datasets",
                     "/jobs/track.preview_operativo/runs"):
            response = client.get("/api/automation-control" + path,
                                  headers=headers)
            assert response.status_code == 403


@pytest.mark.parametrize("username,role", [
    ("ADMICORP", "ADMINISTRADOR"),
    (" admicorp ", "LECTOR_GLOBAL"),
])
def test_explicit_whitelist_can_read(api, username, role):
    client, headers = api
    with patch("app.routes.automation_control_routes.UserORM.get_by_id",
               return_value=_actor(username=username, role=role)):
        response = client.get("/api/automation-control/summary", headers=headers)
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["job_count"] == 18
    assert payload["dataset_count"] == 2
    assert payload["worker_health"] == "UNKNOWN"
    assert payload["manual_actions_enabled"] is False
    assert payload["effective_schedule_verified"] is False


def test_invalid_identity_is_forbidden(api):
    client, _ = api
    app = client.application
    with app.app_context():
        non_numeric = create_access_token(identity="not-a-number")
    response = client.get("/api/automation-control/summary",
                          headers={"Authorization": f"Bearer {non_numeric}"})
    assert response.status_code == 403


def test_user_no_longer_exists_is_forbidden(api):
    client, headers = api
    with patch("app.routes.automation_control_routes.UserORM.get_by_id",
               return_value=None):
        assert client.get("/api/automation-control/jobs",
                          headers=headers).status_code == 403


def test_jobs_include_provenance_without_inventing_health(api):
    client, headers = api
    with patch("app.routes.automation_control_routes.UserORM.get_by_id",
               return_value=_actor()):
        res = client.get("/api/automation-control/jobs?domain=marketing",
                         headers=headers)
    assert res.status_code == 200
    jobs = res.get_json()["jobs"]
    assert len(jobs) == 3
    assert all(item["schedule_source"] == "CODE_REFERENCE" for item in jobs)
    assert all(item["effective_enabled"] is None for item in jobs)
    assert all(item["worker_health"] == "UNKNOWN" for item in jobs)
    assert all(item["data_freshness"] == "UNKNOWN" for item in jobs)
    assert all(not item["manual_run_supported"] for item in jobs)


def test_dataset_api_is_explicit_about_missing_sla_and_cutoffs(api):
    client, headers = api
    with patch("app.routes.automation_control_routes.UserORM.get_by_id",
               return_value=_actor()):
        res = client.get("/api/automation-control/datasets", headers=headers)
    assert res.status_code == 200
    ds = res.get_json()["datasets"]
    funnel = next(x for x in ds if x["key"] == "marketing.sales_funnel")
    assert len(funnel["sources"]) == 5
    assert funnel["latest_complete_business_date"] is None
    assert funnel["expected_cutoff_policy"] is None
    assert funnel["data_freshness"] == "UNKNOWN"


def test_unknown_job_is_404_and_uninstrumented_job_is_not_success(api):
    client, headers = api
    with patch("app.routes.automation_control_routes.UserORM.get_by_id",
               return_value=_actor()):
        assert client.get("/api/automation-control/jobs/bogus",
                          headers=headers).status_code == 404
        res = client.get(
            "/api/automation-control/jobs/track.warehouse_retention/runs",
            headers=headers)
    assert res.status_code == 200
    assert res.get_json()["coverage"] == "NOT_INSTRUMENTED"
    assert res.get_json()["rows"] == []


@pytest.mark.parametrize("param", [
    "limit=0", "limit=101", "offset=-1", "offset=10001", "limit=bad"
])
def test_pagination_rejected_without_query(api, param):
    client, headers = api
    with (patch("app.routes.automation_control_routes.UserORM.get_by_id",
                return_value=_actor()),
          patch("app.routes.automation_control_routes.list_job_runs") as service):
        res = client.get(
            "/api/automation-control/jobs/marketing.iventas_sync/runs?" + param,
            headers=headers)
    assert res.status_code == 400
    service.assert_not_called()


def test_runs_are_delegated_and_pagination_preserved(api):
    client, headers = api
    data = {
        "coverage": "DOMAIN_RUNS", "rows": [{"run_id": 9}],
        "has_more": False, "limit": 4, "offset": 2,
    }
    with (patch("app.routes.automation_control_routes.UserORM.get_by_id",
                return_value=_actor()),
          patch("app.routes.automation_control_routes.list_job_runs",
                return_value=data) as service):
        res = client.get(
            "/api/automation-control/jobs/marketing.meta_sync/runs?limit=4&offset=2",
            headers=headers)
    assert res.status_code == 200
    assert res.get_json()["rows"] == [{"run_id": 9}]
    service.assert_called_once_with("marketing.meta_sync", limit=4, offset=2)


def test_internal_failure_is_sanitized_and_not_false_success(api):
    client, headers = api
    with (patch("app.routes.automation_control_routes.UserORM.get_by_id",
                return_value=_actor()),
          patch("app.routes.automation_control_routes.list_job_runs",
                side_effect=RuntimeError("secret-do-not-return"))):
        res = client.get(
            "/api/automation-control/jobs/marketing.meta_sync/runs",
            headers=headers)
    assert res.status_code == 500
    assert "secret-do-not-return" not in res.get_data(as_text=True)


def test_no_mutating_methods_exist(api):
    client, headers = api
    with patch("app.routes.automation_control_routes.UserORM.get_by_id",
               return_value=_actor()):
        res = client.post("/api/automation-control/jobs", headers=headers)
    assert res.status_code == 405


def test_marketing_run_preserves_noncanonical_completed_without_green():
    row = SimpleNamespace(
        id=11, date_to=date(2026, 10, 13),
        started_at=datetime(2026, 10, 13, 15, tzinfo=timezone.utc),
        finished_at=None, status="COMPLETED", is_canonical=False,
        branches_requested=26, branches_completed=25, branches_failed=1,
    )
    result = job_read_service._serialize_sync_run(row, is_meta=False)
    assert result["status_raw"] == "COMPLETED"
    assert result["is_canonical"] is False
    assert result["counts"]["branches_failed"] == 1
    assert result["started_at_utc"].endswith("+00:00")


def test_track_current_does_not_mean_canonical():
    row = SimpleNamespace(
        id=7, track_date=date(2026, 10, 12),
        started_at_utc=None, finished_at_utc=None, status="success",
        is_current=True, trigger_source="scheduler_hourly_preview",
        version_type="preview_operativo", error_message=None,
    )
    result = job_read_service._serialize_track_run(row)
    assert result["is_current"] is True
    assert result["is_canonical"] is None
    assert result["error_available"] is False


def test_naive_timestamp_is_not_labeled_utc():
    assert job_read_service._utc_iso(datetime(2026, 10, 13, 10)) is None


def test_supported_runs_uses_only_confirmed_evidence():
    assert job_read_service.has_run_source("marketing.iventas_sync")
    assert job_read_service.has_run_source("track.base_nocturna_retry")
    assert not job_read_service.has_run_source("track.warehouse_retention")
    assert not job_read_service.has_run_source("track.pending_manual_canonical_close")
