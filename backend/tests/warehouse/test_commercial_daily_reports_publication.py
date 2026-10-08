from types import SimpleNamespace

import pytest

from app.warehouse.jobs import commercial_daily_reports_job as job


class FakeVisibilityQuery:
    def __init__(self, rules):
        self.rules = rules

    def filter_by(self, **kwargs):
        return self

    def all(self):
        return self.rules


def test_reject_global_existing_document(monkeypatch):
    doc = SimpleNamespace(id=3, visibility_mode="GLOBAL", is_sensitive=True)
    with pytest.raises(job.CommercialDailyPublicationError):
        job._validate_exclusive_access(doc, 7)


def test_reject_other_user_rule(monkeypatch):
    doc = SimpleNamespace(id=3, visibility_mode="CUSTOM", is_sensitive=True)
    rules = [SimpleNamespace(visibility_type="USER", user_id=8)]
    monkeypatch.setattr(job, "InternalDocumentVisibilityORM", SimpleNamespace(query=FakeVisibilityQuery(rules)))
    with pytest.raises(job.CommercialDailyPublicationError):
        job._validate_exclusive_access(doc, 7)


def test_accept_exact_one_admicorp_user_rule(monkeypatch):
    doc = SimpleNamespace(id=3, visibility_mode="CUSTOM", is_sensitive=True)
    rules = [SimpleNamespace(visibility_type="USER", user_id=7)]
    monkeypatch.setattr(job, "InternalDocumentVisibilityORM", SimpleNamespace(query=FakeVisibilityQuery(rules)))
    job._validate_exclusive_access(doc, 7)


def test_retry_safe_two_metrics(monkeypatch):
    monkeypatch.setattr(job, "_resolve_users", lambda: (11, 7))
    calls = []
    def fake_publish(*, metric, cutoff, automation_id, admicorp_id):
        calls.append((metric, cutoff, automation_id, admicorp_id))
        return {"metric": metric}
    monkeypatch.setattr(job, "_publish_one", fake_publish)
    from datetime import date
    result = job.run_job(business_date=date(2026, 10, 6))
    assert [call[0] for call in calls] == ["venta_nueva", "reactivaciones"]
    assert all(call[3] == 7 for call in calls)
    assert len(result["reports"]) == 2


def _xlsx_bytes(value, modified=None):
    from io import BytesIO
    from datetime import datetime
    from openpyxl import Workbook

    book = Workbook()
    book.active["A1"] = value
    if modified is not None:
        book.properties.modified = datetime(2026, 10, modified)
    output = BytesIO()
    book.save(output)
    return output.getvalue()


def test_cutoff_version_label_gets_new_revision_instead_of_duplicate():
    from datetime import date

    existing = [
        SimpleNamespace(version_label="2026-10-07"),
        SimpleNamespace(version_label="2026-10-07-r2"),
        SimpleNamespace(version_label="2026-10-06"),
    ]
    assert job._next_cutoff_version_label(
        cutoff=date(2026, 10, 7), versions=existing
    ) == "2026-10-07-r3"
    assert job._next_cutoff_version_label(
        cutoff=date(2026, 10, 8), versions=existing
    ) == "2026-10-08"


def test_logical_fingerprint_ignores_core_metadata_but_detects_changes():
    a = _xlsx_bytes(12, modified=1)
    b = _xlsx_bytes(12, modified=2)
    c = _xlsx_bytes(13, modified=2)

    assert job._report_content_fingerprint(a) == job._report_content_fingerprint(b)
    assert job._report_content_fingerprint(a) != job._report_content_fingerprint(c)


class FakeDocumentQuery:
    def __init__(self, doc):
        self.doc = doc

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def first(self):
        return self.doc


def _setup_existing_doc(monkeypatch, *, cutoff_label="2026-10-07"):
    current = SimpleNamespace(
        id=12, version_label=cutoff_label,
        warehouse_upload_id=123, file_hash_sha256="old",
    )
    doc = SimpleNamespace(
        id=2917,
        current_version=current,
        versions=[current],
        visibility_mode="CUSTOM",
        is_sensitive=True,
    )
    monkeypatch.setattr(
        job, "InternalDocumentORM",
        SimpleNamespace(
            query=FakeDocumentQuery(doc), title="title",
            status="status", id=SimpleNamespace(asc=lambda: "id"),
        ),
    )
    monkeypatch.setattr(job, "_validate_exclusive_access", lambda d, u: None)
    monkeypatch.setattr(
        job,
        "build_commercial_daily_xlsx",
        lambda **kwargs: _xlsx_bytes(20),
    )
    return doc


def test_same_day_correction_creates_revision_without_replacing_history(monkeypatch):
    from datetime import date

    doc = _setup_existing_doc(monkeypatch)
    monkeypatch.setattr(job, "_existing_report_is_equivalent", lambda d, p: False)
    uploads = []
    labels = []

    def upload(**kwargs):
        uploads.append(kwargs)
        return {"warehouse_upload_id": 456}

    def publish(**kwargs):
        labels.append(kwargs)
        return {"created": True, "version_label": kwargs["version_label"]}

    monkeypatch.setattr(job, "create_warehouse_document_upload", upload)
    monkeypatch.setattr(job, "add_internal_document_version_from_warehouse_upload", publish)
    result = job._publish_one(
        metric="reactivaciones",
        cutoff=date(2026, 10, 7),
        automation_id=47,
        admicorp_id=48,
    )

    assert len(uploads) == 1
    assert labels[0]["document_id"] == 2917
    assert labels[0]["version_label"] == "2026-10-07-r2"
    assert result["publication"]["version_label"] == "2026-10-07-r2"
    assert doc.current_version.version_label == "2026-10-07"


def test_identical_report_is_noop_before_warehouse_upload(monkeypatch):
    from datetime import date

    _setup_existing_doc(monkeypatch)
    monkeypatch.setattr(job, "_existing_report_is_equivalent", lambda d, p: True)

    def should_not_upload(**kwargs):
        raise AssertionError("No second upload for an equivalent report")

    monkeypatch.setattr(job, "create_warehouse_document_upload", should_not_upload)
    result = job._publish_one(
        metric="reactivaciones",
        cutoff=date(2026, 10, 7),
        automation_id=47,
        admicorp_id=48,
    )
    assert result["warehouse_upload_id"] == 123
    assert result["publication"]["created"] is False


def test_older_cutoff_cannot_replace_newer_document(monkeypatch):
    from datetime import date

    _setup_existing_doc(monkeypatch, cutoff_label="2026-10-08")
    with pytest.raises(job.CommercialDailyPublicationError, match="newer report"):
        job._publish_one(
            metric="reactivaciones",
            cutoff=date(2026, 10, 7),
            automation_id=47,
            admicorp_id=48,
        )
