"""Synthetic integrity tests for frozen, unsendable V2 follow-up cohorts."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import BigInteger, Column, Integer, MetaData, Table, create_engine, func
from sqlalchemy.orm import Session

from app.models.marketing import (
    MarketingCampaignV2ORM as Campaign,
    MarketingCampaignV2RecipientORM as Recipient,
    MarketingCampaignV2RecipientEvidenceORM as Evidence,
    MarketingCampaignV2ProviderStatsSnapshotORM as Snapshot,
    MarketingCampaignV2ProviderRecipientObservationORM as Observation,
    MarketingCampaignV2BlacklistORM as Blacklist,
)
from app.services.marketing_campaign_v2_followup_preview_service import (
    build_followup_preview, FOLLOWUP_DERIVED_SOURCE,
)
from app.services.marketing_campaign_v2_followup_freeze_service import (
    FOLLOWUP_FREEZE_VERSION, FollowupFreezeConflictError,
    FollowupFreezeValidationError, freeze_followup_campaign, _require_postgresql,
)
from app.services.marketing_campaign_v2_query_service import MarketingCampaignV2NotFoundError
from app.services.marketing_campaign_v2_preflight_service import build_campaign_v2_preflight
from app.services.marketing_campaign_v2_contact_gate_service import verify_outbound_contact_admission, CampaignV2ContactGateConflict
from app.services.marketing_campaign_v2_dispatch_config_service import MarketingCampaignV2DispatchConfigValidationError
from types import SimpleNamespace

NOW = datetime(2026, 10, 20, 17, 0, tzinfo=timezone.utc)


@pytest.fixture
def session():
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    Table("socios_vencidos_cartera", metadata, Column("id", BigInteger, primary_key=True))
    Table("socios_activos_snapshots", metadata, Column("id", BigInteger, primary_key=True))
    Table(
        "socios_activos_snapshot_rows", metadata,
        Column("id", BigInteger, primary_key=True),
        Column("snapshot_id", BigInteger),
    )
    for model in (Campaign, Recipient, Evidence, Snapshot, Observation, Blacklist):
        model.__table__.to_metadata(metadata)
    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    with Session(engine) as active:
        active.add(Campaign(
            id=2, name="Azahares fuente", source="EXPIRED_MEMBERS",
            purpose="REACTIVATION",
            audience_definition_json={
                "filters": {"allowed_sucursal_keys": ["BRANCH A"], "audience_families": ["DOMICILIADO"]},
            },
            created_at=NOW, frozen_at=NOW, updated_at=NOW,
        ))
        for rid in range(10, 14):
            active.add(Recipient(
                id=rid, campaign_id=2,
                phone_mx10=f"68610000{rid:02d}", source="EXPIRED_MEMBERS",
                member_name=f"SOCIO {rid}", sucursal="BRANCH A",
                conflict_fields_json=[], created_at=NOW,
            ))
        active.add(Evidence(
            id=50, recipient_id=10, evidence_order=0,
            source="EXPIRED_MEMBERS", phone_mx10="6861000010",
            evidence_json=["origen de prueba"], created_at=NOW,
        ))
        active.add(Snapshot(
            id=101, campaign_v2_id=2,
            provider="IVENTAS", provider_campaign_id="provider-2",
            fetched_at=NOW, created_at=NOW,
            raw_successful=3, raw_failed=1, raw_sent=0, raw_delivered=1,
            raw_viewed=2, raw_answered=0, raw_interaction_groups=0,
            raw_interaction_items=0, provider_recipient_count=4,
            matched_recipient_count=4, unmatched_provider_count=0,
            frozen_recipient_without_provider_status_count=0,
            fingerprint="a" * 64,
        ))
        active.add_all([
            Observation(
                snapshot_id=101, campaign_recipient_id=rid,
                normalized_phone=f"mx10:68610000{rid:02d}",
                outcome="FAILED" if rid == 13 else "SUCCESSFUL",
                delivery_bucket=("DELIVERED" if rid == 11 else "VIEWED") if rid != 13 else None,
                button_labels_json=[], created_at=NOW,
            ) for rid in range(10, 14)
        ])
        active.commit()
        yield active
    engine.dispose()


def _preview(active):
    return build_followup_preview(
        source_campaign_id=2,
        selected_statuses=["VIEWED", "DELIVERED"],
        expected_snapshot_id=101,
        allowed_sucursal_keys=["BRANCH A"], session=active,
    )


def _freeze(active, **overrides):
    preview = _preview(active)
    args = dict(
        source_campaign_id=2,
        name="Azahares · Seguimiento",
        selected_statuses=["DELIVERED", "VIEWED"],
        source_snapshot_id=101,
        expected_preview_fingerprint=preview["preview_fingerprint"],
        expected_recipient_count=preview["candidate_count"],
        actor_user_id=7,
        allowed_sucursal_keys=["BRANCH A"],
        session=active,
        now=NOW,
    )
    args.update(overrides)
    # Unit tests use SQLite for relational assertions.  Production keeps
    # PostgreSQL mandatory and obtains a transaction-scoped advisory lock.
    with patch(
        "app.services.marketing_campaign_v2_followup_freeze_service._require_postgresql"
    ), patch(
        "app.services.marketing_campaign_v2_followup_freeze_service.acquire_campaign_v2_contact_gate"
    ):
        return freeze_followup_campaign(**args)


def _derived(active):
    return active.query(Campaign).filter(Campaign.source == FOLLOWUP_DERIVED_SOURCE).all()


def test_postgresql_is_mandatory_for_actual_freeze(session):
    with pytest.raises(FollowupFreezeConflictError, match="PostgreSQL"):
        _require_postgresql(session)
    assert _derived(session) == []


def test_freeze_copies_only_selected_recipients_evidence_and_scope(session):
    result = _freeze(session)
    assert result["status"] == "FROZEN_FOLLOWUP"
    assert result["recipient_count"] == 3
    assert result["source_campaign_id"] == 2
    assert result["source_snapshot_id"] == 101
    assert result["send_authorized"] is False
    assert result["quota_reserved"] is False
    assert result["dispatch_locked"] is True
    assert result["provider_calls"] == 0
    assert len(_derived(session)) == 1
    new = _derived(session)[0]
    assert int(new.id) == result["derived_campaign_id"]
    assert new.provider is None and new.provider_campaign_id is None
    assert new.created_by_user_id == 7
    frozen = new.audience_definition_json
    assert frozen["filters"] == {
        "allowed_sucursal_keys": ["BRANCH A"], "audience_families": ["DOMICILIADO"]
    }
    assert frozen["followup"]["version"] == FOLLOWUP_FREEZE_VERSION
    assert frozen["followup"]["selected_statuses"] == ["DELIVERED", "VIEWED"]
    assert frozen["followup"]["source_snapshot_fingerprint"] == "a" * 64
    assert frozen["followup"]["source_preview_fingerprint"] == _preview(session)["preview_fingerprint"]
    assert frozen["followup"]["dispatch_locked"] is True
    copied = sorted(new.recipients, key=lambda r: r.id)
    assert [r.phone_mx10 for r in copied] == [
        "6861000010", "6861000011", "6861000012"
    ]
    assert copied[0].member_name == "SOCIO 10"
    assert len(copied[0].evidence_rows) == 1
    assert copied[0].evidence_rows[0].id != 50
    assert copied[0].evidence_rows[0].evidence_json == ["origen de prueba"]
    assert session.query(func.count(Recipient.id)).filter(Recipient.campaign_id == 2).scalar() == 4
    assert session.query(func.count(Observation.id)).scalar() == 4


def test_repeated_freeze_with_another_name_fails_and_keeps_one_cohort(session):
    _freeze(session)
    with pytest.raises(FollowupFreezeConflictError, match="otra cohorte"):
        _freeze(session, name="Intento repetido")
    assert len(_derived(session)) == 1


def test_blacklist_does_not_silently_shrink_previewed_cohort(session):
    session.add(Blacklist(id=9, phone_mx10="6861000011", created_at=NOW))
    session.commit()
    with pytest.raises(FollowupFreezeConflictError, match="lista negra"):
        _freeze(session)
    assert not _derived(session)
    assert session.query(func.count(Recipient.id)).scalar() == 4


def test_stale_fingerprint_and_count_fail_closed(session):
    with pytest.raises(FollowupFreezeConflictError, match="audiencia cambió"):
        _freeze(session, expected_preview_fingerprint="0" * 64)
    with pytest.raises(FollowupFreezeConflictError, match="audiencia cambió"):
        _freeze(session, expected_recipient_count=2)
    with pytest.raises(FollowupFreezeConflictError, match="snapshot cambió"):
        _freeze(session, source_snapshot_id=100)
    assert not _derived(session)


def test_wrong_scope_is_indistinguishable_from_missing_source(session):
    with pytest.raises(MarketingCampaignV2NotFoundError):
        _freeze(session, allowed_sucursal_keys=["BRANCH B"])
    assert not _derived(session)


def test_bad_freeze_inputs_do_not_write(session):
    with pytest.raises(FollowupFreezeValidationError):
        _freeze(session, name=" ")
    with pytest.raises(FollowupFreezeValidationError):
        _freeze(session, name="x" * 256)
    with pytest.raises(FollowupFreezeValidationError):
        _freeze(session, expected_preview_fingerprint="tampered")
    assert not _derived(session)


def test_disjoint_freeze_after_first_does_not_reuse_contacts(session):
    first = _freeze(session, selected_statuses=["VIEWED"], expected_recipient_count=2,
        expected_preview_fingerprint=build_followup_preview(
            source_campaign_id=2, selected_statuses=["VIEWED"],
            allowed_sucursal_keys=["BRANCH A"], session=session,
        )["preview_fingerprint"])
    second = _freeze(session, selected_statuses=["DELIVERED"], expected_recipient_count=1,
        expected_preview_fingerprint=build_followup_preview(
            source_campaign_id=2, selected_statuses=["DELIVERED"],
            allowed_sucursal_keys=["BRANCH A"], session=session,
        )["preview_fingerprint"])
    assert first["derived_campaign_id"] != second["derived_campaign_id"]
    assert len(_derived(session)) == 2


def test_dispatch_preflight_rejects_frozen_followup_even_with_template(session):
    frozen = _freeze(session)
    with patch(
        "app.services.marketing_campaign_v2_preflight_service.build_campaign_v2_sendable_projection",
        return_value={"campaign": {"source": FOLLOWUP_DERIVED_SOURCE}},
    ):
        with pytest.raises(MarketingCampaignV2DispatchConfigValidationError, match="bloqueado"):
            build_campaign_v2_preflight(
                campaign_id=frozen["derived_campaign_id"],
                template_id=1, allowed_sucursal_keys=["BRANCH A"], session=session,
            )


def test_outbound_contact_gate_still_rejects_followup_even_if_bypassing_preflight(session):
    frozen = _freeze(session)
    child = SimpleNamespace(campaign_v2_id=frozen["derived_campaign_id"])
    with pytest.raises(CampaignV2ContactGateConflict, match="no tiene autorización"):
        verify_outbound_contact_admission(child=child, session=session)
