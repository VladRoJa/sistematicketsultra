"""Issue #856 D2b: strict approval -> READY/HELD materialization invariants."""
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

import pytest

from app.services import marketing_campaign_v2_dispatch_approval_service as approval
from app.services import marketing_campaign_v2_manifest_service as manifest

NOW = datetime(2026, 10, 13, 17, tzinfo=timezone.utc)
FP = "a" * 64
QUOTE = "b" * 64


@dataclass(frozen=True)
class Plan:
    batches: tuple
    ready: bool = True
    mode: str = "IMMEDIATE"
    campaign_id: int = 99
    dispatch_fingerprint: str = FP
    sendable_phones: tuple = tuple(str(i) for i in range(12))


def batches():
    return (
        NS(sucursal_canon="A", provider_channel_id="channel-one",
           template_id=2, recipients=tuple(range(5))),
        NS(sucursal_canon="B", provider_channel_id="channel-two",
           template_id=2, recipients=tuple(range(7))),
    )


def synthetic_plan():
    return Plan(batches=batches())


def synthetic_quote():
    return {
        "status": "COMPLETE", "currency": "MXN", "quote_fingerprint": QUOTE,
        "sendable_recipients": 12, "total_estimated_mxn": "6.00",
        "batches": [
            {"sucursal_canon": "A", "recipients": 5,
             "channel_id": "channel-one", "estimated_mxn": "2.50",
             "revision_id": 11},
            {"sucursal_canon": "B", "recipients": 7,
             "channel_id": "channel-two", "estimated_mxn": "3.50",
             "revision_id": 12},
        ],
    }


def synthetic_approval():
    return NS(
        dispatch_fingerprint=FP, recipient_count=12,
        approved_estimated_mxn=Decimal("6.00"),
        manifest_json={
            "version": manifest.MANIFEST_VERSION, "send_authorized": False,
            "quote_fingerprint": QUOTE,
            "batches": [
                {"sucursal_canon": "A", "provider_channel_id": "channel-one",
                 "recipients": 5, "planned_status": "READY",
                 "cost_rate_revision_id": 11, "estimated_mxn": "2.50",
                 "channel_attestation_id": 101, "portfolio_attestation_id": 301,
                 "portfolio_key": "shared", "hold_reason": None,
                 "hold_evidence": None},
                {"sucursal_canon": "B", "provider_channel_id": "channel-two",
                 "recipients": 7, "planned_status": "HELD",
                 "cost_rate_revision_id": 12, "estimated_mxn": "3.50",
                 "channel_attestation_id": None, "portfolio_attestation_id": None,
                 "portfolio_key": None, "hold_reason": "CHANNEL_DAILY_QUOTA",
                 "hold_evidence": {"source": "EXPLICIT_OPERATOR_DECISION",
                                   "dispatch_fingerprint": FP,
                                   "quote_fingerprint": QUOTE}},
            ],
        },
    )


def test_explicit_hold_only_reserves_ready_portfolio():
    p = synthetic_plan()
    ready, held = approval._ready_plan_and_holds(p, ["B"])
    assert held == {"B"}
    assert [b.sucursal_canon for b in ready.batches] == ["A"]
    quota = {
        "status": "REVIEWABLE",
        "batches": [{"sucursal_canon": "A", "provider_channel_id": "channel-one",
                     "portfolio_key": "shared", "channel_evidence_id": 101,
                     "portfolio_evidence_id": 301,
                     "recommendation": "CAPACITY_REVIEWED"}],
    }
    with patch.object(approval, "assess_preflight_capacity", return_value=quota):
        _, needed, ids, _ = approval._assess_scopes(
            ready, session=MagicMock(), timestamp=NOW,
        )
    assert needed == {("CHANNEL", "channel-one"): 5, ("PORTFOLIO", "shared"): 5}
    assert ("CHANNEL", "channel-two") not in ids


@pytest.mark.parametrize("invalid", [
    ["B", "B"], ["A", "B"], ["NOT_A_BRANCH"], [" B "], [42], "B",
])
def test_invalid_held_selection_fails_without_write(invalid):
    with pytest.raises(approval.CampaignV2ApprovalValidationError):
        approval._ready_plan_and_holds(synthetic_plan(), invalid)


def test_manifest_must_match_full_quote_and_held_audit():
    p = synthetic_plan()
    a = synthetic_approval()
    rows = manifest._assert_manifest(p, synthetic_quote(), a)
    assert rows["A"]["planned_status"] == "READY"
    assert rows["B"]["planned_status"] == "HELD"

    a.manifest_json["batches"][1]["hold_evidence"]["quote_fingerprint"] = "bad"
    with pytest.raises(approval.CampaignV2ApprovalConflictError, match="HELD"):
        manifest._assert_manifest(p, synthetic_quote(), a)


@pytest.mark.parametrize("mutate", [
    lambda a: a.manifest_json.update({"send_authorized": True}),
    lambda a: a.manifest_json["batches"][0].update({"recipients": 4}),
    lambda a: a.manifest_json["batches"][0].update({"estimated_mxn": "2.51"}),
    lambda a: a.manifest_json["batches"].append(dict(a.manifest_json["batches"][0])),
    lambda a: a.manifest_json["batches"][1].update({"planned_status": "READY"}),
])
def test_manifest_tampering_fails_closed(mutate):
    a = synthetic_approval()
    mutate(a)
    with pytest.raises(approval.CampaignV2ApprovalConflictError):
        manifest._assert_manifest(synthetic_plan(), synthetic_quote(), a)


def test_all_held_manifest_never_allowed():
    a = synthetic_approval()
    a.manifest_json["batches"][0].update({
        "planned_status": "HELD", "hold_reason": "CHANNEL_DAILY_QUOTA",
        "hold_evidence": {"dispatch_fingerprint": FP, "quote_fingerprint": QUOTE},
    })
    with pytest.raises(approval.CampaignV2ApprovalConflictError, match="completamente HELD"):
        manifest._assert_manifest(synthetic_plan(), synthetic_quote(), a)


def test_stale_confirmation_not_materialized():
    session = MagicMock()
    session.get_bind.return_value.dialect.name = "sqlite"
    with pytest.raises(approval.CampaignV2ApprovalConflictError, match="PostgreSQL"):
        manifest.materialize_approved_manifest(
            campaign_id=99, actor_user_id=7,
            allowed_sucursal_keys=None, session=session, now=NOW,
        )
    session.commit.assert_not_called()


def test_existing_child_must_be_exact_ready_or_held_snapshot():
    p = synthetic_plan()
    definition = synthetic_approval().manifest_json["batches"]
    rows_by_name = {x["sucursal_canon"]: x for x in definition}
    children = [
        NS(sucursal_canon="A", status="SUBMITTED"),
        NS(sucursal_canon="B", status="HELD"),
    ]
    # The fixture is intentionally minimal: stub serialization, then verify
    # the impossible SUBMITTED state is rejected before any persistence.
    with patch.object(manifest, "build_provider_campaign_idempotency_key", return_value="key"), \
         patch.object(manifest, "build_campaign_v2_provider_dispatch_batch", return_value=NS()), \
         patch.object(manifest, "serialize_campaign_v2_provider_request_snapshot", return_value={}):
        with pytest.raises(approval.CampaignV2ApprovalConflictError):
            manifest._validate_existing(p, rows_by_name, children)


def test_materialization_never_imports_provider_dispatch():
    import inspect
    source = inspect.getsource(manifest)
    assert "provider.create_campaign(" not in source
    assert "IVentasBroadcastProvider(" not in source
    assert "send_authorized" in source
