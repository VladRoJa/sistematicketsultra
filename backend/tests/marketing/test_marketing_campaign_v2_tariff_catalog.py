from __future__ import annotations

from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    inspect as sa_inspect,
    text,
)
from sqlalchemy.exc import IntegrityError

from app.models.marketing import (
    MarketingCampaignV2TariffORM,
    MarketingReactivationTariffORM,
)
from app.services.marketing_reactivation_service import (
    normalize_reactivation_tariff_key,
)


EXPECTED_SNAPSHOT_SHA256 = "00b9475ea8bdfbaf3c9d1d3571d630035ff315ab8cd374fb0339e18589162bae"
EXPECTED_FAMILY_COUNTS = {
    "DOMICILIADO": 102,
    "TRIMESTRAL": 21,
    "CONVENIO": 12,
    "SEMESTRE": 10,
    "OUT_OF_SEGMENT": 10,
    "ESTUDIANTE": 6,
    "MES": 5,
}
V2_ONLY_KEYS = {
    "$349 ATLETA CAR/COBACH ROSARITO",
    "3 MESES PROPORCIONAL",
    "50% 1ER MES 60+ 12 MESES",
    "ANUALIDAD EN LINEA",
    "MISION ZOE ENS",
    "PAGO EN LÍNEA ANUALIDAD X 4999",
    "PAGO EN LINEA CIERRE ABRIL",
    "PROMO 14 FEB",
    "PROMO DIA DE LA MUJER",
    "SEMANA INSTRUCTOR PERSONALIZADO EXTERNO $900",
    "SEMESTRAL $2,999 + 1 MES GRATIS",
    "TRES MESES POR 1,490",
    "ULTRA FIT KIDS SIN PLAZO $399",
}
CONFLICTING_CATEGORIES = {
    "CONVENIO DOMICILIADO $549": {
        "legacy": "Domiciliado",
        "v2": "Convenio",
    },
    "MEMBRESIA LM": {
        "legacy": "Membresía",
        "v2": "Convenio",
    },
}


def _migration_module():
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "c3a7e1f5b9d2_add_marketing_campaign_v2_tariff_catalog.py"
    )
    spec = importlib.util.spec_from_file_location(
        "marketing_campaign_v2_tariff_catalog_migration",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _snapshot_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "data"
        / "reference"
        / "marketing_campaign_v2_tariffs_2026-09-30.json"
    )


def _create_legacy_table(metadata: MetaData) -> Table:
    return Table(
        "marketing_reactivation_tariffs",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("tarifa_key", String(255), nullable=False, unique=True),
        Column("tarifa_raw", String(255), nullable=False),
        Column("categoria_tarifa", String(100), nullable=False),
        Column("reactivation_group", String(30), nullable=False),
    )


def _legacy_rows() -> list[dict[str, object]]:
    return [
        {
            "id": index,
            "tarifa_key": tarifa_key,
            "tarifa_raw": tarifa_key,
            "categoria_tarifa": categories["legacy"],
            "reactivation_group": (
                "DOMICILIATED_FLOW"
                if tarifa_key == "CONVENIO DOMICILIADO $549"
                else "REACTIVATE"
            ),
        }
        for index, (tarifa_key, categories) in enumerate(
            CONFLICTING_CATEGORIES.items(),
            start=1,
        )
    ]


def test_model_is_independent_from_legacy_reactivation_group():
    columns = MarketingCampaignV2TariffORM.__table__.c
    assert set(columns.keys()) == {
        "id",
        "tarifa_key",
        "tarifa_raw",
        "categoria_tarifa",
        "audience_family",
    }
    assert "reactivation_group" not in columns
    assert MarketingReactivationTariffORM.__table__.c.reactivation_group.nullable is False

    constraint_names = {
        constraint.name
        for constraint in MarketingCampaignV2TariffORM.__table__.constraints
    }
    assert "uq_marketing_campaign_v2_tariffs_tarifa_key" in constraint_names
    assert "ck_marketing_campaign_v2_tariffs_audience_family" in constraint_names

    assert {
        index.name
        for index in MarketingCampaignV2TariffORM.__table__.indexes
    } == {"ix_marketing_campaign_v2_tariffs_audience_family"}


def test_snapshot_checksum_normalization_uniqueness_and_distribution():
    migration = _migration_module()
    snapshot_path = _snapshot_path()
    payload = snapshot_path.read_bytes()

    assert hashlib.sha256(payload).hexdigest() == EXPECTED_SNAPSHOT_SHA256
    assert migration._EXPECTED_SNAPSHOT_SHA256 == EXPECTED_SNAPSHOT_SHA256

    document = json.loads(payload.decode("utf-8"))
    assert document["artifact_policy"] == "immutable"
    assert document["row_count"] == 166
    assert len(document["tariffs"]) == 166

    production_keys = [
        normalize_reactivation_tariff_key(row["tarifa_raw"])
        for row in document["tariffs"]
    ]
    migration_keys = [
        migration._normalize_tariff_key(row["tarifa_raw"])
        for row in document["tariffs"]
    ]
    assert production_keys == migration_keys
    assert None not in production_keys
    assert len(production_keys) == 166
    assert len(set(production_keys)) == 166
    assert [
        key
        for key, count in Counter(production_keys).items()
        if count > 1
    ] == []

    assert Counter(
        row["audience_family"]
        for row in document["tariffs"]
    ) == Counter(EXPECTED_FAMILY_COUNTS)
    assert len(migration._load_snapshot_rows()) == 166


def test_snapshot_checksum_detects_any_byte_change(tmp_path, monkeypatch):
    migration = _migration_module()
    mutated = tmp_path / "mutated.json"
    payload = _snapshot_path().read_bytes()
    mutated.write_bytes(payload + b" ")

    monkeypatch.setattr(migration, "_SNAPSHOT_PATH", mutated)

    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        migration._load_snapshot_rows()


def test_upgrade_loads_exact_catalog_and_preserves_legacy_categories():
    migration = _migration_module()
    engine = create_engine("sqlite://")
    metadata = MetaData()
    legacy = _create_legacy_table(metadata)

    try:
        with engine.begin() as connection:
            metadata.create_all(connection)
            connection.execute(legacy.insert(), _legacy_rows())

            context = MigrationContext.configure(connection)
            with Operations.context(context):
                migration.upgrade()

            inspector = sa_inspect(connection)
            assert "marketing_campaign_v2_tariffs" in inspector.get_table_names()

            v2_columns = {
                column["name"]
                for column in inspector.get_columns(
                    "marketing_campaign_v2_tariffs"
                )
            }
            assert "reactivation_group" not in v2_columns

            assert connection.scalar(
                text("SELECT COUNT(*) FROM marketing_campaign_v2_tariffs")
            ) == 166
            assert connection.scalar(
                text(
                    "SELECT COUNT(DISTINCT tarifa_key) "
                    "FROM marketing_campaign_v2_tariffs"
                )
            ) == 166

            family_counts = dict(
                connection.execute(
                    text(
                        "SELECT audience_family, COUNT(*) "
                        "FROM marketing_campaign_v2_tariffs "
                        "GROUP BY audience_family"
                    )
                ).all()
            )
            assert family_counts == EXPECTED_FAMILY_COUNTS

            v2_rows = dict(
                connection.execute(
                    text(
                        "SELECT tarifa_key, categoria_tarifa "
                        "FROM marketing_campaign_v2_tariffs"
                    )
                ).all()
            )
            assert V2_ONLY_KEYS <= set(v2_rows)
            for tarifa_key, categories in CONFLICTING_CATEGORIES.items():
                assert v2_rows[tarifa_key] == categories["v2"]

            legacy_rows = dict(
                connection.execute(
                    text(
                        "SELECT tarifa_key, categoria_tarifa "
                        "FROM marketing_reactivation_tariffs"
                    )
                ).all()
            )
            for tarifa_key, categories in CONFLICTING_CATEGORIES.items():
                assert legacy_rows[tarifa_key] == categories["legacy"]
    finally:
        engine.dispose()


def test_upgrade_constraints_enforce_unique_key_and_family_domain():
    migration = _migration_module()
    engine = create_engine("sqlite://")

    try:
        with engine.begin() as connection:
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                migration.upgrade()

            duplicate = {
                "tarifa_key": "ESTUDIANTE",
                "tarifa_raw": "ESTUDIANTE",
                "categoria_tarifa": "Estudiante",
                "audience_family": "ESTUDIANTE",
            }
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        "INSERT INTO marketing_campaign_v2_tariffs "
                        "(tarifa_key, tarifa_raw, categoria_tarifa, audience_family) "
                        "VALUES "
                        "(:tarifa_key, :tarifa_raw, :categoria_tarifa, :audience_family)"
                    ),
                    duplicate,
                )

        with engine.begin() as connection:
            invalid_family = {
                "tarifa_key": "INVALID FAMILY TEST",
                "tarifa_raw": "INVALID FAMILY TEST",
                "categoria_tarifa": "Mensualidad",
                "audience_family": "INVALID",
            }
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        "INSERT INTO marketing_campaign_v2_tariffs "
                        "(tarifa_key, tarifa_raw, categoria_tarifa, audience_family) "
                        "VALUES "
                        "(:tarifa_key, :tarifa_raw, :categoria_tarifa, :audience_family)"
                    ),
                    invalid_family,
                )
    finally:
        engine.dispose()


def test_downgrade_removes_only_v2_catalog_and_preserves_legacy():
    migration = _migration_module()
    engine = create_engine("sqlite://")
    metadata = MetaData()
    legacy = _create_legacy_table(metadata)

    try:
        with engine.begin() as connection:
            metadata.create_all(connection)
            connection.execute(legacy.insert(), _legacy_rows())

            context = MigrationContext.configure(connection)
            with Operations.context(context):
                migration.upgrade()
                migration.downgrade()

            inspector = sa_inspect(connection)
            assert "marketing_campaign_v2_tariffs" not in inspector.get_table_names()
            assert "marketing_reactivation_tariffs" in inspector.get_table_names()

            legacy_rows = dict(
                connection.execute(
                    text(
                        "SELECT tarifa_key, categoria_tarifa "
                        "FROM marketing_reactivation_tariffs"
                    )
                ).all()
            )
            assert legacy_rows == {
                key: values["legacy"]
                for key, values in CONFLICTING_CATEGORIES.items()
            }
    finally:
        engine.dispose()
