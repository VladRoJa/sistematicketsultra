from __future__ import annotations

import io
import json
from datetime import date, datetime, timedelta, timezone

from flask import Flask
from flask_jwt_extended import JWTManager
from PIL import Image
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models.sucursal_model import Sucursal
from app.models.system_daily_check import (
    SystemDailyCheckAnswerORM,
    SystemDailyCheckIssueAttachmentORM,
    SystemDailyCheckIssueORM,
    SystemDailyCheckORM,
    SystemDailyCheckPromptStateORM,
    SystemDailyCheckRolloutBranchORM,
)
from app.models.user_model import UserORM, usuario_sucursal
from app.routes.auth_routes import auth_bp
from app.routes.system_daily_check_bi_routes import system_daily_check_bi_bp
from app.routes.system_daily_check_routes import system_daily_check_bp
from app.services.system_daily_check_service import QUESTIONS


def _png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (3, 3)).save(output, format="PNG")
    return output.getvalue()


def _payload() -> dict:
    answers = []
    for question in QUESTIONS:
        row = {
            "question_key": question.key,
            "answer": (
                "NO"
                if question.key == "GASCA_WORKING"
                else "YES"
            ),
        }
        if question.key == "GASCA_WORKING":
            row["issue"] = {
                "reported_to_support": True,
                "description": "Gasca no abre.",
            }
        answers.append(row)

    return {
        "answers": answers,
        "general_status": "MINOR_FAILURE",
    }


def _app():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="m3-integral-secret",
        JWT_SECRET_KEY="m3-integral-jwt",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    JWTManager(app)
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(
        system_daily_check_bp,
        url_prefix="/api/system-daily-checks",
    )
    app.register_blueprint(
        system_daily_check_bi_bp,
        url_prefix="/api/system-daily-checks/bi",
    )
    return app


def test_integral_v1_flow_login_to_bi_drilldown(
    monkeypatch,
    tmp_path,
):
    app = _app()
    t0 = datetime(2026, 10, 9, 16, 0, tzinfo=timezone.utc)
    business_date = date(2026, 10, 9)
    monkeypatch.setenv(
        "SYSTEM_DAILY_CHECK_ATTACHMENT_DIR",
        str(tmp_path / "evidence"),
    )

    with app.app_context():
        db.metadata.create_all(
            db.engine,
            tables=[
                Sucursal.__table__,
                UserORM.__table__,
                usuario_sucursal,
                SystemDailyCheckORM.__table__,
                SystemDailyCheckAnswerORM.__table__,
                SystemDailyCheckIssueORM.__table__,
                SystemDailyCheckIssueAttachmentORM.__table__,
                SystemDailyCheckPromptStateORM.__table__,
                SystemDailyCheckRolloutBranchORM.__table__,
            ],
        )

        db.session.add(
            Sucursal(
                sucursal_id=10,
                serie="T10",
                sucursal="PILOTO",
                estado="BC",
                operational_status="ACTIVA",
                is_demo=False,
                municipio="MEXICALI",
                direccion="N/A",
            )
        )
        db.session.add(
            UserORM(
                id=1,
                username="sistemas",
                password=generate_password_hash("secret"),
                rol="SISTEMAS",
                sucursal_id=10,
                department_id=1,
            )
        )
        db.session.flush()
        db.session.add(
            SystemDailyCheckRolloutBranchORM(
                sucursal_id=10,
                enabled_from=business_date,
                configured_by_user_id=1,
            )
        )
        db.session.commit()

    client = app.test_client()
    login = client.post(
        "/api/auth/login",
        json={
            "username": "sistemas",
            "password": "secret",
        },
    )
    assert login.status_code == 200
    token = login.get_json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    import app.services.system_daily_check_service as daily_service

    current_time = {"value": t0}

    def _fixed_utc_now(now=None):
        value = now or current_time["value"]
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    monkeypatch.setattr(
        daily_service,
        "_utc_now",
        _fixed_utc_now,
    )

    initial = client.get(
        "/api/system-daily-checks/today/status",
        headers=headers,
    )
    assert initial.status_code == 200
    assert initial.get_json()["postpone_count"] == 0
    assert initial.get_json()["can_postpone"] is True

    first = client.post(
        "/api/system-daily-checks/today/postpone",
        headers=headers,
    )
    assert first.status_code == 200
    assert first.get_json()["postpone_count"] == 1

    current_time["value"] = t0 + timedelta(minutes=5)
    second = client.post(
        "/api/system-daily-checks/today/postpone",
        headers=headers,
    )
    assert second.status_code == 200
    assert second.get_json()["postpone_count"] == 2

    current_time["value"] = t0 + timedelta(minutes=10)
    mandatory = client.get(
        "/api/system-daily-checks/today/status",
        headers=headers,
    )
    assert mandatory.status_code == 200
    assert mandatory.get_json()["mandatory"] is True
    assert mandatory.get_json()["can_postpone"] is False

    submitted = client.post(
        "/api/system-daily-checks/today/submit",
        query_string={"sucursal_id": 10},
        data={
            "payload": json.dumps(_payload()),
            "evidence__GASCA_WORKING": (
                io.BytesIO(_png_bytes()),
                "gasca.png",
            ),
        },
        headers=headers,
        content_type="multipart/form-data",
    )
    assert submitted.status_code == 201
    check_id = submitted.get_json()["id"]

    current_time["value"] = t0 + timedelta(minutes=10, seconds=1)
    released = client.get(
        "/api/system-daily-checks/today/status",
        headers=headers,
    )
    assert released.status_code == 200
    assert released.get_json()["completed"] is True
    assert released.get_json()["should_prompt"] is False

    history = client.get(
        "/api/system-daily-checks/bi/history",
        query_string={
            "date_from": business_date.isoformat(),
            "date_to": business_date.isoformat(),
            "answer": "NO",
        },
        headers=headers,
    )
    assert history.status_code == 200
    assert history.get_json()["total"] == 1
    assert history.get_json()["items"][0]["id"] == check_id

    summary = client.get(
        "/api/system-daily-checks/bi/summary",
        query_string={
            "date_from": business_date.isoformat(),
            "date_to": business_date.isoformat(),
        },
        headers=headers,
    )
    assert summary.status_code == 200
    summary_payload = summary.get_json()
    assert summary_payload["universe"]["expected_checklists"] == 1
    assert summary_payload["summary"]["completed"] == 1
    assert summary_payload["summary"]["pending"] == 0
    assert summary_payload["failures"]["no_answers"] == 1
    assert summary_payload["failures"]["reported"] == 1
    assert summary_payload["postponements"]["completed_after_2"] == 1
    assert summary_payload["postponements"]["reached_mandatory"] == 1

    issues = client.get(
        "/api/system-daily-checks/bi/issues",
        query_string={
            "date_from": business_date.isoformat(),
            "date_to": business_date.isoformat(),
            "reported_to_support": "true",
        },
        headers=headers,
    )
    assert issues.status_code == 200
    assert issues.get_json()["total"] == 1
    assert issues.get_json()["items"][0]["check_id"] == check_id

    detail = client.get(
        f"/api/system-daily-checks/bi/checks/{check_id}",
        headers=headers,
    )
    assert detail.status_code == 200
    detail_payload = detail.get_json()
    gasca = next(
        answer
        for answer in detail_payload["answers"]
        if answer["question_key"] == "GASCA_WORKING"
    )
    assert gasca["answer"] == "NO"
    assert gasca["issue"]["reported_to_support"] is True
    assert len(gasca["issue"]["attachments"]) == 1
    assert gasca["issue"]["attachments"][0][
        "original_filename"
    ] == "gasca.png"

    with app.app_context():
        db.session.remove()
