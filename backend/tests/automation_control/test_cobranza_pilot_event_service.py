"""Read-only event: generated, queued, blocked, completed; never PII."""
from types import SimpleNamespace as NS
from unittest.mock import Mock

from app.services.automation_control import cobranza_pilot_event_service as svc


def _fake_session(monkeypatch, *, meta, job=None, submitted=False):
    campaign = NS(
        id=106, name="COBRANZA RECURRENTE RECHAZADOS - 2026-11-12",
        audience_definition_json={"source_metadata": meta},
    )
    child = NS(
        recipient_count=21, status="SUBMITTED" if submitted else "READY",
        provider_campaign_id="synthetic-provider-id" if submitted else None,
    )
    query_campaign = Mock()
    query_campaign.filter.return_value = query_campaign
    query_campaign.order_by.return_value = query_campaign
    query_campaign.limit.return_value = query_campaign
    query_campaign.all.return_value = [campaign]
    query_job = Mock()
    query_job.filter.return_value = query_job
    query_job.order_by.return_value = query_job
    query_job.first.return_value = job
    query_child = Mock()
    query_child.filter.return_value = query_child
    query_child.all.return_value = [child]
    query_recipient = Mock()
    query_recipient.filter.return_value = query_recipient
    query_recipient.count.return_value = 21
    session = Mock()
    session.query.side_effect = [query_campaign, query_job, query_child, query_recipient]
    monkeypatch.setattr(svc.db, "session", session)
    return session


def _metadata():
    return {
        "automation_job": "cobranza_recurrente_rechazados",
        "pilot_branch_key": "VILLAS_DEL_REY",
        "auto_pilot_date": "2026-11-12",
    }


def test_generated_event_is_not_delivery(monkeypatch):
    _fake_session(monkeypatch, meta=_metadata())
    result = svc.read_cobranza_pilot_event()
    assert result["stage"] == "PREPARED"
    assert result["recipient_count"] == 21
    assert result["accepted_count"] == 0
    assert "phone" not in repr(result).lower()


def test_finished_event_distinguishes_provider_acceptance(monkeypatch):
    _fake_session(monkeypatch, meta=_metadata(), job=NS(status="COMPLETED"), submitted=True)
    result = svc.read_cobranza_pilot_event()
    assert result["stage"] == "COMPLETED"
    assert result["accepted_count"] == 21


def test_blocked_event_is_visible(monkeypatch):
    metadata = _metadata()
    metadata["auto_pilot_blocked"] = True
    _fake_session(monkeypatch, meta=metadata)
    assert svc.read_cobranza_pilot_event()["stage"] == "AUTO_SEND_BLOCKED"


def test_unmarked_campaign_not_displayed(monkeypatch):
    metadata = _metadata()
    metadata.pop("auto_pilot_date")
    _fake_session(monkeypatch, meta=metadata)
    assert svc.read_cobranza_pilot_event() is None
