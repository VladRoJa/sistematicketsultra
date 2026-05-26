#   backend\app\track_alerts\services\track_alert_delivery_service.py


from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from app.extensions import db
from app.models.warehouse import TrackAlertEventORM
from app.track_alerts.services.track_alert_email_renderer_service import (
    render_executive_alert_email,
)
from app.utils.email_sender import send_email_html
from app.track_alerts.services.track_alert_region_rules_service import (
    evaluate_regional_rankings,
)
from app.track_alerts.services.track_alert_region_email_renderer_service import (
    render_regional_executive_email,
)


def send_executive_track_alert_email(
    *,
    track_date: date,
    generation_mode: str = "manual_preview",
    to_list: list[str],
    only_unsent: bool = True,
) -> dict[str, Any]:
    if not to_list:
        raise RuntimeError("No se recibieron destinatarios para alertas Track.")

    events = _get_events_for_delivery(
        track_date=track_date,
        generation_mode=generation_mode,
        only_unsent=only_unsent,
    )

    if not events:
        return {
            "track_date": track_date.isoformat(),
            "generation_mode": generation_mode,
            "sent": False,
            "reason": "No hay alertas pendientes para enviar.",
            "total_events": 0,
            "recipients": to_list,
        }

    rendered = render_executive_alert_email(
        track_date=track_date.isoformat(),
        events=events,
    )

    send_email_html(
        to_list=to_list,
        subject=rendered["subject"],
        html=rendered["html"],
    )

    sent_at = datetime.now(timezone.utc)

    for event in events:
        event.was_sent = True
        event.sent_at = sent_at

    db.session.commit()

    return {
        "track_date": track_date.isoformat(),
        "generation_mode": generation_mode,
        "sent": True,
        "subject": rendered["subject"],
        "total_events": len(events),
        "recipients": to_list,
        "sent_at": sent_at.isoformat(),
    }

def send_regional_executive_track_alert_email(
    *,
    track_date: date,
    generation_mode: str = "manual_preview",
    to_list: list[str],
) -> dict[str, Any]:
    if not to_list:
        raise RuntimeError("No se recibieron destinatarios para alertas regionales Track.")

    rankings = evaluate_regional_rankings(
        track_date=track_date,
        generation_mode=generation_mode,
    )

    income_compliance_ranking = rankings["income_compliance_ranking"]
    income_ranking = rankings["income_ranking"]
    new_clients_ranking = rankings["new_clients_ranking"]

    if not income_compliance_ranking:
        return {
            "track_date": track_date.isoformat(),
            "generation_mode": generation_mode,
            "sent": False,
            "reason": "No hay ranking regional disponible para enviar.",
            "total_regions": 0,
            "recipients": to_list,
        }

    rendered = render_regional_executive_email(
        track_date=track_date.isoformat(),
        income_compliance_ranking=income_compliance_ranking,
        income_ranking=income_ranking,
        new_clients_ranking=new_clients_ranking,
        generation_mode=generation_mode,
    )

    send_email_html(
        to_list=to_list,
        subject=rendered["subject"],
        html=rendered["html"],
    )

    sent_at = datetime.now(timezone.utc)

    return {
        "track_date": track_date.isoformat(),
        "generation_mode": generation_mode,
        "sent": True,
        "subject": rendered["subject"],
        "total_regions": rendered["total_regions"],
        "recipients": to_list,
        "sent_at": sent_at.isoformat(),
    }

def _get_events_for_delivery(
    *,
    track_date: date,
    generation_mode: str,
    only_unsent: bool,
) -> list[TrackAlertEventORM]:
    query = (
        db.session.query(TrackAlertEventORM)
        .filter(
            TrackAlertEventORM.track_date == track_date,
        )
        .order_by(
            TrackAlertEventORM.severity.asc(),
            TrackAlertEventORM.ranking_position.asc(),
            TrackAlertEventORM.id.asc(),
        )
    )

    if only_unsent:
        query = query.filter(
            TrackAlertEventORM.was_sent.is_(False),
        )

    events = query.all()

    filtered_events: list[TrackAlertEventORM] = []

    for event in events:
        metadata = event.metadata_json or {}

        if metadata.get("generation_mode") == generation_mode:
            filtered_events.append(event)

    return filtered_events