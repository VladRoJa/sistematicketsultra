from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.extensions import db
from app.models.user_model import UserORM
from app.maintenance_planner.service import (
    MaintenancePlannerError,
    build_planner_board,
    schedule_ticket,
)


maintenance_planner_bp = Blueprint("maintenance_planner", __name__)


def _current_user():
    return UserORM.get_by_id(get_jwt_identity())


def _parse_branch_ids() -> list[int]:
    values = request.args.getlist("branch_id")
    result: list[int] = []
    for raw in values:
        try:
            parsed = int(raw)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            result.append(parsed)
    return sorted(set(result))


@maintenance_planner_bp.route("/board", methods=["GET"])
@jwt_required()
def get_board():
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    try:
        payload = build_planner_board(
            user,
            start_date=request.args.get("start_date"),
            end_date=request.args.get("end_date"),
            branch_ids=_parse_branch_ids(),
            state=request.args.get("estado"),
        )
        return jsonify(payload), 200
    except MaintenancePlannerError as exc:
        return jsonify({"mensaje": exc.message}), exc.status_code


@maintenance_planner_bp.route(
    "/tickets/<int:ticket_id>/schedule",
    methods=["PUT"],
)
@jwt_required()
def put_schedule(ticket_id: int):
    user = _current_user()
    if not user:
        return jsonify({"mensaje": "Usuario no encontrado."}), 401

    payload = request.get_json(silent=True) or {}
    try:
        ticket = schedule_ticket(
            ticket_id,
            user,
            due_date=payload.get("due_date"),
            reason=payload.get("reason"),
        )
        db.session.commit()
        return jsonify(
            {
                "mensaje": "Ticket programado correctamente.",
                "ticket": ticket.to_dict(),
            }
        ), 200
    except MaintenancePlannerError as exc:
        db.session.rollback()
        return jsonify({"mensaje": exc.message}), exc.status_code
    except Exception:
        db.session.rollback()
        raise
