"""Independent M6 review E2E: live JWT, current DB roles, 2-man rule and PG16."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.extensions import db
from app.warehouse.services import google_ads_m6_correction_decision_service as review
from test_google_ads_m6_correction_candidate_stage_pg_e2e import (
    candidate_lab, REASON, _counts,
)
from test_google_ads_m6_manual_raw_postgres import real_warehouse
from test_google_ads_m6_manual_structured_postgres import lab

REV = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/ac42e8b9d510_google_ads_m6_correction_review.py"
)
URI = "/api/integrations/google-ads/corrections/candidates/"
NOTE = "Validacion independiente de identidad, importes y evidencias."
CONFIRM = "REVISION_INDEPENDIENTE_SIN_PUBLICAR"


@pytest.fixture
def reviewer_lab(candidate_lab, monkeypatch):
    client, token, other, engine, campaign, group = candidate_lab
    spec = importlib.util.spec_from_file_location("m6_review_e2e", REV)
    assert spec and spec.loader
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    with engine.begin() as conn:
        mig.op = Operations(MigrationContext.configure(conn))
        mig.upgrade()
        conn.execute(sa.text("""
            INSERT INTO warehouse_operators
                (id, user_id, can_view, can_upload, can_archive)
            VALUES (2, 48, true, false, false)
        """))
    monkeypatch.setenv(review.FLAG, "true")
    monkeypatch.setenv(review.REVIEWERS, "48")
    try:
        yield client, token, other, engine, campaign, group
    finally:
        db.session.remove()
        with engine.begin() as conn:
            conn.execute(sa.text(
                "DELETE FROM warehouse_audit_logs WHERE action = :action"
            ), {"action": review.ACTION})
            conn.execute(sa.text("DELETE FROM google_ads_m6_correction_decisions"))
            conn.execute(sa.text("DELETE FROM warehouse_operators WHERE user_id = 48"))
            mig.op = Operations(MigrationContext.configure(conn))
            mig.downgrade()


def _stage(client, token, campaign, group):
    response = client.post(URI + "ingest",
                           json={
                               "campaign_upload_id": campaign,
                               "ad_group_upload_id": group,
                               "revision": 1,
                               "expected_publication_id": None,
                               "reason": REASON,
                               "confirmation": "INGESTAR_CORRECCION_M6_SIN_PUBLICAR",
                           },
                           headers={"Authorization": "Bearer " + token})
    assert response.status_code == 201, response.get_json()
    return response.json["case_id"]


def _review(client, token, case_id, decision="APPROVED", note=NOTE,
            confirmation=CONFIRM):
    return client.post(
        URI + str(case_id) + "/review",
        json={"decision": decision, "note": note, "confirmation": confirmation},
        headers={"Authorization": "Bearer " + token} if token else {},
    )


def _review_counts(engine):
    with engine.connect() as conn:
        return (
            conn.execute(sa.text(
                "SELECT count(*) FROM google_ads_m6_correction_decisions"
            )).scalar_one(),
            conn.execute(sa.text(
                "SELECT count(*) FROM warehouse_audit_logs WHERE action = :action"
            ), {"action": review.ACTION}).scalar_one(),
        )


def test_review_requires_distinct_allowlisted_admin_and_replays_without_writes(
    reviewer_lab,
):
    client, actor, reviewer, engine, campaign, group = reviewer_lab
    cid = _stage(client, actor, campaign, group)
    assert _review_counts(engine) == (0, 0)
    assert _review(client, None, cid).status_code == 401
    assert _review(client, reviewer, cid, confirmation="WRONG").status_code == 400
    assert _review(client, actor, cid).status_code == 403
    assert _review_counts(engine) == (0, 0)
    accepted = _review(client, reviewer, cid)
    assert accepted.status_code == 201, accepted.get_json()
    assert accepted.json["status"] == "REVIEW_RECORDED"
    assert accepted.json["decision"] == "APPROVED"
    assert len(accepted.json["snapshot_sha256"]) == 64
    assert accepted.json["eligible_for_publication"] is False
    assert accepted.json["campaign_rows"] == 27
    assert accepted.json["group_rows"] == 43
    assert _review_counts(engine) == (1, 2)
    replay = _review(client, reviewer, cid)
    assert replay.status_code == 200, replay.get_json()
    assert replay.json["status"] == "ALREADY_REVIEWED"
    assert replay.json["snapshot_sha256"] == accepted.json["snapshot_sha256"]
    assert _review_counts(engine) == (1, 2)
    changed = _review(client, reviewer, cid, note="Cambio no permitido de motivacion")
    assert changed.status_code == 409
    assert changed.json["code"] == "CORRECTION_REVIEW_CONFLICT"
    assert _review_counts(engine) == (1, 2)
    assert _counts(engine) == (1, 27, 43, 0, 0, 0, 2)


def test_review_denies_missing_allowlist_downgraded_role_and_self_approval(
    reviewer_lab, monkeypatch,
):
    client, actor, reviewer, engine, campaign, group = reviewer_lab
    cid = _stage(client, actor, campaign, group)
    monkeypatch.delenv(review.FLAG)
    assert _review(client, reviewer, cid).status_code == 503
    monkeypatch.setenv(review.FLAG, "true")
    monkeypatch.delenv(review.REVIEWERS)
    assert _review(client, reviewer, cid).status_code == 403
    monkeypatch.setenv(review.REVIEWERS, "47,48")
    self_review = _review(client, actor, cid)
    assert self_review.status_code == 403
    assert self_review.json["code"] == "CORRECTION_SELF_REVIEW_FORBIDDEN"
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE users SET rol = 'GERENTE' WHERE id = 48"))
    assert _review(client, reviewer, cid).status_code == 403
    assert _review_counts(engine) == (0, 0)


def test_review_rejects_candidate_mutation_even_with_stale_approval(
    reviewer_lab,
):
    client, actor, reviewer, engine, campaign, group = reviewer_lab
    cid = _stage(client, actor, campaign, group)
    accepted = _review(client, reviewer, cid)
    assert accepted.status_code == 201, accepted.get_json()
    with engine.begin() as conn:
        # Equally alter matching campaign/group costs: totals still reconcile.
        conn.execute(sa.text("""
            UPDATE google_ads_m6_correction_campaign_facts
               SET cost = cost + 10
             WHERE id = (SELECT min(id) FROM google_ads_m6_correction_campaign_facts)
        """))
        conn.execute(sa.text("""
            UPDATE google_ads_m6_correction_group_facts
               SET cost = cost + 10
             WHERE id = (SELECT min(id) FROM google_ads_m6_correction_group_facts)
        """))
    retry = _review(client, reviewer, cid)
    assert retry.status_code == 409, retry.get_json()
    assert retry.json["code"] == "CORRECTION_REVIEW_CONFLICT"
    assert _review_counts(engine) == (1, 2)


def test_second_review_audit_failure_rolls_back_decision(reviewer_lab):
    client, actor, reviewer, engine, campaign, group = reviewer_lab
    cid = _stage(client, actor, campaign, group)
    with client.application.app_context():
        app_engine = db.engine
        n = {"count": 0}
        def fail_second(conn, cursor, stmt, parameters, context, executemany):
            if "INSERT INTO warehouse_audit_logs" in stmt:
                n["count"] += 1
                if n["count"] == 2:
                    raise RuntimeError("Synthetic second review audit failure")
        sa.event.listen(app_engine, "before_cursor_execute", fail_second)
        try:
            aborted = _review(client, reviewer, cid)
            assert aborted.status_code == 503
            assert _review_counts(engine) == (0, 0)
        finally:
            sa.event.remove(app_engine, "before_cursor_execute", fail_second)
    ok = _review(client, reviewer, cid)
    assert ok.status_code == 201, ok.get_json()
    assert _review_counts(engine) == (1, 2)


def test_rejection_is_persistent_not_replaceable_with_approval(reviewer_lab):
    client, actor, reviewer, engine, campaign, group = reviewer_lab
    cid = _stage(client, actor, campaign, group)
    rejected = _review(client, reviewer, cid, decision="REJECTED")
    assert rejected.status_code == 201
    assert rejected.json["decision"] == "REJECTED"
    attempt = _review(client, reviewer, cid, decision="APPROVED")
    assert attempt.status_code == 409
    assert attempt.json["code"] == "CORRECTION_REVIEW_CONFLICT"
    assert _review_counts(engine) == (1, 2)
