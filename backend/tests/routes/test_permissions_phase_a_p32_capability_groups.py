"""P32 Fase A: test authentication boundary and cross-domain hard stops.

112 P31 -> 102 uncatalogued operations, of which 82 have reviewed handler
source in four priority domains. Requests are synthetic; no real sends, data,
users, permissions or external providers. All 102 still need business parity.
"""
import csv
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app import create_app
from app.routes import (
    contact_center_routes as cc,
    google_ads_m6_continuity_routes as ads,
    marketing_campaign_v2_routes as marketing,
)
from app.utils.contact_center_access import ContactCenterAuthorizationError
from app.services.marketing_access import MarketingAuthorizationError

ROOT = Path(__file__).resolve().parents[3]
P31 = ROOT / "docs/security/permissions_phase_a_p31_effective_guards_20261027.csv"
P32 = ROOT / "docs/security/permissions_phase_a_p32_102_capability_contract_20261027.csv"
PRIORITY = {"marketing": 42, "purchase-requisitions": 19, "integrations": 11, "contact-center": 10}
PROTOCOL_EXCEPTIONS = {
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
    ("POST", "/api/auth/refresh"),
    ("POST", "/api/warehouse/internal/gasca-report-jobs"),
}


def rows(path):
    with path.open(encoding="utf-8", newline="") as inp:
        return list(csv.DictReader(inp))


def test_p32_102_exact_projection_and_four_domain_source_evidence():
    previous = [row for row in rows(P31) if row["p31_guard_parity_class"] == "out_of_scope_p31"]
    now = rows(P32)
    identity = ("family", "method", "route", "handler", "review_group", "risk_triage")
    assert len(previous) == len(now) == 102
    assert [{k: row[k] for k in identity} for row in previous] == [
        {k: row[k] for k in identity} for row in now
    ]
    from collections import Counter
    counts = Counter(row["family"] for row in now)
    assert {k: counts[k] for k in PRIORITY} == PRIORITY
    priority = [row for row in now if row["family"] in PRIORITY]
    backlog = [row for row in now if row["family"] not in PRIORITY]
    assert len(priority) == 82 and len(backlog) == 20
    assert all(row["evidence_level"] == "handler_source_inspected" for row in priority)
    assert all(row["source_file"].startswith("backend/app/routes/") for row in priority)
    assert all(row["evidence_level"] == "p31_inventory_only_pending_source" for row in backlog)
    assert all(row["catalog_action_decision"] == "needs_contract_and_effective_parity" for row in now)
    assert all(row["grants_modified"] == "NO" for row in now)
    assert len({(row["method"], row["route"]) for row in now}) == 102


@pytest.fixture(scope="module")
def suite_app():
    app = create_app()
    app.config["TESTING"] = True
    return app


def _synthetic_path(route):
    return re.sub(r"<(?:int|path|uuid|string):[^>]+>", "12345", route)


@pytest.mark.parametrize("item", [
    item for item in rows(P32) if (item["method"], item["route"]) not in PROTOCOL_EXCEPTIONS
], ids=lambda x: x["handler"])
def test_p32_98_user_routes_reject_anonymous_before_service(suite_app, item):
    # No domain service may run because JWT rejects BEFORE handler invocation.
    response = suite_app.test_client().open(
        _synthetic_path(item["route"]), method=item["method"], json={},
    )
    assert response.status_code == 401


def _bearer_client(blueprint, prefix):
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="p32-synthetic-session-only")
    JWTManager(app)
    app.register_blueprint(blueprint, url_prefix=prefix)
    with app.app_context():
        token = create_access_token(identity="881")
    return app.test_client(), {"Authorization": "Bearer " + token}


@pytest.mark.parametrize("capability", ["dispatch_config", "global", "send"])
def test_marketing_dispatch_requires_independent_capabilities(capability):
    # These are distinct backend permissions, never marketing.manage blanket.
    access = SimpleNamespace(
        can_manage_dispatch_config=capability != "dispatch_config",
        is_global=capability != "global",
        can_send_campaigns=capability != "send",
    )
    if capability == "send":
        with pytest.raises(MarketingAuthorizationError):
            marketing._require_campaign_v2_send(access)
    else:
        with patch.object(marketing, "_resolve_request_access",
                          return_value=(object(), access)):
            with pytest.raises(MarketingAuthorizationError):
                marketing._resolve_campaign_v2_dispatch_config_request()


def test_marketing_execute_denies_before_provider_construction():
    client, header = _bearer_client(marketing.marketing_campaign_v2_bp, "/api/marketing")
    access = SimpleNamespace(can_manage_dispatch_config=False, is_global=False,
                             can_send_campaigns=False)
    with patch.object(marketing, "_resolve_request_access",
                      return_value=(SimpleNamespace(id=881), access)), \
         patch.object(marketing, "IVentasBroadcastProvider") as provider:
        response = client.post(
            "/api/marketing/campaigns-v2/7/dispatch/execute",
            json={"execution_id": 2, "child_id": 3, "operator_password": "not-used"},
            headers=header,
        )
    assert response.status_code == 403
    provider.assert_not_called()


def test_contact_manager_cannot_access_foreign_branch_case_or_unowned_case():
    actor = SimpleNamespace(id=881)
    access = SimpleNamespace(is_supervisor=False, is_manager=True,
                             allowed_branch_ids=[7])
    foreign = SimpleNamespace(sucursal_id=8, assigned_user_id=881)
    with pytest.raises(ContactCenterAuthorizationError):
        cc._assert_case_access(foreign, actor, access)
    another_actor_case = SimpleNamespace(sucursal_id=7, assigned_user_id=999)
    with pytest.raises(ContactCenterAuthorizationError):
        cc._assert_case_access(another_actor_case, actor, access)
    owned = SimpleNamespace(sucursal_id=7, assigned_user_id=881)
    cc._assert_case_access(owned, actor, access)


def test_contact_manager_never_inherits_operator_verification():
    with pytest.raises(ContactCenterAuthorizationError):
        cc._assert_operator_access(SimpleNamespace(is_manager=True))


def test_google_ads_publish_deny_before_canonical_service(monkeypatch):
    monkeypatch.setenv("GOOGLE_ADS_M6_DAILY_PUBLICATION_ENABLED", "true")
    client, header = _bearer_client(ads.google_ads_m6_continuity_bp,
                                   "/api/integrations/google-ads")
    with patch.object(ads, "require_current_admicorp",
                      side_effect=PermissionError("blocked")), \
         patch.object(ads, "publish_manual_daily_pair") as publish:
        response = client.post(
            "/api/integrations/google-ads/manual/publish",
            json={"campaign_upload_id": 1, "ad_group_upload_id": 2},
            headers=header,
        )
    assert response.status_code == 403
    publish.assert_not_called()


def test_google_ads_review_guard_distinct_from_admin_publication(monkeypatch):
    monkeypatch.setenv(ads.CORRECTION_REVIEW_FLAG, "true")
    client, header = _bearer_client(ads.google_ads_m6_continuity_bp,
                                   "/api/integrations/google-ads")
    with patch.object(ads, "require_warehouse_view", return_value=({"code": "FORBIDDEN"}, 403)), \
         patch.object(ads, "decide_m6_correction") as decide:
        response = client.post(
            "/api/integrations/google-ads/corrections/candidates/8/review",
            json={"decision": "APPROVED"},
            headers=header,
        )
    assert response.status_code == 403
    decide.assert_not_called()
