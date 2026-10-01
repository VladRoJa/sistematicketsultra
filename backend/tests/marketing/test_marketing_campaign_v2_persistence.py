from __future__ import annotations

from datetime import date
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import BigInteger, Column, Integer, MetaData, String, Table, create_engine, inspect as sa_inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2RecipientORM,
    MarketingReactivationCampaignORM,
    MarketingReactivationCampaignRecipientORM,
)
from app.services.marketing_phone import normalize_phone


def _migration():
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "a4d8c2e6f1b5_add_marketing_campaign_v2_persistence.py"
    )
    spec = importlib.util.spec_from_file_location("campaign_v2_persistence", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _prerequisites(metadata):
    Table("users", metadata, Column("id", Integer, primary_key=True))
    Table(
        "socios_vencidos_cartera",
        metadata,
        Column("id", BigInteger, primary_key=True),
        Column("nombre", String(255)),
        Column("tarifa", String(255)),
    )
    Table(
        "socios_activos_snapshot_rows",
        metadata,
        Column("id", BigInteger, primary_key=True),
        Column("nombre", String(255)),
        Column("tarifa", String(255)),
    )


@pytest.fixture
def engine():
    value = create_engine("sqlite://")
    metadata = MetaData()
    _prerequisites(metadata)
    MarketingCampaignV2ORM.__table__.to_metadata(metadata)
    MarketingCampaignV2RecipientORM.__table__.to_metadata(metadata)
    with value.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        metadata.create_all(connection)
        connection.execute(
            text(
                "INSERT INTO socios_vencidos_cartera (id, nombre, tarifa) "
                "VALUES (10, 'Vencido vivo', 'Tarifa viva')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO socios_activos_snapshot_rows (id, nombre, tarifa) "
                "VALUES (20, 'Activo vivo', 'Tarifa activa')"
            )
        )
    try:
        yield value
    finally:
        value.dispose()


def _campaign(campaign_id=1, **overrides):
    values = {
        "id": campaign_id,
        "name": f"Campaign {campaign_id}",
        "source": "EXPIRED_MEMBERS",
        "audience_definition_json": {"source": "EXPIRED_MEMBERS"},
    }
    values.update(overrides)
    return MarketingCampaignV2ORM(**values)


def _recipient(recipient_id=1, **overrides):
    values = {
        "id": recipient_id,
        "campaign_id": 1,
        "phone_mx10": "6861234567",
        "source": "EXPIRED_MEMBERS",
    }
    values.update(overrides)
    return MarketingCampaignV2RecipientORM(**values)


def test_campaign_and_recipient_v2_orm_contracts_are_independent_from_legacy():
    campaign_columns = MarketingCampaignV2ORM.__table__.c
    assert set(campaign_columns.keys()) == {
        "id", "name", "purpose", "source", "provider", "provider_campaign_id",
        "audience_definition_json", "created_by_user_id", "frozen_at",
        "created_at", "updated_at",
    }
    assert campaign_columns.purpose.nullable is False
    assert campaign_columns.purpose.default.arg == "UNCLASSIFIED"
    assert MarketingCampaignV2ORM.__tablename__ != MarketingReactivationCampaignORM.__tablename__

    recipient_columns = MarketingCampaignV2RecipientORM.__table__.c
    assert recipient_columns.phone_mx10.nullable is False
    assert recipient_columns.source.nullable is False
    for name in (
        "socios_vencidos_cartera_id", "socios_activos_snapshot_row_id",
        "member_id", "member_pin", "member_name", "sucursal", "tarifa_raw",
        "categoria_tarifa", "audience_family", "fecha_vencimiento_date",
        "inclusion_reason",
    ):
        assert recipient_columns[name].nullable is True
    assert "source_record_id" not in recipient_columns
    assert MarketingCampaignV2RecipientORM.__tablename__ != (
        MarketingReactivationCampaignRecipientORM.__tablename__
    )

    fks = {
        fk.parent.name: (fk.target_fullname, fk.ondelete)
        for fk in MarketingCampaignV2RecipientORM.__table__.foreign_keys
    }
    assert fks["campaign_id"] == ("marketing_campaign_v2_campaigns.id", "CASCADE")
    assert fks["socios_vencidos_cartera_id"] == ("socios_vencidos_cartera.id", "RESTRICT")
    assert fks["socios_activos_snapshot_row_id"] == ("socios_activos_snapshot_rows.id", "RESTRICT")


def test_phone_only_default_purpose_uniqueness_and_domain_constraints(engine):
    phone = normalize_phone("+52 686 123 4567")
    assert phone == "6861234567"

    with Session(engine) as session:
        session.add_all([
            _campaign(1, source="FUNNEL_PORTFOLIO", audience_definition_json={"source": "FUNNEL_PORTFOLIO"}),
            _campaign(2),
        ])
        session.add(_recipient(1, phone_mx10=phone, source="FUNNEL_PORTFOLIO"))
        session.commit()
        session.expunge_all()

        campaign = session.get(MarketingCampaignV2ORM, 1)
        recipient = session.get(MarketingCampaignV2RecipientORM, 1)
        assert campaign.purpose == "UNCLASSIFIED"
        assert recipient.phone_mx10 == phone
        assert recipient.member_id is None
        assert recipient.member_pin is None
        assert recipient.sucursal is None
        assert recipient.tarifa_raw is None
        assert recipient.audience_family is None

        session.add(_recipient(2, phone_mx10=phone, source="FUNNEL_PORTFOLIO"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(_recipient(3, campaign_id=2, phone_mx10=phone))
        session.commit()

        session.add(_recipient(4, campaign_id=2, phone_mx10="123"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(_recipient(5, campaign_id=2, phone_mx10="6861234568", audience_family="INVALID"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(_campaign(3, purpose="INVALID"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_optional_canonical_refs_restrict_and_frozen_snapshot_survives_source_changes(engine):
    with Session(engine) as session:
        session.add(_campaign())
        session.add_all([
            _recipient(
                1,
                socios_vencidos_cartera_id=10,
                member_pin="PIN-10",
                member_name="Vencido congelado",
                tarifa_raw="Tarifa congelada",
                categoria_tarifa="Convenio",
                audience_family="CONVENIO",
                fecha_vencimiento_date=date(2026, 8, 31),
                inclusion_reason="MATCHED_FILTERS",
            ),
            _recipient(
                2,
                phone_mx10="6861234568",
                source="ACTIVE_MEMBERS",
                socios_activos_snapshot_row_id=20,
                member_id="SOCIO-20",
                member_name="Activo congelado",
                tarifa_raw="Tarifa activa congelada",
                audience_family="DOMICILIADO",
            ),
        ])
        session.commit()

        session.execute(text("UPDATE socios_vencidos_cartera SET nombre='Cambio', tarifa='Cambio' WHERE id=10"))
        session.execute(text("UPDATE socios_activos_snapshot_rows SET nombre='Cambio', tarifa='Cambio' WHERE id=20"))
        session.commit()
        session.expunge_all()

        assert session.get(MarketingCampaignV2RecipientORM, 1).member_name == "Vencido congelado"
        assert session.get(MarketingCampaignV2RecipientORM, 1).tarifa_raw == "Tarifa congelada"
        assert session.get(MarketingCampaignV2RecipientORM, 2).member_name == "Activo congelado"

        with pytest.raises(IntegrityError):
            session.execute(text("DELETE FROM socios_vencidos_cartera WHERE id=10"))
            session.commit()
        session.rollback()
        with pytest.raises(IntegrityError):
            session.execute(text("DELETE FROM socios_activos_snapshot_rows WHERE id=20"))
            session.commit()
        session.rollback()


def test_campaign_delete_cascades_recipients_without_deleting_canonical_sources(engine):
    with Session(engine) as session:
        session.add(_campaign())
        session.add(_recipient(socios_vencidos_cartera_id=10))
        session.commit()
        session.execute(text("DELETE FROM marketing_campaign_v2_campaigns WHERE id=1"))
        session.commit()
        assert session.scalar(text("SELECT COUNT(*) FROM marketing_campaign_v2_recipients")) == 0
        assert session.scalar(text("SELECT COUNT(*) FROM socios_vencidos_cartera WHERE id=10")) == 1
        assert session.scalar(text("SELECT COUNT(*) FROM socios_activos_snapshot_rows WHERE id=20")) == 1


def test_migration_upgrade_downgrade_and_legacy_intact():
    migration = _migration()
    engine = create_engine("sqlite://")
    metadata = MetaData()
    _prerequisites(metadata)
    legacy_campaigns = Table(
        "marketing_reactivation_campaigns", metadata,
        Column("id", BigInteger, primary_key=True), Column("marker", String(50), nullable=False),
    )
    legacy_recipients = Table(
        "marketing_reactivation_campaign_recipients", metadata,
        Column("id", BigInteger, primary_key=True),
        Column("campaign_id", BigInteger, nullable=False),
        Column("marker", String(50), nullable=False),
    )

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            metadata.create_all(connection)
            connection.execute(legacy_campaigns.insert(), {"id": 900, "marker": "legacy-campaign"})
            connection.execute(
                legacy_recipients.insert(),
                {"id": 901, "campaign_id": 900, "marker": "legacy-recipient"},
            )

            context = MigrationContext.configure(connection)
            with Operations.context(context):
                migration.upgrade()

            tables = set(sa_inspect(connection).get_table_names())
            assert "marketing_campaign_v2_campaigns" in tables
            assert "marketing_campaign_v2_recipients" in tables

            connection.execute(
                text(
                    "INSERT INTO marketing_campaign_v2_campaigns (id, name, source) "
                    "VALUES (1, 'Phone only', 'FUNNEL_PORTFOLIO')"
                )
            )
            assert connection.scalar(
                text("SELECT purpose FROM marketing_campaign_v2_campaigns WHERE id=1")
            ) == "UNCLASSIFIED"
            connection.execute(
                text(
                    "INSERT INTO marketing_campaign_v2_recipients "
                    "(id, campaign_id, phone_mx10, source) "
                    "VALUES (1, 1, '6861234567', 'FUNNEL_PORTFOLIO')"
                )
            )

            with Operations.context(context):
                migration.downgrade()

            tables = set(sa_inspect(connection).get_table_names())
            assert "marketing_campaign_v2_campaigns" not in tables
            assert "marketing_campaign_v2_recipients" not in tables
            assert connection.scalar(
                text("SELECT marker FROM marketing_reactivation_campaigns WHERE id=900")
            ) == "legacy-campaign"
            assert connection.scalar(
                text(
                    "SELECT marker FROM marketing_reactivation_campaign_recipients "
                    "WHERE id=901"
                )
            ) == "legacy-recipient"
    finally:
        engine.dispose()
