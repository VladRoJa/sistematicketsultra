from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    text,
)


REVISION = "a3f7c1d9e5b2"
EXPECTED_SAFE_COUNT = 198
EXCLUDED_CONFLICT_KEYS = {
    "SEMANA SLRC $199",
    "TARJETA DE REGALO",
    "TRIMESTRE NAVIDAD",
}


def _migration_module():
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / f"{REVISION}_seed_campaign_v2_safe_tariff_overrides.py"
    )
    spec = importlib.util.spec_from_file_location(
        "campaign_v2_safe_tariff_seed_migration",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_tables(metadata: MetaData):
    base = Table(
        "marketing_campaign_v2_tariffs",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("tarifa_key", String(255), nullable=False, unique=True),
        Column("tarifa_raw", String(255), nullable=False),
        Column("categoria_tarifa", String(100), nullable=False),
        Column("audience_family", String(30), nullable=False),
    )
    overrides = Table(
        "marketing_campaign_v2_tariff_overrides",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("tarifa_key", String(255), nullable=False, unique=True),
        Column("tarifa_raw", String(255), nullable=False),
        Column("categoria_tarifa", String(100), nullable=False),
        Column("audience_family", String(30), nullable=False),
        Column("created_by_user_id", Integer, nullable=True),
        Column("updated_by_user_id", Integer, nullable=True),
    )
    return base, overrides


def test_safe_seed_snapshot_is_unique_and_excludes_catalog_conflicts():
    migration = _migration_module()
    rows = migration._validated_rows()

    assert len(rows) == EXPECTED_SAFE_COUNT
    assert len({row["tarifa_key"] for row in rows}) == EXPECTED_SAFE_COUNT
    assert EXCLUDED_CONFLICT_KEYS.isdisjoint(
        {row["tarifa_key"] for row in rows}
    )

    by_key = {row["tarifa_key"]: row for row in rows}
    assert by_key["MEMBRESIA ESPECIAL"] == {
        "tarifa_key": "MEMBRESIA ESPECIAL",
        "tarifa_raw": "MEMBRESIA ESPECIAL",
        "categoria_tarifa": "Mensualidad",
        "audience_family": "DOMICILIADO",
    }
    assert by_key["COBACH $399"]["categoria_tarifa"] == "Estudiante"
    assert by_key["COBACH $399"]["audience_family"] == "ESTUDIANTE"
    assert by_key["ANUALIDAD SEMPRA"]["audience_family"] == "SEMESTRE"


def test_upgrade_is_insert_only_idempotent_and_preserves_manual_overrides():
    migration = _migration_module()
    engine = create_engine("sqlite://")
    metadata = MetaData()
    base, overrides = _create_tables(metadata)

    try:
        with engine.begin() as connection:
            metadata.create_all(connection)

            connection.execute(
                base.insert(),
                {
                    "id": 1,
                    "tarifa_key": "MENSUALIDAD",
                    "tarifa_raw": "MENSUALIDAD",
                    "categoria_tarifa": "Mensualidad",
                    "audience_family": "DOMICILIADO",
                },
            )
            connection.execute(
                overrides.insert(),
                {
                    "tarifa_key": "PRIMER MES",
                    "tarifa_raw": "PRIMER MES",
                    "categoria_tarifa": "Estudiante",
                    "audience_family": "ESTUDIANTE",
                    "created_by_user_id": 7,
                    "updated_by_user_id": 7,
                },
            )

            context = MigrationContext.configure(connection)
            with Operations.context(context):
                migration.upgrade()
                migration.upgrade()

            assert connection.scalar(
                text(
                    "SELECT COUNT(*) "
                    "FROM marketing_campaign_v2_tariff_overrides"
                )
            ) == EXPECTED_SAFE_COUNT - 1

            manual = connection.execute(
                text(
                    "SELECT categoria_tarifa, audience_family, "
                    "created_by_user_id, updated_by_user_id "
                    "FROM marketing_campaign_v2_tariff_overrides "
                    "WHERE tarifa_key = 'PRIMER MES'"
                )
            ).one()
            assert manual == ("Estudiante", "ESTUDIANTE", 7, 7)

            seeded = connection.execute(
                text(
                    "SELECT categoria_tarifa, audience_family, "
                    "created_by_user_id, updated_by_user_id "
                    "FROM marketing_campaign_v2_tariff_overrides "
                    "WHERE tarifa_key = 'MEMBRESIA ESPECIAL'"
                )
            ).one()
            assert seeded == ("Mensualidad", "DOMICILIADO", None, None)

            base_row = connection.execute(
                text(
                    "SELECT categoria_tarifa, audience_family "
                    "FROM marketing_campaign_v2_tariffs "
                    "WHERE tarifa_key = 'MENSUALIDAD'"
                )
            ).one()
            assert base_row == ("Mensualidad", "DOMICILIADO")

            with Operations.context(context):
                migration.downgrade()

            remaining = connection.execute(
                text(
                    "SELECT tarifa_key, categoria_tarifa, audience_family, "
                    "created_by_user_id "
                    "FROM marketing_campaign_v2_tariff_overrides"
                )
            ).all()
            assert remaining == [
                ("PRIMER MES", "Estudiante", "ESTUDIANTE", 7)
            ]
    finally:
        engine.dispose()
