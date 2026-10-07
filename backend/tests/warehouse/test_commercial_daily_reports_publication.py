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
    monkeypatch.setattr(job.InternalDocumentVisibilityORM, "query", FakeVisibilityQuery(rules))
    with pytest.raises(job.CommercialDailyPublicationError):
        job._validate_exclusive_access(doc, 7)


def test_accept_exact_one_admicorp_user_rule(monkeypatch):
    doc = SimpleNamespace(id=3, visibility_mode="CUSTOM", is_sensitive=True)
    rules = [SimpleNamespace(visibility_type="USER", user_id=7)]
    monkeypatch.setattr(job.InternalDocumentVisibilityORM, "query", FakeVisibilityQuery(rules))
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
