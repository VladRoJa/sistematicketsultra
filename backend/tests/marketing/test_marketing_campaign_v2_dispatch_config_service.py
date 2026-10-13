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
    MarketingCampaignV2ORM,
    MarketingCampaignV2ProviderCampaignORM,
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
    MarketingCampaignV2ORM.__table__.to_metadata(metadata)
    MarketingCampaignV2ProviderCampaignORM.__table__.to_metadata(metadata)
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


def test_template_catalog_normalizes_optional_file_url(session):
    saved = service.save_template(
        provider="IVENTAS",
        template_name="media_template",
        label="Media template",
        is_active=True,
        purposes=["NEW_SALE"],
        variables={},
        compatible_channel_ids=["channel-current"],
        metadata={
            "approval_status": "APPROVED",
            "file_url": "  https://media.example.test/header.png  ",
        },
        actor_user_id=7,
        session=session,
        now=NOW,
    )

    assert saved["metadata"]["approval_status"] == "APPROVED"
    assert saved["metadata"]["file_url"] == "https://media.example.test/header.png"

    row = service.resolve_dispatch_template(
        template_id=saved["id"],
        provider="IVENTAS",
        purpose="NEW_SALE",
        session=session,
    )
    assert service.template_file_url(row) == "https://media.example.test/header.png"


def test_template_catalog_rejects_non_https_file_url(session):
    with pytest.raises(
        service.MarketingCampaignV2DispatchConfigValidationError,
        match="URL HTTPS absoluta",
    ):
        service.save_template(
            provider="IVENTAS",
            template_name="bad_media",
            label="Bad media",
            is_active=True,
            purposes=["NEW_SALE"],
            variables={},
            compatible_channel_ids=[],
            metadata={"file_url": "http://media.example.test/header.png"},
            actor_user_id=7,
            session=session,
        )


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


def _active_channel(session):
    return service.save_channel_binding(
        provider="IVENTAS", sucursal_id=4,
        provider_channel_id="channel-current",
        is_active=True, is_default=True, actor_user_id=7,
        session=session, now=NOW,
    )


def test_admin_template_requires_explicit_active_channels(session):
    _active_channel(session)
    def register(channels, **extra):
        return service.save_template(
            provider="IVENTAS", template_name="admin_v1", label="Admin V1",
            is_active=True, purposes=["REACTIVATION"],
            variables={"1": "branch"}, compatible_channel_ids=channels,
            actor_user_id=7, require_explicit_channels=True,
            session=session, now=NOW, **extra,
        )

    with pytest.raises(service.MarketingCampaignV2DispatchConfigValidationError,
                       match="al menos un canal"):
        register([])
    with pytest.raises(service.MarketingCampaignV2DispatchConfigValidationError,
                       match="inexistentes o inactivos"):
        register(["unknown-channel"])

    saved = register(["channel-current"])
    assert saved["compatible_channel_ids"] == ["channel-current"]
    assert service.list_templates(active_only=True, purpose="REACTIVATION", session=session)
    assert not service.template_allows_channel(
        session.get(MarketingCampaignV2TemplateORM, saved["id"]), "other-channel"
    )


def test_admin_template_inactive_visible_only_in_admin_list(session):
    _active_channel(session)
    saved = service.save_template(
        provider="IVENTAS", template_name="inactive-admin", label="Inactive",
        is_active=False, purposes=["REACTIVATION"], variables={},
        compatible_channel_ids=["channel-current"], actor_user_id=7,
        require_explicit_channels=True, session=session, now=NOW,
    )
    assert service.list_templates(active_only=True, session=session) == []
    assert [row["id"] for row in service.list_templates(
        active_only=False, session=session
    )] == [saved["id"]]


def test_admin_template_rejects_nonconsecutive_variables(session):
    _active_channel(session)
    with pytest.raises(service.MarketingCampaignV2DispatchConfigValidationError,
                       match="consecutivas"):
        service.save_template(
            provider="IVENTAS", template_name="gap", label="Gap",
            is_active=True, purposes=["REACTIVATION"],
            variables={"1": "branch", "3": "amount"},
            compatible_channel_ids=["channel-current"],
            actor_user_id=7, require_explicit_channels=True, session=session,
        )


def _campaign_child(session, *, binding_id, template_id, status="READY"):
    campaign = MarketingCampaignV2ORM(
        name="Legacy audit", purpose="REACTIVATION",
        source="EXPIRED_MEMBERS", created_by_user_id=7,
        audience_definition_json={"schema_version": 1}, frozen_at=NOW,
    )
    session.add(campaign)
    session.flush()
    child = MarketingCampaignV2ProviderCampaignORM(
        campaign_v2_id=campaign.id,
        provider="IVENTAS", sucursal_id=4, sucursal_canon="TEC_MXL",
        channel_binding_id=binding_id, provider_channel_id="channel-current",
        template_id=template_id, template_name="historic-template",
        recipient_count=2, dispatch_fingerprint="a" * 64,
        idempotency_key="b" * 64, status=status,
        created_by_user_id=7,
        request_snapshot_json={"leads": []},
    )
    session.add(child)
    session.commit()
    return child


def test_admin_template_rejects_mutating_previously_used_dispatch(session):
    channel = _active_channel(session)
    saved = service.save_template(
        provider="IVENTAS", template_name="historic-template",
        label="Histórica", is_active=True,
        purposes=["REACTIVATION"], variables={"1": "branch"},
        compatible_channel_ids=["channel-current"], actor_user_id=7,
        require_explicit_channels=True, session=session, now=NOW,
    )
    _campaign_child(session, binding_id=channel["id"], template_id=saved["id"])
    original = dict(
        template_id=saved["id"], provider="IVENTAS",
        template_name="historic-template", label="Histórica",
        is_active=True, purposes=["REACTIVATION"],
        variables={"1": "branch"}, compatible_channel_ids=["channel-current"],
        actor_user_id=7, require_explicit_channels=True, session=session, now=NOW,
    )
    with pytest.raises(service.MarketingCampaignV2DispatchConfigConflictError,
                       match="lotes auditados"):
        service.save_template(**{**original, "template_name": "different-name"})
    with pytest.raises(service.MarketingCampaignV2DispatchConfigConflictError,
                       match="pendientes"):
        service.save_template(**{**original, "is_active": False})
    updated = service.save_template(**{**original, "label": "Etiqueta editable"})
    assert updated["label"] == "Etiqueta editable"


def test_admin_binding_prevents_changing_identity_used_by_child(session):
    channel = _active_channel(session)
    saved = service.save_template(
        provider="IVENTAS", template_name="historic-template",
        label="Histórica", is_active=True, purposes=["REACTIVATION"],
        variables={}, compatible_channel_ids=["channel-current"],
        actor_user_id=7, require_explicit_channels=True, session=session,
    )
    _campaign_child(session, binding_id=channel["id"], template_id=saved["id"])
    with pytest.raises(service.MarketingCampaignV2DispatchConfigConflictError,
                       match="envíos auditados"):
        service.save_channel_binding(
            binding_id=channel["id"], provider="IVENTAS", sucursal_id=4,
            provider_channel_id="changed-id", is_active=True,
            is_default=True, actor_user_id=7, session=session,
            require_immutable_history=True,
        )
    with pytest.raises(service.MarketingCampaignV2DispatchConfigConflictError,
                       match="pendientes"):
        service.save_channel_binding(
            binding_id=channel["id"], provider="IVENTAS", sucursal_id=4,
            provider_channel_id="channel-current", is_active=False,
            is_default=False, actor_user_id=7, session=session,
            require_immutable_history=True,
        )
