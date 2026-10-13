"""M5 seed: PostgreSQL 16 isolated positive and negative migration gates."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "migrations"
SCHEMA_PATH = MIGRATIONS / "versions/c7e4a9b2d601_google_ads_m5_branch_identity_schema.py"
SEED_PATH = MIGRATIONS / "versions/a63e9f21d48b_seed_google_ads_m5_approved_identities.py"


def _module(path, name):
    spec = spec_from_file_location(name, path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


schema = _module(SCHEMA_PATH, "m5_schema_for_seed")
seed = _module(SEED_PATH, "m5_controlled_seed")
DB_URL = os.environ.get("GOOGLE_ADS_M5_SEED_TEST_POSTGRES_URL")


def test_manifest_and_single_head():
    data = seed._load()
    assert len(data["rows"]) == 26
    assert seed.revision == "a63e9f21d48b"
    assert seed.down_revision == schema.revision
    scripts = ScriptDirectory(str(MIGRATIONS))
    heads = scripts.get_heads()
    assert len(heads) == 1
    assert seed.revision in {
        x.revision for x in scripts.iterate_revisions(heads[0], "base")
    }


def _engine():
    if not DB_URL:
        pytest.skip("Requires isolated M5 seed PostgreSQL")
    url = sa.engine.make_url(DB_URL)
    if (url.get_backend_name() != "postgresql"
        or url.host not in {"127.0.0.1", "localhost"}
        or url.database != "google_ads_m5_seed_test"
        or url.username != "google_ads_m5_seed_ci"):
        pytest.fail("Nonisolated database forbidden")
    return sa.create_engine(DB_URL, future=True)


def _tables():
    m = sa.MetaData()
    rt = sa.Table("warehouse_report_types", m,
        sa.Column("id", sa.Integer, primary_key=True), sa.Column("key", sa.Text))
    upload = sa.Table("warehouse_uploads", m,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("report_type_id", sa.Integer),
        sa.Column("original_filename", sa.Text),
        sa.Column("date_from", sa.Date), sa.Column("date_to", sa.Date),
        sa.Column("status", sa.Text), sa.Column("file_hash_sha256", sa.String(64)),
        sa.Column("file_size_bytes", sa.Integer),
        sa.Column("source_file_deleted_at", sa.DateTime(timezone=True)))
    branches = sa.Table("sucursales", m,
        sa.Column("sucursal_id", sa.Integer, primary_key=True),
        sa.Column("operational_status", sa.Text))
    cat = sa.Table("track_branch_catalog", m,
        sa.Column("sucursal_canon", sa.Text, primary_key=True),
        sa.Column("sucursal_id", sa.Integer),
        sa.Column("is_track_active", sa.Boolean))
    aliases = sa.Table("track_branch_aliases", m,
        sa.Column("raw_branch_name", sa.Text),
        sa.Column("source_family", sa.Text),
        sa.Column("sucursal_canon", sa.Text),
        sa.Column("is_active", sa.Boolean))
    groups = sa.Table("google_ads_ad_group_daily_metrics", m,
        sa.Column("customer_id", sa.String(10)),
        sa.Column("campaign_key", sa.String(80)), sa.Column("ad_group_key", sa.String(80)),
        sa.Column("campaign_name", sa.Text), sa.Column("ad_group_name", sa.Text),
        sa.Column("report_date", sa.Date), sa.Column("cost", sa.Numeric(18,2)),
        sa.Column("clicks", sa.Integer), sa.Column("impressions", sa.BigInteger),
        sa.Column("free_pass_conversions", sa.Numeric(18,4)),
        sa.Column("web_purchase_conversions", sa.Numeric(18,4)),
        sa.Column("currency_code", sa.String(3)),
        sa.Column("source_kind", sa.Text), sa.Column("source_upload_id", sa.Integer),
        sa.Column("campaign_id", sa.Text), sa.Column("ad_group_id", sa.Text))
    ledger = sa.Table("google_ads_daily_metrics", m,
        sa.Column("customer_id", sa.String(10)),
        sa.Column("campaign_key", sa.String(80)), sa.Column("report_date", sa.Date),
        sa.Column("cost", sa.Numeric(18,2)), sa.Column("clicks", sa.Integer),
        sa.Column("impressions", sa.BigInteger), sa.Column("currency_code", sa.String(3)))
    return m, rt, upload, branches, cat, aliases, groups, ledger


def _fake_identities(data):
    rows = [tuple(item[:5]) + (Decimal(item[6]),) for item in data["rows"]]
    extras = [("UG | Nacional", "Marca", Decimal("1375.60")),
              ("UG | Preapertura", "EGADE", Decimal("126.04"))]
    extras += [(f"Sin actividad {i}", "Grupo de anuncios 1", Decimal("0"))
               for i in range(10)]
    extras += [("Sin actividad otros", x, Decimal("0")) for x in
               ("Branded", "Gimnasio", "Guardería", "Location", "Own Branded")]
    for campaign, group, cost in extras:
        ck = "name:" + seed.sha256(seed._norm(campaign).encode()).hexdigest()
        gk = "name:" + seed.sha256((ck + "\x1f" + seed._norm(group)).encode()).hexdigest()
        rows.append((campaign, group, ck, gk, None, cost))
    assert len(rows) == 43
    return rows


@pytest.fixture
def dataset(monkeypatch):
    engine = _engine()
    meta, rt, upload, branches, cat, aliases, groups, ledger = _tables()
    data = seed._load()
    try:
        with engine.begin() as conn:
            meta.create_all(conn)
            conn.execute(rt.insert(), {"id": 1, "key": "google_ads_ad_group_daily"})
            conn.execute(upload.insert(), dict(
                id=21499, report_type_id=1,
                original_filename="Informe de grupo de anuncios (7).xlsx",
                date_from=date(2026,9,24), date_to=date(2026,10,8),
                status="ACTIVE", file_hash_sha256=data["upload_sha256"],
                file_size_bytes=79836, source_file_deleted_at=None))
            conn.execute(branches.insert(), [
                {"sucursal_id": r[5], "operational_status": "ACTIVA"}
                for r in data["rows"]])
            conn.execute(cat.insert(), [
                {"sucursal_canon": r[4], "sucursal_id": r[5],
                 "is_track_active": True} for r in data["rows"]])
            conn.execute(aliases.insert(), [
                {"raw_branch_name": r[1], "source_family": "google_ads_family",
                 "sucursal_canon": r[4], "is_active": True} for r in data["rows"]])
            source_rows = []
            by_campaign = defaultdict(lambda: [Decimal("0"), 0, 0])
            for camp, group, ck, gk, _, cost in _fake_identities(data):
                for offset in range(15):
                    day = date(2026,9,24) + timedelta(days=offset)
                    amount = cost if offset == 0 else Decimal("0")
                    clicks = 7887 if group == "Villas del Rey" and offset == 0 else 0
                    impressions = 79198 if clicks else 0
                    source_rows.append(dict(
                        customer_id="2739125201", campaign_key=ck, ad_group_key=gk,
                        campaign_name=camp, ad_group_name=group, report_date=day,
                        cost=amount, clicks=clicks, impressions=impressions,
                        free_pass_conversions=64 if clicks else 0,
                        web_purchase_conversions=16 if clicks else 0,
                        currency_code="MXN", source_kind="WAREHOUSE_XLSX",
                        source_upload_id=21499, campaign_id=None, ad_group_id=None))
                    totals = by_campaign[(ck, day)]
                    totals[0] += amount
                    totals[1] += clicks
                    totals[2] += impressions
            assert len(source_rows) == 645
            conn.execute(groups.insert(), source_rows)
            conn.execute(ledger.insert(), [
                dict(customer_id="2739125201", campaign_key=ck, report_date=day,
                     cost=totals[0], clicks=totals[1], impressions=totals[2],
                     currency_code="MXN")
                for (ck, day), totals in by_campaign.items()
            ])
            monkeypatch.setattr(schema, "op", Operations(MigrationContext.configure(conn)))
            monkeypatch.setattr(seed, "op", Operations(MigrationContext.configure(conn)))
            schema.upgrade()
            mapped = sa.Table(schema.TABLE, sa.MetaData(), autoload_with=conn)
            yield conn, mapped, groups, ledger, aliases, upload, cat
            conn.execute(sa.delete(mapped))
            schema.downgrade()
            meta.drop_all(conn)
    finally:
        engine.dispose()


def test_pg16_seed_is_exact_and_idempotent(dataset):
    conn, mapped, *_ = dataset
    assert conn.execute(sa.select(sa.func.count()).select_from(mapped)).scalar_one() == 0
    seed.upgrade()
    seed.upgrade()
    rows = conn.execute(sa.select(mapped)).mappings().all()
    assert len(rows) == 26
    assert len({(r["customer_id"], r["campaign_key"], r["ad_group_key"]) for r in rows}) == 26
    assert all(r["source_upload_id"] == 21499 for r in rows)
    assert all(r["approval_status"] == "APPROVED_PROVISIONAL_XLSX" for r in rows)
    seed.downgrade()
    assert conn.execute(sa.select(sa.func.count()).select_from(mapped)).scalar_one() == 0


@pytest.mark.parametrize("tamper", [
    "upload_hash", "inactive_branch", "cost_drift", "ledger_drift",
    "unknown_clicks", "official_ids", "source_changed",
])
def test_pg16_seed_refuses_tampered_source_with_zero_writes(dataset, tamper):
    conn, mapped, groups, ledger, aliases, upload, cat = dataset
    if tamper == "upload_hash":
        conn.execute(sa.update(upload).values(file_hash_sha256="0"*64))
    elif tamper == "inactive_branch":
        conn.execute(sa.update(cat).where(cat.c.sucursal_id == 1).values(is_track_active=False))
    elif tamper == "cost_drift":
        conn.execute(sa.update(groups).where(groups.c.ad_group_name == "Villas del Rey")
                     .where(groups.c.report_date == date(2026,9,24)).values(cost=999))
    elif tamper == "ledger_drift":
        conn.execute(sa.update(ledger).where(ledger.c.report_date == date(2026,9,24)).values(cost=999))
    elif tamper == "unknown_clicks":
        conn.execute(sa.update(groups).where(groups.c.ad_group_name == "Branded").values(clicks=1))
    elif tamper == "official_ids":
        conn.execute(sa.update(groups).where(groups.c.ad_group_name == "Villas del Rey")
                     .values(ad_group_id="123"))
    else:
        conn.execute(sa.update(groups).where(groups.c.ad_group_name == "Villas del Rey")
                     .values(source_upload_id=999))
    with pytest.raises(RuntimeError, match="M5 seed rechazado"):
        seed.upgrade()
    assert conn.execute(sa.select(sa.func.count()).select_from(mapped)).scalar_one() == 0


def test_pg16_downgrade_rejects_modified_mapping(dataset):
    conn, mapped, *_ = dataset
    seed.upgrade()
    conn.execute(sa.update(mapped).values(approval_reference="MANUAL_OVERRIDE"))
    with pytest.raises(RuntimeError, match="downgrade"):
        seed.downgrade()
    assert conn.execute(sa.select(sa.func.count()).select_from(mapped)).scalar_one() == 26
