"""Google Ads M4: approved branch aliases (no attribution or spend writes)."""
from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path

import pytest
import sqlalchemy as sa


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "migrations" / "versions"
    / "b14d9e2c6f80_seed_google_ads_family_aliases.py"
)
spec = spec_from_file_location("google_ads_family_m4_test", MIGRATION_PATH)
migration = module_from_spec(spec)
spec.loader.exec_module(migration)

DB_URL = os.getenv("GOOGLE_ADS_M4_TEST_POSTGRES_URL")


def test_manifest_covers_only_26_operational_branches():
    migration._validate_manifest()
    aliases = migration.APPROVED_ALIASES
    assert len(aliases) == 26
    assert {id_ for _, _, id_ in aliases} == set(range(1, 27))
    assert len({canon for _, canon, _ in aliases}) == 26
    assert ("Paseo Villalta", "SALTILLO_VILLALTA", 24) in aliases
    assert ("Sendero Sur Saltillo", "SEND_SALTILLO", 18) in aliases
    assert ("Insurgentes Sur", "INSURGENTES", 22) in aliases
    assert ("Serranía", "SERRANIA", 26) in aliases
    disallowed = {"Marca", "EGADE", "Grupo de anuncios 1"}
    assert not ({raw for raw, _, _ in aliases} & disallowed)
    assert migration.FAMILY == "google_ads_family"


def _isolated_engine():
    uri = sa.engine.make_url(DB_URL)
    if (
        uri.get_backend_name() != "postgresql"
        or uri.host not in ("127.0.0.1", "localhost")
        or uri.database != "google_ads_m4_test"
        or uri.username != "google_ads_m4_ci"
    ):
        pytest.fail("Se rechaza cualquier BD no aislada para la prueba M4.")
    return sa.create_engine(DB_URL, future=True, pool_pre_ping=True)


def _schema():
    metadata = sa.MetaData()
    branches = sa.Table(
        "sucursales", metadata,
        sa.Column("sucursal_id", sa.Integer, primary_key=True),
        sa.Column("operational_status", sa.String(32), nullable=False),
    )
    catalog = sa.Table(
        "track_branch_catalog", metadata,
        sa.Column("sucursal_canon", sa.Text, primary_key=True),
        sa.Column("sucursal_id", sa.Integer, sa.ForeignKey("sucursales.sucursal_id")),
        sa.Column("is_track_active", sa.Boolean, nullable=False),
    )
    alias = sa.Table(
        "track_branch_aliases", metadata,
        sa.Column("source_family", sa.Text, primary_key=True),
        sa.Column("raw_branch_name", sa.Text, primary_key=True),
        sa.Column("sucursal_canon", sa.Text, sa.ForeignKey(
            "track_branch_catalog.sucursal_canon"
        ), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False),
        sa.Column("notes", sa.Text),
    )
    return metadata, branches, catalog, alias


@pytest.mark.skipif(not DB_URL, reason="Requiere PostgreSQL aislado M4.")
def test_postgres_seed_is_idempotent_and_rollback_preserves_other_families(
    monkeypatch,
):
    engine = _isolated_engine()
    metadata, branches, catalog, alias = _schema()
    try:
        with engine.begin() as connection:
            metadata.create_all(connection)
            connection.execute(
                branches.insert(),
                [
                    {"sucursal_id": id_, "operational_status": "ACTIVA"}
                    for _, _, id_ in migration.APPROVED_ALIASES
                ],
            )
            connection.execute(
                catalog.insert(),
                [
                    {
                        "sucursal_canon": canon,
                        "sucursal_id": id_,
                        "is_track_active": True,
                    }
                    for _, canon, id_ in migration.APPROVED_ALIASES
                ],
            )
            connection.execute(
                alias.insert(),
                [
                    {
                        "source_family": "gasca_family",
                        "raw_branch_name": "SERRANIA",
                        "sucursal_canon": "SERRANIA",
                        "is_active": True,
                    },
                ],
            )
            monkeypatch.setattr(
                migration.op, "get_bind", lambda: connection,
            )
            migration.upgrade()
            migration.upgrade()  # same mapping must not create extra rows
            rows = connection.execute(
                sa.select(alias).where(
                    alias.c.source_family == "google_ads_family"
                )
            ).mappings().all()
            assert len(rows) == 26
            assert all(row["is_active"] for row in rows)
            assert {
                row["raw_branch_name"]: row["sucursal_canon"] for row in rows
            } == {
                raw: canon for raw, canon, _ in migration.APPROVED_ALIASES
            }

            migration.downgrade()
            assert connection.execute(
                sa.select(sa.func.count()).select_from(alias).where(
                    alias.c.source_family == "google_ads_family"
                )
            ).scalar_one() == 0
            assert connection.execute(
                sa.select(sa.func.count()).select_from(alias).where(
                    alias.c.source_family == "gasca_family"
                )
            ).scalar_one() == 1
            metadata.drop_all(connection)
    finally:
        engine.dispose()


@pytest.mark.skipif(not DB_URL, reason="Requiere PostgreSQL aislado M4.")
def test_postgres_rejects_inactive_branch_before_writes(monkeypatch):
    engine = _isolated_engine()
    metadata, branches, catalog, alias = _schema()
    try:
        with engine.begin() as connection:
            metadata.create_all(connection)
            connection.execute(
                branches.insert(),
                [
                    {
                        "sucursal_id": id_,
                        "operational_status": (
                            "PAUSADA" if id_ == 24 else "ACTIVA"
                        ),
                    }
                    for _, _, id_ in migration.APPROVED_ALIASES
                ],
            )
            connection.execute(
                catalog.insert(),
                [
                    {
                        "sucursal_canon": canon,
                        "sucursal_id": id_,
                        "is_track_active": True,
                    }
                    for _, canon, id_ in migration.APPROVED_ALIASES
                ],
            )
            monkeypatch.setattr(
                migration.op, "get_bind", lambda: connection,
            )
            with pytest.raises(RuntimeError, match="no elegible"):
                migration.upgrade()
            assert connection.execute(
                sa.select(sa.func.count()).select_from(alias)
            ).scalar_one() == 0
            metadata.drop_all(connection)
    finally:
        engine.dispose()
