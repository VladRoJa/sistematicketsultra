"""M6 structured pair: real Flask JWT + PostgreSQL16 + filesystem RAW.

Dedicated CI database only, all facts synthetic, no production calls.
"""
from __future__ import annotations

from datetime import date
from io import BytesIO
import sqlalchemy as sa
import pytest

from app.models.google_ads_daily import GoogleAdsDailyMetricORM
from app.models.google_ads_ad_group_daily import GoogleAdsAdGroupDailyMetricORM
from app.models.google_ads_m6_continuity import (
    GoogleAdsBranchApprovalVersionORM,
    GoogleAdsBranchApprovedIdentityORM,
)
from app.warehouse.services import google_ads_m6_manual_preview_service as preview_svc
from app.warehouse.services import google_ads_m6_manual_structured_service as svc
from test_google_ads_m6_manual_raw_postgres import real_warehouse, _confirm
from test_google_ads_m6_manual_preview import daily_xlsx, post as preview_post

URL = "/api/integrations/google-ads/manual/ingest"


def _ingest(client, token, campaign_id, group_id, *, confirmation=None):
    return client.post(
        URL,
        headers={"Authorization": "Bearer " + token} if token else {},
        json={
            "campaign_upload_id": campaign_id,
            "ad_group_upload_id": group_id,
            "confirmation": confirmation or svc.CONFIRMATION,
        },
    )


@pytest.fixture
def lab(real_warehouse, monkeypatch):
    client, token, other, engine, root = real_warehouse
    files = daily_xlsx()
    preflight = preview_post(client, token, files=files)
    assert preflight.status_code == 200, preflight.get_json()
    ticket = preflight.json["raw_confirm_ticket"]
    raw = _confirm(client, token, ticket, files)
    assert raw.status_code == 201, raw.get_json()
    campaign_id = raw.json["uploads"][svc.CAMPAIGN_TYPE]["upload_id"]
    group_id = raw.json["uploads"][svc.GROUP_TYPE]["upload_id"]

    # Additional tables belong to this test only and are dropped before
    # real_warehouse fixture tears down the underlying Warehouse schema.
    m = sa.MetaData()
    sa.Table("users", m, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table("warehouse_uploads", m, sa.Column("id", sa.Integer, primary_key=True))
    catalog = sa.Table(
        "track_branch_catalog", m,
        sa.Column("sucursal_canon", sa.Text, primary_key=True),
    )
    daily = GoogleAdsDailyMetricORM.__table__.to_metadata(m)
    groups = GoogleAdsAdGroupDailyMetricORM.__table__.to_metadata(m)
    versions = GoogleAdsBranchApprovalVersionORM.__table__.to_metadata(m)
    identities = GoogleAdsBranchApprovedIdentityORM.__table__.to_metadata(m)

    with engine.begin() as conn:
        for table in (catalog, daily, groups, versions, identities):
            assert not sa.inspect(conn).has_table(table.name), table.name
            table.create(conn)
        conn.execute(catalog.insert(), [
            {"sucursal_canon": "LAB_BRANCH_" + str(i)} for i in range(26)
        ])
        # Historical M6 approval points to 21604/21605. These fixture rows
        # provide foreign keys only; the frozen historical XLSX are injected
        # by the reference preflight fixture, never read from production.
        conn.execute(sa.text("""
            INSERT INTO warehouse_uploads
              (id, original_filename, stored_filename, stored_path,
               file_size_bytes, file_hash_sha256, extension,
               source_id, family_id, operational_role_id, report_type_id,
               period_type, cutoff_date, date_from, date_to, status,
               uploaded_by_user_id)
            VALUES (:id, :filename, :filename, 'synthetic-history',
                    1, :digest, 'xlsx', 1, 1, 1, :report_type,
                    'rango', :start, :start, :end, 'ACTIVE', 47)
        """), [
            {"id": 21604, "filename": "fake_history_campaign.xlsx",
             "digest": "a" * 64, "report_type": 1,
             "start": date(2026, 10, 9), "end": date(2026, 10, 12)},
            {"id": 21605, "filename": "fake_history_group.xlsx",
             "digest": "b" * 64, "report_type": 2,
             "start": date(2026, 10, 9), "end": date(2026, 10, 12)},
        ])
        _, _, mapping = preview_svc._historical_catalog()
        assert len(mapping) == 26
        conn.execute(versions.insert(), {
            "id": 1,
            "customer_id": svc.CUSTOMER_ID,
            "approval_reference": svc.M6_REFERENCE,
            "source_approval_reference": svc.M5_REFERENCE,
            "valid_from": date(2026, 10, 9),
            "valid_to": None,
            "source_campaign_upload_id": 21604,
            "source_ad_group_upload_id": 21605,
            "approved_by_user_id": 47,
            "approved_on": date(2026, 10, 13),
        })
        conn.execute(identities.insert(), [
            {
                "approval_version_id": 1,
                "campaign_key": campaign_key, "ad_group_key": group_key,
                "sucursal_canon": branch,
            }
            for (campaign_key, group_key), branch in mapping.items()
        ])

    monkeypatch.setenv("GOOGLE_ADS_OAUTH_CUSTOMER_ID", "2739125201")
    try:
        yield client, token, other, engine, campaign_id, group_id
    finally:
        with engine.begin() as conn:
            for table in (identities, versions, groups, daily, catalog):
                table.drop(conn)


def _counts(engine, day=date(2026, 10, 13)):
    with engine.connect() as conn:
        n = {}
        for table in ("google_ads_daily_metrics",
                      "google_ads_ad_group_daily_metrics"):
            n[table] = conn.execute(sa.text(
                "SELECT count(*) FROM " + table +
                " WHERE report_date = :day"), {"day": day}).scalar_one()
        n["audits"] = conn.execute(sa.text("""
            SELECT count(*) FROM warehouse_audit_logs
            WHERE action = 'GOOGLE_ADS_M6_PAIR_IMPORT'
        """)).scalar_one()
        return n


def test_atomic_ingest_idempotent_and_not_published(lab, monkeypatch):
    client, token, other, engine, campaign_id, group_id = lab
    assert _ingest(client, token, campaign_id, group_id).status_code == 503
    assert _ingest(client, None, campaign_id, group_id).status_code in (401, 503)
    monkeypatch.setenv("GOOGLE_ADS_M6_STRUCTURED_INGESTION_ENABLED", "true")
    assert _ingest(client, None, campaign_id, group_id).status_code == 401
    assert _ingest(client, other, campaign_id, group_id).status_code == 403
    assert _ingest(client, token, campaign_id, group_id,
                   confirmation="WRONG").status_code == 400
    assert _counts(engine) == {
        "google_ads_daily_metrics": 0,
        "google_ads_ad_group_daily_metrics": 0,
        "audits": 0,
    }

    res = _ingest(client, token, campaign_id, group_id)
    assert res.status_code == 201, res.get_json()
    assert res.json["status"] == "STRUCTURED_PAIR_STAGED"
    assert res.json["eligible_for_publication"] is False
    assert res.json["funnel_publication"] == "NOT_AUTHORIZED"
    assert res.json["campaign_rows"] == 27
    assert res.json["group_rows"] == 43
    assert _counts(engine) == {
        "google_ads_daily_metrics": 27,
        "google_ads_ad_group_daily_metrics": 43,
        "audits": 2,
    }
    with engine.connect() as conn:
        assert conn.execute(sa.text("""
            SELECT distinct source_upload_id FROM google_ads_daily_metrics
        """)).scalars().all() == [campaign_id]
        assert conn.execute(sa.text("""
            SELECT distinct source_upload_id FROM google_ads_ad_group_daily_metrics
        """)).scalars().all() == [group_id]
    again = _ingest(client, token, campaign_id, group_id)
    assert again.status_code == 200, again.get_json()
    assert again.json["status"] == "ALREADY_INGESTED"
    assert _counts(engine)["audits"] == 2


def test_second_table_insert_failure_rolls_back_first_and_both_audits(
    lab, monkeypatch
):
    client, token, other, engine, campaign_id, group_id = lab
    monkeypatch.setenv("GOOGLE_ADS_M6_STRUCTURED_INGESTION_ENABLED", "true")
    def fail_group(conn, cursor, statement, parameters, context, executemany):
        if "INSERT INTO google_ads_ad_group_daily_metrics" in statement:
            raise RuntimeError("Synthetic rollback assertion")
    # Flask-SQLAlchemy creates its OWN engine from the same isolated URL;
    # instrumenting the _test_engine() setup engine does not intercept writes.
    from app.extensions import db
    with client.application.app_context():
        application_engine = db.engine
        sa.event.listen(application_engine, "before_cursor_execute", fail_group)
        try:
            r = _ingest(client, token, campaign_id, group_id)
            assert r.status_code == 503, r.get_json()
            assert r.json["code"] == "M6_STRUCTURED_STAGE_FAILED"
            assert _counts(engine) == {
                "google_ads_daily_metrics": 0,
                "google_ads_ad_group_daily_metrics": 0,
                "audits": 0,
            }
        finally:
            sa.event.remove(application_engine, "before_cursor_execute", fail_group)
    ok = _ingest(client, token, campaign_id, group_id)
    assert ok.status_code == 201, ok.get_json()
    assert _counts(engine)["audits"] == 2


def test_identity_approval_and_manual_provenance_fail_closed(lab, monkeypatch):
    client, token, other, engine, campaign_id, group_id = lab
    monkeypatch.setenv("GOOGLE_ADS_M6_STRUCTURED_INGESTION_ENABLED", "true")
    with engine.begin() as conn:
        conn.execute(sa.text("""
            DELETE FROM google_ads_branch_approved_identities
            WHERE approval_version_id = 1
        """))
    r = _ingest(client, token, campaign_id, group_id)
    assert r.status_code == 409, r.get_json()
    assert r.json["code"] == "M6_APPROVED_IDENTITIES_MISMATCH"
    assert _counts(engine)["audits"] == 0


def test_archived_or_generic_raw_cannot_ingest(lab, monkeypatch):
    client, token, other, engine, campaign_id, group_id = lab
    monkeypatch.setenv("GOOGLE_ADS_M6_STRUCTURED_INGESTION_ENABLED", "true")
    with engine.begin() as conn:
        conn.execute(sa.text("""
            UPDATE warehouse_audit_logs
            SET details = jsonb_set(details::jsonb, '{upload_origin}',
                                    '"generic_upload"')::json
            WHERE upload_id = :id AND action = 'UPLOAD'
        """), {"id": group_id})
    r = _ingest(client, token, campaign_id, group_id)
    assert r.status_code == 409, r.get_json()
    assert r.json["code"] == "RAW_PAIR_PROVENANCE_INVALID"
    assert _counts(engine)["audits"] == 0
