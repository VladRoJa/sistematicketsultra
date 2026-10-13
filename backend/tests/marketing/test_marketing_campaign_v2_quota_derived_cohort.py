"""D3c2: fresh derived frozen cohort safety, no provider or implicit approval."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

import pytest

from app.models.marketing import (
    MarketingCampaignV2RecipientORM as Recipient,
    MarketingCampaignV2RecipientEvidenceORM as Evidence,
)
from app.services import marketing_campaign_v2_held_derived_cohort_service as svc
from app.services import marketing_campaign_v2_derived_contact_guard as guard

NOW = datetime(2026, 10, 13, 21, tzinfo=timezone.utc)
FINGERPRINT = "a" * 64


def test_cross_campaign_submitted_contact_denied_even_when_origin_held():
    session = MagicMock()
    session.query.return_value.join.return_value.filter.return_value.all.return_value = []
    child = NS(status="SUBMITTED", recipient_count=1,
               request_snapshot_json={"leads":[{"phone":"5216861234567"}]},
               reconciliation_resolution=None)
    session.query.return_value.filter.return_value.all.return_value = [child]
    with patch.object(guard, "get_blacklisted_phones", return_value=set()):
        with pytest.raises(guard.DerivedContactConflict, match="coincidente"):
            guard.assert_no_prior_or_pending_contact(
                phones=["6861234567"], session=session,
            )


def test_derived_contact_guard_rejects_blacklist_and_invalid_snapshots():
    session = MagicMock()
    with patch.object(guard, "get_blacklisted_phones", return_value={"6861234567"}):
        with pytest.raises(guard.DerivedContactConflict, match="lista negra"):
            guard.assert_no_prior_or_pending_contact(
                phones=["6861234567"], session=session,
            )
    session.query.return_value.join.return_value.filter.return_value.all.return_value = []
    session.query.return_value.filter.return_value.all.return_value = [
        NS(status="SUBMITTED", recipient_count=2,
           request_snapshot_json={"leads":[]}, reconciliation_resolution=None)
    ]
    with patch.object(guard, "get_blacklisted_phones", return_value=set()):
        with pytest.raises(guard.DerivedContactConflict, match="incompleto"):
            guard.assert_no_prior_or_pending_contact(
                phones=["6861234567"], session=session,
            )


def test_derived_freeze_clones_only_held_recipient_and_evidence_atomically():
    session = MagicMock()
    session.get_bind.return_value.dialect.name = "postgresql"
    original = NS(
        id=77, name="Campaña original", purpose="REACTIVATION",
        audience_definition_json={"filters":{"allowed_sucursal_keys":None}},
    )
    intent = NS(
        id=55, status="PENDING_FRESH_COHORT",
        source_approval_id=9, source_manifest_digest="b"*64,
        candidate_fingerprint=FINGERPRINT, candidate_recipients=1,
        derived_campaign_id=None, materialized_at=None,
    )
    approval = NS(id=9, template_id=2)
    child = NS(id=100, status="HELD", sucursal_canon="B")
    session.get.side_effect = lambda model, id: (
        original if model is svc.MarketingCampaignV2ORM else
        child if model is svc.MarketingCampaignV2ProviderCampaignORM else None
    )
    def query(model):
        q = MagicMock()
        if model is svc.MarketingCampaignV2HeldReleaseIntentORM:
            q.filter.return_value.with_for_update.return_value.one_or_none.return_value = intent
        if model is svc.MarketingCampaignV2DispatchApprovalORM:
            q.filter.return_value.one_or_none.return_value = approval
        return q
    session.query.side_effect = query
    original_recipient = Recipient(
        id=501, campaign_id=77, phone_mx10="6861234567", source="EXPIRED",
        sucursal="Sucursal B",
    )
    original_recipient.evidence_rows.append(Evidence(
        evidence_order=0, source="EXPIRED", phone_mx10="6861234567",
        evidence_json=["synthetic"],
    ))
    batch = NS(sucursal_canon="B", recipients=(
        NS(recipient_id=501, phone_mx10="6861234567"),
    ))
    fresh = dict(
        source_approval_id=9, source_manifest_digest="b"*64,
        candidate_fingerprint=FINGERPRINT, recipient_count=1,
    )
    def assign_identity():
        derived = session.add.call_args.args[0]
        derived.id = 999
    session.flush.side_effect = assign_identity

    with patch.object(svc, "_evaluate", return_value=fresh), \
         patch.object(svc, "build_campaign_v2_preflight",
                      return_value=NS(batches=(batch,))) as plan, \
         patch.object(svc, "_source_recipients",
                      return_value=[original_recipient]) as source, \
         patch.object(svc, "assert_no_prior_or_pending_contact") as dedup:
        response = svc.freeze_derived_held_cohort(
            source_campaign_id=77, source_child_id=100, intent_id=55,
            expected_candidate_fingerprint=FINGERPRINT,
            expected_recipient_count=1, actor_user_id=7,
            allowed_sucursal_keys=None, session=session, now=NOW,
        )
    assert response["derived_campaign_id"] == 999
    assert response["status"] == "FROZEN_DERIVED"
    assert response["send_authorized"] is False
    assert response["provider_calls"] == 0
    assert intent.status == "FROZEN_DERIVED"
    assert intent.derived_campaign_id == 999
    cohort = session.add.call_args.args[0]
    assert cohort.source == guard.DERIVED_SOURCE
    assert len(cohort.recipients) == 1
    assert cohort.recipients[0].phone_mx10 == "6861234567"
    assert cohort.recipients[0].campaign_id is None
    assert len(cohort.recipients[0].evidence_rows) == 1
    assert cohort.recipients[0].evidence_rows[0].evidence_json == ["synthetic"]
    assert session.commit.call_count == 1
    dedup.assert_called_once()
    plan.assert_called_once()
    source.assert_called_once()


def test_changed_intent_or_second_freeze_refused_before_insert():
    session = MagicMock()
    session.get_bind.return_value.dialect.name = "postgresql"
    intent = NS(
        id=55, status="FROZEN_DERIVED", source_approval_id=9,
        source_manifest_digest="b"*64, candidate_fingerprint=FINGERPRINT,
        candidate_recipients=1, derived_campaign_id=999, materialized_at=NOW,
    )
    session.query.return_value.filter.return_value.with_for_update.return_value.one_or_none.return_value = intent
    session.get.return_value = NS(
        audience_definition_json={"filters":{"allowed_sucursal_keys":None}},
    )
    with patch.object(svc, "_evaluate", return_value={
        "candidate_fingerprint":FINGERPRINT, "recipient_count":1,
        "source_manifest_digest":"b"*64, "source_approval_id":9,
    }):
        with pytest.raises(svc.HeldReleaseConflict, match="materializada"):
            svc.freeze_derived_held_cohort(
                source_campaign_id=77, source_child_id=100, intent_id=55,
                expected_candidate_fingerprint=FINGERPRINT,
                expected_recipient_count=1, actor_user_id=7,
                allowed_sucursal_keys=None, session=session, now=NOW,
            )
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_derived_module_cannot_invoke_provider_or_old_approval():
    import inspect
    code = inspect.getsource(svc)
    assert "provider.create_campaign(" not in code
    assert "IVentasBroadcastProvider" not in code
    assert "approve_dispatch_reservation(" not in code
    assert "child.status =" not in code
