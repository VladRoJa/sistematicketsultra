"""M5 identity-schema regressions; PG tests require isolated postgres."""
from __future__ import annotations

from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
import json
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.models.google_ads_branch_identity_mapping import GoogleAdsBranchIdentityMappingORM

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "docs/contratos/google_ads/GOOGLE_ADS_M5_IDENTITY_APPROVED_20261012.json"
MIGRATION = ROOT / "backend/migrations/versions/c7e4a9b2d601_google_ads_m5_branch_identity_schema.py"
spec = spec_from_file_location("m5_schema", MIGRATION)
migration = module_from_spec(spec)
spec.loader.exec_module(migration)


def sample():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    identity = manifest["mappings"][0]
    return {
        "customer_id": identity["customer_id"],
        "campaign_key": identity["campaign_key"],
        "ad_group_key": identity["ad_group_key"],
        "sucursal_canon": identity["sucursal_canon"],
        "source_upload_id": 21499,
        "valid_from": date(2026, 9, 24),
        "valid_to": date(2026, 10, 8),
        "approval_status": "APPROVED_PROVISIONAL_XLSX",
        "approval_reference": manifest["manifest_id"],
        "approved_on": date(2026, 10, 12),
    }


def test_static_manifest_and_model():
    doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = doc["mappings"]
    assert len(rows) == 26
    assert len({(x["customer_id"], x["campaign_key"], x["ad_group_key"]) for x in rows}) == 26
    assert {x["sucursal_id"] for x in rows} == set(range(1, 27))
    assert sum(int(x["historical_cost_mxn"].replace(".", "")) for x in rows) == 1762473
    assert doc["status"] == "APPROVED_PROVISIONAL_XLSX"
    assert doc["scope"] == "HISTORICAL_XLSX_ONLY"
    assert migration.down_revision == "b14d9e2c6f80"
    assert GoogleAdsBranchIdentityMappingORM.__tablename__ == migration.TABLE


@pytest.fixture()
def schema(monkeypatch):
    uri = os.environ.get("GOOGLE_ADS_M5_TEST_POSTGRES_URL")
    if not uri:
        pytest.skip("PostgreSQL 16 aislado requerido")
    url = sa.engine.make_url(uri)
    if (url.get_backend_name(), url.host, url.database, url.username) not in (
        ("postgresql", "127.0.0.1", "google_ads_m5_test", "google_ads_m5_ci"),
        ("postgresql", "localhost", "google_ads_m5_test", "google_ads_m5_ci"),
    ):
        pytest.fail("Se rechaza una base no aislada.")
    engine = sa.create_engine(url, future=True)
    metadata = sa.MetaData()
    branch = sa.Table("track_branch_catalog", metadata,
        sa.Column("sucursal_canon", sa.Text, primary_key=True))
    upload = sa.Table("warehouse_uploads", metadata,
        sa.Column("id", sa.Integer, primary_key=True))
    try:
        with engine.begin() as conn:
            metadata.create_all(conn)
            conn.execute(branch.insert(), [
                {"sucursal_canon": "VILLAS_DEL_REY"},
                {"sucursal_canon": "VILLA_VERDE"},
            ])
            conn.execute(upload.insert(), [{"id": 21499}])
            monkeypatch.setattr(
                migration, "op", Operations(MigrationContext.configure(conn)))
            migration.upgrade()
            table = sa.Table(migration.TABLE, sa.MetaData(), autoload_with=conn)
            assert set(table.columns.keys()) == set(
                GoogleAdsBranchIdentityMappingORM.__table__.columns.keys())
            assert conn.execute(sa.select(sa.func.count()).select_from(table)).scalar_one() == 0
            yield conn, table
            conn.execute(sa.delete(table))
            migration.downgrade()
            metadata.drop_all(conn)
    finally:
        engine.dispose()


def test_postgres_valid_insert_and_rollback_guard(schema):
    conn, table = schema
    conn.execute(sa.insert(table).values(**sample()))
    with pytest.raises(RuntimeError, match="rollback bloqueado"):
        migration.downgrade()
    assert conn.execute(sa.select(sa.func.count()).select_from(table)).scalar_one() == 1


@pytest.mark.parametrize("changes", [
    {"sucursal_canon": "UNKNOWN"},
    {"source_upload_id": 999},
    {"customer_id": "invalid"},
    {"campaign_key": "name:invalid"},
    {"ad_group_key": "name:invalid"},
    {"valid_from": date(2026, 10, 9)},
    {"approval_status": "VERIFIED_OFFICIAL_IDS"},
    {"approval_reference": " "},
])
def test_postgres_rejects_invalid_identity(schema, changes):
    conn, table = schema
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            conn.execute(sa.insert(table).values(**dict(sample(), **changes)))
    assert conn.execute(sa.select(sa.func.count()).select_from(table)).scalar_one() == 0


def test_postgres_rejects_duplicate_triple(schema):
    conn, table = schema
    data = sample()
    conn.execute(sa.insert(table).values(**data))
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            conn.execute(sa.insert(table).values(
                **dict(data, sucursal_canon="VILLA_VERDE")))
    assert conn.execute(sa.select(sa.func.count()).select_from(table)).scalar_one() == 1


def test_postgres_restricts_source_deletion(schema):
    conn, table = schema
    conn.execute(sa.insert(table).values(**sample()))
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            conn.execute(sa.text("DELETE FROM warehouse_uploads WHERE id=21499"))
