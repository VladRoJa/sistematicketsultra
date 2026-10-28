"""P33: 102/102 source inventory, 16 JWT boundaries and GET triage.

Synthetic Flask only: NO execution of mutating handlers or mail/queues.
P33 confirms source-level guard flow, NOT actor/object permit parity.
"""
import csv
import inspect
import re
from pathlib import Path
from collections import Counter
from unittest.mock import patch

import pytest

from app import create_app
from app.utils.permission_get_surface_audit import (
    PRIORITY, get_review_priority, make_get_review_report,
)
from app.utils.permission_route_inventory import flask_registry
from app.routes import warehouse_internal_jobs as internal_jobs

ROOT = Path(__file__).resolve().parents[3]
P32 = ROOT / "docs/security/permissions_phase_a_p32_102_capability_contract_20261027.csv"
P33 = ROOT / "docs/security/permissions_phase_a_p33_102_source_closure_20261027.csv"
PROTOCOLS = {
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
    ("POST", "/api/auth/refresh"),
    ("POST", "/api/warehouse/internal/gasca-report-jobs"),
}


def _read(path):
    with path.open(newline="", encoding="utf-8") as inp:
        return list(csv.DictReader(inp))


def _new_rows():
    return [r for r in _read(P33) if r["evidence_level"] == "p31_inventory_only_pending_source"]


def test_p33_preserves_102_identities_and_inspects_remaining_20():
    before, after = _read(P32), _read(P33)
    identity = ("family", "method", "route", "handler", "review_group", "risk_triage")
    assert len(before) == len(after) == 102
    assert [{k: row[k] for k in identity} for row in before] == [
        {k: row[k] for k in identity} for row in after
    ]
    counts = Counter(row["p33_evidence"] for row in after)
    assert counts == {"prior_p32_source_inspected": 82, "handler_source_inspected": 20}
    assert len(_new_rows()) == 20
    assert all(row["p33_source_file"].startswith("backend/app/") for row in after)
    assert all(row["p33_effective_scope_certified"] == "NO" for row in after)
    assert all(row["grants_modified"] == "NO" for row in after)
    assert all(row["catalog_action_decision"] == "needs_contract_and_effective_parity" for row in after)
    assert {tuple(row[k] for k in ("method", "route")) for row in _new_rows() if
            (row["method"], row["route"]) in PROTOCOLS} == PROTOCOLS


@pytest.fixture(scope="module")
def suite_app():
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.mark.parametrize("row", [
    row for row in _new_rows()
    if (row["method"], row["route"]) not in PROTOCOLS
], ids=lambda item: item["handler"])
def test_p33_sixteen_newly_reviewed_user_mutations_require_jwt(suite_app, row):
    path = re.sub(r"<(?:int|path|uuid|string):[^>]+>", "810000", row["route"])
    result = suite_app.test_client().open(path, method=row["method"], json={})
    assert result.status_code == 401


def test_p33_internal_job_requires_hmac_token_not_jwt(suite_app):
    # Force synthetic configured token, no secret content is printed.
    with patch.dict(suite_app.config, {"WAREHOUSE_INTERNAL_JOBS_TOKEN": "test-p33-only"}):
        result = suite_app.test_client().post(
            "/api/warehouse/internal/gasca-report-jobs",
            json={"report_type_key": "reporte_direccion"},
        )
    assert result.status_code == 403


def test_p33_public_auth_endpoints_stay_separate_from_user_jwt():
    from app.routes import auth_routes
    for function in (
        auth_routes.login,
        auth_routes.revoke_session,
        auth_routes.refresh_session,
    ):
        source = inspect.getsource(function)
        assert "jwt_required" not in source
    source = inspect.getsource(auth_routes.refresh_session)
    assert "_origin_allowed()" in source
    assert "rotate_refresh(" in source
    assert "request.cookies.get(" in source
    assert "_set_refresh_cookie(" in source


@pytest.mark.parametrize("route,endpoint,expected", [
    ("/api/integrations/google-ads/oauth/callback", "google_ads_oauth_callback", "oauth_callback_protocol"),
    ("/api/warehouse/internal/report", "internal_report", "internal_or_machine_protocol"),
    ("/api/reports/export.xlsx", "export_xlsx", "download_export_or_document"),
    ("/api/contact-center/contacts", "get_contacts", "identity_or_personal_records"),
    ("/api/track/daily-mart", "get_track_daily_mart", "operational_and_financial_data"),
    ("/api/health", "index", "general_read_review"),
])
def test_p33_get_triage_heuristics_are_review_queue_not_acl(route, endpoint, expected):
    assert get_review_priority(route, endpoint) == expected
    assert PRIORITY[expected] in (1, 2, 3)


def test_p33_get_report_keeps_uncatalogued_and_problematic_get_only():
    rows = [
        {"method": "GET", "route": "/api/users/8", "endpoint": "get_user",
         "family": "users", "classification": "not_cataloged"},
        {"method": "GET", "route": "/api/reports/file", "endpoint": "download_file",
         "family": "reports", "classification": "handler_mismatch"},
        {"method": "GET", "route": "/api/warehouse/upload", "endpoint": "get_upload",
         "family": "warehouse", "classification": "exact"},
        {"method": "POST", "route": "/api/track/run", "endpoint": "run_track",
         "family": "track", "classification": "not_cataloged"},
    ]
    summary = make_get_review_report({"route_rows": rows})
    assert summary["count"] == 2
    assert all(item["method"] == "GET" for item in summary["items"])
    assert {i["review_category"] for i in summary["items"]} == {
        "identity_or_personal_records", "download_export_or_document",
    }
    assert all(not i["jwt_enforcement_checked"] and not i["resource_scope_checked"] for i in summary["items"])
    assert summary["read_only"] is True
    assert summary["handlers_executed"] is False
    assert summary["auth_or_branch_scope_certified"] is False


def test_p33_get_registry_read_only_and_no_handlers_invoked(suite_app):
    found = flask_registry(suite_app)
    get_rows = [r for r in found if r["method"] == "GET"]
    assert get_rows
    assert all(r["route"].startswith("/api/") for r in get_rows)
    # Compare with no catalog rows: this deliberately DOES NOT claim a live
    # 247 count or classify JWT with URL/name heuristics.
    from app.utils.permission_route_inventory import compare_route_maps
    summary = make_get_review_report(compare_route_maps(get_rows, []))
    assert summary["count"] == len(get_rows)
    assert all(row["decision"] == "review_required" for row in summary["items"])
