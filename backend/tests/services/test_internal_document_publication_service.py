from types import SimpleNamespace

from app.internal_documents.services import (
    internal_document_publication_service as service,
)


class _FakeQuery:
    def __init__(self, first_value):
        self.first_value = first_value

    def filter_by(self, **_kwargs):
        return self

    def first(self):
        return self.first_value


class _FakeScalarQuery:
    def __init__(self, value):
        self.value = value

    def filter(self, *_args):
        return self

    def scalar(self):
        return self.value


class _FakeSession:
    def __init__(self, max_version):
        self.max_version = max_version
        self.added = []
        self.commits = 0

    def query(self, *_args):
        return _FakeScalarQuery(self.max_version)

    def add(self, item):
        self.added.append(item)

    def flush(self):
        for item in self.added:
            if getattr(item, "id", None) is None:
                item.id = 99

    def commit(self):
        self.commits += 1


class _FakeVersion:
    version_number = 0
    document_id = 0
    query = _FakeQuery(None)

    def __init__(self, **kwargs):
        self.id = None
        for key, value in kwargs.items():
            setattr(self, key, value)


def test_add_internal_document_version_replaces_current(monkeypatch):
    current_version = SimpleNamespace(
        is_current=True,
        is_hidden_from_users=False,
    )
    document = SimpleNamespace(
        id=10,
        current_version_id=5,
        current_version=current_version,
        updated_by=None,
    )
    upload = SimpleNamespace(
        id=20,
        original_filename="Agregadoras.xlsx",
        mime_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        file_size_bytes=1234,
        file_hash_sha256="abc123",
    )
    fake_session = _FakeSession(max_version=3)
    audit_calls = []

    fake_document_model = SimpleNamespace(
        query=_FakeQuery(document),
    )
    fake_version_model = _FakeVersion
    fake_version_model.query = _FakeQuery(None)

    monkeypatch.setattr(service, "InternalDocumentORM", fake_document_model)
    monkeypatch.setattr(
        service,
        "InternalDocumentVersionORM",
        fake_version_model,
    )
    monkeypatch.setattr(
        service,
        "_resolve_warehouse_upload",
        lambda _upload_id: upload,
    )
    monkeypatch.setattr(
        service,
        "_log_document_audit",
        lambda **kwargs: audit_calls.append(kwargs),
    )
    monkeypatch.setattr(
        service,
        "db",
        SimpleNamespace(
            session=fake_session,
            func=SimpleNamespace(max=lambda value: value),
        ),
    )

    result = service.add_internal_document_version_from_warehouse_upload(
        document_id=10,
        warehouse_upload_id=20,
        created_by_user_id=7,
        version_label="2026-09-28",
        change_notes="Corte automático 2026-09-28.",
        audit_metadata={"origin": "agregadoras_auto"},
    )

    assert result["created"] is True
    assert result["version_number"] == 4
    assert result["version_label"] == "2026-09-28"
    assert current_version.is_current is False
    assert current_version.is_hidden_from_users is True
    assert document.current_version_id == 99
    assert document.updated_by == 7
    assert fake_session.commits == 1
    assert len(fake_session.added) == 1
    assert audit_calls[0]["action"] == "DOCUMENT_VERSION_REPLACED"


def test_add_internal_document_version_is_idempotent_by_upload(monkeypatch):
    document = SimpleNamespace(
        id=10,
        current_version_id=8,
        current_version=None,
        updated_by=None,
    )
    existing_version = SimpleNamespace(
        id=8,
        version_number=2,
        version_label="2026-09-28",
    )
    upload = SimpleNamespace(id=20)
    fake_session = _FakeSession(max_version=2)

    fake_document_model = SimpleNamespace(
        query=_FakeQuery(document),
    )
    fake_version_model = _FakeVersion
    fake_version_model.query = _FakeQuery(existing_version)

    monkeypatch.setattr(service, "InternalDocumentORM", fake_document_model)
    monkeypatch.setattr(
        service,
        "InternalDocumentVersionORM",
        fake_version_model,
    )
    monkeypatch.setattr(
        service,
        "_resolve_warehouse_upload",
        lambda _upload_id: upload,
    )
    monkeypatch.setattr(
        service,
        "db",
        SimpleNamespace(
            session=fake_session,
            func=SimpleNamespace(max=lambda value: value),
        ),
    )

    result = service.add_internal_document_version_from_warehouse_upload(
        document_id=10,
        warehouse_upload_id=20,
        created_by_user_id=7,
    )

    assert result["created"] is False
    assert result["version_id"] == 8
    assert result["version_number"] == 2
    assert fake_session.added == []
    assert fake_session.commits == 0
