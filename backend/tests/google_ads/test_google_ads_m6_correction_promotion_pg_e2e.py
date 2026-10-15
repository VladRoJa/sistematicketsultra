"""Atomic approved M6 revision publication; isolated PG16, no live data."""
from __future__ import annotations

from datetime import date
from pathlib import Path
import importlib.util
import json

import pytest
import sqlalchemy as sa

from app.extensions import db
from app.warehouse.services import google_ads_m6_correction_promotion_service as promote_svc
from app.warehouse.services import google_ads_m6_correction_decision_service as review_svc
from test_google_ads_m6_correction_decision_pg_e2e import (
    reviewer_lab, _stage, _review,
)
from test_google_ads_m6_correction_candidate_stage_pg_e2e import (
    candidate_lab, _stage as stage_rev2,
)
from test_google_ads_m6_manual_structured_postgres import lab
from test_google_ads_m6_manual_raw_postgres import real_warehouse
from app.models.google_ads_m6_daily_publication import GoogleAdsM6DailyPublicationORM

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/c5e7a2d93f10_google_ads_m6_correction_promotions.py"
)
API = "/api/integrations/google-ads/corrections/candidates/"


@pytest.fixture
def promotion_lab(reviewer_lab, monkeypatch):
    client, actor, reviewer, engine, camp, group = reviewer_lab
    spec = importlib.util.spec_from_file_location("ga_m6_promotion_migration", MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    with engine.begin() as conn:
        module.op = Operations(MigrationContext.configure(conn))
        module.upgrade()
    monkeypatch.setenv(promote_svc.FLAG, "true")
    try:
        yield client, actor, reviewer, engine, camp, group
    finally:
        db.session.remove()
        with engine.begin() as conn:
            conn.execute(sa.text(
                "DELETE FROM warehouse_audit_logs WHERE action = :a"
            ), {"a": promote_svc.ACTION})
            conn.execute(sa.text(
                "DELETE FROM google_ads_m6_correction_promotions"
            ))
            conn.execute(sa.text(
                "DELETE FROM google_ads_m6_daily_publications"
            ))
            module.op = Operations(MigrationContext.configure(conn))
            module.downgrade()


def _promote(client, token, cid, decision, *, sha=None, revision=1,
             prior=None, confirmation="PUBLICAR_REVISION_GOOGLE_ADS_M6"):
    return client.post(
        API + str(cid) + "/promote",
        headers={"Authorization": "Bearer " + token} if token else {},
        json={
            "decision_id": decision["decision_id"],
            "snapshot_sha256": sha or decision["snapshot_sha256"],
            "revision": revision,
            "expected_publication_id": prior,
            "confirmation": confirmation,
        },
    )


def _audit_counts(engine):
    with engine.connect() as conn:
        pub = conn.execute(sa.text(
            "SELECT count(*) FROM google_ads_m6_daily_publications"
        )).scalar_one()
        promotions = conn.execute(sa.text(
            "SELECT count(*) FROM google_ads_m6_correction_promotions"
        )).scalar_one()
        audits = conn.execute(sa.text(
            "SELECT count(*) FROM warehouse_audit_logs WHERE action = :a"
        ), {"a": promote_svc.ACTION}).scalar_one()
        facts = [
            conn.execute(sa.text("SELECT count(*) FROM " + table)).scalar_one()
            for table in ("google_ads_daily_metrics",
                          "google_ads_ad_group_daily_metrics")
        ]
        return pub, promotions, audits, tuple(facts)


def test_first_revision_promotes_with_replay_and_no_original_fact_writes(
    promotion_lab,
):
    client, actor, reviewer, engine, camp, group = promotion_lab
    cid = _stage(client, actor, camp, group)
    decision = _review(client, reviewer, cid).json
    assert _audit_counts(engine) == (0, 0, 0, (0, 0))
    approved = _promote(client, actor, cid, decision)
    assert approved.status_code == 201, approved.get_json()
    assert approved.json["status"] == "CORRECTION_CANONICAL_PROMOTED"
    assert approved.json["revision"] == 1
    assert approved.json["is_canonical"] is True
    assert _audit_counts(engine) == (1, 1, 2, (0, 0))
    duplicate = _promote(client, actor, cid, decision)
    assert duplicate.status_code == 200, duplicate.get_json()
    assert duplicate.json["status"] == "ALREADY_PROMOTED"
    assert _audit_counts(engine) == (1, 1, 2, (0, 0))
    with engine.connect() as conn:
        rows = conn.execute(sa.text("""
            SELECT p.revision, p.is_canonical, x.case_id, x.decision_id
            FROM google_ads_m6_daily_publications p
            JOIN google_ads_m6_correction_promotions x ON x.publication_id = p.id
        """)).mappings().all()
        assert len(rows) == 1
        assert rows[0]["revision"] == 1
        assert rows[0]["is_canonical"] is True
        assert rows[0]["case_id"] == cid
        assert rows[0]["decision_id"] == decision["decision_id"]


def test_promotion_requires_current_identity_decision_and_matching_digest(
    promotion_lab, monkeypatch,
):
    client, actor, reviewer, engine, camp, group = promotion_lab
    cid = _stage(client, actor, camp, group)
    decision = _review(client, reviewer, cid).json
    monkeypatch.delenv(promote_svc.FLAG)
    assert _promote(client, actor, cid, decision).status_code == 503
    monkeypatch.setenv(promote_svc.FLAG, "true")
    assert _promote(client, None, cid, decision).status_code == 401
    assert _promote(client, reviewer, cid, decision).status_code == 403
    assert _promote(client, actor, cid, decision, sha="0" * 64).status_code == 409
    assert _promote(client, actor, cid, decision, confirmation="NO").status_code == 400
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET rol = 'GERENTE' WHERE id = 48"))
    assert _promote(client, actor, cid, decision).status_code == 409
    assert _audit_counts(engine) == (0, 0, 0, (0, 0))


def test_supersedes_earlier_canonical_atomically_without_deleting_it(
    promotion_lab,
):
    client, actor, reviewer, engine, camp, group = promotion_lab
    pub = GoogleAdsM6DailyPublicationORM.__table__
    with engine.begin() as conn:
        previous = conn.execute(pub.insert().returning(pub.c.id), {
            "customer_id": promote_svc.CUSTOMER_ID,
            "business_date": date(2026, 10, 13), "revision": 1,
            "campaign_upload_id": 990101, "ad_group_upload_id": 990102,
            "approval_version_id": 1,
            "campaign_sha256": "f" * 64, "ad_group_sha256": "e" * 64,
            "is_canonical": True, "published_by_user_id": 47,
            "published_on": date(2026, 10, 14),
        }).scalar_one()
        conn.execute(sa.text("""
            UPDATE warehouse_audit_logs
               SET details = details::jsonb || CAST(:extra AS jsonb)
             WHERE upload_id IN (:camp, :grp) AND action = 'UPLOAD'
        """), {
            "extra": json.dumps({
                "intended_revision": 2,
                "expected_publication_id": previous,
            }), "camp": camp, "grp": group,
        })
    prepared = stage_rev2(client, actor, camp, group,
                          revision=2, expected=previous)
    assert prepared.status_code == 201, prepared.get_json()
    cid = prepared.json["case_id"]
    reviewed = _review(client, reviewer, cid)
    assert reviewed.status_code == 201, reviewed.get_json()
    result = _promote(client, actor, cid, reviewed.json,
                      revision=2, prior=previous)
    assert result.status_code == 201, result.get_json()
    assert _audit_counts(engine) == (2, 1, 2, (0, 0))
    with engine.connect() as conn:
        versions = conn.execute(sa.text("""
            SELECT id, revision, is_canonical
            FROM google_ads_m6_daily_publications ORDER BY revision
        """)).mappings().all()
        assert [(v["revision"], v["is_canonical"]) for v in versions] == [
            (1, False), (2, True),
        ]
        assert versions[0]["id"] == previous
        reference = conn.execute(sa.text("""
            SELECT superseded_publication_id
            FROM google_ads_m6_correction_promotions
        """)).scalar_one()
        assert reference == previous
    again = _promote(client, actor, cid, reviewed.json,
                     revision=2, prior=previous)
    assert again.status_code == 200, again.get_json()


def test_second_promotion_audit_failure_rolls_back_publication(promotion_lab):
    client, actor, reviewer, engine, camp, group = promotion_lab
    cid = _stage(client, actor, camp, group)
    decision = _review(client, reviewer, cid).json
    with client.application.app_context():
        app_engine = db.engine
        n = {"count": 0}
        def fail_second(conn, cursor, stmt, params, ctx, executemany):
            if "INSERT INTO warehouse_audit_logs" in stmt:
                n["count"] += 1
                if n["count"] == 2:
                    raise RuntimeError("Synthetic promotion audit failure")
        sa.event.listen(app_engine, "before_cursor_execute", fail_second)
        try:
            denied = _promote(client, actor, cid, decision)
            assert denied.status_code == 503, denied.get_json()
            assert _audit_counts(engine) == (0, 0, 0, (0, 0))
        finally:
            sa.event.remove(app_engine, "before_cursor_execute", fail_second)
    accepted = _promote(client, actor, cid, decision)
    assert accepted.status_code == 201, accepted.get_json()
    assert _audit_counts(engine) == (1, 1, 2, (0, 0))


def test_rejected_or_changed_candidate_never_promotes(promotion_lab):
    client, actor, reviewer, engine, camp, group = promotion_lab
    cid = _stage(client, actor, camp, group)
    rejected = _review(client, reviewer, cid, decision="REJECTED").json
    refused = _promote(client, actor, cid, rejected)
    assert refused.status_code == 409
    assert refused.json["code"] == "CORRECTION_INDEPENDENT_APPROVAL_REQUIRED"
    assert _audit_counts(engine) == (0, 0, 0, (0, 0))
