"""Correction staging E2E: JWT + Warehouse permissions, real RAW/FS and PG16.

A synthetic test-only endpoint dispatches to the INTERNAL service; the
production app never registers it. No calls to remote services or prod DB.
"""
from __future__ import annotations

from datetime import date
import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from flask import jsonify, request
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models.google_ads_m6_daily_publication import GoogleAdsM6DailyPublicationORM
from app.warehouse.services import google_ads_m6_correction_candidate_service as svc
from test_google_ads_m6_manual_structured_postgres import lab
from test_google_ads_m6_continuity_postgres import _test_engine

REV_PATH = (
    Path(__file__).resolve().parents[2] /
    "migrations/versions/e8b2c41d7a60_google_ads_m6_correction_candidates.py"
)
REASON = "Se detecto una inconsistencia y se solicita revision historica."


def _migration():
    spec = importlib.util.spec_from_file_location("m6_corr_stage_e2e", REV_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def candidate_lab(lab, monkeypatch):
    client, token, other, engine, campaign, group = lab
    migration = _migration()
    pub = GoogleAdsM6DailyPublicationORM.__table__
    with engine.begin() as conn:
        assert not sa.inspect(conn).has_table(pub.name)
        pub.create(conn)
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()
        # Preexisting 13-Oct legacy RAW are evidence, not part of the new pair.
        conn.execute(sa.text("""
            INSERT INTO warehouse_uploads (
                id, original_filename, stored_filename, stored_path,
                file_size_bytes, file_hash_sha256, extension,
                source_id, family_id, operational_role_id, report_type_id,
                period_type, cutoff_date, date_from, date_to, status,
                uploaded_by_user_id
            ) VALUES (
                :id, 'legacy.xlsx', 'legacy.xlsx', 'synthetic-only',
                1, :digest, 'xlsx', 1, 1, 1, :kind,
                'rango', '2026-10-13', '2026-10-13', '2026-10-13',
                'ARCHIVED', 47
            )
        """), [
            {"id": 990101, "digest": "f" * 64, "kind": 1},
            {"id": 990102, "digest": "e" * 64, "kind": 2},
        ])
        conn.execute(sa.text("""
            UPDATE warehouse_audit_logs
               SET details = jsonb_set(
                   jsonb_set(details::jsonb, '{upload_origin}',
                             '"google_ads_correction_pair"'),
                   '{correction_case_intent}', '"CANDIDATE_ONLY"')::json
             WHERE upload_id IN (:campaign, :groups) AND action = 'UPLOAD'
        """), {"campaign": campaign, "groups": group})

    # No this endpoint in Suite Ultra. Tests inject it solely into a
    # disposable Flask app with real JWT checking.
    @client.application.post("/__isolated_ci_only/m6-correction-candidate")
    @jwt_required()
    def _test_only_dispatch():
        data = request.get_json()
        try:
            result = svc.stage_m6_correction_candidate(**data)
        except svc.GoogleAdsM6CorrectionStageError as exc:
            code = str(exc)
            return jsonify({"code": code}), (
                503 if code == "CORRECTION_CANDIDATE_DISABLED"
                else 403 if code == "FORBIDDEN" else 409
            )
        except Exception:
            client.application.logger.exception("isolated test candidate stage failed")
            return jsonify({"code": "CORRECTION_STAGE_FAILED"}), 503
        return jsonify(result), 200 if result["status"] == "ALREADY_STAGED" else 201

    monkeypatch.setenv("GOOGLE_ADS_OAUTH_CUSTOMER_ID", svc.CUSTOMER_ID)
    monkeypatch.setenv(svc.FLAG, "true")
    try:
        yield client, token, other, engine, campaign, group
    finally:
        db.session.remove()
        with engine.begin() as conn:
            for table in (migration.GROUP, migration.CAMPAIGN, migration.CASE):
                conn.execute(sa.text("DELETE FROM " + table))
            migration.op = Operations(MigrationContext.configure(conn))
            migration.downgrade()
            pub.drop(conn)


from alembic.migration import MigrationContext
from alembic.operations import Operations


def _stage(client, token, campaign, group, *, revision=1, expected=None,
           reason=REASON):
    return client.post("/__isolated_ci_only/m6-correction-candidate",
                       headers={"Authorization": "Bearer " + token} if token else {},
                       json={
                           "campaign_upload_id": campaign,
                           "group_upload_id": group,
                           "revision": revision,
                           "expected_publication_id": expected,
                           "reason": reason,
                       })


def _counts(engine):
    with engine.connect() as conn:
        return tuple(conn.execute(sa.text("SELECT count(*) FROM " + table)).scalar_one()
                     for table in (
                         "google_ads_m6_correction_cases",
                         "google_ads_m6_correction_campaign_facts",
                         "google_ads_m6_correction_group_facts",
                         "google_ads_daily_metrics",
                         "google_ads_ad_group_daily_metrics",
                         "google_ads_m6_daily_publications",
                     )) + (conn.execute(sa.text("""
                         SELECT count(*) FROM warehouse_audit_logs
                         WHERE action = :action
                     """), {"action": svc.AUDIT}).scalar_one(),)


def test_candidate_is_unpublished_atomic_idempotent_and_keeps_legacy(candidate_lab):
    client, token, other, engine, camp, group = candidate_lab
    assert _counts(engine) == (0, 0, 0, 0, 0, 0, 0)
    first = _stage(client, token, camp, group)
    assert first.status_code == 201, first.get_json()
    assert first.json["status"] == "CANDIDATE_STAGED"
    assert first.json["eligible_for_publication"] is False
    assert first.json["funnel_publication"] == "NOT_AUTHORIZED"
    assert first.json["campaign_rows"] == 27
    assert first.json["group_rows"] == 43
    assert _counts(engine) == (1, 27, 43, 0, 0, 0, 2)
    again = _stage(client, token, camp, group)
    assert again.status_code == 200, again.get_json()
    assert again.json["status"] == "ALREADY_STAGED"
    assert _counts(engine) == (1, 27, 43, 0, 0, 0, 2)
    changed = _stage(client, token, camp, group, reason="Otro motivo explicito")
    assert changed.status_code == 409
    assert changed.json["code"] == "CORRECTION_CANDIDATE_CONFLICT"
    assert _counts(engine) == (1, 27, 43, 0, 0, 0, 2)
    with engine.connect() as conn:
        assert conn.execute(sa.text("""
            SELECT count(*) FROM warehouse_uploads
            WHERE id IN (990101, 990102) AND status = 'ARCHIVED'
        """)).scalar_one() == 2


def test_requires_flag_jwt_admicorp_and_warehouse_upload(candidate_lab, monkeypatch):
    client, token, other, engine, camp, group = candidate_lab
    monkeypatch.delenv(svc.FLAG)
    disabled = _stage(client, token, camp, group)
    assert disabled.status_code == 503
    assert disabled.json["code"] == "CORRECTION_CANDIDATE_DISABLED"
    monkeypatch.setenv(svc.FLAG, "true")
    assert _stage(client, None, camp, group).status_code == 401
    assert _stage(client, other, camp, group).status_code == 403
    with engine.begin() as conn:
        conn.execute(sa.text("""
            UPDATE warehouse_operators SET can_upload = false
            WHERE user_id = 47
        """))
    denied = _stage(client, token, camp, group)
    assert denied.status_code == 403
    assert _counts(engine) == (0, 0, 0, 0, 0, 0, 0)


def test_bad_provenance_or_missing_prior_evidence_cannot_stage(candidate_lab):
    client, token, other, engine, camp, group = candidate_lab
    with engine.begin() as conn:
        conn.execute(sa.text("""
            UPDATE warehouse_audit_logs
               SET details = jsonb_set(details::jsonb, '{upload_origin}',
                                       '"generic_upload"')::json
             WHERE upload_id = :id AND action = 'UPLOAD'
        """), {"id": group})
    rejected = _stage(client, token, camp, group)
    assert rejected.status_code == 409
    assert rejected.json["code"] == "CORRECTION_RAW_PROVENANCE_INVALID"
    with engine.begin() as conn:
        conn.execute(sa.text("""
            UPDATE warehouse_audit_logs
               SET details = jsonb_set(details::jsonb, '{upload_origin}',
                                       '"google_ads_correction_pair"')::json
             WHERE upload_id = :id AND action = 'UPLOAD'
        """), {"id": group})
        conn.execute(sa.text("""
            UPDATE warehouse_uploads SET cutoff_date = '2026-10-12',
               date_from = '2026-10-12', date_to = '2026-10-12'
            WHERE id IN (990101, 990102)
        """))
    prior = _stage(client, token, camp, group)
    assert prior.status_code == 409
    assert prior.json["code"] == "CORRECTION_PRIOR_RAW_REQUIRED"
    assert _counts(engine) == (0, 0, 0, 0, 0, 0, 0)


def test_revision_two_requires_exact_canonical_without_promoting(candidate_lab):
    client, token, other, engine, camp, group = candidate_lab
    pub = GoogleAdsM6DailyPublicationORM.__table__
    with engine.begin() as conn:
        prior_id = conn.execute(pub.insert().returning(pub.c.id), {
            "customer_id": svc.CUSTOMER_ID, "business_date": date(2026, 10, 13),
            "revision": 1, "campaign_upload_id": 990101,
            "ad_group_upload_id": 990102, "approval_version_id": 1,
            "campaign_sha256": "f" * 64, "ad_group_sha256": "e" * 64,
            "is_canonical": True, "published_by_user_id": 47,
            "published_on": date(2026, 10, 14),
        }).scalar_one()
    assert _stage(client, token, camp, group).json["code"] == "CORRECTION_REVISION_MISMATCH"
    assert _stage(client, token, camp, group, revision=2).status_code == 409
    accepted = _stage(client, token, camp, group,
                      revision=2, expected=prior_id)
    assert accepted.status_code == 201, accepted.get_json()
    assert _counts(engine) == (1, 27, 43, 0, 0, 1, 2)
    with engine.connect() as conn:
        assert conn.execute(sa.select(pub.c.is_canonical)).scalar_one() is True


def test_second_audit_error_rolls_back_everything(candidate_lab):
    client, token, other, engine, camp, group = candidate_lab
    sequence = {"n": 0}

    def fail_second(conn, cursor, stmt, parameters, context, executemany):
        if "INSERT INTO warehouse_audit_logs" in stmt:
            sequence["n"] += 1
            if sequence["n"] == 2:
                raise RuntimeError("synthetic second audit failure")

    app_engine = db.engine
    sa.event.listen(app_engine, "before_cursor_execute", fail_second)
    try:
        response = _stage(client, token, camp, group)
        assert response.status_code == 503, response.get_json()
        assert _counts(engine) == (0, 0, 0, 0, 0, 0, 0)
    finally:
        sa.event.remove(app_engine, "before_cursor_execute", fail_second)
    assert _stage(client, token, camp, group).status_code == 201
    assert _counts(engine) == (1, 27, 43, 0, 0, 0, 2)
