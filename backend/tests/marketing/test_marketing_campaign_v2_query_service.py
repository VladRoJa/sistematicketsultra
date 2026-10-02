from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import BigInteger, Column, Integer, MetaData, String, Table, create_engine
from sqlalchemy.orm import Session

from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2RecipientEvidenceORM,
    MarketingCampaignV2RecipientORM,
)
from app.services.marketing_campaign_v2_query_service import (
    MarketingCampaignV2NotFoundError,
    MarketingCampaignV2QueryValidationError,
    get_campaign_v2,
    get_campaign_v2_recipient,
    list_campaign_v2,
    list_campaign_v2_recipients,
    update_campaign_v2_purpose,
)


NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def _definition(scope):
    return {
        "filters": {"allowed_sucursal_keys": scope},
        "preview": {
            "fingerprint": "abc",
            "fingerprint_version": "campaign-v2-freeze-v1",
        },
    }


def _metadata():
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    Table(
        "socios_vencidos_cartera",
        metadata,
        Column("id", BigInteger, primary_key=True),
    )
    Table(
        "socios_activos_snapshots",
        metadata,
        Column("id", BigInteger, primary_key=True),
    )
    Table(
        "socios_activos_snapshot_rows",
        metadata,
        Column("id", BigInteger, primary_key=True),
        Column("snapshot_id", BigInteger),
    )
    MarketingCampaignV2ORM.__table__.to_metadata(metadata)
    MarketingCampaignV2RecipientORM.__table__.to_metadata(metadata)
    MarketingCampaignV2RecipientEvidenceORM.__table__.to_metadata(metadata)
    return metadata


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    metadata = _metadata()
    metadata.create_all(engine)
    with Session(engine) as value:
        value.add_all(
            [
                MarketingCampaignV2ORM(
                    id=1,
                    name="Global",
                    purpose="REACTIVATION",
                    source="EXPIRED_MEMBERS",
                    audience_definition_json=_definition(None),
                    frozen_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                ),
                MarketingCampaignV2ORM(
                    id=2,
                    name="A",
                    purpose="ACTIVE_MEMBERS",
                    source="ACTIVE_MEMBERS",
                    provider="IVENTAS",
                    provider_campaign_id="provider-campaign-2",
                    audience_definition_json=_definition(["BRANCH A"]),
                    frozen_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                ),
                MarketingCampaignV2ORM(
                    id=3,
                    name="AB",
                    purpose="REACTIVATION",
                    source="EXPIRED_MEMBERS",
                    audience_definition_json=_definition(["BRANCH A", "BRANCH B"]),
                    frozen_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                ),
                MarketingCampaignV2ORM(
                    id=4,
                    name="Malformed",
                    purpose="REACTIVATION",
                    source="EXPIRED_MEMBERS",
                    audience_definition_json={"broken": True},
                    frozen_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                ),
            ]
        )
        value.add_all(
            [
                MarketingCampaignV2RecipientORM(
                    id=10,
                    campaign_id=2,
                    phone_mx10="6861000001",
                    source="ACTIVE_MEMBERS",
                    member_name="A",
                    conflict_fields_json=[],
                ),
                MarketingCampaignV2RecipientORM(
                    id=11,
                    campaign_id=2,
                    phone_mx10="6861000002",
                    source="ACTIVE_MEMBERS",
                    member_name=None,
                    conflict_fields_json=["member_name"],
                ),
                MarketingCampaignV2RecipientORM(
                    id=20,
                    campaign_id=3,
                    phone_mx10="6861000003",
                    source="EXPIRED_MEMBERS",
                    conflict_fields_json=[],
                ),
            ]
        )
        value.add_all(
            [
                MarketingCampaignV2RecipientEvidenceORM(
                    id=100,
                    recipient_id=10,
                    evidence_order=1,
                    source="ACTIVE_MEMBERS",
                    phone_mx10="6861000001",
                    member_name="second",
                    evidence_json=["B"],
                    created_at=NOW,
                ),
                MarketingCampaignV2RecipientEvidenceORM(
                    id=101,
                    recipient_id=10,
                    evidence_order=0,
                    source="ACTIVE_MEMBERS",
                    phone_mx10="6861000001",
                    member_name="first",
                    evidence_json=["A"],
                    created_at=NOW,
                ),
            ]
        )
        value.commit()
        yield value
    engine.dispose()


def test_partial_scope_hides_global_outside_and_malformed_campaigns(session):
    result = list_campaign_v2(
        allowed_sucursal_keys=("BRANCH A",),
        session=session,
    )
    assert [row["id"] for row in result["rows"]] == [2]
    assert result["rows"][0]["provider"] == "IVENTAS"
    assert result["rows"][0]["provider_campaign_id"] == "provider-campaign-2"


def test_partial_scope_sees_only_campaigns_fully_contained_in_current_scope(session):
    result = list_campaign_v2(
        allowed_sucursal_keys=("BRANCH A", "BRANCH B"),
        session=session,
    )
    assert {row["id"] for row in result["rows"]} == {2, 3}


def test_global_scope_reads_valid_global_and_local_but_denies_malformed(session):
    result = list_campaign_v2(allowed_sucursal_keys=None, session=session)
    assert {row["id"] for row in result["rows"]} == {1, 2, 3}


def test_known_campaign_id_outside_scope_fails_as_not_found(session):
    with pytest.raises(MarketingCampaignV2NotFoundError):
        get_campaign_v2(
            campaign_id=3,
            allowed_sucursal_keys=("BRANCH A",),
            session=session,
        )


def test_campaign_detail_uses_frozen_definition_and_recipient_count(session):
    result = get_campaign_v2(
        campaign_id=2,
        allowed_sucursal_keys=("BRANCH A",),
        session=session,
    )
    assert result["recipient_count"] == 2
    assert result["provider"] == "IVENTAS"
    assert result["provider_campaign_id"] == "provider-campaign-2"
    assert result["audience_definition"] == _definition(["BRANCH A"])
    assert result["preview_fingerprint"] == "abc"


def test_recipient_list_is_stable_paginated_and_counts_evidence_without_loading_rows(session):
    result = list_campaign_v2_recipients(
        campaign_id=2,
        allowed_sucursal_keys=("BRANCH A",),
        page=1,
        page_size=10,
        session=session,
    )
    assert [row["id"] for row in result["rows"]] == [10, 11]
    assert result["rows"][0]["evidence_count"] == 2
    assert result["rows"][1]["conflict_fields"] == ["member_name"]


def test_recipient_detail_reads_only_frozen_evidence_in_evidence_order(session):
    result = get_campaign_v2_recipient(
        campaign_id=2,
        recipient_id=10,
        allowed_sucursal_keys=("BRANCH A",),
        session=session,
    )
    assert [row["evidence_order"] for row in result["evidence"]] == [0, 1]
    assert [row["member_name"] for row in result["evidence"]] == ["first", "second"]


def test_recipient_id_from_another_campaign_is_not_disclosed(session):
    with pytest.raises(MarketingCampaignV2NotFoundError):
        get_campaign_v2_recipient(
            campaign_id=2,
            recipient_id=20,
            allowed_sucursal_keys=("BRANCH A",),
            session=session,
        )


def test_purpose_is_only_mutation_and_preserves_frozen_definition_and_frozen_at(session):
    before = get_campaign_v2(
        campaign_id=2,
        allowed_sucursal_keys=("BRANCH A",),
        session=session,
    )
    result = update_campaign_v2_purpose(
        campaign_id=2,
        purpose="NEW_SALE",
        allowed_sucursal_keys=("BRANCH A",),
        session=session,
        now=datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc),
    )
    assert result["purpose"] == "NEW_SALE"
    assert result["frozen_at"] == before["frozen_at"]
    assert result["audience_definition"] == before["audience_definition"]
    assert result["recipient_count"] == before["recipient_count"]


def test_invalid_purpose_and_empty_backend_scope_fail_closed(session):
    with pytest.raises(MarketingCampaignV2QueryValidationError):
        update_campaign_v2_purpose(
            campaign_id=2,
            purpose="SENT",
            allowed_sucursal_keys=("BRANCH A",),
            session=session,
        )
    with pytest.raises(MarketingCampaignV2QueryValidationError):
        list_campaign_v2(allowed_sucursal_keys=(), session=session)


def test_list_filters_and_pagination_are_stable(session):
    result = list_campaign_v2(
        allowed_sucursal_keys=None,
        purpose="REACTIVATION",
        source="EXPIRED_MEMBERS",
        page=1,
        page_size=1,
        session=session,
    )
    assert result["total"] == 2
    assert result["total_pages"] == 2
    assert len(result["rows"]) == 1


def test_query_source_filter_accepts_funnel_portfolio():
    from app.services import marketing_campaign_v2_query_service as service

    assert service._normalize_optional_source("funnel_portfolio") == "FUNNEL_PORTFOLIO"
