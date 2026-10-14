"""Dedicated real PG16 proof that late candidates coexist without altering canonical data."""
from __future__ import annotations

from datetime import date
from pathlib import Path
import importlib.util
import ast

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError

from app.models.google_ads_m6_correction import (
    GoogleAdsM6CorrectionCaseORM,
    GoogleAdsM6CorrectionCampaignORM,
    GoogleAdsM6CorrectionGroupORM,
)
from test_google_ads_m6_continuity_postgres import _test_engine

REVISION = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/e8b2c41d7a60_google_ads_m6_correction_candidates.py"
)
DAY = date(2026, 10, 13)
CUST = "2739125201"
CKEY = "name:" + "a" * 64
GKEY = "name:" + "b" * 64


def _revision():
    spec = importlib.util.spec_from_file_location("m6_corr_pg16", REVISION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _reject(conn, stmt, args):
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            conn.execute(stmt, args)


def test_schema_only_orm_and_migration_are_independent_of_existing_facts():
    migration = _revision()
    assert migration.down_revision == "c9e1a4d6b720"
    assert {migration.CASE, migration.CAMPAIGN, migration.GROUP} == {
        GoogleAdsM6CorrectionCaseORM.__tablename__,
        GoogleAdsM6CorrectionCampaignORM.__tablename__,
        GoogleAdsM6CorrectionGroupORM.__tablename__,
    }
    tree = ast.parse(REVISION.read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in ("publish", "replace", "supersede")
        for node in tree.body
    )
    code = REVISION.read_text(encoding="utf-8")
    for forbidden in ("op.alter_column(", "op.execute(", "INSERT INTO", "UPDATE ", "DELETE FROM"):
        assert forbidden not in code


def test_pg16_two_candidate_revisions_preserve_canonical_and_m5():
    engine = _test_engine()
    migration = _revision()
    with engine.connect() as conn:
        tx = conn.begin()
        try:
            assert conn.execute(sa.text("SHOW server_version")).scalar_one().startswith("16.")
            meta = sa.MetaData()
            users = sa.Table("users", meta, sa.Column("id", sa.Integer, primary_key=True))
            uploads = sa.Table("warehouse_uploads", meta, sa.Column("id", sa.Integer, primary_key=True))
            approval = sa.Table("google_ads_branch_approval_versions", meta,
                                sa.Column("id", sa.BigInteger, primary_key=True))
            publication = sa.Table("google_ads_m6_daily_publications", meta,
                                   sa.Column("id", sa.BigInteger, primary_key=True),
                                   sa.Column("is_canonical", sa.Boolean, nullable=False))
            old_c = sa.Table("google_ads_daily_metrics", meta,
                             sa.Column("id", sa.Integer, primary_key=True),
                             sa.Column("cost", sa.Numeric(18, 2), nullable=False))
            old_g = sa.Table("google_ads_ad_group_daily_metrics", meta,
                             sa.Column("id", sa.Integer, primary_key=True),
                             sa.Column("cost", sa.Numeric(18, 2), nullable=False))
            meta.create_all(conn)
            conn.execute(users.insert(), {"id": 47})
            conn.execute(uploads.insert(), [{"id": i} for i in range(22001, 22007)])
            conn.execute(approval.insert(), {"id": 900})
            conn.execute(publication.insert(), {"id": 901, "is_canonical": True})
            conn.execute(old_c.insert(), {"id": 11, "cost": 123})
            conn.execute(old_g.insert(), {"id": 12, "cost": 123})

            migration.op = Operations(MigrationContext.configure(conn))
            migration.upgrade()
            insp = sa.inspect(conn)
            for table in (migration.CASE, migration.CAMPAIGN, migration.GROUP):
                assert insp.has_table(table)
                assert conn.execute(sa.text("SELECT COUNT(*) FROM " + table)).scalar_one() == 0

            cases = sa.Table(migration.CASE, sa.MetaData(), autoload_with=conn)
            campaigns = sa.Table(migration.CAMPAIGN, sa.MetaData(), autoload_with=conn)
            groups = sa.Table(migration.GROUP, sa.MetaData(), autoload_with=conn)
            args = {
                "customer_id": CUST, "business_date": DAY, "revision": 1,
                "expected_publication_id": None, "campaign_upload_id": 22001,
                "ad_group_upload_id": 22002, "approval_version_id": 900,
                "campaign_sha256": "a" * 64, "ad_group_sha256": "b" * 64,
                "requested_by_user_id": 47, "reason": "RAW-only historical correction",
            }
            first = conn.execute(cases.insert().returning(cases.c.id), args).scalar_one()
            second_args = {
                **args, "revision": 2, "expected_publication_id": 901,
                "campaign_upload_id": 22003, "ad_group_upload_id": 22004,
            }
            second = conn.execute(cases.insert().returning(cases.c.id),
                                  second_args).scalar_one()
            _reject(conn, cases.insert(), second_args)
            _reject(conn, cases.insert(), {**args, "revision": 3})
            _reject(conn, cases.insert(), {**args, "revision": 1,
                                           "business_date": date(2026, 10, 12)})
            _reject(conn, cases.insert(), {**args, "revision": 3,
                                           "expected_publication_id": 901,
                                           "campaign_upload_id": 22002,
                                           "ad_group_upload_id": 22002})
            _reject(conn, cases.insert(), {**args, "revision": 3,
                                           "expected_publication_id": 901,
                                           "campaign_upload_id": 99999})

            metrics = {
                "currency_code": "MXN", "cost": 123, "impressions": 20,
                "clicks": 4, "conversions": 1, "conversion_value": 22,
            }
            row = {"case_id": first, "campaign_key": CKEY,
                   "campaign_name": "Same campaign", **metrics}
            other = {**row, "case_id": second, "cost": 125}
            conn.execute(campaigns.insert(), [row, other])
            _reject(conn, campaigns.insert(), row)
            _reject(conn, campaigns.insert(), {**row, "campaign_key": "bad"})
            _reject(conn, campaigns.insert(), {**other, "cost": -1})
            grow = {**row, "ad_group_key": GKEY, "ad_group_name": "Same group",
                    "free_pass_conversions": 1, "web_purchase_conversions": 0}
            conn.execute(groups.insert(), [grow, {**grow, "case_id": second}])
            _reject(conn, groups.insert(), grow)
            _reject(conn, groups.insert(), {**grow, "ad_group_key": "bad"})
            _reject(conn, groups.insert(), {**grow, "currency_code": "USD"})

            assert conn.execute(sa.select(sa.func.count()).select_from(cases)).scalar_one() == 2
            assert conn.execute(sa.select(sa.func.count()).select_from(campaigns)).scalar_one() == 2
            assert conn.execute(sa.select(sa.func.count()).select_from(groups)).scalar_one() == 2
            assert conn.execute(sa.select(publication.c.is_canonical)).scalar_one() is True
            assert conn.execute(sa.select(old_c.c.cost)).scalar_one() == 123
            assert conn.execute(sa.select(old_g.c.cost)).scalar_one() == 123
            with pytest.raises(RuntimeError, match="rollback blocked"):
                migration.downgrade()
            conn.execute(groups.delete())
            conn.execute(campaigns.delete())
            conn.execute(cases.delete())
            migration.downgrade()
            assert not sa.inspect(conn).has_table(migration.CASE)
        finally:
            tx.rollback()
    engine.dispose()
