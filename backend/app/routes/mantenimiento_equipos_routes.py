from datetime import datetime
import os
import threading

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.extensions import db
from app.models.mantenimiento_equipo import FamiliaEquipoORM
from app.models.user_model import UserORM
from app.services.mantenimiento_equipos_report_service import (
    BUSINESS_TIMEZONE,
    construir_reporte_xlsx,
)
from app.services.mantenimiento_equipos_service import (
    MantenimientoEquiposError,
    listar_fallas_activas,
    listar_familias_activas,
    preparar_compromiso_estructurado,
)
from app.utils.email_sender import send_email_html
from app.utils.error_handler import manejar_error
from app.utils.notify_targets import build_subject, pick_recipients
from app.utils.notify_utils import render_ticket_html


mantenimiento_equipos_bp = Blueprint("mantenimiento_equipos", __name__)


def _current_user():
    return UserORM.get_by_id(get_jwt_identity())


def _send_email_after_commit(recipients, subject, html):
    if os.getenv("SMTP_SYNC_DEBUG", "0") == "1":
        send_email_html(recipients, subject, html)
        return

    threading.Thread(
        target=send_email_html,
        args=(recipients, subject, html),
        daemon=True,
    ).start()


def _notify_commitment(ticket, actor):
    notified = []
    try:
        if os.getenv("NOTIFY_EMAIL_ON_UPDATE", "true").lower() != "true":
            return notified

        notified = pick_recipients(ticket, actor.username, event="update") or []
        if not notified:
            return notified

        subject = build_subject(
            ticket,
            "Compromiso y diagnóstico de mantenimiento",
        )
        html = render_ticket_html(ticket.to_dict())
        _send_email_after_commit(notified, subject, html)
    except Exception as exc:
        current_app.logger.exception(
            "No se pudo notificar compromiso estructurado del ticket %s: %s",
            getattr(ticket, "id", None),
            exc,
        )

    return notified


@mantenimiento_equipos_bp.route("/familias", methods=["GET"])
@jwt_required()
def listar_familias():
    return jsonify([family.to_dict() for family in listar_familias_activas()]), 200


@mantenimiento_equipos_bp.route(
    "/familias/<int:familia_equipo_id>/fallas",
    methods=["GET"],
)
@jwt_required()
def listar_fallas(familia_equipo_id):
    family = FamiliaEquipoORM.query.filter(
        FamiliaEquipoORM.id == familia_equipo_id,
        FamiliaEquipoORM.activo.is_(True),
    ).first()
    if not family:
        return jsonify({"mensaje": "Familia de equipo no encontrada."}), 404

    failures = listar_fallas_activas(familia_equipo_id)
    return jsonify([failure.to_dict() for failure in failures]), 200


@mantenimiento_equipos_bp.route(
    "/tickets/<int:ticket_id>/compromiso",
    methods=["PUT"],
)
@jwt_required()
def guardar_compromiso_estructurado(ticket_id):
    actor = _current_user()
    if not actor:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    payload = request.get_json(silent=True)
    if payload is None:
        payload = {}

    try:
        ticket = preparar_compromiso_estructurado(
            ticket_id,
            actor,
            payload,
        )
        db.session.commit()
    except MantenimientoEquiposError as exc:
        db.session.rollback()
        return jsonify({"mensaje": exc.message}), exc.status_code
    except Exception as exc:
        db.session.rollback()
        return manejar_error(exc, "guardar_compromiso_estructurado")

    notified = _notify_commitment(ticket, actor)
    return jsonify(
        {
            "mensaje": "Compromiso y diagnóstico guardados correctamente.",
            "ticket": ticket.to_dict(),
            "notificados": notified,
        }
    ), 200


@mantenimiento_equipos_bp.route("/reporte", methods=["GET"])
@jwt_required()
def descargar_reporte():
    actor = _current_user()
    if not actor:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    if str(actor.username or "").strip().upper() != "ADMICORP":
        return jsonify({"mensaje": "Sólo ADMICORP puede descargar el reporte."}), 403

    try:
        output = construir_reporte_xlsx()
        business_date = datetime.now(BUSINESS_TIMEZONE).strftime("%Y%m%d")
        return send_file(
            output,
            mimetype=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            as_attachment=True,
            download_name=f"mantenimiento_equipos_{business_date}.xlsx",
        )
    except Exception as exc:
        return manejar_error(exc, "descargar_reporte_mantenimiento_equipos")
