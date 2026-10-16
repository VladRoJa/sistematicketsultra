"""Expired started dispatch: only an accepted prefix may continue with live quota.

No iVentas calls and no production data. The old reservation MUST NOT be
mistaken for fresh capacity, and HELD batches must remain excluded.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest

from app.services import marketing_campaign_v2_governed_dispatch_service as svc

NOW = datetime(2026, 10, 16, 19, 0, tzinfo=timezone.utc)
DIGEST = "a" * 64


@dataclass(frozen=True)
class Plan:
    campaign_id: int
    dispatch_fingerprint: str
    batches: tuple


def synthetic(monkeypatch):
    approval = NS(
        id=8, campaign_v2_id=22, template_id=10,
        expires_at=NOW - timedelta(minutes=5),
        manifest_json={"basis": "SUITE_BRANCH_EXCEPTION_CAPS_V1"},
    )
    execution = NS(
        id=8, approval_id=8, status="AUTHORIZED",
        last_child_id=133, manifest_digest=DIGEST,
        confirmed_at=NOW - timedelta(minutes=25),
        expires_at=approval.expires_at,
    )
    accepted = NS(
        id=133, status="SUBMITTED", sucursal_canon="A",
        submit_started_at=NOW-timedelta(minutes=11),
        submitted_at=NOW-timedelta(minutes=11),
        submitted_by_user_id=7, provider_campaign_id="synthetic-accepted",
    )
    ready = NS(id=134, status="READY", sucursal_canon="B")
    held = NS(id=135, status="HELD", sucursal_canon="INDEPENDENCIA")
    children = [accepted, ready, held]
    batches = [
        NS(sucursal_canon="A"),
        NS(sucursal_canon="B"),
        NS(sucursal_canon="INDEPENDENCIA"),
    ]
    plan = Plan(
        campaign_id=22, dispatch_fingerprint="f"*64, batches=tuple(batches),
    )
    manifest = {
        "A": {"planned_status": "READY"},
        "B": {
            "planned_status": "READY",
            "channel_attestation_id": None,
            "portfolio_attestation_id": None,
            "portfolio_key": None,
            "policy_revision_id": None,
            "operator_channel_cap": None,
            "operator_portfolio_cap": None,
        },
        "INDEPENDENCIA": {"planned_status": "HELD"},
    }
    quota_calls = []

    def assess(plan, *, session, timestamp, **kwargs):
        quota_calls.append((tuple(b.sucursal_canon for b in plan.batches), kwargs))
        assert kwargs["ignore_campaign_id"] is None
        assert kwargs["basis_preference"] == "SUITE_BRANCH_EXCEPTION_CAPS_V1"
        assert tuple(b.sucursal_canon for b in plan.batches) == ("B",)
        return ({"status": "REVIEWABLE"}, {("CHANNEL", "ch-B"): 7},
                {("CHANNEL", "ch-B"): None},
                {"B": {
                    "channel_evidence_id": None,
                    "portfolio_evidence_id": None, "portfolio_key": None,
                    "policy_revision_id": None, "operator_channel_cap": None,
                    "operator_portfolio_cap": None,
                }})

    monkeypatch.setattr(svc, "build_campaign_v2_preflight", lambda **kwargs: plan)
    monkeypatch.setattr(svc, "budget_for_existing_approval",
                        lambda **kwargs: {"quote_fingerprint": "b"*64})
    monkeypatch.setattr(svc, "_assert_manifest", lambda *args: manifest)
    monkeypatch.setattr(svc, "_check_child_identities", lambda **kwargs: None)
    monkeypatch.setattr(svc, "_load_campaign_rows", lambda **kwargs: children)
    monkeypatch.setattr(svc, "_assess_scopes", assess)
    monkeypatch.setattr(svc, "manifest_digest", lambda *args: DIGEST)

    session = MagicMock()
    session.get_bind.return_value.dialect.name = "postgresql"
    query_campaign = MagicMock()
    query_campaign.filter.return_value.with_for_update.return_value.one_or_none.return_value = NS(id=22)
    query_approval = MagicMock()
    query_approval.filter.return_value.order_by.return_value.with_for_update.return_value.first.return_value = approval
    query_execution = MagicMock()
    query_execution.filter.return_value.one_or_none.return_value = execution
    query_reservations = MagicMock()
    query_reservations.filter.return_value.all.return_value = [
        NS(scope_kind="CHANNEL", scope_key="ch-B", reserved_until=approval.expires_at)
    ]
    def query(cls):
        return {
            svc.MarketingCampaignV2ORM: query_campaign,
            svc.MarketingCampaignV2DispatchApprovalORM: query_approval,
            svc.MarketingCampaignV2GovernedExecutionORM: query_execution,
            svc.MarketingCampaignV2CapacityReservationORM: query_reservations,
        }[cls]
    session.query.side_effect = query
    return session, children, execution, approval, quota_calls


def invoke(session):
    return svc._locked_review(
        campaign_id=22, session=session, now=NOW,
        allowed_sucursal_keys=None, ignore_self=True,
        refresh_after_lock=False, allow_started_continuation=True,
    )


def test_expired_started_dispatch_rechecks_only_ready_suffix_and_excludes_holds(monkeypatch):
    session, children, execution, approval, checks = synthetic(monkeypatch)
    result = invoke(session)
    assert result[0] is approval
    assert result[3] is children
    assert len(checks) == 2
    assert session.execute.call_count == 1
    assert session.commit.call_count == 0
    assert execution.last_child_id == 133
    assert children[0].provider_campaign_id == "synthetic-accepted"
    assert children[2].status == "HELD"


@pytest.mark.parametrize("mutation", [
    lambda rows, execution, approval: setattr(rows[0], "status", "READY"),
    lambda rows, execution, approval: setattr(rows[0], "provider_campaign_id", None),
    lambda rows, execution, approval: setattr(rows[0], "submitted_at", None),
    lambda rows, execution, approval: setattr(rows[1], "status", "SUBMITTING"),
    lambda rows, execution, approval: setattr(rows[2], "status", "READY"),
    lambda rows, execution, approval: setattr(execution, "last_child_id", 999),
    lambda rows, execution, approval: setattr(execution, "status", "IN_FLIGHT"),
    lambda rows, execution, approval: setattr(rows[0], "submit_started_at",
                                             approval.expires_at + timedelta(seconds=1)),
])
def test_tampered_or_uncertain_prefix_never_reaches_quota_or_provider(monkeypatch, mutation):
    session, children, execution, approval, checks = synthetic(monkeypatch)
    mutation(children, execution, approval)
    with pytest.raises(svc.GovernedDispatchConflict):
        invoke(session)
    session.commit.assert_not_called()
    assert checks == []


def test_expired_unstarted_campaign_is_still_blocked(monkeypatch):
    session, children, execution, approval, checks = synthetic(monkeypatch)
    children[0].status = "READY"
    execution.last_child_id = None
    with pytest.raises(svc.GovernedDispatchConflict):
        invoke(session)
    assert checks == []


def test_normal_authorization_still_respects_expiry(monkeypatch):
    session, *_ = synthetic(monkeypatch)
    with pytest.raises(svc.GovernedDispatchConflict, match="vencida"):
        svc._locked_review(
            campaign_id=22, session=session, now=NOW,
            allowed_sucursal_keys=None, ignore_self=False,
            refresh_after_lock=False, allow_started_continuation=False,
        )
