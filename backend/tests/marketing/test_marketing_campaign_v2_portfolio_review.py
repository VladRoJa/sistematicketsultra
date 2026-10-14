"""Issue #856 B3 — read-only evidence coverage, never automatic Meta verification."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import werkzeug
from importlib.metadata import version
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import marketing_campaign_v2_routes as routes
from app.services.marketing_campaign_v2_portfolio_review_service import build_portfolio_review

CANDIDATES = [
    {"business_id": "1039061498449710"},
    {"business_id": "629679279215746"},
]


def binding(branch, channel, *, active=True, default=True, branch_id=None):
    return {
        "provider": "IVENTAS", "sucursal_id": branch_id or branch,
        "sucursal_canon": f"SUCURSAL_{branch}", "provider_channel_id": channel,
        "is_active": active, "is_default": default,
    }


def claim(rev, channel, business, *, kind="OPERATOR_STATEMENT", waba=None, state="DECLARED"):
    return {
        "revision_id": rev, "provider_channel_id": channel,
        "business_id": business, "waba_id": waba,
        "evidence_kind": kind, "state": state,
        "source_reference": f"doc-{rev}",
    }


def review(bindings, claims, portfolios=None):
    return build_portfolio_review(
        bindings=bindings, portfolios=CANDIDATES if portfolios is None else portfolios,
        revisions=claims,
    )


def test_empty_report_does_not_invent_the_26_channels():
    report = review([], [])
    assert report["summary"]["total_channels"] == 0
    assert report["summary"]["api_verified"] == 0
    assert report["rows"] == []


def test_unconfigured_active_defaults_are_pending_and_inactive_are_excluded():
    report = review([
        binding(1, "ch-a"), binding(2, "ch-b", active=False),
        binding(3, "ch-c", default=False),
    ], [])
    assert [row["review_state"] for row in report["rows"]] == ["PENDING"]
    assert report["summary"]["pending"] == 1


def test_only_operator_statement_does_not_count_as_documented():
    report = review([binding(1, "ch-a")], [claim(1, "ch-a", "629679279215746")])
    row = report["rows"][0]
    assert row["review_state"] == "DECLARED_UNVERIFIED"
    assert row["flags"] == ["OPERATOR_ONLY", "WABA_NOT_RECORDED"]
    assert row["api_verified"] is False


def test_provider_document_is_still_not_graph_verification():
    report = review([binding(1, "ch-a")], [
        claim(1, "ch-a", "629679279215746", kind="IVENTAS_CONFIRMATION"),
    ])
    assert report["rows"][0]["review_state"] == "DOCUMENTED_UNVERIFIED"
    assert report["summary"]["api_verified"] == 0
    assert report["meta_verification_available"] is False


def test_withdrawn_latest_is_not_a_current_association():
    report = review([binding(1, "ch-a")], [
        claim(1, "ch-a", "629679279215746"),
        claim(2, "ch-a", None, state="WITHDRAWN"),
    ])
    assert report["rows"][0]["review_state"] == "WITHDRAWN"
    assert report["rows"][0]["business_id"] is None
    assert report["rows"][0]["revision_count"] == 2


def test_full_history_catches_old_business_changes_beyond_recent_250():
    older = [
        claim(1, "ch-a", "1039061498449710"),
        *[claim(n, "ch-a", "629679279215746", kind="META_DOCUMENT")
          for n in range(2, 255)],
    ]
    report = review([binding(1, "ch-a")], older)
    assert report["rows"][0]["review_state"] == "REVIEW_REQUIRED"
    assert "HISTORICAL_BUSINESS_CHANGE" in report["rows"][0]["flags"]
    assert report["rows"][0]["revision_count"] == 254


def test_one_waba_across_two_businesses_flagged_both_sides():
    report = review([binding(1, "ch-a"), binding(2, "ch-b")], [
        claim(1, "ch-a", "1039061498449710", waba="18888123456789", kind="META_DOCUMENT"),
        claim(2, "ch-b", "629679279215746", waba="18888123456789", kind="META_DOCUMENT"),
    ])
    assert report["summary"]["review_required"] == 2
    assert all("WABA_CROSS_BUSINESS" in row["flags"] for row in report["rows"])


def test_same_waba_same_business_is_not_cross_business_conflict():
    report = review([binding(1, "ch-a"), binding(2, "ch-b")], [
        claim(1, "ch-a", "629679279215746", waba="18888123456789", kind="META_DOCUMENT"),
        claim(2, "ch-b", "629679279215746", waba="18888123456789", kind="META_DOCUMENT"),
    ])
    assert report["summary"]["review_required"] == 0
    assert report["summary"]["documented_unverified"] == 2


def test_missing_catalog_candidate_and_duplicate_branch_need_review():
    report = review([
        binding(1, "ch-a"), binding(2, "ch-b", branch_id=1),
    ], [claim(1, "ch-a", "777777999999", kind="META_DOCUMENT")])
    assert all(row["review_state"] == "REVIEW_REQUIRED" for row in report["rows"])
    assert "MISSING_PORTFOLIO_CATALOG" in report["rows"][0]["flags"]
    assert all("MULTIPLE_DEFAULT_BRANCH" in row["flags"] for row in report["rows"])


def _client():
    if not hasattr(werkzeug, "__version__"):
        werkzeug.__version__ = version("werkzeug")
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="campaign-v2-portfolio-review-test")
    JWTManager(app)
    app.register_blueprint(routes.marketing_campaign_v2_bp, url_prefix="/api/marketing")
    with app.app_context():
        token = create_access_token(identity="7")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def test_review_requires_jwt():
    client, _ = _client()
    response = client.get("/api/marketing/campaigns-v2/dispatch/portfolio-review")
    assert response.status_code == 401


def test_review_denies_non_global_operator_without_service_call():
    client, headers = _client()
    limited = SimpleNamespace(is_global=False, can_manage_dispatch_config=True)
    with patch.object(routes, "_resolve_request_access", return_value=(SimpleNamespace(id=7), limited)), \
         patch.object(routes, "list_portfolio_review") as read:
        response = client.get(
            "/api/marketing/campaigns-v2/dispatch/portfolio-review", headers=headers,
        )
    assert response.status_code == 403
    read.assert_not_called()


def test_global_review_read_only():
    client, headers = _client()
    global_admin = SimpleNamespace(is_global=True, can_manage_dispatch_config=True)
    dataset = review([binding(1, "ch-a")], [])
    with patch.object(routes, "_resolve_request_access", return_value=(SimpleNamespace(id=7), global_admin)), \
         patch.object(routes, "list_portfolio_review", return_value=dataset) as read, \
         patch.object(routes, "register_channel_portfolio_evidence") as write:
        response = client.get(
            "/api/marketing/campaigns-v2/dispatch/portfolio-review", headers=headers,
        )
    assert response.status_code == 200
    assert response.get_json()["summary"]["pending"] == 1
    read.assert_called_once()
    write.assert_not_called()
