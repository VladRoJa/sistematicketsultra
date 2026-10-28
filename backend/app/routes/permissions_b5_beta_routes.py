"""B5: editor beta de grants de Nube, aislado del enforcement HTTP.

El flag PERMISSIONS_B5_EDITOR_ENABLED es FALSE por defecto. Preview es
solo diagnóstico; las mutaciones exigen flag, JWT admin y allowlist exacta.
Los guards de documentos jamás leen estas concesiones.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy import or_

from app.extensions import db
from app.models.permissions import (
    PermissionActionORM, PermissionGrantAuditLogORM, PermissionGrantORM,
    PermissionModuleORM,
)
from app.models.sucursal_model import Sucursal, SucursalOperationalStatus
from app.models.user_model import UserORM, usuario_sucursal
from app.routes.permissions_catalog_routes import (
    _current_admin_user_or_error,
    _permission_grant_audit_payload,
    _permission_grant_request_ip,
    _serialize_permission_grant,
)

permissions_b5_beta_bp = Blueprint("permissions_b5_beta", __name__)

B5_ACTION_KEY = "internal_documents.view"
B5_MODULE_KEY = "internal_documents"
B5_ALLOWED_SCOPES = frozenset({"branch", "branch_list"})
_B5_MUTABLE_FIELDS = frozenset({
    "principal_user_id", "action_full_key", "effect", "scope_type",
    "scope_branch_id", "scope_branch_ids", "starts_at", "expires_at",
    "reason", "grant_id", "expected_updated_at",
})


def b5_editor_enabled() -> bool:
    configured = current_app.config.get(
        "PERMISSIONS_B5_EDITOR_ENABLED",
        os.environ.get("PERMISSIONS_B5_EDITOR_ENABLED", "false"),
    )
    return str(configured).strip().lower() == "true"


def _error(detail: str, status: int):
    return jsonify({"error": "B5 beta", "detail": detail}), status


def _require_write_gate():
    if not b5_editor_enabled():
        return _error("Editor B5 deshabilitado por configuración del servidor.", 403)
    return None


def _parse_iso(value, label):
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}: usa fecha ISO 8601 con zona horaria explícita.")
    try:
        date = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label}: fecha ISO 8601 inválida.") from exc
    if date.tzinfo is None or date.utcoffset() is None:
        raise ValueError(f"{label}: falta zona horaria.")
    return date.astimezone(timezone.utc)


def _positive_id(value):
    return value if type(value) is int and value > 0 else None


def _normalize_input(raw, *, editing=False):
    if not isinstance(raw, dict) or set(raw) - _B5_MUTABLE_FIELDS:
        raise ValueError("Payload inválido o contiene campos no admitidos.")
    if raw.get("action_full_key") != B5_ACTION_KEY:
        raise ValueError("Acción no permitida en el piloto B5.")
    user_id = _positive_id(raw.get("principal_user_id"))
    if not user_id:
        raise ValueError("principal_user_id debe ser un entero positivo.")
    if raw.get("effect") not in {"allow", "deny"}:
        raise ValueError("effect debe ser allow o deny.")
    scope = raw.get("scope_type")
    if scope not in B5_ALLOWED_SCOPES:
        raise ValueError("Solo se admiten scopes branch y branch_list.")
    if scope == "branch":
        branch = _positive_id(raw.get("scope_branch_id"))
        if not branch or raw.get("scope_branch_ids") not in (None, []):
            raise ValueError("Scope branch requiere una sucursal y ninguna lista.")
        branches = [branch]
    else:
        given = raw.get("scope_branch_ids")
        if (not isinstance(given, list) or not given
                or any(_positive_id(x) is None for x in given)
                or len(given) != len(set(given))
                or raw.get("scope_branch_id") is not None):
            raise ValueError("branch_list exige sucursales positivas, únicas y no vacías.")
        branches = sorted(given)
    reason = raw.get("reason")
    if not isinstance(reason, str) or not 8 <= len(reason.strip()) <= 1000:
        raise ValueError("Motivo explícito obligatorio (8 a 1000 caracteres).")
    start = _parse_iso(raw.get("starts_at"), "starts_at")
    end = _parse_iso(raw.get("expires_at"), "expires_at")
    if start and end and start >= end:
        raise ValueError("expires_at debe ser posterior a starts_at.")
    grant_id = raw.get("grant_id")
    if grant_id is not None and _positive_id(grant_id) is None:
        raise ValueError("grant_id inválido.")
    if editing and not grant_id:
        raise ValueError("Para editar se requiere grant_id.")
    expected = raw.get("expected_updated_at")
    if editing and expected is None:
        raise ValueError("expected_updated_at obligatorio para edición.")
    if expected is not None:
        expected = _parse_iso(expected, "expected_updated_at")
    return {
        "user_id": user_id, "effect": raw["effect"], "scope": scope,
        "branches": branches, "reason": reason.strip(), "starts_at": start,
        "expires_at": end, "grant_id": grant_id, "expected_updated_at": expected,
    }


def _overlap_dates(a_start, a_end, b_start, b_end):
    # [start, end): a_end == b_start NO se solapa.
    def utc(dt):
        return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt
    a_start, a_end, b_start, b_end = map(utc, (a_start, a_end, b_start, b_end))
    return ((a_end is None or b_start is None or b_start < a_end)
            and (b_end is None or a_start is None or a_start < b_end))


def _record_branches(grant):
    if grant.scope_type == "branch":
        value = _positive_id(grant.scope_branch_id)
        return {value} if value else None
    if grant.scope_type == "branch_list":
        values = grant.scope_branch_ids
        if (not isinstance(values, list) or not values
                or any(_positive_id(value) is None for value in values)
                or len(values) != len(set(values))):
            return None
        return set(values)
    return None


def _resolve_target(data, *, lock=False):
    target = UserORM.query.filter(UserORM.id == data["user_id"])
    if lock:
        # Bloqueo del principal serializa inclusive dos creates sin grants previos.
        target = target.with_for_update()
    user = target.first()
    if user is None:
        return None, None, _error("Usuario objetivo no encontrado.", 404)
    action = PermissionActionORM.query.filter_by(full_key=B5_ACTION_KEY, is_active=True).first()
    if not action:
        return None, None, _error("Acción B5 no disponible.", 409)
    module = PermissionModuleORM.query.filter_by(
        id=action.module_id, key=B5_MODULE_KEY, is_active=True
    ).first()
    if not module:
        return None, None, _error("Módulo B5 inactivo.", 409)
    return user, action, None


def _check_branches(user, wanted):
    assigned = {user.sucursal_id}
    assigned.update(db.session.execute(
        db.select(usuario_sucursal.c.sucursal_id).where(
            usuario_sucursal.c.user_id == user.id
        )
    ).scalars().all())
    if not set(wanted).issubset(assigned):
        return "No se permite alcance fuera de las sucursales asignadas al usuario."
    rows = Sucursal.query.filter(Sucursal.sucursal_id.in_(wanted)).all()
    eligible = {
        branch.sucursal_id for branch in rows
        if branch.operational_status == SucursalOperationalStatus.ACTIVA
        and not branch.is_demo
    }
    if eligible != set(wanted):
        return "Hay sucursales inexistentes, inactivas o de demostración."
    return None


def _check_conflicts(data, action, user):
    rows = PermissionGrantORM.query.filter(
        PermissionGrantORM.action_id == action.id,
        PermissionGrantORM.is_active.is_(True),
        PermissionGrantORM.deleted_at.is_(None),
        or_(
            (PermissionGrantORM.principal_type == "user") &
            (PermissionGrantORM.principal_user_id == user.id),
            (PermissionGrantORM.principal_type == "role") &
            (db.func.upper(db.func.trim(PermissionGrantORM.principal_role_key))
             == str(user.rol or "").strip().upper()),
        ),
    ).all()
    for existing in rows:
        if existing.id == data["grant_id"]:
            continue
        if existing.principal_type != "user":
            return "Existe un grant por rol que requiere revisión independiente."
        previous_branches = _record_branches(existing)
        if previous_branches is None:
            return "Existe un grant global/custom o de alcance ambiguo."
        if (previous_branches.intersection(data["branches"])
                and _overlap_dates(
                    data["starts_at"], data["expires_at"],
                    existing.starts_at, existing.expires_at,
                )):
            return f"Conflicto con grant #{existing.id}: sucursal y vigencia solapadas."
    return None


def _evaluate(data, *, lock=False):
    user, action, error = _resolve_target(data, lock=lock)
    if error:
        return None, error
    branch_error = _check_branches(user, data["branches"])
    if branch_error:
        return None, _error(branch_error, 409)
    conflict = _check_conflicts(data, action, user)
    if conflict:
        return None, _error(conflict, 409)
    return (user, action), None


def _validate_existing(grant_id, data, *, lock=False):
    if data["grant_id"] != grant_id:
        return None, _error("grant_id no coincide con el recurso.", 400)
    grant = PermissionGrantORM.query.filter_by(id=grant_id).first()
    if not grant:
        return None, _error("Grant inexistente.", 404)
    if (grant.principal_type != "user" or grant.principal_user_id != data["user_id"]
            or not grant.action or grant.action.full_key != B5_ACTION_KEY
            or grant.deleted_at is not None or not grant.is_active):
        return None, _error("Este grant no puede modificarse en B5.", 409)
    previous = grant.updated_at
    expected = data["expected_updated_at"]
    if previous is None or previous.replace(tzinfo=previous.tzinfo or timezone.utc).astimezone(timezone.utc) != expected:
        return None, _error("Grant actualizado en otra sesión (stale).", 409)
    return grant, None


def _audit(grant, event, admin, reason, before):
    db.session.add(PermissionGrantAuditLogORM(
        grant_id=grant.id, event_type=event,
        before_payload=before,
        after_payload=_permission_grant_audit_payload(grant),
        changed_by_user_id=admin.id,
        reason=reason, request_ip=_permission_grant_request_ip(),
        user_agent=request.headers.get("User-Agent"),
    ))


def _admin_and_gate(*, writing=False):
    admin, error = _current_admin_user_or_error()
    if error:
        return None, error
    if writing:
        error = _require_write_gate()
        if error:
            return None, error
    return admin, None


@permissions_b5_beta_bp.get("/grants/beta/status")
@jwt_required()
def status():
    _, error = _admin_and_gate()
    if error:
        return error
    return jsonify({
        "mode": "compare_only", "enabled": b5_editor_enabled(),
        "action_full_key": B5_ACTION_KEY,
        "allowed_scopes": sorted(B5_ALLOWED_SCOPES),
        "grants_enforced": False, "object_access_certified": False,
    })


@permissions_b5_beta_bp.post("/grants/beta/preview")
@jwt_required()
def preview():
    _, error = _admin_and_gate()
    if error:
        return error
    try:
        data = _normalize_input(request.get_json(silent=True))
    except ValueError as exc:
        return _error(str(exc), 400)
    _, error = _evaluate(data)
    if error:
        return error
    return jsonify({
        "status": "valid_configuration",
        "mode": "compare_only", "catalog_allowed": None,
        "object_access_certified": False, "http_authorization": "not_evaluated",
        "action_full_key": B5_ACTION_KEY, "branches": data["branches"],
        "note": "Preview informativo; ningún guard HTTP concede acceso por este grant.",
    })


@permissions_b5_beta_bp.post("/grants/beta")
@jwt_required()
def create_beta_grant():
    admin, error = _admin_and_gate(writing=True)
    if error:
        return error
    try:
        data = _normalize_input(request.get_json(silent=True))
    except ValueError as exc:
        return _error(str(exc), 400)
    try:
        resolved, error = _evaluate(data, lock=True)
        if error:
            return error
        _, action = resolved
        grant = PermissionGrantORM(
            principal_type="user", principal_user_id=data["user_id"],
            module_id=action.module_id, action_id=action.id,
            effect=data["effect"], scope_type=data["scope"],
            scope_branch_id=data["branches"][0] if data["scope"] == "branch" else None,
            scope_branch_ids=data["branches"] if data["scope"] == "branch_list" else [],
            reason=data["reason"], is_active=True,
            starts_at=data["starts_at"], expires_at=data["expires_at"],
            created_by_user_id=admin.id, updated_by_user_id=admin.id,
        )
        db.session.add(grant)
        db.session.flush()
        _audit(grant, "created", admin, data["reason"], None)
        db.session.commit()
        return jsonify({"status": "created", "grant": _serialize_permission_grant(grant)}), 201
    except Exception:
        db.session.rollback()
        current_app.logger.exception("B5 grant create failure")
        return _error("No se pudo registrar el grant; transacción revertida.", 500)


@permissions_b5_beta_bp.patch("/grants/beta/<int:grant_id>")
@jwt_required()
def update_beta_grant(grant_id):
    admin, error = _admin_and_gate(writing=True)
    if error:
        return error
    try:
        data = _normalize_input(request.get_json(silent=True), editing=True)
    except ValueError as exc:
        return _error(str(exc), 400)
    try:
        resolved, error = _evaluate(data, lock=True)
        if error:
            return error
        grant, error = _validate_existing(grant_id, data)
        if error:
            return error
        before = _permission_grant_audit_payload(grant)
        grant.effect = data["effect"]
        grant.scope_type = data["scope"]
        grant.scope_branch_id = data["branches"][0] if data["scope"] == "branch" else None
        grant.scope_branch_ids = data["branches"] if data["scope"] == "branch_list" else []
        grant.starts_at, grant.expires_at = data["starts_at"], data["expires_at"]
        grant.reason = data["reason"]
        grant.updated_at = datetime.now(timezone.utc)
        grant.updated_by_user_id = admin.id
        db.session.flush()
        _audit(grant, "updated", admin, data["reason"], before)
        db.session.commit()
        return jsonify({"status": "updated", "grant": _serialize_permission_grant(grant)})
    except Exception:
        db.session.rollback()
        current_app.logger.exception("B5 grant update failure")
        return _error("No se pudo editar el grant; transacción revertida.", 500)


@permissions_b5_beta_bp.post("/grants/beta/<int:grant_id>/disable")
@jwt_required()
def disable_beta_grant(grant_id):
    admin, error = _admin_and_gate(writing=True)
    if error:
        return error
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) != {"reason", "expected_updated_at"}:
        return _error("Se requiere reason y expected_updated_at.", 400)
    reason = body["reason"]
    if not isinstance(reason, str) or not 8 <= len(reason.strip()) <= 1000:
        return _error("Motivo explícito obligatorio (8 a 1000 caracteres).", 400)
    try:
        expected = _parse_iso(body["expected_updated_at"], "expected_updated_at")
    except ValueError as exc:
        return _error(str(exc), 400)
    try:
        # Primero identificar el principal y luego bloquear su fila para
        # serializar disable contra create/patch de la misma acción.
        row = PermissionGrantORM.query.filter_by(id=grant_id).first()
        if not row or row.principal_type != "user" or not row.principal_user_id:
            return _error("Grant B5 no encontrado.", 404)
        user = UserORM.query.filter(UserORM.id == row.principal_user_id).with_for_update().first()
        if not user:
            return _error("Usuario objetivo no encontrado.", 404)
        grant = PermissionGrantORM.query.filter_by(id=grant_id).first()
        if (not grant or not grant.action or grant.action.full_key != B5_ACTION_KEY
                or not grant.is_active or grant.deleted_at is not None
                or _record_branches(grant) is None):
            return _error("Grant fuera del alcance del editor B5.", 409)
        previous = grant.updated_at
        if previous is None or previous.replace(tzinfo=previous.tzinfo or timezone.utc).astimezone(timezone.utc) != expected:
            return _error("Grant actualizado en otra sesión (stale).", 409)
        before = _permission_grant_audit_payload(grant)
        grant.is_active = False
        grant.reason = reason.strip()
        grant.updated_by_user_id = admin.id
        grant.updated_at = datetime.now(timezone.utc)
        db.session.flush()
        _audit(grant, "disabled", admin, reason.strip(), before)
        db.session.commit()
        return jsonify({"status": "disabled", "grant_id": grant.id})
    except Exception:
        db.session.rollback()
        current_app.logger.exception("B5 grant disable failure")
        return _error("No se pudo desactivar; transacción revertida.", 500)
