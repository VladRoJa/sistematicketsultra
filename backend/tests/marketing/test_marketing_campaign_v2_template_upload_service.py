import json
import os
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token
from sqlalchemy import Column, Integer, MetaData, Table, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.models.iventas_template_upload import IventasTemplateUploadORM
from app.models.marketing import MarketingCampaignV2TemplateORM
from app.routes import marketing_campaign_v2_routes as routes
from app.services import marketing_campaign_v2_template_upload_service as service
from app.services.marketing_access import MarketingAuthorizationError


@pytest.fixture
def session(monkeypatch):
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    IventasTemplateUploadORM.__table__.to_metadata(metadata)
    catalog = MarketingCampaignV2TemplateORM.__table__.to_metadata(metadata)
    catalog.c.id.type = Integer()
    metadata.create_all(engine)
    targets = [
        {"sucursal_id": number, "sucursal_canon": f"BRANCH_{number}", "provider_channel_id": f"channel-{number}",
         "is_default": True}
        for number in (1, 2)
    ]
    monkeypatch.setattr(service, "list_channel_bindings", lambda **_: targets)
    with Session(engine) as value:
        yield value
    engine.dispose()


def _request(**overrides):
    return {"name": "asistencia_demo", "category": "UTILITY", "message": "Hola, Ana. Entrena con nosotros.",
            "fields": [{"start": 6, "end": 9}], "buttons": ["Me interesa"], "branch_ids": [1, 2],
            **overrides}


def test_queue_records_each_branch_and_discards_image_after_last_result(session):
    upload = service.create_upload(_request(), BytesIO(b"\x89PNG\r\n\x1a\nsynthetic"), actor_id=47, session=session)
    upload_id = upload.id
    first = service.claim_next_branch(session)
    assert first[1]["sucursal_id"] == 1
    assert first[2]["fields"][0]["example"] == "Ana"
    assert first[4] == "image/png"
    assert service.claim_next_branch(session) is None
    service.finish_branch(session, upload_id, 1, "EXISTS", "Ya existe")
    second = service.claim_next_branch(session)
    assert second[1]["sucursal_id"] == 2
    service.finish_branch(session, upload_id, 2, "SUBMITTED")
    history = service.upload_history(session=session)[0]
    assert history["status"] == service.FINISHED
    assert history["requested_by_user_id"] == 47
    assert [branch["status"] for branch in history["branches"]] == ["EXISTS", "SUBMITTED"]
    assert "image" not in history
    assert session.get(IventasTemplateUploadORM, upload_id).image is None


def test_recover_interruption_preserves_other_branches(session):
    upload = service.create_upload(_request(), None, actor_id=47, session=session)
    upload_id = upload.id
    assert service.claim_next_branch(session)[0] == upload_id
    service.recover_interrupted_uploads(session)
    assert service.claim_next_branch(session)[1]["sucursal_id"] == 2
    service.finish_branch(session, upload_id, 2, "ERROR")
    assert [branch["status"] for branch in service.upload_history(session=session)[0]["branches"]] == [
        "VERIFY", "ERROR",
    ]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"branch_ids": [3]}, "canal de iVentas"),
        ({"message": "Hola, Ana!"}, "después del último campo"),
        ({"category": []}, "Marketing o Utilidad"),
        ({"buttons": ["a", "b", "c", "d"]}, "hasta 3 botones"),
    ],
)
def test_rejects_invalid_request_before_creating_job(session, overrides, message):
    with pytest.raises(service.TemplateUploadError, match=message):
        service.create_upload(_request(**overrides), None, actor_id=47, session=session)
    assert not service.upload_history(session=session)


def test_marks_exact_occurrence_using_browser_offsets():
    template = service.validate_template(_request(
        message="💪 Ana saluda a Ana hoy.",
        fields=[{"start": 16, "end": 19}],
    ))
    assert template["fields"] == [{"start": 16, "end": 19, "example": "Ana"}]


def test_http_protects_upload_and_only_queues_for_admin(session, monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="fake-secret-for-local-test-long-enough")
    JWTManager(app)
    app.register_blueprint(routes.marketing_campaign_v2_bp, url_prefix="/api/marketing")
    with app.app_context():
        auth = {"Authorization": f"Bearer {create_access_token(identity='47')}"}
    client = app.test_client()
    url = "/api/marketing/campaigns-v2/dispatch/template-uploads"
    assert client.get(url).status_code == 401

    def denied():
        raise MarketingAuthorizationError("Acceso restringido.")

    monkeypatch.setattr(routes, "_resolve_campaign_v2_dispatch_config_request", denied)
    assert client.post(url, headers=auth).status_code == 403
    monkeypatch.setattr(
        routes, "_resolve_campaign_v2_dispatch_config_request", lambda: (SimpleNamespace(id=47), None),
    )
    assert client.post(url, headers=auth).status_code == 409
    monkeypatch.setenv("IVENTAS_TEMPLATE_UPLOAD_ENABLED", "true")
    monkeypatch.setattr(routes, "create_upload", lambda payload, image, actor_id: service.create_upload(
        payload, image, actor_id=actor_id, session=session,
    ))
    response = client.post(url, data={"template": json.dumps(_request())}, headers=auth)
    assert response.status_code == 201
    assert response.get_json()["status"] == service.QUEUED


def test_worker_processes_two_separate_account_logins(session, monkeypatch):
    from sqlalchemy.orm import scoped_session, sessionmaker
    from app.rpa.workers import iventas_template_upload_worker as worker
    from app.services.marketing_campaign_v2_template_credentials_service import IventasTemplateCredentials

    worker_session = scoped_session(sessionmaker(bind=session.get_bind()))
    monkeypatch.setattr(worker, "db", SimpleNamespace(session=worker_session))
    logins = {
        1: IventasTemplateCredentials("first@example.test", "example-one"),
        2: IventasTemplateCredentials("second@example.test", "example-two"),
    }
    monkeypatch.setattr(worker, "load_iventas_template_credentials", lambda: logins)
    monkeypatch.setattr(
        worker, "resolve_dispatch_channel_binding",
        lambda sucursal_id: SimpleNamespace(provider_channel_id=f"channel-{sucursal_id}"),
    )
    processed = []

    def upload(browser, login, template, image, image_type):
        assert template["name"] == "asistencia_demo"
        processed.append(login)
        if login is logins[1]:
            return "ERROR", "Cuenta no confirmada."
        return "SUBMITTED", "Estado en iVentas: En revisión."

    monkeypatch.setattr(worker, "upload_template", upload)
    service.create_upload(_request(), None, actor_id=47, session=session)
    assert worker._run_one(object())
    assert worker._run_one(object())
    assert not worker._run_one(object())
    worker_session.remove()

    assert processed == list(logins.values())
    result = service.upload_history(session=session)[0]
    assert [branch["status"] for branch in result["branches"]] == ["ERROR", "SUBMITTED"]


def test_catalog_publishes_channels_individually_after_approval(session, monkeypatch):
    monkeypatch.setattr(service, "resolve_dispatch_channel_binding",
                        lambda sucursal_id, **_: SimpleNamespace(provider_channel_id=f"channel-{sucursal_id}"))
    upload_id = service.create_upload(_request(
        catalog={"purpose": "ACTIVE_MEMBERS", "sources": ["first_name"]},
    ), None, actor_id=47, session=session).id
    for branch_id in (1, 2):
        assert service.claim_next_branch(session)[1]["sucursal_id"] == branch_id
        service.finish_branch(session, upload_id, branch_id, service.IN_REVIEW)
    assert session.query(MarketingCampaignV2TemplateORM).count() == 0

    now = datetime.now(timezone.utc) + timedelta(seconds=1)
    assert service.claim_due_review(session, now=now)[1]["sucursal_id"] == 1
    service.finish_review(session, upload_id, 1, service.IN_REVIEW, "Pendiente")
    assert service.claim_due_review(session, now=now)[1]["sucursal_id"] == 2
    service.finish_review(session, upload_id, 2, service.APPROVED, "Aprobada por iVentas")

    row = session.query(MarketingCampaignV2TemplateORM).one()
    assert row.is_active
    assert row.compatible_channel_ids_json == ["channel-2"]
    assert row.variables_json == {"1": "first_name"}
    assert row.purposes_json == ["ACTIVE_MEMBERS"]
    assert service.claim_due_review(session, now=now) is None

    assert service.claim_due_review(session, now=now + service.REVIEW_INTERVAL)[1]["sucursal_id"] == 1
    service.finish_review(session, upload_id, 1, service.APPROVED, "Aprobada por iVentas")
    assert row.compatible_channel_ids_json == ["channel-1", "channel-2"]
    assert service.claim_due_review(session, now=now + 2 * service.REVIEW_INTERVAL) is None


def test_changed_channel_cannot_publish_catalog_entry(session, monkeypatch):
    monkeypatch.setattr(service, "resolve_dispatch_channel_binding",
                        lambda **_: SimpleNamespace(provider_channel_id="new-channel"))
    upload_id = service.create_upload(_request(
        branch_ids=[1], catalog={"purpose": "ACTIVE_MEMBERS", "sources": ["first_name"]},
    ), None, actor_id=47, session=session).id
    service.claim_next_branch(session)
    service.finish_branch(session, upload_id, 1, service.IN_REVIEW)
    service.claim_due_review(session)
    service.finish_review(session, upload_id, 1, service.APPROVED, "Aprobada por iVentas")
    assert session.query(MarketingCampaignV2TemplateORM).count() == 0
    assert service.upload_history(session=session)[0]["branches"][0]["status"] == "VERIFY"


def test_catalog_requires_source_for_each_field_and_send_url_for_an_image(session):
    with pytest.raises(service.TemplateUploadError, match="cada campo"):
        service.create_upload(_request(
            catalog={"purpose": "ACTIVE_MEMBERS", "sources": []},
        ), None, actor_id=47, session=session)
    with pytest.raises(service.TemplateUploadError, match="URL HTTPS"):
        service.create_upload(_request(
            catalog={"purpose": "ACTIVE_MEMBERS", "sources": ["first_name"]},
        ), BytesIO(b"\x89PNG\r\n\x1a\nsynthetic"), actor_id=47, session=session)


def test_same_name_cannot_queue_different_content(session):
    catalog = {"purpose": "ACTIVE_MEMBERS", "sources": ["first_name"]}
    service.create_upload(_request(catalog=catalog), None, actor_id=47, session=session)
    with pytest.raises(service.TemplateUploadError, match="contenido distinto"):
        service.create_upload(_request(
            message="Hola, Ana. Regresa a entrenar.", catalog=catalog,
        ), None, actor_id=47, session=session)


def test_postgres_upgrade_preserves_catalog_and_upload_history():
    url = os.getenv("QUOTA_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("isolated PostgreSQL quota_ci required")
    parts = make_url(url)
    if (parts.get_backend_name() != "postgresql" or parts.host not in {"127.0.0.1", "localhost"}
            or parts.database != "quota_ci" or parts.username != "quota_ci"):
        pytest.fail("Refusing a non-synthetic database")
    scripts = ScriptDirectory(str(Path(__file__).resolve().parents[2] / "migrations"))
    migration = scripts.get_revision("i21c11202601").module
    assert migration.down_revision == "i20c11202601"

    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TEMP TABLE marketing_campaign_v2_templates (id bigint PRIMARY KEY) ON COMMIT DROP",
            )
            connection.exec_driver_sql(
                "CREATE TEMP TABLE marketing_iventas_template_uploads (id integer PRIMARY KEY) ON COMMIT DROP",
            )
            connection.exec_driver_sql("INSERT INTO marketing_campaign_v2_templates VALUES (101)")
            connection.exec_driver_sql("INSERT INTO marketing_iventas_template_uploads VALUES (202)")
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                assert connection.exec_driver_sql(
                    "SELECT upload_fingerprint FROM marketing_campaign_v2_templates WHERE id = 101",
                ).one() == (None,)
                assert connection.exec_driver_sql(
                    "SELECT next_review_at FROM marketing_iventas_template_uploads WHERE id = 202",
                ).one() == (None,)
                assert connection.exec_driver_sql(
                    "SELECT to_regclass('ix_marketing_iventas_template_uploads_next_review_at') IS NOT NULL",
                ).scalar_one()
                migration.downgrade()
            assert connection.exec_driver_sql("SELECT * FROM marketing_campaign_v2_templates").one() == (101,)
            assert connection.exec_driver_sql("SELECT * FROM marketing_iventas_template_uploads").one() == (202,)
    finally:
        engine.dispose()
