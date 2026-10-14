"""Fail-closed global Funnel account spend post-12-Oct using real PG16 joins."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.google_ads_daily import GoogleAdsDailyMetricORM
from app.models.google_ads_m6_daily_publication import GoogleAdsM6DailyPublicationORM
from app.models.google_ads_m6_continuity import GoogleAdsBranchApprovalVersionORM
from app.models.warehouse import WarehouseUploadORM
from app.services import marketing_google_ads_funnel_service as service
from test_google_ads_m6_continuity_postgres import _test_engine

CUST = "2739125201"


@pytest.fixture()
def campaign_gate_pg(monkeypatch):
    engine = _test_engine()
    metadata = sa.MetaData()
    sa.Table("users", metadata, sa.Column("id", sa.Integer, primary_key=True))
    uploads = WarehouseUploadORM.__table__.to_metadata(metadata)
    # The complete WarehouseUploadORM has catalog FKs; isolate the fields used
    # by the daily canonical source gate without inventing production sources.
    metadata.remove(uploads)
    uploads = sa.Table(
        "warehouse_uploads", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("source_file_deleted_at", sa.DateTime(timezone=True)),
        sa.Column("file_hash_sha256", sa.Text, nullable=False),
        sa.Column("date_from", sa.Date),
        sa.Column("date_to", sa.Date),
    )
    version = GoogleAdsBranchApprovalVersionORM.__table__.to_metadata(metadata)
    fact = GoogleAdsDailyMetricORM.__table__.to_metadata(metadata)
    pub = GoogleAdsM6DailyPublicationORM.__table__.to_metadata(metadata)
    with engine.connect() as conn:
        tx = conn.begin()
        try:
            for table in metadata.tables.values():
                assert not sa.inspect(conn).has_table(table.name), table.name
            metadata.create_all(conn)
            conn.execute(metadata.tables["users"].insert(), {"id": 47})
            conn.execute(uploads.insert(), [
                {"id": 21604, "status": "ACTIVE", "file_hash_sha256": "a"*64,
                 "date_from": date(2026, 10, 9), "date_to": date(2026, 10, 12)},
                {"id": 21605, "status": "ACTIVE", "file_hash_sha256": "b"*64,
                 "date_from": date(2026, 10, 9), "date_to": date(2026, 10, 12)},
                {"id": 22001, "status": "ACTIVE", "file_hash_sha256": "c"*64,
                 "date_from": date(2026, 10, 13), "date_to": date(2026, 10, 13)},
                {"id": 22002, "status": "ACTIVE", "file_hash_sha256": "d"*64,
                 "date_from": date(2026, 10, 13), "date_to": date(2026, 10, 13)},
                {"id": 22003, "status": "ACTIVE", "file_hash_sha256": "e"*64,
                 "date_from": date(2026, 10, 14), "date_to": date(2026, 10, 14)},
            ])
            vid = conn.execute(version.insert().returning(version.c.id), {
                "customer_id": CUST,
                "approval_reference": service.M6_REFERENCE,
                "source_approval_reference": service.M5_REFERENCE,
                "valid_from": date(2026, 10, 9), "valid_to": None,
                "source_campaign_upload_id": 21604,
                "source_ad_group_upload_id": 21605,
                "approved_by_user_id": 47, "approved_on": date(2026, 10, 13),
            }).scalar_one()
            rows = [{
                "customer_id": CUST, "campaign_id": None,
                "campaign_key": "name:" + format(n, "064x"),
                "campaign_name": f"Campaign {n}",
                "report_date": date(2026, 10, 13),
                "currency_code": "MXN", "cost": Decimal("10.00"),
                "clicks": 2, "impressions": 20,
                "conversions": Decimal("0"), "conversion_value": Decimal("0"),
                "source_kind": "WAREHOUSE_XLSX", "source_upload_id": 22001,
            } for n in range(1, 28)]
            rows.append({
                **rows[0], "report_date": date(2026, 10, 12),
                "cost": Decimal("100.00"), "source_upload_id": 21604,
            })
            rows.append({
                **rows[0], "report_date": date(2026, 10, 14),
                "cost": Decimal("900.00"), "source_upload_id": 22003,
            })
            conn.execute(fact.insert(), rows)
            def publication(is_canonical=False):
                return conn.execute(pub.insert().returning(pub.c.id), {
                    "customer_id": CUST, "business_date": date(2026, 10, 13),
                    "revision": 1, "campaign_upload_id": 22001,
                    "ad_group_upload_id": 22002,
                    "approval_version_id": vid,
                    "campaign_sha256": "c"*64, "ad_group_sha256": "d"*64,
                    "is_canonical": is_canonical,
                    "published_by_user_id": 47, "published_on": date(2026, 10, 14),
                }).scalar_one()
            with Session(bind=conn) as session:
                monkeypatch.setattr(service, "db", SimpleNamespace(session=session))
                monkeypatch.setenv("GOOGLE_ADS_OAUTH_CUSTOMER_ID", CUST)
                yield conn, publication, pub, uploads, fact
        finally:
            tx.rollback()
    engine.dispose()


def _read(cutoff=date(2026, 10, 14), global_=True):
    return service.read_google_ads_funnel_investment(
        month_start=date(2026, 10, 1),
        cutoff_date=cutoff, is_global=global_,
    )


def test_unpublished_structured_spend_does_not_appear_in_funnel(campaign_gate_pg):
    conn, publication, pub, uploads, fact = campaign_gate_pg
    old_only = _read()
    assert old_only["status"] == "partial"
    assert old_only["amount"] == 100.0
    assert old_only["covered_days"] == 1
    publication(is_canonical=False)
    assert _read()["amount"] == 100.0
    assert _read(global_=False)["amount"] is None


def test_only_exact_canonical_upload_counts_and_missing_day_remains_missing(campaign_gate_pg):
    conn, publication, pub, uploads, fact = campaign_gate_pg
    pid = publication(is_canonical=True)
    result = _read()
    assert result["status"] == "partial"
    assert result["amount"] == 370.0
    assert result["covered_days"] == 2
    assert result["missing_days"] == 12  # 1..14 cutoff: 12 missing days
    # Day 14 structured but unpublished: must not add 900 MXN.
    assert result["data_to"] == "2026-10-13"
    conn.execute(sa.update(uploads).where(uploads.c.id == 22001).values(status="ARCHIVED"))
    assert _read()["amount"] == 100.0
    conn.execute(sa.update(uploads).where(uploads.c.id == 22001).values(status="ACTIVE"))
    conn.execute(sa.update(pub).where(pub.c.id == pid).values(campaign_sha256="f"*64))
    assert _read()["amount"] == 100.0


def test_canonical_day_incomplete_campaign_count_fails_closed(campaign_gate_pg):
    conn, publication, pub, uploads, facts = campaign_gate_pg
    publication(is_canonical=True)
    conn.execute(sa.delete(facts).where(
        facts.c.report_date == date(2026, 10, 13),
        facts.c.campaign_key == "name:" + format(27, "064x"),
    ))
    result = _read(cutoff=date(2026, 10, 13))
    assert result["status"] == "requires_review"
    assert result["amount"] is None
    assert service.build_funnel_investment_sources(
        meta_assigned=1000.0, google_ads=result,
    )["combined"] is None
