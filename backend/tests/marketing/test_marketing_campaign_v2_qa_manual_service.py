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
    MarketingCampaignV2BlacklistORM,
    MarketingCampaignV2ChannelBindingORM,
    MarketingCampaignV2ORM,
    MarketingCampaignV2RecipientEvidenceORM,
    MarketingCampaignV2RecipientORM,
    MarketingCampaignV2TemplateORM,
)
from app.models.sucursal_model import Sucursal
from app.models.warehouse import TrackBranchAliasORM, TrackBranchCatalogORM
from app.services import marketing_campaign_v2_qa_manual_service as service
from app.services import marketing_campaign_v2_dispatch_config_service as dispatch_config
from app.services import marketing_campaign_v2_preflight_service as preflight
from app.services.marketing_campaign_v2_dispatch_branch_service import (
    resolve_frozen_recipient_branch,
)


NOW = datetime(2026, 10, 7, 23, 45, tzinfo=timezone.utc)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    metadata = MetaData()

    Table("users", metadata, Column("id", Integer, primary_key=True))
    Table(
        "socios_vencidos_cartera",
        metadata,
        Column("id", BigInteger, primary_key=True),
    )
    Table(
        "socios_activos_snapshot_rows",
        metadata,
        Column("id", BigInteger, primary_key=True),
    )
    Table(
        "socios_activos_snapshots",
        metadata,
        Column("id", BigInteger, primary_key=True),
    )

    Sucursal.__table__.to_metadata(metadata)
    TrackBranchCatalogORM.__table__.to_metadata(metadata)
    TrackBranchAliasORM.__table__.to_metadata(metadata)
    MarketingCampaignV2BlacklistORM.__table__.to_metadata(metadata)
    MarketingCampaignV2ChannelBindingORM.__table__.to_metadata(metadata)
    MarketingCampaignV2TemplateORM.__table__.to_metadata(metadata)
    MarketingCampaignV2ORM.__table__.to_metadata(metadata)
    MarketingCampaignV2RecipientORM.__table__.to_metadata(metadata)
    MarketingCampaignV2RecipientEvidenceORM.__table__.to_metadata(metadata)
    metadata.create_all(engine)

    with Session(engine) as value:
        value.execute(
            Table("users", MetaData(), autoload_with=engine).insert().values(id=47)
        )
        value.execute(
            Table("sucursales", MetaData(), autoload_with=engine).insert().values(
                sucursal_id=16,
                serie="AZAH",
                sucursal="Azahares Culiacan",
                estado="Sinaloa",
                operational_status="ACTIVA",
                is_demo=False,
                municipio="Culiacan",
                direccion="QA",
            )
        )
        value.add(
            TrackBranchCatalogORM(
                sucursal_canon="AZAHARES_CUL",
                sucursal_id=16,
                track_label="AZAHARES CUL",
                display_order=16,
                is_track_active=True,
            )
        )
        value.commit()
        yield value
    engine.dispose()


def _recipients():
    return [
        {"name": "QA Uno", "phone": "6861000001"},
        {"name": "QA Dos", "phone": "6861000002"},
        {"name": "QA Tres", "phone": "6861000003"},
        {"name": "QA Cuatro", "phone": "6861000004"},
        {"name": "QA Cinco", "phone": "6861000005"},
    ]


def _preview(session, recipients=None):
    return service.build_campaign_v2_qa_manual_preview(
        name="QA V2 - PROD SMOKE - INVITA Y GANA 4800",
        purpose="NEW_SALE",
        sucursal_id=16,
        recipients=recipients or _recipients(),
        session=session,
    )


def test_preview_is_deterministic_and_branch_scoped(session):
    preview = _preview(session)
    reversed_preview = _preview(session, list(reversed(_recipients())))

    assert preview["source"] == "QA_MANUAL"
    assert preview["purpose"] == "NEW_SALE"
    assert preview["sucursal_id"] == 16
    assert preview["sucursal_canon"] == "AZAHARES_CUL"
    assert preview["track_label"] == "AZAHARES CUL"
    assert preview["recipient_count"] == 5
    assert preview["preview_fingerprint"] == reversed_preview["preview_fingerprint"]
    assert [row["phone_mx10"] for row in preview["recipients"]] == sorted(
        row["phone"] for row in _recipients()
    )


def test_preview_rejects_duplicate_phone_after_normalization(session):
    recipients = _recipients() + [
        {"name": "Duplicado", "phone": "+52 686 100 0001"}
    ]

    with pytest.raises(
        service.MarketingCampaignV2QAManualValidationError,
        match="duplicado",
    ):
        _preview(session, recipients)


def test_preview_rejects_more_than_ten_recipients(session):
    recipients = [
        {"name": f"QA {index}", "phone": f"68610000{index:02d}"}
        for index in range(11)
    ]

    with pytest.raises(
        service.MarketingCampaignV2QAManualValidationError,
        match="máximo 10",
    ):
        _preview(session, recipients)


def test_freeze_requires_current_preview_fingerprint(session):
    preview = _preview(session)

    with pytest.raises(
        service.MarketingCampaignV2QAManualConflictError,
        match="Preview QA cambió",
    ):
        service.freeze_campaign_v2_qa_manual(
            name=preview["name"],
            purpose="NEW_SALE",
            sucursal_id=16,
            recipients=_recipients(),
            expected_preview_fingerprint="0" * 64,
            created_by_user_id=47,
            session=session,
            now=NOW,
        )

    assert session.query(MarketingCampaignV2ORM).count() == 0


def test_freeze_persists_exact_five_with_evidence_and_resolvable_branch(session):
    preview = _preview(session)

    frozen = service.freeze_campaign_v2_qa_manual(
        name=preview["name"],
        purpose="NEW_SALE",
        sucursal_id=16,
        recipients=_recipients(),
        expected_preview_fingerprint=preview["preview_fingerprint"],
        created_by_user_id=47,
        session=session,
        now=NOW,
    )

    assert frozen["recipient_count"] == 5
    assert frozen["source"] == "QA_MANUAL"
    assert frozen["sucursal_canon"] == "AZAHARES_CUL"

    campaign = session.get(MarketingCampaignV2ORM, frozen["campaign_id"])
    assert campaign is not None
    assert campaign.created_by_user_id == 47
    assert campaign.audience_definition_json["source_metadata"]["qa_manual"] is True
    assert campaign.audience_definition_json["preview"]["summary"]["unique_recipient_count"] == 5

    recipients = (
        session.query(MarketingCampaignV2RecipientORM)
        .filter(MarketingCampaignV2RecipientORM.campaign_id == campaign.id)
        .order_by(MarketingCampaignV2RecipientORM.phone_mx10.asc())
        .all()
    )
    assert len(recipients) == 5
    assert {row.phone_mx10 for row in recipients} == {
        row["phone"] for row in _recipients()
    }
    assert all(row.source == "QA_MANUAL" for row in recipients)
    assert all(row.sucursal == "AZAHARES CUL" for row in recipients)

    evidence = session.query(MarketingCampaignV2RecipientEvidenceORM).all()
    assert len(evidence) == 5
    assert all(row.source == "QA_MANUAL" for row in evidence)
    assert all(row.sucursal_key == "AZAHARES_CUL" for row in evidence)
    assert all(row.evidence_json == ["QA_MANUAL_SMOKE"] for row in evidence)

    branch = resolve_frozen_recipient_branch(recipients[0], session=session)
    assert branch is not None
    assert branch.sucursal_id == 16
    assert branch.sucursal_canon == "AZAHARES_CUL"


def test_same_qa_campaign_name_cannot_be_frozen_twice(session):
    preview = _preview(session)
    kwargs = {
        "name": preview["name"],
        "purpose": "NEW_SALE",
        "sucursal_id": 16,
        "recipients": _recipients(),
        "expected_preview_fingerprint": preview["preview_fingerprint"],
        "created_by_user_id": 47,
        "session": session,
        "now": NOW,
    }

    service.freeze_campaign_v2_qa_manual(**kwargs)

    with pytest.raises(
        service.MarketingCampaignV2QAManualConflictError,
        match="Ya existe",
    ):
        service.freeze_campaign_v2_qa_manual(**kwargs)


def test_qa_manual_flows_into_real_m2_preflight_with_exact_phone_set(session):
    preview = _preview(session)
    frozen = service.freeze_campaign_v2_qa_manual(
        name=preview["name"],
        purpose="NEW_SALE",
        sucursal_id=16,
        recipients=_recipients(),
        expected_preview_fingerprint=preview["preview_fingerprint"],
        created_by_user_id=47,
        session=session,
        now=NOW,
    )

    binding = dispatch_config.save_channel_binding(
        provider="IVENTAS",
        sucursal_id=16,
        provider_channel_id="6a2201f802ec4b00086b8bb2",
        is_active=True,
        is_default=True,
        actor_user_id=47,
        session=session,
        now=NOW,
    )
    template = dispatch_config.save_template(
        provider="IVENTAS",
        template_name="invita_y_gana_4800",
        label="Invita y gana - 4,800 puntos",
        is_active=True,
        purposes=["NEW_SALE"],
        variables={},
        compatible_channel_ids=["6a2201f802ec4b00086b8bb2"],
        actor_user_id=47,
        session=session,
        now=NOW,
    )

    plan = preflight.build_campaign_v2_preflight(
        campaign_id=frozen["campaign_id"],
        template_id=template["id"],
        allowed_sucursal_keys=None,
        provider="IVENTAS",
        session=session,
    )

    expected_phones = {row["phone"] for row in _recipients()}
    assert plan.ready is True
    assert plan.frozen_count == 5
    assert plan.blacklisted_phones == ()
    assert set(plan.sendable_phones) == expected_phones
    assert len(plan.batches) == 1
    batch = plan.batches[0]
    assert batch.ready is True
    assert batch.sucursal_id == 16
    assert batch.sucursal_canon == "AZAHARES_CUL"
    assert batch.channel_binding_id == binding["id"]
    assert batch.provider_channel_id == "6a2201f802ec4b00086b8bb2"
    assert batch.template_name == "invita_y_gana_4800"
    assert {row.phone_mx10 for row in batch.recipients} == expected_phones
    assert batch.blocked_reasons == ()
