from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PIL import Image

from app.services.system_daily_check_attachment_service import (
    cleanup_system_daily_check_attachments,
    create_system_daily_check_issue_attachment,
    validate_system_daily_check_attachment,
)
from app.services.system_daily_check_attachment_storage_service import (
    resolve_system_daily_check_attachment_path,
    validate_system_daily_check_attachment_storage_key,
)
from app.services.system_daily_check_service import (
    SystemDailyCheckValidationError,
)


def _png_bytes() -> bytes:
    output = BytesIO()
    image = Image.new("RGB", (4, 4), (255, 255, 255))
    image.save(output, format="PNG")
    return output.getvalue()


def test_validate_png_detects_real_format_and_hash():
    validated = validate_system_daily_check_attachment(
        content=_png_bytes(),
        original_filename="evidencia.png",
        declared_mime_type="image/png",
    )

    assert validated.mime_type == "image/png"
    assert validated.extension == ".png"
    assert validated.size_bytes > 0
    assert len(validated.sha256) == 64


def test_validate_pdf_requires_matching_extension_and_eof():
    valid_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF"
    validated = validate_system_daily_check_attachment(
        content=valid_pdf,
        original_filename="evidencia.pdf",
        declared_mime_type="application/pdf",
    )
    assert validated.mime_type == "application/pdf"
    assert validated.extension == ".pdf"

    with pytest.raises(SystemDailyCheckValidationError, match="extensión"):
        validate_system_daily_check_attachment(
            content=valid_pdf,
            original_filename="evidencia.jpg",
            declared_mime_type="image/jpeg",
        )

    with pytest.raises(SystemDailyCheckValidationError, match="incompleto"):
        validate_system_daily_check_attachment(
            content=b"%PDF-1.4\nmissing eof",
            original_filename="evidencia.pdf",
            declared_mime_type="application/pdf",
        )


def test_storage_key_rejects_traversal_and_foreign_prefix():
    with pytest.raises(ValueError):
        validate_system_daily_check_attachment_storage_key(
            "../../etc/passwd"
        )
    with pytest.raises(ValueError):
        validate_system_daily_check_attachment_storage_key(
            "purchase-requisitions/1/file.pdf"
        )


def test_create_attachment_writes_inside_isolated_root_and_cleanup(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "SYSTEM_DAILY_CHECK_ATTACHMENT_DIR",
        str(tmp_path),
    )
    issue = SimpleNamespace(id=77)
    actor = SimpleNamespace(id=9)
    session = MagicMock()
    session.get.return_value = issue

    attachment, storage_key = (
        create_system_daily_check_issue_attachment(
            issue_id=77,
            content=_png_bytes(),
            original_filename="foto.png",
            declared_mime_type="image/png",
            actor=actor,
            session=session,
        )
    )

    assert attachment.issue_id == 77
    assert attachment.uploaded_by_user_id == 9
    assert attachment.mime_type == "image/png"
    assert attachment.storage_key == storage_key
    assert storage_key.startswith(
        "system-daily-checks/issues/77/"
    )

    path = resolve_system_daily_check_attachment_path(storage_key)
    assert path.is_file()
    assert tmp_path.resolve() in path.parents
    assert path.read_bytes() == _png_bytes()

    cleanup_system_daily_check_attachments([storage_key])
    assert not path.exists()


def test_create_attachment_rejects_missing_issue(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "SYSTEM_DAILY_CHECK_ATTACHMENT_DIR",
        str(tmp_path),
    )
    session = MagicMock()
    session.get.return_value = None

    with pytest.raises(LookupError, match="no encontrada"):
        create_system_daily_check_issue_attachment(
            issue_id=88,
            content=_png_bytes(),
            original_filename="foto.png",
            declared_mime_type="image/png",
            actor=SimpleNamespace(id=9),
            session=session,
        )

    assert list(tmp_path.rglob("*")) == []
