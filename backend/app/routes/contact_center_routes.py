from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models.contact_center import (
    ContactCenterAppointmentORM,
    ContactCenterCaseORM,
)
from app.services.contact_center_service import (
    ContactCenterDuplicateError,
    ContactCenterNotFoundError,
    ContactCenterValidationError,
    add_interaction,
    assign_case,
    close_appointment,
    create_appointment,
    create_contact_with_case,
    find_duplicate_contacts,
    get_contact_detail,
    import_crm_candidate,
    list_agents,
    list_appointments,
    list_branches,
    list_contacts,
    list_crm_candidates,
    merge_contacts,
    reschedule_appointment,
    serialize_appointment,
    serialize_case,
    serialize_contact,
    serialize_interaction,
    verify_appointment_purchase,
)
from app.utils.contact_center_access import (
    ContactCenterAuthorizationError,
    get_current_contact_center_user,
)
from app.utils.contact_center_notify import (
    queue_appointment_created_notification,
)


contact_center_bp = Blueprint("contact_center", __name__)
BUSINESS_TZ = ZoneInfo("America/Tijuana")


@contact_center_bp.errorhandler(ContactCenterDuplicateError)
def _handle_duplicate(exc):
    db.session.rollback()
    return jsonify({
        "mensaje": str(exc),
        "duplicates": exc.candidates,
    }), 409


@contact_center_bp.errorhandler(ContactCenterValidationError)
def _handle_validation(exc):
    db.session.rollback()
    return jsonify({"mensaje": str(exc)}), 400


@contact_center_bp.errorhandler(ContactCenterNotFoundError)
def _handle_not_found(exc):
    db.session.rollback()
    return jsonify({"mensaje": str(exc)}), 404


@contact_center_bp.errorhandler(ContactCenterAuthorizationError)
def _handle_authorization(exc):
    db.session.rollback()
    return jsonify({"mensaje": str(exc)}), 403


def _context():
    return get_current_contact_center_user()


def _parse_date_arg(name: str) -> date | None:
    raw = str(request.args.get(name) or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ContactCenterValidationError(
            f"{name} debe tener formato YYYY-MM-DD."
        ) from exc


def _assert_contact_access(detail, actor, access) -> None:
    if access.is_supervisor:
        return

    assigned = any(
        case.get("status") != "CLOSED"
        and int(case.get("assigned_user", {}).get("id") or 0) == int(actor.id)
        for case in detail.get("cases", [])
        if isinstance(case.get("assigned_user"), dict)
    )
    if not assigned:
        raise ContactCenterAuthorizationError(
            "El contacto no pertenece a tu cartera."
        )


def _assert_case_access(case: ContactCenterCaseORM, actor, access) -> None:
    if access.is_supervisor:
        return
    if int(case.assigned_user_id or 0) != int(actor.id):
        raise ContactCenterAuthorizationError(
            "El caso no pertenece a tu cartera."
        )


def _assert_appointment_access(appointment, actor, access) -> None:
    _assert_case_access(appointment.case, actor, access)


@contact_center_bp.get("/access")
@jwt_required()
def get_access():
    actor, access = _context()
    return jsonify({
        "allowed": True,
        "user": {
            "id": int(actor.id),
            "username": actor.username,
            "role": actor.rol,
        },
        "is_supervisor": access.is_supervisor,
    }), 200


@contact_center_bp.get("/lookups")
@jwt_required()
def get_lookups():
    _, access = _context()
    return jsonify({
        "branches": list_branches(),
        "agents": list_agents() if access.is_supervisor else [],
    }), 200


@contact_center_bp.get("/contacts")
@jwt_required()
def get_contacts():
    actor, access = _context()
    rows = list_contacts(
        actor=actor,
        is_supervisor=access.is_supervisor,
        status=request.args.get("status"),
        source_type=request.args.get("source_type"),
        query_text=request.args.get("q"),
    )
    return jsonify({"rows": rows, "count": len(rows)}), 200


@contact_center_bp.post("/contacts")
@jwt_required()
def post_contact():
    actor, _ = _context()
    payload = request.get_json(silent=True) or {}

    try:
        contact, case = create_contact_with_case(payload, actor)
        db.session.commit()
    except (
        ContactCenterDuplicateError,
        ContactCenterValidationError,
        ContactCenterNotFoundError,
    ):
        db.session.rollback()
        raise
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Error creando contacto Contact Center."
        )
        return jsonify({
            "mensaje": "No se pudo crear el contacto."
        }), 500

    return jsonify({
        "contact": serialize_contact(contact),
        "case": serialize_case(case),
    }), 201


@contact_center_bp.get("/contacts/duplicates")
@jwt_required()
def get_duplicates():
    _context()
    exclude_contact_id = request.args.get("exclude_contact_id")
    try:
        exclude_value = (
            int(exclude_contact_id)
            if exclude_contact_id not in (None, "")
            else None
        )
    except (TypeError, ValueError) as exc:
        raise ContactCenterValidationError(
            "exclude_contact_id inválido."
        ) from exc

    rows = find_duplicate_contacts(
        phone=request.args.get("phone"),
        email=request.args.get("email"),
        exclude_contact_id=exclude_value,
    )
    return jsonify({"rows": rows, "count": len(rows)}), 200


@contact_center_bp.get("/contacts/<int:contact_id>")
@jwt_required()
def get_contact(contact_id: int):
    actor, access = _context()
    detail = get_contact_detail(contact_id)
    _assert_contact_access(detail, actor, access)
    return jsonify(detail), 200


@contact_center_bp.post("/contacts/merge")
@jwt_required()
def post_merge_contacts():
    actor, access = _context()
    if not access.is_supervisor:
        raise ContactCenterAuthorizationError(
            "Sólo ADMICORP puede fusionar contactos en esta fase."
        )

    payload = request.get_json(silent=True) or {}
    try:
        survivor_id = int(payload.get("survivor_contact_id"))
        merged_id = int(payload.get("merged_contact_id"))
    except (TypeError, ValueError) as exc:
        raise ContactCenterValidationError(
            "Los IDs de contactos son obligatorios."
        ) from exc

    try:
        survivor = merge_contacts(
            survivor_contact_id=survivor_id,
            merged_contact_id=merged_id,
            field_resolution=payload.get("field_resolution") or {},
            actor=actor,
        )
        db.session.commit()
    except (ContactCenterValidationError, ContactCenterNotFoundError):
        db.session.rollback()
        raise
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Error fusionando contactos Contact Center."
        )
        return jsonify({
            "mensaje": "No se pudieron fusionar los contactos."
        }), 500

    return jsonify({
        "contact": serialize_contact(survivor),
        "merged_contact_id": merged_id,
    }), 200


@contact_center_bp.post("/cases/<int:case_id>/assign")
@jwt_required()
def post_assign_case(case_id: int):
    actor, access = _context()
    payload = request.get_json(silent=True) or {}
    try:
        assigned_user_id = int(payload.get("assigned_user_id"))
    except (TypeError, ValueError) as exc:
        raise ContactCenterValidationError(
            "assigned_user_id es obligatorio."
        ) from exc

    try:
        case = assign_case(
            case_id,
            assigned_user_id,
            actor,
            is_supervisor=access.is_supervisor,
        )
        db.session.commit()
    except (ContactCenterValidationError, ContactCenterNotFoundError):
        db.session.rollback()
        raise

    return jsonify({"case": serialize_case(case)}), 200


@contact_center_bp.post("/cases/<int:case_id>/interactions")
@jwt_required()
def post_interaction(case_id: int):
    actor, access = _context()
    payload = request.get_json(silent=True) or {}

    try:
        row = add_interaction(
            case_id,
            payload,
            actor,
            is_supervisor=access.is_supervisor,
        )
        db.session.commit()
    except (ContactCenterValidationError, ContactCenterNotFoundError):
        db.session.rollback()
        raise

    return jsonify({"interaction": serialize_interaction(row)}), 201


@contact_center_bp.post("/cases/<int:case_id>/appointments")
@jwt_required()
def post_appointment(case_id: int):
    actor, access = _context()
    payload = request.get_json(silent=True) or {}

    try:
        appointment = create_appointment(
            case_id,
            payload,
            actor,
            is_supervisor=access.is_supervisor,
        )
        db.session.commit()
    except (ContactCenterValidationError, ContactCenterNotFoundError):
        db.session.rollback()
        raise
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Error creando cita Contact Center."
        )
        return jsonify({"mensaje": "No se pudo crear la cita."}), 500

    notification = {
        "queued": False,
        "recipients": [],
        "status": "FAILED",
    }
    try:
        notification = queue_appointment_created_notification(
            appointment
        )
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "La cita %s se creó pero falló la preparación del correo.",
            appointment.id,
        )

    return jsonify({
        "appointment": serialize_appointment(appointment),
        "notification": notification,
    }), 201


@contact_center_bp.get("/appointments")
@jwt_required()
def get_appointments():
    actor, access = _context()
    date_from = _parse_date_arg("date_from")
    date_to = _parse_date_arg("date_to")
    if date_from and date_to and date_from > date_to:
        raise ContactCenterValidationError(
            "date_from no puede ser posterior a date_to."
        )

    rows = list_appointments(
        actor=actor,
        is_supervisor=access.is_supervisor,
        date_from=date_from,
        date_to=date_to,
    )
    return jsonify({"rows": rows, "count": len(rows)}), 200


@contact_center_bp.post("/appointments/<int:appointment_id>/close")
@jwt_required()
def post_close_appointment(appointment_id: int):
    actor, access = _context()
    appointment = ContactCenterAppointmentORM.query.get(appointment_id)
    if appointment is None:
        raise ContactCenterNotFoundError("Cita no encontrada.")
    _assert_appointment_access(appointment, actor, access)

    payload = request.get_json(silent=True) or {}
    try:
        appointment = close_appointment(
            appointment_id,
            payload,
            actor,
        )
        db.session.commit()
    except (ContactCenterValidationError, ContactCenterNotFoundError):
        db.session.rollback()
        raise

    if appointment.purchase_reported:
        try:
            appointment = verify_appointment_purchase(appointment.id)
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception(
                "La compra de la cita %s quedó reportada, "
                "pero no pudo verificarse en Venta Total.",
                appointment.id,
            )
            appointment = ContactCenterAppointmentORM.query.get(
                appointment_id
            )

    return jsonify({
        "appointment": serialize_appointment(appointment),
    }), 200


@contact_center_bp.post(
    "/appointments/<int:appointment_id>/reschedule"
)
@jwt_required()
def post_reschedule_appointment(appointment_id: int):
    actor, access = _context()
    appointment = ContactCenterAppointmentORM.query.get(appointment_id)
    if appointment is None:
        raise ContactCenterNotFoundError("Cita no encontrada.")
    _assert_appointment_access(appointment, actor, access)

    payload = request.get_json(silent=True) or {}
    try:
        replacement = reschedule_appointment(
            appointment_id,
            payload,
            actor,
        )
        db.session.commit()
    except (ContactCenterValidationError, ContactCenterNotFoundError):
        db.session.rollback()
        raise

    notification = {
        "queued": False,
        "recipients": [],
        "status": "FAILED",
    }
    try:
        notification = queue_appointment_created_notification(
            replacement
        )
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "La cita %s fue reagendada pero falló la preparación del correo.",
            replacement.id,
        )

    return jsonify({
        "appointment": serialize_appointment(replacement),
        "notification": notification,
    }), 201


@contact_center_bp.post(
    "/appointments/<int:appointment_id>/verify-purchase"
)
@jwt_required()
def post_verify_purchase(appointment_id: int):
    actor, access = _context()
    appointment = ContactCenterAppointmentORM.query.get(appointment_id)
    if appointment is None:
        raise ContactCenterNotFoundError("Cita no encontrada.")
    _assert_appointment_access(appointment, actor, access)

    try:
        appointment = verify_appointment_purchase(appointment_id)
        db.session.commit()
    except (ContactCenterValidationError, ContactCenterNotFoundError):
        db.session.rollback()
        raise

    return jsonify({
        "appointment": serialize_appointment(appointment),
    }), 200


@contact_center_bp.get("/crm-candidates")
@jwt_required()
def get_crm_candidates():
    _context()
    month = str(request.args.get("month") or "").strip()
    if not month:
        month = datetime.now(BUSINESS_TZ).strftime("%Y-%m")
    return jsonify(list_crm_candidates(month)), 200


@contact_center_bp.post(
    "/crm-candidates/<int:contact_row_id>/import"
)
@jwt_required()
def post_import_crm_candidate(contact_row_id: int):
    actor, access = _context()
    payload = request.get_json(silent=True) or {}

    target_contact_id = payload.get("contact_id")
    if target_contact_id not in (None, ""):
        try:
            target_contact_id = int(target_contact_id)
        except (TypeError, ValueError) as exc:
            raise ContactCenterValidationError(
                "contact_id inválido."
            ) from exc
    else:
        target_contact_id = None

    try:
        contact, case = import_crm_candidate(
            contact_row_id,
            actor,
            target_contact_id=target_contact_id,
        )

        if (
            not access.is_supervisor
            and int(case.assigned_user_id or 0) != int(actor.id)
        ):
            raise ContactCenterAuthorizationError(
                "Ese contacto ya tiene un caso activo asignado a otro agente."
            )

        db.session.commit()
    except (
        ContactCenterDuplicateError,
        ContactCenterValidationError,
        ContactCenterNotFoundError,
        ContactCenterAuthorizationError,
    ):
        db.session.rollback()
        raise

    return jsonify({
        "contact": serialize_contact(contact),
        "case": serialize_case(case),
    }), 201


@contact_center_bp.get("/report")
@jwt_required()
def get_report():
    actor, access = _context()
    date_from = _parse_date_arg("date_from")
    date_to = _parse_date_arg("date_to")

    contacts = list_contacts(
        actor=actor,
        is_supervisor=access.is_supervisor,
    )
    appointments = list_appointments(
        actor=actor,
        is_supervisor=access.is_supervisor,
        date_from=date_from,
        date_to=date_to,
    )

    status_counts = {
        "NEW": 0,
        "IN_PROGRESS": 0,
        "FOLLOW_UP": 0,
        "APPOINTMENT": 0,
    }
    for row in contacts:
        status = str(row.get("case", {}).get("status") or "")
        if status in status_counts:
            status_counts[status] += 1

    return jsonify({
        "summary": {
            "active_cases": len(contacts),
            "new": status_counts["NEW"],
            "in_progress": status_counts["IN_PROGRESS"],
            "follow_up": status_counts["FOLLOW_UP"],
            "appointment_cases": status_counts["APPOINTMENT"],
            "appointments": len(appointments),
            "closure_pending": sum(
                1 for row in appointments
                if row.get("closure_pending")
            ),
            "purchase_reported": sum(
                1 for row in appointments
                if row.get("purchase_reported")
            ),
            "purchase_verified": sum(
                1 for row in appointments
                if row.get("purchase_verification_status") == "VERIFIED"
            ),
        },
        "appointments": appointments,
    }), 200
