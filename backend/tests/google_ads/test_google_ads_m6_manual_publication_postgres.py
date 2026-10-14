"""Canonical publication E2E: real PG16 + Flask JWT + immutable RAW evidence.

Uses only the isolated dedicated google_ads_m6_ci PostgreSQL and synthetic
spreadsheets. Never publishes to production or runs M6 approval outside CI.
"""
from __future__ import annotations

import pytest
import sqlalchemy as sa

from app.models.google_ads_m6_daily_publication import GoogleAdsM6DailyPublicationORM
from app.warehouse.services.google_ads_m6_manual_publication_service import (
    PUBLISH_AUDIT, CONFIRMATION,
)
from test_google_ads_m6_manual_raw_postgres import real_warehouse
from test_google_ads_m6_manual_structured_postgres import lab, _ingest, _counts

URL = "/api/integrations/google-ads/manual/publish"


@pytest.fixture()
def publication_lab(lab):
    client, token, other, engine, campaign, group = lab
    table = GoogleAdsM6DailyPublicationORM.__table__
    with engine.begin() as conn:
        assert not sa.inspect(conn).has_table(table.name)
        table.create(conn)
    try:
        yield client, token, other, engine, campaign, group
    finally:
        # This fixture holds a Flask app context across HTTP requests; the
        # Warehouse-view permission check can leave an ORM read transaction
        # open. Remove it BEFORE DDL teardown or PostgreSQL waits on its lock.
        from app.extensions import db
        with client.application.app_context():
            db.session.remove()
        with engine.begin() as conn:
            table.drop(conn)


def _publish(client, token, campaign, group, confirmation=CONFIRMATION):
    return client.post(
        URL,
        headers={"Authorization": "Bearer " + token} if token else {},
        json={
            "campaign_upload_id": campaign,
            "ad_group_upload_id": group,
            "confirmation": confirmation,
        },
    )


def _published(engine):
    with engine.connect() as conn:
        publication = conn.execute(sa.text("""
            SELECT id, is_canonical, campaign_upload_id, ad_group_upload_id,
                   revision, approval_version_id
            FROM google_ads_m6_daily_publications
        """)).mappings().all()
        audit = conn.execute(sa.text("""
            SELECT upload_id, details FROM warehouse_audit_logs
            WHERE action = :action ORDER BY upload_id
        """), {"action": PUBLISH_AUDIT}).mappings().all()
        return [dict(x) for x in publication], [dict(x) for x in audit]


def test_requires_explicit_flag_actor_confirmation_and_fully_ingested_pair(
    publication_lab, monkeypatch,
):
    client, token, other, engine, camp, group = publication_lab
    assert _publish(client, token, camp, group).status_code == 503
    assert _published(engine) == ([], [])
    monkeypatch.setenv("GOOGLE_ADS_M6_DAILY_PUBLICATION_ENABLED", "true")
    assert _publish(client, None, camp, group).status_code == 401
    assert _publish(client, other, camp, group).status_code == 403
    assert _publish(client, token, camp, group, "WRONG").status_code == 400
    assert _publish(client, token, camp, camp).status_code == 400
    assert _publish(client, token, camp, group).status_code == 409
    assert _published(engine) == ([], [])
    monkeypatch.setenv("GOOGLE_ADS_M6_STRUCTURED_INGESTION_ENABLED", "true")
    stage = _ingest(client, token, camp, group)
    assert stage.status_code == 201, stage.get_json()
    assert _published(engine) == ([], [])
    assert _counts(engine)["audits"] == 2


def test_exact_canonical_publication_is_audited_and_idempotent(
    publication_lab, monkeypatch,
):
    client, token, other, engine, camp, group = publication_lab
    monkeypatch.setenv("GOOGLE_ADS_M6_STRUCTURED_INGESTION_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_ADS_M6_DAILY_PUBLICATION_ENABLED", "true")
    assert _ingest(client, token, camp, group).status_code == 201
    first = _publish(client, token, camp, group)
    assert first.status_code == 201, first.get_json()
    assert first.json["status"] == "CANONICAL_DAY_PUBLISHED"
    assert first.json["is_canonical"] is True
    assert first.json["campaign_rows"] == 27
    assert first.json["group_rows"] == 43
    pubs, audits = _published(engine)
    assert len(pubs) == 1 and pubs[0]["is_canonical"]
    assert pubs[0]["revision"] == 1
    assert {r["upload_id"] for r in audits} == {camp, group}
    assert all(row["details"]["publication_id"] == pubs[0]["id"] for row in audits)
    assert all(row["details"]["is_canonical"] is True for row in audits)
    repeated = _publish(client, token, camp, group)
    assert repeated.status_code == 200, repeated.get_json()
    assert repeated.json["status"] == "ALREADY_PUBLISHED"
    assert _published(engine) == (pubs, audits)


def test_changed_structured_cost_or_missing_import_audit_rejected(
    publication_lab, monkeypatch,
):
    client, token, other, engine, camp, group = publication_lab
    monkeypatch.setenv("GOOGLE_ADS_M6_STRUCTURED_INGESTION_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_ADS_M6_DAILY_PUBLICATION_ENABLED", "true")
    assert _ingest(client, token, camp, group).status_code == 201
    with engine.begin() as conn:
        conn.execute(sa.text("""
            UPDATE google_ads_daily_metrics SET cost = cost + 0.01
            WHERE customer_id = '2739125201' AND source_upload_id = :id
        """), {"id": camp})
    rejected = _publish(client, token, camp, group)
    assert rejected.status_code == 409, rejected.get_json()
    assert rejected.json["code"] == "EXISTING_STRUCTURED_FACT_CONFLICT"
    assert _published(engine) == ([], [])


def test_archived_raw_blocks_publication(publication_lab, monkeypatch):
    client, token, other, engine, camp, group = publication_lab
    monkeypatch.setenv("GOOGLE_ADS_M6_STRUCTURED_INGESTION_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_ADS_M6_DAILY_PUBLICATION_ENABLED", "true")
    assert _ingest(client, token, camp, group).status_code == 201
    with engine.begin() as conn:
        conn.execute(sa.text(
            "UPDATE warehouse_uploads SET status = 'ARCHIVED' WHERE id = :id"
        ), {"id": group})
    result = _publish(client, token, camp, group)
    assert result.status_code == 409, result.get_json()
    assert result.json["code"] in ("RAW_PAIR_UNREADABLE",
                                   "RAW_PAIR_METADATA_MISMATCH",
                                   "RAW_PAIR_PROVENANCE_INVALID")
    assert _published(engine) == ([], [])


def test_publication_second_audit_failure_rolls_back_canonical_row(
    publication_lab, monkeypatch,
):
    client, token, other, engine, camp, group = publication_lab
    monkeypatch.setenv("GOOGLE_ADS_M6_STRUCTURED_INGESTION_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_ADS_M6_DAILY_PUBLICATION_ENABLED", "true")
    assert _ingest(client, token, camp, group).status_code == 201
    from app.extensions import db
    sequence = {"n": 0}
    def fail_second_audit(conn, cursor, stmt, parameters, context, executemany):
        if "INSERT INTO warehouse_audit_logs" in stmt:
            sequence["n"] += 1
            if sequence["n"] == 2:
                raise RuntimeError("synthetic audit-2 failure")
    with client.application.app_context():
        app_engine = db.engine
        sa.event.listen(app_engine, "before_cursor_execute", fail_second_audit)
        try:
            failed = _publish(client, token, camp, group)
            assert failed.status_code == 503, failed.get_json()
            assert failed.json["code"] == "M6_PUBLICATION_FAILED"
            assert _published(engine) == ([], [])
        finally:
            sa.event.remove(app_engine, "before_cursor_execute", fail_second_audit)
    success = _publish(client, token, camp, group)
    assert success.status_code == 201, success.get_json()
    assert len(_published(engine)[1]) == 2
