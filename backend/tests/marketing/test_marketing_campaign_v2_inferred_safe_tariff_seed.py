from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, text


REVISION = "b5d9e2a7c1f4"
EXPECTED_SAFE_COUNT = 113
REVIEW_ONLY_KEYS = {'PROMO MARZO ANTICIPADO $649', 'TARIFA PRUEBA REC', 'CONVENIO LABORATORIOS DELIA BARRAZA RECURRENTE $499', '14 MESES POR $7,139', 'TARJETA DE REGALO', 'ANUALIDAD CONVENIO $3999', 'CONVENIO CCP RECURRENTE $499', 'CONVENIO CARLS JR RECURRENTE $499', 'SAN VALENTÍN PRIMER MES $299.50', 'PENALIZACIÓN', 'CORTESIA CLASES', '3 X 2 MESES POR $998', 'ATLETA 12 MESES', '6 MESES', '3 X 2 MESES POR $1,198 METEPEC', 'ATLETA 6 MESES', 'MES DE REGALO X ANUALIDAD', 'SEMANA SLRC $199', 'MES REACTIVACION IXTAPALUCA', 'PROMO MEXICALI BSB', 'CONVENIO YOGUFRUT RECURRENTE $499', 'CONVENIO MOBI MUEBLES RECURRENTE $499', 'CONVENIO DK FOOD RECURRENTE $499'}


def _migration_module():
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / f"{REVISION}_seed_campaign_v2_inferred_safe_tariff_overrides.py"
    )
    spec = importlib.util.spec_from_file_location(
        "campaign_v2_inferred_safe_tariff_seed_migration",
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


def test_inferred_safe_seed_is_unique_and_keeps_review_only_keys_out():
    migration = _migration_module()
    rows = migration._validated_rows()
    by_key = {row["tarifa_key"]: row for row in rows}

    assert len(rows) == EXPECTED_SAFE_COUNT
    assert len(by_key) == EXPECTED_SAFE_COUNT
    assert REVIEW_ONLY_KEYS.isdisjoint(by_key)

    assert by_key["MEMBRESIA CULIACAN"]["categoria_tarifa"] == "Mensualidad"
    assert by_key["MEMBRESIA CULIACAN"]["audience_family"] == "DOMICILIADO"
    assert by_key["TRIMESTRE ESTUDIANTE $1,499"]["audience_family"] == "TRIMESTRAL"
    assert by_key["DOMICILIADO SIN PLAZO $699 HE"]["categoria_tarifa"] == "Recurrente"
    assert by_key["ANUALIDAD $2,999"]["audience_family"] == "SEMESTRE"


def test_inferred_upgrade_is_insert_only_idempotent_and_downgrade_is_selective():
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
                    "tarifa_key": "ANUALIDAD $2,999",
                    "tarifa_raw": "ANUALIDAD $2,999",
                    "categoria_tarifa": "Anualidad",
                    "audience_family": "SEMESTRE",
                },
            )
            connection.execute(
                overrides.insert(),
                {
                    "tarifa_key": "MENSUALIDAD CULIACAN",
                    "tarifa_raw": "MENSUALIDAD CULIACAN",
                    "categoria_tarifa": "Convenio",
                    "audience_family": "CONVENIO",
                    "created_by_user_id": 9,
                    "updated_by_user_id": 9,
                },
            )

            context = MigrationContext.configure(connection)
            with Operations.context(context):
                migration.upgrade()
                migration.upgrade()

            assert connection.scalar(
                text("SELECT COUNT(*) FROM marketing_campaign_v2_tariff_overrides")
            ) == EXPECTED_SAFE_COUNT - 1

            manual = connection.execute(
                text(
                    "SELECT categoria_tarifa, audience_family, created_by_user_id "
                    "FROM marketing_campaign_v2_tariff_overrides "
                    "WHERE tarifa_key = 'MENSUALIDAD CULIACAN'"
                )
            ).one()
            assert manual == ("Convenio", "CONVENIO", 9)

            seeded = connection.execute(
                text(
                    "SELECT categoria_tarifa, audience_family, created_by_user_id "
                    "FROM marketing_campaign_v2_tariff_overrides "
                    "WHERE tarifa_key = 'MEMBRESIA CULIACAN'"
                )
            ).one()
            assert seeded == ("Mensualidad", "DOMICILIADO", None)

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
                ("MENSUALIDAD CULIACAN", "Convenio", "CONVENIO", 9)
            ]
    finally:
        engine.dispose()
