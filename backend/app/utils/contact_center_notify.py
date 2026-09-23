from __future__ import annotations

import html
import threading
from datetime import timezone
from zoneinfo import ZoneInfo

from flask import current_app
from sqlalchemy import func

from app.extensions import db
from app.models.contact_center import (
    ContactCenterAppointmentORM,
    ContactCenterNotificationORM,
)
from app.models.user_model import UserORM
from app.utils.email_sender import send_email_html


BUSINESS_TZ = ZoneInfo("America/Tijuana")


def _branch_manager_emails(sucursal_id: int) -> list[str]:
    rows = (
        UserORM.query
        .filter(
            UserORM.sucursal_id == sucursal_id,
            func.lower(UserORM.rol) == "gerente",
        )
        .all()
    )
    result: list[str] = []
    seen: set[str] = set()
    for row in rows:
        email = str(row.email or "").strip()
        key = email.casefold()
        if email and "@" in email and key not in seen:
            seen.add(key)
            result.append(email)
    return result


def _render_appointment_html(appointment: ContactCenterAppointmentORM) -> str:
    local_at = appointment.scheduled_at.astimezone(BUSINESS_TZ)
    contact = appointment.contact
    branch = appointment.sucursal
    case = appointment.case
    agent = UserORM.get_by_id(appointment.created_by_user_id)

    fields = [
        ("Contacto", contact.display_name or "Sin nombre"),
        ("Teléfono", contact.phone_mx10 or contact.primary_phone_raw),
        ("Sucursal", branch.sucursal if branch else str(appointment.sucursal_id)),
        ("Fecha", local_at.strftime("%d/%m/%Y")),
        ("Hora", local_at.strftime("%H:%M")),
        ("Origen", case.source_type),
        ("Agente", agent.username if agent else "Suite Ultra"),
        ("Comentario", appointment.notes or "Sin comentario"),
    ]

    rows = "".join(
        (
            "<tr>"
            f"<td style='padding:6px 10px;font-weight:600'>{html.escape(str(label))}</td>"
            f"<td style='padding:6px 10px'>{html.escape(str(value))}</td>"
            "</tr>"
        )
        for label, value in fields
    )
    return (
        "<div style='font-family:Arial,sans-serif;color:#222'>"
        "<h2>Nueva cita de Contact Center</h2>"
        "<p>Se agendó una cita para tu sucursal. El resultado deberá cerrarse en Suite Ultra.</p>"
        f"<table style='border-collapse:collapse'>{rows}</table>"
        "</div>"
    )


def queue_appointment_created_notification(
    appointment: ContactCenterAppointmentORM,
) -> dict:
    recipients = _branch_manager_emails(int(appointment.sucursal_id))
    notification = ContactCenterNotificationORM(
        appointment_id=appointment.id,
        event_type="APPOINTMENT_CREATED",
        recipients_json=recipients,
        status="PENDING" if recipients else "FAILED",
        error=None if recipients else "No hay gerentes con correo para la sucursal.",
    )
    db.session.add(notification)
    db.session.commit()

    if not recipients:
        return {
            "queued": False,
            "recipients": [],
            "status": "FAILED",
        }

    local_at = appointment.scheduled_at.astimezone(BUSINESS_TZ)
    branch_name = (
        appointment.sucursal.sucursal
        if appointment.sucursal is not None
        else str(appointment.sucursal_id)
    )
    subject = (
        f"[Contact Center] Nueva cita — {branch_name} — "
        f"{local_at.strftime('%d/%m/%Y %H:%M')}"
    )
    body = _render_appointment_html(appointment)
    app = current_app._get_current_object()
    notification_id = int(notification.id)

    def _send() -> None:
        with app.app_context():
            row = ContactCenterNotificationORM.query.get(notification_id)
            if row is None:
                return
            try:
                send_email_html(recipients, subject, body)
                row.status = "SENT"
                row.sent_at = datetime_now_utc()
                row.error = None
            except Exception as exc:
                row.status = "FAILED"
                row.error = str(exc)[:2000]
                app.logger.exception(
                    "No se pudo enviar notificación de cita Contact Center %s",
                    appointment.id,
                )
            finally:
                db.session.commit()
                db.session.remove()

    threading.Thread(target=_send, daemon=True).start()
    return {
        "queued": True,
        "recipients": recipients,
        "status": "PENDING",
    }


def datetime_now_utc():
    from datetime import datetime
    return datetime.now(timezone.utc)
