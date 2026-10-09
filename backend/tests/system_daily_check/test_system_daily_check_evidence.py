from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token
from werkzeug.datastructures import FileStorage

from app.routes import system_daily_check_routes as routes
from app.services.system_daily_check_attachment_service import (
    validate_system_daily_check_attachment,
)
from app.services.system_daily_check_attachment_storage_service import (
    build_system_daily_check_attachment_storage_key,
    resolve_system_daily_check_attachment_path,
    validate_system_daily_check_attachment_storage_key,
    write_system_daily_check_attachment_bytes,
)


def _png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (2, 2)).save(output, format="PNG")
    return output.getvalue()


def test_validate_attachment_accepts_real_png_and_pdf():
    png = validate_system_daily_check_attachment(
        content=_png_bytes(),
        original_filename="evidencia.png",
        declared_mime_type="image/png",
    )
    assert png.mime_type == "image/png"
    assert png.extension == ".png"
    assert len(png.sha256) == 64

    pdf = validate_system_daily_check_attachment(
        content=b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF",
        original_filename="evidencia.pdf",
        declared_mime_type="application/pdf",
    )
    assert pdf.mime_type == "application/pdf"
    assert pdf.extension == ".pdf"


@pytest.mark.parametrize(
    ("filename", "mime"),
    [
        ("evidencia.jpg", "image/jpeg"),
        ("evidencia.exe", "application/octet-stream"),
    ],
)
def test_validate_attachment_rejects_mismatched_or_unsupported_content(
    filename,
    mime,
):
    with pytest.raises(routes.SystemDailyCheckValidationError):
        validate_system_daily_check_attachment(
            content=_png_bytes(),
            original_filename=filename,
            declared_mime_type=mime,
        )


def test_storage_key_is_issue_scoped_and_cannot_escape_root(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "SYSTEM_DAILY_CHECK_ATTACHMENT_DIR",
        str(tmp_path),
    )
    storage_key = build_system_daily_check_attachment_storage_key(
        15,
        ".png",
    )
    assert storage_key.startswith(
        "system-daily-checks/issues/15/"
    )
    assert validate_system_daily_check_attachment_storage_key(
        storage_key
    ) == storage_key

    path = write_system_daily_check_attachment_bytes(
        storage_key,
        b"abc",
    )
    assert path.read_bytes() == b"abc"
    assert tmp_path.resolve() in path.parents

    with pytest.raises(ValueError):
        resolve_system_daily_check_attachment_path(
            "system-daily-checks/issues/15/../../escape.png"
        )


class TestMultipartSubmit:
    def setup_method(self):
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            JWT_SECRET_KEY="m2-evidence-routes-test",
        )
        JWTManager(self.app)
        self.app.register_blueprint(
            routes.system_daily_check_bp,
            url_prefix="/api/system-daily-checks",
        )
        self.actor = SimpleNamespace(
            id=20,
            username="SISTEMAS",
            rol="SISTEMAS",
            sucursal_id=10,
        )

    def _token(self):
        with self.app.app_context():
            return create_access_token(identity=str(self.actor.id))

    def _client(self):
        return self.app.test_client()

    def _multipart(self, *, evidence_key="GASCA_WORKING"):
        import json

        payload = {
            "answers": [
                {
                    "question_key": "GASCA_WORKING",
                    "answer": "NO",
                    "issue": {
                        "reported_to_support": True,
                        "description": "Gasca no abre.",
                    },
                }
            ],
            "general_status": "MINOR_FAILURE",
        }
        return {
            "payload": json.dumps(payload),
            f"evidence__{evidence_key}": (
                io.BytesIO(_png_bytes()),
                "gasca.png",
            ),
        }

    def test_multipart_submit_attaches_file_to_matching_no_issue(self):
        issue = SimpleNamespace(id=301, attachments=[])
        answer = SimpleNamespace(
            question_key="GASCA_WORKING",
            issue=issue,
        )
        check = SimpleNamespace(
            id=44,
            sucursal_id=10,
            business_date=__import__("datetime").date(2026, 10, 9),
            performed_by_user_id=self.actor.id,
            general_status="MINOR_FAILURE",
            submitted_at=__import__("datetime").datetime(
                2026,
                10,
                9,
                16,
                0,
                tzinfo=__import__("datetime").timezone.utc,
            ),
            answers=[answer],
        )
        attachment = SimpleNamespace(id=501)

        with (
            patch.object(
                routes.UserORM,
                "get_by_id",
                return_value=self.actor,
            ),
            patch.object(
                routes,
                "submit_today",
                return_value=check,
            ),
            patch.object(
                routes,
                "create_system_daily_check_issue_attachment",
                return_value=(
                    attachment,
                    "system-daily-checks/issues/301/a.png",
                ),
            ) as create_attachment,
            patch.object(routes.db.session, "commit") as commit,
            patch.object(routes.db.session, "rollback") as rollback,
        ):
            response = self._client().post(
                "/api/system-daily-checks/today/submit?sucursal_id=10",
                data=self._multipart(),
                headers={
                    "Authorization": f"Bearer {self._token()}"
                },
                content_type="multipart/form-data",
            )

        assert response.status_code == 201
        create_attachment.assert_called_once()
        kwargs = create_attachment.call_args.kwargs
        assert kwargs["issue_id"] == 301
        assert kwargs["actor"] is self.actor
        assert kwargs["original_filename"] == "gasca.png"
        assert kwargs["declared_mime_type"] == "image/png"
        assert issue.attachments == [attachment]
        commit.assert_called_once_with()
        rollback.assert_not_called()

    def test_evidence_for_yes_or_unknown_issue_rolls_back_without_commit(self):
        check = SimpleNamespace(
            id=44,
            sucursal_id=10,
            business_date=__import__("datetime").date(2026, 10, 9),
            performed_by_user_id=self.actor.id,
            general_status="NORMAL",
            submitted_at=__import__("datetime").datetime(
                2026,
                10,
                9,
                16,
                0,
                tzinfo=__import__("datetime").timezone.utc,
            ),
            answers=[
                SimpleNamespace(
                    question_key="GASCA_WORKING",
                    issue=None,
                )
            ],
        )

        with (
            patch.object(
                routes.UserORM,
                "get_by_id",
                return_value=self.actor,
            ),
            patch.object(
                routes,
                "submit_today",
                return_value=check,
            ),
            patch.object(
                routes,
                "create_system_daily_check_issue_attachment",
            ) as create_attachment,
            patch.object(routes.db.session, "commit") as commit,
            patch.object(routes.db.session, "rollback") as rollback,
            patch.object(
                routes,
                "cleanup_system_daily_check_attachments",
            ) as cleanup,
        ):
            response = self._client().post(
                "/api/system-daily-checks/today/submit",
                data=self._multipart(),
                headers={
                    "Authorization": f"Bearer {self._token()}"
                },
                content_type="multipart/form-data",
            )

        assert response.status_code == 400
        assert response.get_json()["code"] == (
            "SYSTEM_DAILY_CHECK_VALIDATION_ERROR"
        )
        create_attachment.assert_not_called()
        commit.assert_not_called()
        rollback.assert_called_once_with()
        cleanup.assert_called_once_with([])

    def test_cleanup_runs_when_second_file_fails_after_first_was_written(self):
        issue = SimpleNamespace(id=301, attachments=[])
        check = SimpleNamespace(
            id=44,
            sucursal_id=10,
            business_date=__import__("datetime").date(2026, 10, 9),
            performed_by_user_id=self.actor.id,
            general_status="MINOR_FAILURE",
            submitted_at=__import__("datetime").datetime(
                2026,
                10,
                9,
                16,
                0,
                tzinfo=__import__("datetime").timezone.utc,
            ),
            answers=[
                SimpleNamespace(
                    question_key="GASCA_WORKING",
                    issue=issue,
                )
            ],
        )
        import json

        payload = {
            "answers": [
                {
                    "question_key": "GASCA_WORKING",
                    "answer": "NO",
                    "issue": {
                        "reported_to_support": True,
                        "description": "Gasca no abre.",
                    },
                }
            ],
            "general_status": "MINOR_FAILURE",
        }
        data = {
            "payload": json.dumps(payload),
            "evidence__GASCA_WORKING": [
                (io.BytesIO(_png_bytes()), "uno.png"),
                (io.BytesIO(_png_bytes()), "dos.png"),
            ],
        }
        first_attachment = SimpleNamespace(id=501)

        with (
            patch.object(
                routes.UserORM,
                "get_by_id",
                return_value=self.actor,
            ),
            patch.object(
                routes,
                "submit_today",
                return_value=check,
            ),
            patch.object(
                routes,
                "create_system_daily_check_issue_attachment",
                side_effect=[
                    (
                        first_attachment,
                        "system-daily-checks/issues/301/uno.png",
                    ),
                    RuntimeError("storage failed"),
                ],
            ),
            patch.object(routes.db.session, "commit") as commit,
            patch.object(routes.db.session, "rollback") as rollback,
            patch.object(
                routes,
                "cleanup_system_daily_check_attachments",
            ) as cleanup,
        ):
            response = self._client().post(
                "/api/system-daily-checks/today/submit",
                data=data,
                headers={
                    "Authorization": f"Bearer {self._token()}"
                },
                content_type="multipart/form-data",
            )

        assert response.status_code == 500
        commit.assert_not_called()
        rollback.assert_called_once_with()
        cleanup.assert_called_once_with([
            "system-daily-checks/issues/301/uno.png"
        ])
