"""M6 paired RAW stage: actual PostgreSQL 16, Flask JWT, Warehouse FS and audits.

This test REFUSES any non-dedicated local CI database. Real create_warehouse_
document_upload performs its own commits, so the test owns separate ephemeral
tables and disk directory and removes both in teardown. No production data.
Only frozen *historical* XLSX lookups are replaced by synthetic fixtures.
"""
from __future__ import annotations

from datetime import date
from hashlib import sha256
from io import BytesIO
from pathlib import Path

import pytest
import sqlalchemy as sa
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.extensions import db
from app.models.warehouse import (
    WarehouseAuditLogORM, WarehouseFamilyORM, WarehouseOperationalRoleORM,
    WarehouseOperatorORM, WarehouseReportTypeORM, WarehouseSourceORM,
    WarehouseUploadORM,
)
from app.routes.google_ads_m6_continuity_routes import google_ads_m6_continuity_bp
from app.warehouse.services import google_ads_m6_manual_preview_service as preview_svc
from app.warehouse.services import google_ads_m6_manual_confirm_service as confirm_svc
from app.warehouse.services.warehouse_document_upload_service import (
    create_warehouse_document_upload,
)
from test_google_ads_m6_continuity_postgres import _test_engine
from test_google_ads_m6_manual_preview import (
    DAY, daily_xlsx, post as preview_post,
)
from test_google_ads_m6_authenticated_postgres import _synthetic_pair


@pytest.fixture
def real_warehouse(tmp_path, monkeypatch):
    engine = _test_engine()
    with engine.connect() as conn:
        assert conn.execute(sa.text("SHOW server_version")).scalar_one().startswith("16.")

    # Flask/Warehouse storage writes under project/uploads/... , never checkout.
    root = tmp_path / "project" / "backend" / "app"
    root.mkdir(parents=True)
    app = Flask("m6_raw_real_postgres_test", root_path=str(root))
    app.config.update(
        TESTING=True, SECRET_KEY="m6-raw-ci-signature-only",
        JWT_SECRET_KEY="m6-raw-ci-jwt-only",
        SQLALCHEMY_DATABASE_URI=str(engine.url),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    JWTManager(app)
    app.register_blueprint(
        google_ads_m6_continuity_bp,
        url_prefix="/api/integrations/google-ads",
    )

    schema = sa.MetaData()
    users = sa.Table(
        "users", schema,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.Text, nullable=False),
        sa.Column("rol", sa.Text, nullable=False),
    )
    sa.Table("track_daily_versions", schema, sa.Column("id", sa.Integer, primary_key=True))
    tables = [
        WarehouseSourceORM, WarehouseFamilyORM, WarehouseOperationalRoleORM,
        WarehouseReportTypeORM, WarehouseUploadORM, WarehouseOperatorORM,
        WarehouseAuditLogORM,
    ]
    for orm in tables:
        orm.__table__.to_metadata(schema)
    with engine.begin() as conn:
        for name in schema.tables:
            assert not sa.inspect(conn).has_table(name), (
                f"Isolation violation: pre-existing table {name}"
            )
        schema.create_all(conn)
        conn.execute(users.insert(), [
            {"id": 47, "username": "admicorp", "rol": "ADMINISTRADOR"},
            {"id": 48, "username": "operator", "rol": "ADMINISTRADOR"},
        ])
        conn.execute(schema.tables["warehouse_sources"].insert(), {
            "id": 1, "key": "google_ads", "label": "Google Ads CI", "active": True,
        })
        conn.execute(schema.tables["warehouse_families"].insert(), {
            "id": 1, "key": "ads", "label": "Ads CI", "active": True,
        })
        conn.execute(schema.tables["warehouse_operational_roles"].insert(), {
            "id": 1, "key": "ads_operator", "label": "Ads CI", "active": True,
        })
        conn.execute(schema.tables["warehouse_report_types"].insert(), [
            {
                "id": index, "key": kind, "label": kind,
                "family_id": 1, "default_source_id": 1,
                "default_operational_role_id": 1,
                "default_period_type": "rango", "active": True,
            }
            for index, kind in enumerate(confirm_svc.REPORT_TYPES, start=1)
        ])
        conn.execute(schema.tables["warehouse_operators"].insert(), {
            "id": 1, "user_id": 47,
            "can_upload": True, "can_view": True, "can_archive": False,
        })

    # Frozen reference only; production filesystem and data must never be read.
    baseline_campaign, baseline_group = _synthetic_pair()
    reference_day = min(row.report_date for row in baseline_group.rows)
    groups = [row for row in baseline_group.rows
              if row.report_date == reference_day]
    assert len(groups) == 43
    manifest = {
        "id": "GOOGLE_ADS_M5_IDENTITY_20261012_V1",
        "customer_id": "2739125201",
        "rows": [
            [r.campaign_name, r.ad_group_name, r.campaign_key,
             r.ad_group_key, f"LAB_BRANCH_{i}", i + 1, "0"]
            for i, r in enumerate(groups[:26])
        ],
    }
    monkeypatch.setattr(
        preview_svc, "_load_files",
        lambda: (baseline_campaign, baseline_group),
    )
    monkeypatch.setattr(preview_svc, "_load_m5", lambda: manifest)
    # October 13 is closed in local timezone; no dependence on CI wall clock.
    from types import SimpleNamespace
    monkeypatch.setattr(
        preview_svc, "datetime",
        SimpleNamespace(now=lambda tz: SimpleNamespace(
            date=lambda: date(2026, 10, 14))),
    )

    try:
        with app.app_context():
            token = create_access_token(identity="47")
            other_token = create_access_token(identity="48")
            yield app.test_client(), token, other_token, engine, tmp_path / "project"
            db.session.remove()
    finally:
        with app.app_context():
            db.session.remove()
        with engine.begin() as conn:
            schema.drop_all(conn)
        engine.dispose()


def _confirm(client, token, ticket, files):
    campaign, group = files
    return client.post(
        "/api/integrations/google-ads/manual/confirm",
        headers={"Authorization": f"Bearer {token}"} if token else {},
        data={
            "campaign": (BytesIO(campaign), "campaign.xlsx"),
            "ad_group": (BytesIO(group), "ad_group.xlsx"),
            "confirmation_ticket": ticket,
        },
        content_type="multipart/form-data",
    )


def _snapshot(engine):
    with engine.connect() as conn:
        uploads = conn.execute(sa.text("""
            SELECT u.id, u.status, rt.key AS report_type_key,
                   u.date_from, u.date_to, u.file_hash_sha256,
                   u.stored_filename, u.stored_path, u.uploaded_by_user_id
            FROM warehouse_uploads u
            JOIN warehouse_report_types rt ON rt.id = u.report_type_id
            ORDER BY u.id
        """)).mappings().all()
        actions = conn.execute(sa.text("""
            SELECT action, upload_id, performed_by_user_id, details
            FROM warehouse_audit_logs ORDER BY id
        """)).mappings().all()
        return [dict(u) for u in uploads], [dict(a) for a in actions]


def test_real_fs_postgres_raw_pair_audit_idempotence_and_permissions(real_warehouse):
    client, token, other, engine, storage_root = real_warehouse
    files = daily_xlsx()
    response = preview_post(client, token, files=files)
    assert response.status_code == 200, response.get_json()
    ticket = response.json["raw_confirm_ticket"]
    # Permission checks are real in DB, not mocking JWT or Warehouse allowlist.
    assert _confirm(client, None, ticket, files).status_code == 401
    assert _confirm(client, other, ticket, files).status_code == 403
    assert _snapshot(engine) == ([], [])

    result = _confirm(client, token, ticket, files)
    assert result.status_code == 201, result.get_json()
    assert result.json["status"] == "RAW_PAIR_STAGED"
    assert result.json["eligible_for_publication"] is False
    assert result.json["eligible_for_structured_ingestion"] is False
    raw, audit = _snapshot(engine)
    assert len(raw) == len(audit) == 2
    assert {x["action"] for x in audit} == {"UPLOAD"}
    assert {x["performed_by_user_id"] for x in audit} == {47}
    for name, content in zip(confirm_svc.REPORT_TYPES, files):
        one = next(x for x in raw if x["report_type_key"] == name)
        assert one["status"] == "ACTIVE"
        assert one["date_from"] == one["date_to"] == DAY
        assert one["file_hash_sha256"] == sha256(content).hexdigest()
        assert one["uploaded_by_user_id"] == 47
        absolute = storage_root / one["stored_path"] / one["stored_filename"]
        assert absolute.is_file()
        assert absolute.read_bytes() == content
        one_audit = next(x for x in audit if x["upload_id"] == one["id"])
        assert one_audit["details"]["publication"] == "NOT_AUTHORIZED"
        assert one_audit["details"]["upload_origin"] == "google_ads_manual_pair"

    retry = _confirm(client, token, ticket, files)
    assert retry.status_code == 200, retry.get_json()
    assert all(x["reused_existing"] for x in retry.json["uploads"].values())
    assert _snapshot(engine) == (raw, audit), (
        "Identical replay must not create a third file, row or audit"
    )


def test_real_partial_raw_then_safe_resume(real_warehouse, monkeypatch):
    client, token, other, engine, storage_root = real_warehouse
    files = daily_xlsx()
    preview = preview_post(client, token, files=files)
    assert preview.status_code == 200, preview.get_json()
    ticket = preview.json["raw_confirm_ticket"]

    def fail_only_group(*, report_type_key, **kwargs):
        if report_type_key == "google_ads_ad_group_daily":
            raise RuntimeError("Synthetic second RAW filesystem failure")
        return create_warehouse_document_upload(
            report_type_key=report_type_key, **kwargs,
        )

    monkeypatch.setattr(confirm_svc, "create_warehouse_document_upload",
                        fail_only_group)
    partial = _confirm(client, token, ticket, files)
    assert partial.status_code == 409, partial.get_json()
    assert partial.json["status"] == "PARTIAL_RAW"
    first, audit = _snapshot(engine)
    assert len(first) == len(audit) == 1
    assert first[0]["report_type_key"] == "google_ads_campaign_daily"
    physical = storage_root / first[0]["stored_path"] / first[0]["stored_filename"]
    assert physical.read_bytes() == files[0]

    monkeypatch.setattr(confirm_svc, "create_warehouse_document_upload",
                        create_warehouse_document_upload)
    result = _confirm(client, token, ticket, files)
    assert result.status_code == 201, result.get_json()
    assert result.json["status"] == "RAW_PAIR_STAGED"
    assert result.json["uploads"]["google_ads_campaign_daily"]["reused_existing"]
    assert not result.json["uploads"]["google_ads_ad_group_daily"]["reused_existing"]
    raw, audits = _snapshot(engine)
    assert len(raw) == len(audits) == 2
    assert physical.read_bytes() == files[0]
