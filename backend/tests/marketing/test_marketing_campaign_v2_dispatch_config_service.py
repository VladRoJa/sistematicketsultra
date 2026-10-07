from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import BigInteger, Column, Integer, MetaData, Table, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(BigInteger, "sqlite")
def _sqlite_bigint_as_integer(_type, _compiler, **_kwargs):
    return "INTEGER"

from app.models.marketing import (
    MarketingCampaignV2ChannelBindingORM,
    MarketingCampaignV2TemplateORM,
)
from app.models.sucursal_model import Sucursal
from app.models.warehouse import TrackBranchCatalogORM
from app.services import marketing_campaign_v2_dispatch_config_service as service


NOW = datetime(2026, 10, 7, 16, 0, tzinfo=timezone.utc)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    Sucursal.__table__.to_metadata(metadata)
    TrackBranchCatalogORM.__table__.to_metadata(metadata)
    MarketingCampaignV2ChannelBindingORM.__table__.to_metadata(metadata)
    MarketingCampaignV2TemplateORM.__table__.to_metadata(metadata)
    metadata.create_all(engine)

    with Session(engine) as value:
        value.execute(
            Table("users", MetaData(), autoload_with=engine).insert().values(id=7)
        )
        value.execute(
            Table("sucursales", MetaData(), autoload_with=engine).insert().values(
                sucursal_id=4,
                serie="TEC",
                sucursal="Tecnológico",
                estado="BC",
                operational_status="ACTIVA",
                is_demo=False,
                municipio="Mexicali",
                direccion="QA",
            )
        )
        value.add(
            TrackBranchCatalogORM(
                sucursal_canon="TEC_MXL",
                sucursal_id=4,
                track_label="TEC MXL",
                display_order=4,
                is_track_active=True,
            )
        )
        value.commit()
        yield value
    engine.dispose()


def test_channel_config_keeps_multiple_channels_and_moves_default(session):
    first = service.save_channel_binding(
        provider="iventas",
        sucursal_id=4,
        provider_channel_id="channel-old",
        is_active=True,
        is_default=True,
        actor_user_id=7,
        session=session,
        now=NOW,
    )
    second = service.save_channel_binding(
        provider="IVENTAS",
        sucursal_id=4,
        provider_channel_id="channel-current",
        is_active=True,
        is_default=True,
        actor_user_id=7,
        session=session,
        now=NOW,
    )

    rows = service.list_channel_bindings(
        provider="IVENTAS",
        active_only=True,
        session=session,
    )
    assert len(rows) == 2
    by_id = {row["id"]: row for row in rows}
    assert by_id[first["id"]]["is_default"] is False
    assert by_id[second["id"]]["is_default"] is True

    resolved = service.resolve_dispatch_channel_binding(
        provider="IVENTAS",
        sucursal_id=4,
        session=session,
    )
    assert resolved.provider_channel_id == "channel-current"
    assert resolved.sucursal_canon == "TEC_MXL"


def test_channel_config_inactive_binding_cannot_resolve(session):
    saved = service.save_channel_binding(
        provider="IVENTAS",
        sucursal_id=4,
        provider_channel_id="channel-current",
        is_active=True,
        is_default=True,
        actor_user_id=7,
        session=session,
        now=NOW,
    )
    service.save_channel_binding(
        binding_id=saved["id"],
        provider="IVENTAS",
        sucursal_id=4,
        provider_channel_id="channel-current",
        is_active=False,
        is_default=True,
        actor_user_id=7,
        session=session,
        now=NOW,
    )

    assert service.resolve_dispatch_channel_binding(
        provider="IVENTAS",
        sucursal_id=4,
        session=session,
    ) is None


def test_template_catalog_normalizes_mapping_and_filters_by_purpose(session):
    saved = service.save_template(
        provider="iventas",
        template_name=" reactivacion_v1 ",
        label=" Reactivación ",
        is_active=True,
        purposes=["REACTIVATION"],
        variables={"2": "expiration_date", "1": "first_name"},
        compatible_channel_ids=["channel-current"],
        actor_user_id=7,
        session=session,
        now=NOW,
    )

    assert saved["provider"] == "IVENTAS"
    assert saved["variables"] == {
        "1": "first_name",
        "2": "expiration_date",
    }
    assert len(
        service.list_templates(
            provider="IVENTAS",
            purpose="REACTIVATION",
            session=session,
        )
    ) == 1
    assert service.list_templates(
        provider="IVENTAS",
        purpose="NEW_SALE",
        session=session,
    ) == []


def test_template_catalog_rejects_unknown_variable_source(session):
    with pytest.raises(
        service.MarketingCampaignV2DispatchConfigValidationError,
        match="no soportada",
    ):
        service.save_template(
            provider="IVENTAS",
            template_name="bad",
            label="Bad",
            is_active=True,
            purposes=["REACTIVATION"],
            variables={"1": "browser_supplied_var"},
            compatible_channel_ids=[],
            actor_user_id=7,
            session=session,
        )


def test_resolve_template_rejects_inactive(session):
    saved = service.save_template(
        provider="IVENTAS",
        template_name="inactive",
        label="Inactive",
        is_active=False,
        purposes=["REACTIVATION"],
        variables={},
        compatible_channel_ids=[],
        actor_user_id=7,
        session=session,
    )

    with pytest.raises(
        service.MarketingCampaignV2DispatchConfigValidationError,
        match="inactivo",
    ):
        service.resolve_dispatch_template(
            template_id=saved["id"],
            provider="IVENTAS",
            purpose="REACTIVATION",
            session=session,
        )
