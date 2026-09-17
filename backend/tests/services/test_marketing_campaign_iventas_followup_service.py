from datetime import date, datetime, timezone
from types import SimpleNamespace as NS

from app.services import marketing_campaign_iventas_followup_service as service


UTC = timezone.utc


def _contact(
    *,
    row_id: int,
    contact_id: str,
    phone: str,
    outbound: datetime | None,
    status: str = "viewed",
):
    return NS(
        id=row_id,
        contact_id=contact_id,
        phone_mx10=phone,
        branch_code="azahares",
        name="Contacto iVentas",
        created_at_utc=datetime(2026, 9, 3, 18, 0, tzinfo=UTC),
        created_at_local=datetime(2026, 9, 3, 11, 0),
        first_message_at_utc=datetime(2026, 9, 3, 18, 1, tzinfo=UTC),
        first_message_at_local=datetime(2026, 9, 3, 11, 1),
        last_outbound_message_at_utc=outbound,
        last_message_status=status,
        channel_name="Ultra Gym Azahares",
        channel_platform="WHATSAPP",
        agent_json={"id": "agent-1", "name": "Gerencia AZAHARES"},
        is_from_ads=False,
        ads_source_id=None,
    )


def test_activity_after_send_is_observational_time_comparison():
    assert service._activity_after_send(
        last_outbound=datetime(2026, 9, 14, 18, 0, tzinfo=UTC),
        sent_at="2026-09-14T17:15:00+00:00",
    ) is True
    assert service._activity_after_send(
        last_outbound=datetime(2026, 9, 14, 16, 0, tzinfo=UTC),
        sent_at="2026-09-14T17:15:00+00:00",
    ) is False
    assert service._activity_after_send(
        last_outbound=None,
        sent_at="2026-09-14T17:15:00+00:00",
    ) is None


def test_enrichment_exposes_latest_canonical_iventas_context(monkeypatch):
    run = NS(
        id=126,
        period_key="IVENTAS-2026-09",
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 16),
        finished_at=datetime(2026, 9, 17, 3, 43, 28, tzinfo=UTC),
    )
    recent = _contact(
        row_id=501,
        contact_id="recent",
        phone="6671009463",
        outbound=datetime(2026, 9, 16, 21, 50, tzinfo=UTC),
        status="viewed",
    )
    older = _contact(
        row_id=500,
        contact_id="older",
        phone="6671009463",
        outbound=datetime(2026, 9, 9, 22, 0, tzinfo=UTC),
        status="delivered",
    )

    monkeypatch.setattr(
        service,
        "_recipient_phones",
        lambda **kwargs: {10: "6671009463", 11: "6679999999"},
    )
    monkeypatch.setattr(service, "_latest_canonical_run", lambda **kwargs: run)
    monkeypatch.setattr(
        service,
        "_contacts_by_phone",
        lambda **kwargs: {"6671009463": [recent, older]},
    )
    monkeypatch.setattr(
        service,
        "_tags_by_contact_row",
        lambda **kwargs: {501: ["Reasignada"]},
    )

    payload = {
        "rows": [
            {
                "recipient_id": 10,
                "sent_at": "2026-09-14T17:15:00+00:00",
            },
            {
                "recipient_id": 11,
                "sent_at": "2026-09-14T17:15:00+00:00",
            },
        ]
    }

    result = service.enrich_campaign_outcome_detail_with_iventas(
        payload,
        session=object(),
    )

    assert result["iventas_source"] == {
        "available": True,
        "sync_run_id": 126,
        "period_key": "IVENTAS-2026-09",
        "date_from": "2026-09-01",
        "date_to": "2026-09-16",
        "finished_at": "2026-09-17T03:43:28+00:00",
    }

    matched = result["rows"][0]
    assert matched["phone_mx10"] == "6671009463"
    assert matched["iventas_contact_found"] is True
    assert matched["iventas_match_status"] == "MULTIPLE"
    assert matched["iventas_match_count"] == 2
    assert matched["iventas_contact_id"] == "recent"
    assert matched["iventas_last_message_status"] == "viewed"
    assert matched["iventas_agent_name"] == "Gerencia AZAHARES"
    assert matched["iventas_tags"] == ["Reasignada"]
    assert matched["iventas_activity_after_send"] is True
    assert matched["iventas_last_outbound_at_local"] == "2026-09-16T14:50:00"

    missing = result["rows"][1]
    assert missing["phone_mx10"] == "6679999999"
    assert missing["iventas_contact_found"] is False
    assert missing["iventas_match_status"] == "NOT_FOUND"
    assert missing["iventas_tags"] == []


def test_enrichment_is_safe_when_no_canonical_run(monkeypatch):
    monkeypatch.setattr(
        service,
        "_recipient_phones",
        lambda **kwargs: {10: "6671009463"},
    )
    monkeypatch.setattr(service, "_latest_canonical_run", lambda **kwargs: None)

    result = service.enrich_campaign_outcome_detail_with_iventas(
        {"rows": [{"recipient_id": 10, "sent_at": None}]},
        session=object(),
    )

    assert result["iventas_source"]["available"] is False
    assert result["rows"][0]["iventas_contact_found"] is False
    assert result["rows"][0]["iventas_match_status"] == "NOT_FOUND"
