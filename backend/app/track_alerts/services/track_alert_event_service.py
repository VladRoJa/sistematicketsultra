#   backend\app\track_alerts\services\track_alert_event_service.py


from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from app.extensions import db
from app.models.warehouse import TrackAlertEventORM
from app.track_alerts.services.track_alert_rules_service import (
    TrackAlertCandidate,
    evaluate_track_alerts,
)


def generate_track_alert_events(
    track_date: date,
    generation_mode: str = "manual_preview",
    replace_existing: bool = True,
) -> dict[str, Any]:
    candidates = evaluate_track_alerts(
        track_date=track_date,
        generation_mode=generation_mode,
    )

    if replace_existing:
        _delete_existing_events(
            track_date=track_date,
            generation_mode=generation_mode,
        )

    events = [
        _candidate_to_event(candidate)
        for candidate in candidates
    ]

    if events:
        db.session.add_all(events)

    db.session.commit()

    return {
        "track_date": track_date.isoformat(),
        "generation_mode": generation_mode,
        "replace_existing": replace_existing,
        "created_events": len(events),
        "items": [
            _event_to_dict(event)
            for event in events
        ],
    }


def _delete_existing_events(
    track_date: date,
    generation_mode: str,
) -> None:
    existing_events = (
        db.session.query(TrackAlertEventORM)
        .filter(
            TrackAlertEventORM.track_date == track_date,
        )
        .all()
    )

    for event in existing_events:
        metadata = event.metadata_json or {}
        if metadata.get("generation_mode") == generation_mode:
            db.session.delete(event)

    db.session.flush()
def _candidate_to_event(
    candidate: TrackAlertCandidate,
) -> TrackAlertEventORM:
    return TrackAlertEventORM(
        track_date=candidate.track_date,
        sucursal_canon=candidate.sucursal_canon,
        alert_code=candidate.alert_code,
        severity=candidate.severity,
        title=candidate.title,
        message=candidate.message,
        metric_value=candidate.metric_value,
        threshold_value=candidate.threshold_value,
        ranking_position=candidate.ranking_position,
        was_sent=False,
        metadata_json=candidate.metadata_json or {},
    )


def _event_to_dict(event: TrackAlertEventORM) -> dict[str, Any]:
    return {
        "id": event.id,
        "track_date": event.track_date.isoformat() if event.track_date else None,
        "sucursal_canon": event.sucursal_canon,
        "alert_code": event.alert_code,
        "severity": event.severity,
        "title": event.title,
        "message": event.message,
        "metric_value": _decimal_to_str(event.metric_value),
        "threshold_value": _decimal_to_str(event.threshold_value),
        "ranking_position": event.ranking_position,
        "was_sent": event.was_sent,
        "sent_at": event.sent_at.isoformat() if event.sent_at else None,
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "metadata_json": event.metadata_json or {},
    }


def _decimal_to_str(value: Decimal | None) -> str | None:
    if value is None:
        return None

    return str(value)