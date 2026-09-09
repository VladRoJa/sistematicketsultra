from datetime import date
from io import StringIO
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import MarketingReactivationCampaignRecipientORM as Recipient


@pytest.fixture
def session():
    """Use the real recipient schema and minimal FK targets in an isolated DB."""
    engine = create_engine("sqlite://")
    metadata = MetaData()
    campaigns = Table(
        "marketing_reactivation_campaigns", metadata,
        Column("id", Integer, primary_key=True),
    )
    cartera = Table(
        "socios_vencidos_cartera", metadata,
        Column("id", Integer, primary_key=True),
    )
    Recipient.__table__.to_metadata(metadata)
    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
        metadata.create_all(connection)
        connection.execute(campaigns.insert(), [{"id": 1}, {"id": 2}])
        connection.execute(cartera.insert(), {"id": 10})
    try:
        with Session(engine) as value:
            yield value
    finally:
        engine.dispose()


def recipient(**overrides):
    values = dict(
        id=1, campaign_id=1, phone_mx10="6861000001",
        socios_vencidos_cartera_id=10,
        fecha_vencimiento_date=date(2026, 9, 1),
        member_name="Socio", sucursal="CENTRO", tarifa="Mensualidad",
        inclusion_status="ELIGIBLE", operational_status="NOT_CONTACTED",
        operational_reason="NO_OUTBOUND_EVIDENCE",
    )
    values.update(overrides)
    return Recipient(**values)


@pytest.mark.parametrize("reference,expiration", [
    (10, date(2026, 9, 1)),
    (None, date(2026, 9, 1)),
    (10, None),
    (None, None),
])
def test_recipient_persists_optional_expired_membership(session, reference, expiration):
    row = recipient(
        socios_vencidos_cartera_id=reference, fecha_vencimiento_date=expiration,
    )
    session.add(row)
    session.commit()
    session.expunge_all()
    saved = session.get(Recipient, 1)
    assert saved.socios_vencidos_cartera_id == reference
    assert saved.fecha_vencimiento_date == expiration
    assert saved.phone_mx10 == "6861000001"
    assert saved.member_name == "Socio"
    assert saved.sucursal == "CENTRO"
    assert saved.tarifa == "Mensualidad"


@pytest.mark.parametrize("overrides", [
    {"campaign_id": None},
    {"campaign_id": 999},
    {"phone_mx10": None},
    {"socios_vencidos_cartera_id": 999},
])
def test_required_fields_and_foreign_keys_remain_enforced(session, overrides):
    session.add(recipient(**overrides))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_phone_remains_unique_within_campaign_with_null_source(session):
    session.add(recipient(socios_vencidos_cartera_id=None, fecha_vencimiento_date=None))
    session.commit()
    session.add(recipient(id=2, socios_vencidos_cartera_id=None, fecha_vencimiento_date=None))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_same_phone_can_belong_to_different_campaigns(session):
    session.add_all([recipient(), recipient(id=2, campaign_id=2)])
    session.commit()
    assert session.query(Recipient).count() == 2


@pytest.mark.parametrize("direction,clause", [
    ("upgrade", "DROP NOT NULL"), ("downgrade", "SET NOT NULL"),
])
def test_migration_only_changes_nullability_in_postgresql(direction, clause):
    path = Path(__file__).resolve().parents[2] / "migrations" / "versions" / (
        "b9e2f7a4d3c5_nullable_campaign_recipient_expiration.py"
    )
    spec = importlib.util.spec_from_file_location("recipient_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output},
    )
    with Operations.context(context):
        getattr(migration, direction)()
    statements = {statement.strip() for statement in output.getvalue().split(";") if statement.strip()}
    assert statements == {
        f"ALTER TABLE marketing_reactivation_campaign_recipients ALTER COLUMN {column} {clause}"
        for column in ("socios_vencidos_cartera_id", "fecha_vencimiento_date")
    }
