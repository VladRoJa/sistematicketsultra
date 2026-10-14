"""Issue #856 B2: prevent candidate Business ID assertions bypassing dispatch rules."""
from importlib.metadata import version
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import werkzeug
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import marketing_campaign_v2_routes as routes
from app.services.marketing_campaign_v2_channel_portfolio_evidence_service import (
    CampaignV2ChannelPortfolioValidationError,
    CampaignV2ChannelPortfolioConflictError,
    normalize_claim,
)

BASE = {
    "provider_channel_id": "provider-001",
    "business_id": "629679279215746",
    "waba_id": None,
    "state": "DECLARED",
    "evidence_kind": "OPERATOR_STATEMENT",
    "source_reference": "Operador referencia 2026-10-14",
    "expected_revision_id": None,
}


def test_claim_valid_and_explicitly_unverified():
    assert normalize_claim(**BASE) == BASE
    withdrawn = normalize_claim(**{
        **BASE, "state": "WITHDRAWN",
        "business_id": None, "waba_id": None, "expected_revision_id": 23,
    })
    assert withdrawn["business_id"] is None
    assert withdrawn["expected_revision_id"] == 23


@pytest.mark.parametrize("changes", [
    {"provider_channel_id": ""},
    {"business_id": "act_123456789"},
    {"business_id": "0"},
    {"waba_id": "not-a-waba"},
    {"state": "VERIFIED"},
    {"state": "WITHDRAWN", "waba_id": "123456789"},
    {"state": "WITHDRAWN", "business_id": "123456789"},
    {"evidence_kind": "SECRET"},
    {"source_reference": ""},
    {"source_reference": "X" * 256},
    {"expected_revision_id": 0},
    {"expected_revision_id": True},
])
def test_bad_claim_rejected(changes):
    with pytest.raises(CampaignV2ChannelPortfolioValidationError):
        normalize_claim(**{**BASE, **changes})


def _client():
    if not hasattr(werkzeug, "__version__"):
        werkzeug.__version__ = version("werkzeug")
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="v2-channel-evidence-test")
    JWTManager(app)
    app.register_blueprint(routes.marketing_campaign_v2_bp, url_prefix="/api/marketing")
    with app.app_context():
        token = create_access_token(identity="7")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("method", ["get", "post"])
def test_evidence_requires_jwt(method):
    client, _ = _client()
    endpoint = "/api/marketing/campaigns-v2/dispatch/channel-portfolio-evidence"
    response = getattr(client, method)(endpoint, json=BASE if method == "post" else None)
    assert response.status_code == 401


@pytest.mark.parametrize("method", ["get", "post"])
def test_evidence_requires_global_dispatch_access(method):
    client, headers = _client()
    restricted = SimpleNamespace(is_global=False, can_manage_dispatch_config=True)
    with patch.object(routes, "_resolve_request_access", return_value=(SimpleNamespace(id=7), restricted)), \
         patch.object(routes, "list_channel_portfolio_evidence") as read, \
         patch.object(routes, "register_channel_portfolio_evidence") as save:
        response = getattr(client, method)(
            "/api/marketing/campaigns-v2/dispatch/channel-portfolio-evidence",
            headers=headers, json=BASE if method == "post" else None,
        )
    assert response.status_code == 403
    read.assert_not_called()
    save.assert_not_called()


def test_global_read_does_not_write():
    client, headers = _client()
    access = SimpleNamespace(is_global=True, can_manage_dispatch_config=True)
    with patch.object(routes, "_resolve_request_access", return_value=(SimpleNamespace(id=7), access)), \
         patch.object(routes, "list_channel_portfolio_evidence", return_value={
             "rows": [], "history": [], "history_is_limited": False,
         }) as read, \
         patch.object(routes, "register_channel_portfolio_evidence") as save:
        response = client.get(
            "/api/marketing/campaigns-v2/dispatch/channel-portfolio-evidence",
            headers=headers,
        )
    assert response.status_code == 200
    assert response.get_json()["history"] == []
    read.assert_called_once()
    save.assert_not_called()


def test_global_write_carries_authenticated_actor_and_expected_revision():
    client, headers = _client()
    access = SimpleNamespace(is_global=True, can_manage_dispatch_config=True)
    with patch.object(routes, "_resolve_request_access", return_value=(SimpleNamespace(id=7), access)), \
         patch.object(routes, "register_channel_portfolio_evidence", return_value={
             "revision_id": 24, "state": "DECLARED", "api_verified": False,
         }) as save:
        response = client.post(
            "/api/marketing/campaigns-v2/dispatch/channel-portfolio-evidence",
            json={**BASE, "expected_revision_id": 23}, headers=headers,
        )
    assert response.status_code == 201
    assert response.get_json()["api_verified"] is False
    assert save.call_args.kwargs["actor_user_id"] == 7
    assert save.call_args.kwargs["expected_revision_id"] == 23


def test_stale_revision_returns_409_without_provider_call():
    client, headers = _client()
    access = SimpleNamespace(is_global=True, can_manage_dispatch_config=True)
    with patch.object(routes, "_resolve_request_access", return_value=(SimpleNamespace(id=7), access)), \
         patch.object(routes, "register_channel_portfolio_evidence",
                      side_effect=CampaignV2ChannelPortfolioConflictError("stale")):
        response = client.post(
            "/api/marketing/campaigns-v2/dispatch/channel-portfolio-evidence",
            json=BASE, headers=headers,
        )
    assert response.status_code == 409


def _fake_mapping_session(*, active_binding=True, has_portfolio=True, previous=None):
    from datetime import datetime, timezone
    from unittest.mock import MagicMock
    from app.models.marketing import (
        MarketingCampaignV2ChannelBindingORM as Binding,
        MarketingCampaignV2PortfolioReferenceORM as Portfolio,
        MarketingCampaignV2ChannelPortfolioEvidenceORM as Evidence,
    )

    session = MagicMock(name="isolated_query_session")

    def query_for(model):
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value = q
        q.with_for_update.return_value = q
        if model is Binding:
            q.one_or_none.return_value = object() if active_binding else None
        elif model is Evidence:
            q.first.return_value = previous
        elif model is Portfolio.id:
            q.first.return_value = (1,) if has_portfolio else None
        else:
            raise AssertionError(f"Unexpected query: {model!r}")
        return q

    session.query.side_effect = query_for

    def commit_row():
        row = session.add.call_args.args[0]
        row.id = 31
        row.created_at = datetime(2026, 10, 14, tzinfo=timezone.utc)

    session.commit.side_effect = commit_row
    return session


def test_b2_rejects_missing_or_inactive_channel_before_write():
    from app.services.marketing_campaign_v2_channel_portfolio_evidence_service import (
        register_channel_portfolio_evidence as register,
    )
    session = _fake_mapping_session(active_binding=False)
    with pytest.raises(CampaignV2ChannelPortfolioValidationError, match="predeterminado activo"):
        register(**BASE, actor_user_id=7, session=session)
    session.add.assert_not_called()
    session.rollback.assert_called_once()


def test_b2_rejects_business_not_registered_in_b1():
    from app.services.marketing_campaign_v2_channel_portfolio_evidence_service import (
        register_channel_portfolio_evidence as register,
    )
    session = _fake_mapping_session(has_portfolio=False)
    with pytest.raises(CampaignV2ChannelPortfolioValidationError, match="primero"):
        register(**BASE, actor_user_id=7, session=session)
    session.add.assert_not_called()


def test_b2_optimistic_revision_blocks_stale_write_and_preserves_old_row():
    from app.services.marketing_campaign_v2_channel_portfolio_evidence_service import (
        register_channel_portfolio_evidence as register,
    )
    old = SimpleNamespace(id=19, state="DECLARED")
    session = _fake_mapping_session(previous=old)
    with pytest.raises(CampaignV2ChannelPortfolioConflictError, match="cambió"):
        register(**BASE, actor_user_id=7, session=session)
    session.add.assert_not_called()


def test_b2_new_declared_revision_is_unverified_and_not_a_quota_write():
    from app.services.marketing_campaign_v2_channel_portfolio_evidence_service import (
        register_channel_portfolio_evidence as register,
    )
    session = _fake_mapping_session()
    result = register(**BASE, actor_user_id=7, session=session)
    assert result["revision_id"] == 31
    assert result["api_verified"] is False
    assert result["business_id"] == BASE["business_id"]
    assert session.add.call_count == 1
    assert session.add.call_args.args[0].__tablename__ == "marketing_campaign_v2_channel_portfolio_evidence"
    session.commit.assert_called_once()
