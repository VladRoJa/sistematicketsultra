"""PostgreSQL 16 isolated integration test of the M6 Alembic migration.

Never connect to production. Uses a dedicated ephemeral GitHub Actions DB,
synthetic identities and a transaction rolled back at test completion.
"""
from __future__ import annotations

from datetime import date
import importlib.util
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError

from app.models.google_ads_branch_identity_mapping import GoogleAdsBranchIdentityMappingORM

TEST_URL = os.environ.get("GOOGLE_ADS_M6_TEST_POSTGRES_URL")


def _revision():
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/b3e7c2d9a104_google_ads_m6_branch_continuity.py"
    )
    spec = importlib.util.spec_from_file_location("m6_pg16_revision", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _test_engine():
    if not TEST_URL:
        pytest.skip("Only enabled with dedicated PostgreSQL 16 test URL")
    url = sa.engine.make_url(TEST_URL)
    if (
        url.get_backend_name() != "postgresql"
        or url.host not in ("localhost", "127.0.0.1")
        or url.database != "google_ads_m6_ci"
        or url.username != "google_ads_m6_ci"
    ):
        pytest.fail("M6 PostgreSQL test must not access non-isolated databases")
    return sa.create_engine(TEST_URL, future=True)


def _reject(conn, sql, values):
    with pytest.raises(IntegrityError):
        # SAVEPOINT keeps the outer transaction usable after PG constraint errors.
        with conn.begin_nested():
            conn.execute(sa.text(sql), values)


def test_real_m6_migration_constraints_and_m5_immutability():
    engine = _test_engine()
    rev = _revision()
    assert rev.down_revision == "f62a1b9d4c07"

    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            server = conn.execute(sa.text("SHOW server_version")).scalar_one()
            assert server.startswith("16."), server

            metadata = sa.MetaData()
            sa.Table("users", metadata, sa.Column("id", sa.Integer, primary_key=True))
            sa.Table("warehouse_uploads", metadata, sa.Column("id", sa.Integer, primary_key=True))
            sa.Table(
                "track_branch_catalog", metadata,
                sa.Column("sucursal_canon", sa.Text, primary_key=True),
            )
            m5 = GoogleAdsBranchIdentityMappingORM.__table__.to_metadata(metadata)
            metadata.create_all(conn)
            conn.execute(sa.text("INSERT INTO users(id) VALUES (47)"))
            conn.execute(sa.text(
                "INSERT INTO warehouse_uploads(id) VALUES (21499), (21604), (21605)"
            ))
            conn.execute(sa.text(
                "INSERT INTO track_branch_catalog(sucursal_canon) VALUES ('VILLAS_DEL_REY')"
            ))
            key_a, key_b = "name:" + "a" * 64, "name:" + "b" * 64
            m5_original = {
                "customer_id": "2739125201", "campaign_key": key_a,
                "ad_group_key": key_b, "sucursal_canon": "VILLAS_DEL_REY",
                "source_upload_id": 21499, "valid_from": date(2026, 9, 24),
                "valid_to": date(2026, 10, 8),
                "approval_status": "APPROVED_PROVISIONAL_XLSX",
                "approval_reference": "GOOGLE_ADS_M5_IDENTITY_20261012_V1",
                "approved_on": date(2026, 10, 12),
            }
            conn.execute(m5.insert(), m5_original)
            baseline = conn.execute(
                sa.text("SELECT * FROM google_ads_branch_identity_mappings")
            ).mappings().one()

            rev.op = Operations(MigrationContext.configure(conn))
            rev.upgrade()
            assert sa.inspect(conn).has_table(rev.VERSIONS)
            assert sa.inspect(conn).has_table(rev.IDENTITIES)

            approval = """
                INSERT INTO google_ads_branch_approval_versions
                  (customer_id, approval_reference, source_approval_reference,
                   valid_from, source_campaign_upload_id, source_ad_group_upload_id,
                   approved_by_user_id, approved_on)
                VALUES
                  (:customer_id, :reference, :parent, :valid_from,
                   :campaign_upload, :group_upload, :actor_id, :approved_on)
                RETURNING id
            """
            args = {
                "customer_id": "2739125201",
                "reference": "M6_SYNTHETIC_APPROVAL",
                "parent": "GOOGLE_ADS_M5_IDENTITY_20261012_V1",
                "valid_from": date(2026, 10, 9),
                "campaign_upload": 21604, "group_upload": 21605,
                "actor_id": 47, "approved_on": date(2026, 10, 13),
            }
            version_id = conn.execute(sa.text(approval), args).scalar_one()
            assert version_id is not None
            _reject(conn, approval, args)  # no duplicate approval/start
            _reject(conn, approval, {
                **args, "reference": "M6_OTHER", "valid_from": date(2026, 10, 10),
                "group_upload": 21604,
            })
            _reject(conn, approval, {
                **args, "reference": "M6_OTHER", "valid_from": date(2026, 10, 10),
                "actor_id": 99999,
            })
            _reject(conn, approval, {
                **args, "reference": "M6_OTHER", "valid_from": date(2026, 10, 10),
                "campaign_upload": 99999,
            })
            ident = """
                INSERT INTO google_ads_branch_approved_identities
                  (approval_version_id, campaign_key, ad_group_key, sucursal_canon)
                VALUES (:version_id, :campaign_key, :ad_group_key, :branch)
            """
            ident_args = {
                "version_id": version_id, "campaign_key": key_a,
                "ad_group_key": key_b, "branch": "VILLAS_DEL_REY",
            }
            conn.execute(sa.text(ident), ident_args)
            _reject(conn, ident, ident_args)  # unique identity per approval
            _reject(conn, ident, {**ident_args, "campaign_key": "invalid"})
            _reject(conn, ident, {**ident_args, "branch": "UNKNOWN_BRANCH"})

            after_m5 = conn.execute(
                sa.text("SELECT * FROM google_ads_branch_identity_mappings")
            ).mappings().one()
            assert dict(after_m5) == dict(baseline)
            with pytest.raises(RuntimeError, match="rollback blocked"):
                rev.downgrade()
            assert sa.inspect(conn).has_table(rev.VERSIONS)
            assert sa.inspect(conn).has_table(rev.IDENTITIES)

            conn.execute(sa.text("DELETE FROM google_ads_branch_approved_identities"))
            conn.execute(sa.text("DELETE FROM google_ads_branch_approval_versions"))
            rev.downgrade()
            assert not sa.inspect(conn).has_table(rev.VERSIONS)
            assert not sa.inspect(conn).has_table(rev.IDENTITIES)
            assert dict(conn.execute(sa.text(
                "SELECT * FROM google_ads_branch_identity_mappings"
            )).mappings().one()) == dict(baseline)
        finally:
            transaction.rollback()
    engine.dispose()
