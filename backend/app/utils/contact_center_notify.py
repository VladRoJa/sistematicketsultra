from __future__ import annotations

import html
import os
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

    source_labels = {
        "CRM": "CRM",
        "MESSAGE": "Mensaje",
        "REACTIVATION": "Reactivación",
        "CAMPAIGN": "Campaña",
        "MANUAL": "Manual",
    }
    month_labels = {
        1: "ENE",
        2: "FEB",
        3: "MAR",
        4: "ABR",
        5: "MAY",
        6: "JUN",
        7: "JUL",
        8: "AGO",
        9: "SEP",
        10: "OCT",
        11: "NOV",
        12: "DIC",
    }

    contact_name = html.escape(str(contact.display_name or "Sin nombre"))
    phone = html.escape(
        str(contact.phone_mx10 or contact.primary_phone_raw or "Sin teléfono")
    )
    branch_name = html.escape(
        str(branch.sucursal if branch else appointment.sucursal_id)
    )
    source = html.escape(
        source_labels.get(str(case.source_type or "").upper(), str(case.source_type or "Sin origen"))
    )
    agent_name = html.escape(
        str(agent.username if agent else "Suite Ultra")
    )
    comment = html.escape(str(appointment.notes or "Sin comentario"))
    date_display = (
        f"{local_at.day:02d} "
        f"{month_labels.get(local_at.month, '')} "
        f"{local_at.year}"
    )
    hour_12 = local_at.strftime("%I:%M").lstrip("0")
    meridiem = "a.m." if local_at.hour < 12 else "p.m."
    time_display = f"{hour_12} {meridiem}"

    frontend_url = os.getenv("SUITE_FRONTEND_URL", "").strip().rstrip("/")
    cta_html = ""
    if frontend_url:
        detail_url = html.escape(
            f"{frontend_url}/#/contact-center",
            quote=True,
        )
        cta_html = f"""
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                   style="border-collapse:collapse;margin-top:24px;">
                <tr>
                    <td align="center">
                        <a href="{detail_url}"
                           style="
                               display:inline-block;
                               background:#1d4ed8;
                               color:#ffffff;
                               text-decoration:none;
                               font-size:14px;
                               font-weight:700;
                               line-height:20px;
                               padding:12px 22px;
                               border-radius:9px;
                           ">
                            Abrir Contact Center
                        </a>
                    </td>
                </tr>
            </table>
        """

    return f"""
    <!doctype html>
    <html>
        <body style="margin:0;padding:0;background:#f3f6fb;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                   style="width:100%;border-collapse:collapse;background:#f3f6fb;">
                <tr>
                    <td align="center" style="padding:28px 12px;">
                        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                               style="
                                   width:100%;
                                   max-width:640px;
                                   border-collapse:separate;
                                   background:#ffffff;
                                   border:1px solid #dbe3ef;
                                   border-radius:16px;
                                   overflow:hidden;
                                   font-family:Arial,Helvetica,sans-serif;
                                   color:#0f172a;
                               ">
                            <tr>
                                <td style="padding:22px 26px;background:#0f172a;">
                                    <div style="
                                        margin:0 0 6px;
                                        color:#93c5fd;
                                        font-size:11px;
                                        font-weight:700;
                                        letter-spacing:1.6px;
                                    ">
                                        SUITE ULTRA · CONTACT CENTER
                                    </div>
                                    <div style="
                                        margin:0;
                                        color:#ffffff;
                                        font-size:25px;
                                        font-weight:800;
                                        line-height:32px;
                                    ">
                                        Nueva cita agendada
                                    </div>
                                </td>
                            </tr>

                            <tr>
                                <td style="padding:24px 26px 8px;">
                                    <div style="
                                        margin:0 0 8px;
                                        color:#64748b;
                                        font-size:13px;
                                        line-height:20px;
                                    ">
                                        Contact Center generó una cita para tu sucursal.
                                        Después de la atención deberá registrarse el resultado en Suite Ultra.
                                    </div>
                                </td>
                            </tr>

                            <tr>
                                <td style="padding:8px 26px 0;">
                                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                                           style="
                                               width:100%;
                                               border-collapse:separate;
                                               background:#eff6ff;
                                               border:1px solid #bfdbfe;
                                               border-radius:12px;
                                           ">
                                        <tr>
                                            <td style="padding:16px 18px;">
                                                <div style="
                                                    color:#1d4ed8;
                                                    font-size:11px;
                                                    font-weight:700;
                                                    letter-spacing:.8px;
                                                    text-transform:uppercase;
                                                    margin-bottom:5px;
                                                ">
                                                    Sucursal
                                                </div>
                                                <div style="
                                                    color:#0f172a;
                                                    font-size:20px;
                                                    font-weight:800;
                                                    line-height:26px;
                                                ">
                                                    {branch_name}
                                                </div>
                                            </td>
                                            <td align="right" style="padding:16px 18px;">
                                                <div style="
                                                    color:#1d4ed8;
                                                    font-size:11px;
                                                    font-weight:700;
                                                    letter-spacing:.8px;
                                                    text-transform:uppercase;
                                                    margin-bottom:5px;
                                                ">
                                                    Fecha y hora
                                                </div>
                                                <div style="
                                                    color:#0f172a;
                                                    font-size:16px;
                                                    font-weight:800;
                                                    line-height:22px;
                                                ">
                                                    {date_display}
                                                </div>
                                                <div style="
                                                    color:#475569;
                                                    font-size:14px;
                                                    font-weight:700;
                                                    line-height:20px;
                                                ">
                                                    {time_display}
                                                </div>
                                            </td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>

                            <tr>
                                <td style="padding:22px 26px 0;">
                                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                                           style="width:100%;border-collapse:collapse;">
                                        <tr>
                                            <td style="
                                                width:50%;
                                                padding:0 12px 14px 0;
                                                vertical-align:top;
                                            ">
                                                <div style="color:#64748b;font-size:11px;font-weight:700;margin-bottom:4px;">
                                                    CONTACTO
                                                </div>
                                                <div style="color:#0f172a;font-size:15px;font-weight:700;">
                                                    {contact_name}
                                                </div>
                                            </td>
                                            <td style="
                                                width:50%;
                                                padding:0 0 14px 12px;
                                                vertical-align:top;
                                            ">
                                                <div style="color:#64748b;font-size:11px;font-weight:700;margin-bottom:4px;">
                                                    TELÉFONO
                                                </div>
                                                <div style="color:#0f172a;font-size:15px;font-weight:700;">
                                                    {phone}
                                                </div>
                                            </td>
                                        </tr>
                                        <tr>
                                            <td style="
                                                width:50%;
                                                padding:0 12px 0 0;
                                                vertical-align:top;
                                            ">
                                                <div style="color:#64748b;font-size:11px;font-weight:700;margin-bottom:4px;">
                                                    ORIGEN
                                                </div>
                                                <div style="color:#0f172a;font-size:14px;font-weight:700;">
                                                    {source}
                                                </div>
                                            </td>
                                            <td style="
                                                width:50%;
                                                padding:0 0 0 12px;
                                                vertical-align:top;
                                            ">
                                                <div style="color:#64748b;font-size:11px;font-weight:700;margin-bottom:4px;">
                                                    AGENDADA POR
                                                </div>
                                                <div style="color:#0f172a;font-size:14px;font-weight:700;">
                                                    {agent_name}
                                                </div>
                                            </td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>

                            <tr>
                                <td style="padding:22px 26px 0;">
                                    <div style="
                                        color:#64748b;
                                        font-size:11px;
                                        font-weight:700;
                                        margin-bottom:7px;
                                    ">
                                        COMENTARIO DEL CONTACT CENTER
                                    </div>
                                    <div style="
                                        background:#f8fafc;
                                        border:1px solid #e2e8f0;
                                        border-radius:10px;
                                        padding:14px 16px;
                                        color:#334155;
                                        font-size:14px;
                                        line-height:21px;
                                    ">
                                        {comment}
                                    </div>
                                </td>
                            </tr>

                            <tr>
                                <td style="padding:0 26px 24px;">
                                    {cta_html}

                                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                                           style="
                                               width:100%;
                                               border-collapse:collapse;
                                               margin-top:24px;
                                               border-top:1px solid #e2e8f0;
                                           ">
                                        <tr>
                                            <td style="padding-top:16px;">
                                                <span style="
                                                    display:inline-block;
                                                    padding:5px 9px;
                                                    background:#fff7ed;
                                                    border:1px solid #fed7aa;
                                                    border-radius:999px;
                                                    color:#c2410c;
                                                    font-size:11px;
                                                    font-weight:700;
                                                ">
                                                    Pendiente de cierre
                                                </span>
                                            </td>
                                        </tr>
                                    </table>

                                    <div style="
                                        margin-top:12px;
                                        color:#94a3b8;
                                        font-size:11px;
                                        line-height:17px;
                                    ">
                                        Notificación automática de Suite Ultra.
                                    </div>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
    </html>
    """


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
    appointment_id = int(appointment.id)

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
                    appointment_id,
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