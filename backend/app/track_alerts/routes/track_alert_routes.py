#    backend\app\track_alerts\routes\track_alert_routes.py


from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from app.extensions import db

from app.track_alerts.services.track_alert_rules_service import (
    evaluate_track_alerts,
)
from app.track_alerts.services.track_alert_event_service import (
    generate_track_alert_events,
)
from app.models.warehouse import TrackAlertEventORM
from app.track_alerts.services.track_alert_email_renderer_service import (
    render_executive_alert_email,
)
from app.track_alerts.services.track_alert_delivery_service import (
    send_executive_track_alert_email,
)

track_alert_bp = Blueprint(
    "track_alerts",
    __name__,
    url_prefix="/api/track-alerts",
)


@track_alert_bp.route("/test", methods=["POST"])
def test_track_alerts():
    payload = request.get_json(silent=True) or {}

    track_date_raw = payload.get("track_date")
    generation_mode = payload.get("generation_mode", "manual_preview")

    if not track_date_raw:
        return jsonify(
            {
                "error": "track_date is required",
            }
        ), 400

    try:
        track_date = datetime.strptime(
            track_date_raw,
            "%Y-%m-%d",
        ).date()
    except ValueError:
        return jsonify(
            {
                "error": "Invalid track_date format. Use YYYY-MM-DD",
            }
        ), 400

    alerts = evaluate_track_alerts(
        track_date=track_date,
        generation_mode=generation_mode,
    )

    return jsonify(
        {
            "track_date": track_date.isoformat(),
            "generation_mode": generation_mode,
            "total_alerts": len(alerts),
            "items": [
                alert.to_dict()
                for alert in alerts
            ],
        }
    )
    
@track_alert_bp.route("/generate", methods=["POST"])
def generate_track_alerts():
    payload = request.get_json(silent=True) or {}

    track_date_raw = payload.get("track_date")
    generation_mode = payload.get("generation_mode", "manual_preview")
    replace_existing = bool(payload.get("replace_existing", True))

    if not track_date_raw:
        return jsonify(
            {
                "error": "track_date is required",
            }
        ), 400

    try:
        track_date = datetime.strptime(
            track_date_raw,
            "%Y-%m-%d",
        ).date()
    except ValueError:
        return jsonify(
            {
                "error": "Invalid track_date format. Use YYYY-MM-DD",
            }
        ), 400

    result = generate_track_alert_events(
        track_date=track_date,
        generation_mode=generation_mode,
        replace_existing=replace_existing,
    )

    return jsonify(result)

@track_alert_bp.route("/preview-email", methods=["GET"])
def preview_track_alert_email():
    track_date_raw = request.args.get("track_date")
    generation_mode = request.args.get(
        "generation_mode",
        "manual_preview",
    )

    if not track_date_raw:
        return jsonify(
            {
                "error": "track_date is required",
            }
        ), 400

    try:
        track_date = datetime.strptime(
            track_date_raw,
            "%Y-%m-%d",
        ).date()
    except ValueError:
        return jsonify(
            {
                "error": "Invalid track_date format. Use YYYY-MM-DD",
            }
        ), 400

    events = (
        db.session.query(TrackAlertEventORM)
        .filter(
            TrackAlertEventORM.track_date == track_date,
        )
        .all()
    )

    filtered_events = []

    for event in events:
        metadata = event.metadata_json or {}

        if metadata.get("generation_mode") == generation_mode:
            filtered_events.append(event)

    rendered = render_executive_alert_email(
        track_date=track_date.isoformat(),
        events=filtered_events,
    )

    return rendered["html"]

@track_alert_bp.route("/send-email", methods=["POST"])
def send_track_alert_email():
    payload = request.get_json(silent=True) or {}

    track_date_raw = payload.get("track_date")
    generation_mode = payload.get("generation_mode", "manual_preview")
    to_list = payload.get("to_list") or []
    only_unsent = bool(payload.get("only_unsent", True))

    if not track_date_raw:
        return jsonify(
            {
                "error": "track_date is required",
            }
        ), 400

    if not isinstance(to_list, list) or not to_list:
        return jsonify(
            {
                "error": "to_list is required and must be a non-empty array",
            }
        ), 400

    try:
        track_date = datetime.strptime(
            track_date_raw,
            "%Y-%m-%d",
        ).date()
    except ValueError:
        return jsonify(
            {
                "error": "Invalid track_date format. Use YYYY-MM-DD",
            }
        ), 400

    result = send_executive_track_alert_email(
        track_date=track_date,
        generation_mode=generation_mode,
        to_list=to_list,
        only_unsent=only_unsent,
    )

    return jsonify(result)