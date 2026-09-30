from types import SimpleNamespace

from app.warehouse.jobs import agregadoras_consolidado_publisher as publisher


def _make_xlsx(tmp_path):
    path = tmp_path / "agregadoras.xlsx"
    path.write_bytes(b"xlsx-test")
    return path


def test_publish_agregadoras_creates_document_first_time(
    monkeypatch,
    tmp_path,
):
    file_path = _make_xlsx(tmp_path)
    upload_calls = []
    publication_calls = []

    monkeypatch.setattr(
        publisher,
        "_resolve_automation_user_id",
        lambda: 7,
    )
    monkeypatch.setattr(
        publisher,
        "_find_existing_document",
        lambda: None,
    )
    monkeypatch.setattr(
        publisher,
        "_resolve_admicorp_user_id",
        lambda: 77,
    )

    def fake_upload(**kwargs):
        upload_calls.append(kwargs)
        return {
            "warehouse_upload_id": 55,
            "upload_id": 55,
        }

    def fake_publish(**kwargs):
        publication_calls.append(kwargs)
        return {
            "created": True,
            "document_id": 99,
            "version_id": 100,
        }

    monkeypatch.setattr(
        publisher,
        "create_warehouse_document_upload",
        fake_upload,
    )
    monkeypatch.setattr(
        publisher,
        "publish_internal_document_from_warehouse_upload",
        fake_publish,
    )

    result = publisher.publish_agregadoras_consolidado_output(
        file_path=file_path,
        cutoff_date="2026-09-28",
        download_filename="Agregadoras 1 enero - 28 septiembre 2026.xlsx",
    )

    assert result["action"] == "document_created"
    assert result["warehouse_upload_id"] == 55

    assert upload_calls[0]["report_type_key"] == "agregadoras_consolidado"
    assert upload_calls[0]["cutoff_date"].isoformat() == "2026-09-28"
    assert upload_calls[0]["uploaded_by_user_id"] == 7

    publication = publication_calls[0]
    assert publication["title"] == "Consolidado de agregadoras"
    assert publication["warehouse_upload_id"] == 55
    assert publication["publish_now"] is True
    assert publication["is_sensitive"] is True
    assert publication["visibility_mode"] == "CUSTOM"
    assert publication["visibility_rules"] == [
        {
            "visibility_type": "USER",
            "user_id": 77,
            "can_view": True,
            "can_download": True,
        }
    ]
    assert publication["version_label"] == "2026-09-28"


def test_publish_agregadoras_adds_version_to_existing_document(
    monkeypatch,
    tmp_path,
):
    file_path = _make_xlsx(tmp_path)
    version_calls = []

    monkeypatch.setattr(
        publisher,
        "_resolve_automation_user_id",
        lambda: 7,
    )
    monkeypatch.setattr(
        publisher,
        "_find_existing_document",
        lambda: SimpleNamespace(id=88),
    )
    monkeypatch.setattr(
        publisher,
        "_resolve_admicorp_user_id",
        lambda: 77,
    )
    monkeypatch.setattr(
        publisher,
        "create_warehouse_document_upload",
        lambda **_kwargs: {"warehouse_upload_id": 56},
    )

    def fake_add_version(**kwargs):
        version_calls.append(kwargs)
        return {
            "created": True,
            "document_id": 88,
            "version_id": 101,
        }

    monkeypatch.setattr(
        publisher,
        "add_internal_document_version_from_warehouse_upload",
        fake_add_version,
    )

    result = publisher.publish_agregadoras_consolidado_output(
        file_path=file_path,
        cutoff_date="2026-09-29",
    )

    assert result["action"] == "version_created"
    assert result["document_id"] == 88
    assert result["warehouse_upload_id"] == 56

    version = version_calls[0]
    assert version["document_id"] == 88
    assert version["warehouse_upload_id"] == 56
    assert version["created_by_user_id"] == 7
    assert version["version_label"] == "2026-09-29"


def test_publish_agregadoras_is_idempotent_for_same_upload(
    monkeypatch,
    tmp_path,
):
    file_path = _make_xlsx(tmp_path)

    monkeypatch.setattr(
        publisher,
        "_resolve_automation_user_id",
        lambda: 7,
    )
    monkeypatch.setattr(
        publisher,
        "_find_existing_document",
        lambda: SimpleNamespace(id=88),
    )
    monkeypatch.setattr(
        publisher,
        "_resolve_admicorp_user_id",
        lambda: 77,
    )
    monkeypatch.setattr(
        publisher,
        "create_warehouse_document_upload",
        lambda **_kwargs: {"warehouse_upload_id": 56},
    )
    monkeypatch.setattr(
        publisher,
        "add_internal_document_version_from_warehouse_upload",
        lambda **_kwargs: {
            "created": False,
            "document_id": 88,
            "version_id": 101,
        },
    )

    result = publisher.publish_agregadoras_consolidado_output(
        file_path=file_path,
        cutoff_date="2026-09-29",
    )

    assert result["action"] == "already_published"
    assert result["document_id"] == 88
    assert result["warehouse_upload_id"] == 56
