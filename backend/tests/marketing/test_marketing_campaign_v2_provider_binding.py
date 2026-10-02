from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.marketing import MarketingCampaignV2ORM
from app.services.marketing_campaign_v2_provider_binding_service import (
    MarketingCampaignV2ProviderBindingConflictError,
    bind_campaign_v2_provider,
)


NOW = datetime(2026, 10, 1, 14, 0, tzinfo=timezone.utc)


def _definition(scope=None):
    return {
        "filters": {"allowed_sucursal_keys": scope},
        "preview": {
            "fingerprint": "abc",
            "fingerprint_version": "campaign-v2-freeze-v1",
        },
    }


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    MarketingCampaignV2ORM.__table__.to_metadata(metadata)
    metadata.create_all(engine)
    with Session(engine) as value:
        value.add_all(
            [
                MarketingCampaignV2ORM(
                    id=1,
                    name="Campaign 1",
                    source="EXPIRED_MEMBERS",
                    audience_definition_json=_definition(None),
                    frozen_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                ),
                MarketingCampaignV2ORM(
                    id=2,
                    name="Campaign 2",
                    source="EXPIRED_MEMBERS",
                    audience_definition_json=_definition(None),
                    frozen_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                ),
                MarketingCampaignV2ORM(
                    id=3,
                    name="Campaign 3",
                    source="EXPIRED_MEMBERS",
                    audience_definition_json=_definition(None),
                    frozen_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                ),
            ]
        )
        value.commit()
        yield value
    engine.dispose()


def test_orm_provider_binding_is_nullable_atomic_and_unique_per_provider_identity():
    columns = MarketingCampaignV2ORM.__table__.c
    assert columns.provider.nullable is True
    assert columns.provider.type.length == 50
    assert columns.provider_campaign_id.nullable is True
    assert columns.provider_campaign_id.type.length == 255

    constraint_names = {
        constraint.name
        for constraint in MarketingCampaignV2ORM.__table__.constraints
    }
    assert (
        "ck_marketing_campaign_v2_campaigns_provider_binding_complete"
        in constraint_names
    )
    assert (
        "uq_marketing_campaign_v2_campaigns_provider_identity"
        in constraint_names
    )


def test_db_rejects_partial_binding_and_duplicate_pair_but_allows_same_id_other_provider(
    session,
):
    campaign1 = session.get(MarketingCampaignV2ORM, 1)
    campaign1.provider = "IVENTAS"
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    campaign1 = session.get(MarketingCampaignV2ORM, 1)
    campaign1.provider = "IVENTAS"
    campaign1.provider_campaign_id = "external-1"
    session.commit()

    campaign2 = session.get(MarketingCampaignV2ORM, 2)
    campaign2.provider = "IVENTAS"
    campaign2.provider_campaign_id = "external-1"
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    campaign3 = session.get(MarketingCampaignV2ORM, 3)
    campaign3.provider = "OTHER"
    campaign3.provider_campaign_id = "external-1"
    session.commit()

    campaign3.provider = "other"
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_binding_is_idempotent_for_same_campaign_and_same_pair(session):
    first = bind_campaign_v2_provider(
        campaign_id=1,
        provider=" iventas ",
        provider_campaign_id=" 6abc425d1575f30008bdc1ac ",
        allowed_sucursal_keys=None,
        session=session,
        now=NOW,
    )
    second = bind_campaign_v2_provider(
        campaign_id=1,
        provider="IVENTAS",
        provider_campaign_id="6abc425d1575f30008bdc1ac",
        allowed_sucursal_keys=None,
        session=session,
        now=NOW,
    )

    assert first == {
        "campaign_id": 1,
        "provider": "IVENTAS",
        "provider_campaign_id": "6abc425d1575f30008bdc1ac",
        "created": True,
    }
    assert second["created"] is False


def test_binding_rejects_rebinding_same_campaign_to_different_identity(session):
    bind_campaign_v2_provider(
        campaign_id=1,
        provider="IVENTAS",
        provider_campaign_id="external-1",
        allowed_sucursal_keys=None,
        session=session,
    )

    with pytest.raises(
        MarketingCampaignV2ProviderBindingConflictError,
        match="otra identidad",
    ):
        bind_campaign_v2_provider(
            campaign_id=1,
            provider="IVENTAS",
            provider_campaign_id="external-2",
            allowed_sucursal_keys=None,
            session=session,
        )


def test_binding_rejects_same_provider_identity_on_second_campaign(session):
    bind_campaign_v2_provider(
        campaign_id=1,
        provider="IVENTAS",
        provider_campaign_id="external-1",
        allowed_sucursal_keys=None,
        session=session,
    )

    with pytest.raises(
        MarketingCampaignV2ProviderBindingConflictError,
        match="otra Campaign V2",
    ):
        bind_campaign_v2_provider(
            campaign_id=2,
            provider="IVENTAS",
            provider_campaign_id="external-1",
            allowed_sucursal_keys=None,
            session=session,
        )


def test_binding_allows_same_external_id_for_different_provider(session):
    bind_campaign_v2_provider(
        campaign_id=1,
        provider="IVENTAS",
        provider_campaign_id="same-id",
        allowed_sucursal_keys=None,
        session=session,
    )
    result = bind_campaign_v2_provider(
        campaign_id=2,
        provider="OTHER",
        provider_campaign_id="same-id",
        allowed_sucursal_keys=None,
        session=session,
    )
    assert result["provider"] == "OTHER"
    assert result["provider_campaign_id"] == "same-id"


def test_migration_revision_and_operations_are_bound_to_current_head(monkeypatch):
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "d3e7f1a9c2b4_add_campaign_v2_provider_binding.py"
    )
    spec = importlib.util.spec_from_file_location("campaign_v2_provider_binding", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.revision == "d3e7f1a9c2b4"
    assert module.down_revision == "b7c2e9f4a1d6"

    calls = []
    monkeypatch.setattr(
        module.op,
        "add_column",
        lambda table, column: calls.append(("add_column", table, column.name)),
    )
    monkeypatch.setattr(
        module.op,
        "create_check_constraint",
        lambda name, table, condition: calls.append(
            ("check", name, table, condition)
        ),
    )
    monkeypatch.setattr(
        module.op,
        "create_unique_constraint",
        lambda name, table, columns: calls.append(
            ("unique", name, table, tuple(columns))
        ),
    )

    module.upgrade()

    assert (
        "add_column",
        "marketing_campaign_v2_campaigns",
        "provider",
    ) in calls
    assert (
        "add_column",
        "marketing_campaign_v2_campaigns",
        "provider_campaign_id",
    ) in calls
    assert any(row[0] == "check" for row in calls)
    assert (
        "unique",
        "uq_marketing_campaign_v2_campaigns_provider_identity",
        "marketing_campaign_v2_campaigns",
        ("provider", "provider_campaign_id"),
    ) in calls
