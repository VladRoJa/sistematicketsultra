"""Issue 856: USD delivered billing reference and immutable dual-currency approvals."""
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest

from app.services import marketing_campaign_v2_usd_pricing_service as usd
from app.services import marketing_campaign_v2_dispatch_approval_service as approval
from app.services import marketing_campaign_v2_manifest_service as manifest

NOW = datetime(2026, 10, 15, 16, 0, tzinfo=timezone.utc)


def plan():
    return NS(
        campaign_id=99, dispatch_fingerprint="a" * 64,
        mode="IMMEDIATE", ready=True, provider="IVENTAS",
        sendable_phones=("123", "456"),
        batches=(NS(
            sucursal_canon="AZAHARES_CUL", provider_channel_id="channel-one",
            template_id=12, recipients=("123", "456"),
        ),),
    )


def test_cost_is_usd_per_delivered_not_per_submitted_charge():
    assert usd.calculate_delivered_cost_usd(billed_deliveries=0) == "0.0000"
    assert usd.calculate_delivered_cost_usd(billed_deliveries=278) == "15.0676"
    assert usd.calculate_delivered_cost_usd(billed_deliveries=1000) == "54.2000"
    assert usd.USD_RATE_VERSION == "IVENTAS_MX_DELIVERED_USD_V1"
    for bad in (-1, 1.4, "1", True):
        with pytest.raises(ValueError):
            usd.calculate_delivered_cost_usd(billed_deliveries=bad)


def test_quote_is_deterministic_without_db_rates_or_fx_and_changes_with_audience():
    p = plan()
    q = usd.estimate_automatic_usd_maximum(plan=p)
    assert q == usd.estimate_automatic_usd_maximum(plan=p)
    assert q["currency"] == "USD"
    assert q["status"] == "COMPLETE"
    assert q["unit_cost_usd"] == "0.0542"
    assert q["maximum_estimated_usd"] == "0.1084"
    assert q["billable_basis"] == "PROVIDER_CONFIRMED_DELIVERED"
    assert q["batches"][0]["maximum_estimated_usd"] == "0.1084"
    altered = NS(**{**vars(p), "dispatch_fingerprint": "b" * 64})
    assert usd.estimate_automatic_usd_maximum(plan=altered)["quote_fingerprint"] != q["quote_fingerprint"]
    assert "total_estimated_mxn" not in q


def test_unready_plan_cannot_be_approved_despite_automatic_price():
    p = plan()
    p.ready = False
    assert usd.estimate_automatic_usd_maximum(plan=p)["status"] == "INCOMPLETE"


def synthetic_approval():
    p = plan()
    quote = usd.estimate_automatic_usd_maximum(plan=p)
    row = NS(
        campaign_v2_id=99, template_id=12,
        dispatch_fingerprint=p.dispatch_fingerprint,
        recipient_count=2,
        approved_estimated_mxn=None,
        approved_estimated_usd=Decimal("0.1084"),
        manifest_json={
            "version": "D2B_READY_HELD_V1",
            "send_authorized": False,
            "quote_fingerprint": quote["quote_fingerprint"],
            "pricing_currency": "USD",
            "pricing_basis": quote["basis"],
            "pricing_rate_version": quote["rate_version"],
            "batches": [{
                "sucursal_canon": "AZAHARES_CUL",
                "provider_channel_id": "channel-one",
                "recipients": 2,
                "planned_status": "READY",
                "hold_reason": None,
                "hold_evidence": None,
                "cost_rate_revision_id": None,
                "estimated_mxn": None,
                "estimated_usd": "0.1084",
            }],
        },
    )
    return p, quote, row


def test_usd_manifest_matches_original_quote_without_legacy_mxn_price():
    p, quote, a = synthetic_approval()
    assert manifest._assert_manifest(p, quote, a)["AZAHARES_CUL"]["planned_status"] == "READY"
    assert manifest.budget_for_existing_approval(
        plan=p, approval=a, session=MagicMock(), now=NOW,
    ) == quote


def test_changed_rate_digest_or_amount_never_materializes():
    p, quote, a = synthetic_approval()
    a.approved_estimated_usd = Decimal("0.2000")
    with pytest.raises(approval.CampaignV2ApprovalConflictError):
        manifest._assert_manifest(p, quote, a)
    a.approved_estimated_usd = Decimal("0.1084")
    a.manifest_json["batches"][0]["estimated_usd"] = "0.0000"
    with pytest.raises(approval.CampaignV2ApprovalConflictError):
        manifest._assert_manifest(p, quote, a)


def test_new_usd_approval_persists_only_usd_and_reserves_capacity_not_messages():
    p, quote, _ = synthetic_approval()
    session = MagicMock()
    session.add.side_effect = lambda obj: setattr(obj, "id", 41) if obj.__class__.__name__.endswith("DispatchApprovalORM") else None
    snapshot = approval._reserve_locked(
        plan=p, budget=quote,
        confirmation=(p.dispatch_fingerprint, quote["quote_fingerprint"], 2, Decimal("0.1084"), 7),
        session=session, timestamp=NOW,
        quantities={("CHANNEL", "channel-one"): 2},
        evidence_ids={("CHANNEL", "channel-one"): None},
        quota_rows={"AZAHARES_CUL": {
            "policy_revision_id": 10, "channel_evidence_id": None,
            "portfolio_evidence_id": None, "operator_channel_cap": 100,
            "operator_portfolio_cap": 100, "portfolio_key": "demo",
        }},
    )
    record = session.add.call_args_list[0].args[0]
    assert record.approved_estimated_usd == Decimal("0.1084")
    assert record.approved_estimated_mxn is None
    assert record.manifest_json["pricing_currency"] == "USD"
    assert snapshot["approved_estimated_usd"] == "0.1084"
    assert snapshot["approved_estimated_mxn"] is None
    assert snapshot["currency"] == "USD"
    assert session.commit.call_count == 1


def test_browser_mxn_price_cannot_override_usd_quote_before_database_access():
    with pytest.raises(approval.CampaignV2ApprovalValidationError):
        approval.approve_dispatch_reservation(
            campaign_id=99, template_id=12, pricing_currency="USD",
            expected_dispatch_fingerprint="a" * 64,
            expected_quote_fingerprint="b" * 64, expected_recipients=2,
            expected_total_mxn="0.00",
            actor_user_id=7, allowed_sucursal_keys=None,
            session=MagicMock(),
        )
