from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import importlib.util

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.marketing import (
    MarketingCampaignV2ChannelBindingORM,
    MarketingCampaignV2ORM,
    MarketingCampaignV2ProviderCampaignORM,
    MarketingCampaignV2TemplateORM,
)
from app.models.warehouse import TrackBranchCatalogORM


NOW = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    Table("sucursales", metadata, Column("sucursal_id", Integer, primary_key=True))
    TrackBranchCatalogORM.__table__.to_metadata(metadata)

    for model in (
        MarketingCampaignV2ORM,
        MarketingCampaignV2ChannelBindingORM,
        MarketingCampaignV2TemplateORM,
        MarketingCampaignV2ProviderCampaignORM,
    ):
        model.__table__.to_metadata(metadata)

    metadata.create_all(engine)
    with Session(engine) as value:
        yield value
    engine.dispose()


def _campaign(campaign_id: int = 1):
    return MarketingCampaignV2ORM(
        id=campaign_id,
        name="QA M1",
        purpose="REACTIVATION",
        source="EXPIRED_MEMBERS",
        audience_definition_json={"schema_version": 1},
        frozen_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def _binding(binding_id: int, channel_id: str, *, default: bool):
    return MarketingCampaignV2ChannelBindingORM(
        id=binding_id,
        provider="IVENTAS",
        sucursal_id=4,
        sucursal_canon="TEC_MXL",
        provider_channel_id=channel_id,
        is_active=True,
        is_default=default,
        metadata_json={},
        created_at=NOW,
        updated_at=NOW,
    )


def _template():
    return MarketingCampaignV2TemplateORM(
        id=1,
        provider="IVENTAS",
        template_name="reactivacion_v1",
        label="Reactivación",
        is_active=True,
        purposes_json=["REACTIVATION"],
        variables_json={"1": "first_name"},
        compatible_channel_ids_json=[],
        metadata_json={},
        created_at=NOW,
        updated_at=NOW,
    )


def test_channel_binding_supports_multiple_channels_but_one_active_default(session):
    session.execute(
        Table("sucursales", MetaData(), autoload_with=session.bind).insert().values(
            sucursal_id=4
        )
    )
    session.add_all([
        _binding(1, "channel-a", default=True),
        _binding(2, "channel-b", default=False),
    ])
    session.commit()

    session.add(_binding(3, "channel-c", default=True))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_campaign_v2_has_persistent_one_to_many_provider_campaign_shape(session):
    session.execute(
        Table("sucursales", MetaData(), autoload_with=session.bind).insert().values(
            sucursal_id=4
        )
    )
    campaign = _campaign()
    binding = _binding(1, "channel-a", default=True)
    template = _template()
    session.add_all([campaign, binding, template])
    session.commit()

    rows = [
        MarketingCampaignV2ProviderCampaignORM(
            id=index,
            campaign_v2_id=campaign.id,
            provider="IVENTAS",
            sucursal_id=4,
            sucursal_canon="TEC_MXL",
            channel_binding_id=binding.id,
            provider_channel_id=binding.provider_channel_id,
            template_id=template.id,
            template_name=template.template_name,
            template_snapshot_json={"variables": {"1": "first_name"}},
            recipient_count=10,
            dispatch_fingerprint=(str(index) * 64)[:64],
            idempotency_key=(str(index + 2) * 64)[:64],
            status="PREPARED",
            created_at=NOW,
            updated_at=NOW,
        )
        for index in (1, 2)
    ]
    session.add_all(rows)
    session.commit()

    loaded = session.get(MarketingCampaignV2ORM, 1)
    assert len(loaded.provider_campaigns) == 2
    assert {row.provider_channel_id for row in loaded.provider_campaigns} == {"channel-a"}


def test_m1_dispatch_migration_is_based_on_current_head():
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "c1f7e9a4b6d2_add_campaign_v2_m1_dispatch_foundation.py"
    )
    spec = importlib.util.spec_from_file_location("campaign_v2_m1_dispatch_foundation", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.revision == "c1f7e9a4b6d2"
    assert module.down_revision == "b9e2f7a4d3c5"
