"""Matriz de auditoría V2: lectura acotada, no autoriza operaciones ni cambia grants.

Las tres perspectivas usan evaluate_pair(). Las verificaciones legacy solo reutilizan
predicados puros de guards identificados; el resto queda como no concluyente.
"""
from collections import defaultdict
from types import SimpleNamespace

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload, selectinload

from app.extensions import db
from app.models.user_model import UserORM, usuario_sucursal
from app.models.permissions import PermissionModuleORM, PermissionActionORM, PermissionGrantORM
from app.models.warehouse import WarehouseOperatorORM
from app.models.planning_targets import PlanningOperatorORM
from app.models.internal_documents import InternalDocumentORM
from app.models.permiso_model import Permiso
from app.routes import permissions_catalog_routes as catalog
from app.utils.internal_documents_access import (
    InternalDocumentUserContext, can_manage_internal_documents,
    can_view_internal_document,
)

permissions_visual_audit_bp = Blueprint("permissions_visual_audit", __name__)

TRACK_READ = {
    "ADMIN", "ADMINISTRADOR", "SUPER_ADMIN", "LECTOR_GLOBAL", "GERENTE",
    "GERENTE_REGIONAL", "SISTEMAS", "GERENCIA DEPORTIVA", "MARKETING", "TIENDA",
}
TRACK_ADMIN = {"ADMIN", "ADMINISTRADOR", "SUPER_ADMIN"}
WAREHOUSE_FLAGS = {
    "warehouse.view": "can_view",
    "warehouse.upload": "can_upload",
    "warehouse.archive": "can_archive",
}
PLANNING_FLAGS = {
    "planning.read": "can_view", "planning.edit": "can_edit",
    "planning.submit": "can_submit", "planning.approve": "can_approve",
    "planning.publish": "can_publish", "planning.configure_model": "can_configure_model",
}


def _optional_positive(name):
    raw = request.args.get(name)
    if raw is None or raw == "":
        return None
    try:
        result = int(raw)
        if result > 0:
            return result
    except (TypeError, ValueError):
        pass
    raise ValueError(name + " debe ser un entero positivo")


def _pagination():
    try:
        limit = int(request.args.get("limit", 25))
        offset = int(request.args.get("offset", 0))
    except (ValueError, TypeError):
        raise ValueError("Paginación inválida")
    if not 1 <= limit <= 50 or offset < 0:
        raise ValueError("limit debe estar entre 1 y 50; offset >= 0")
    return limit, offset


def _batch_context(users):
    """Carga sucursales/operadores en 3 consultas para una página completa."""
    ids = [u.id for u in users]
    if not ids:
        return {}
    branches = defaultdict(list)
    for uid, bid in db.session.query(
        usuario_sucursal.c.user_id, usuario_sucursal.c.sucursal_id,
    ).filter(usuario_sucursal.c.user_id.in_(ids)).all():
        branches[uid].append(int(bid))
    warehouse = {
        op.user_id: op for op in WarehouseOperatorORM.query.filter(
            WarehouseOperatorORM.user_id.in_(ids)
        ).all()
    }
    planning = {
        op.user_id: op for op in PlanningOperatorORM.query.filter(
            PlanningOperatorORM.user_id.in_(ids),
            PlanningOperatorORM.is_active.is_(True),
        ).all()
    }
    scoped_read = {
        uid for (uid,) in db.session.query(Permiso.user_id).filter(
            Permiso.user_id.in_(ids),
            Permiso.departamento_id == 1,
            Permiso.es_admin.is_(False),
        ).all()
    }
    result = {}
    for u in users:
        b = sorted(set(branches[u.id]))
        proxy = SimpleNamespace(
            id=u.id, username=u.username, rol=u.rol,
            sucursal_id=u.sucursal_id, sucursales_ids=b,
            department_id=u.department_id,
        )
        result[u.id] = {
            "user": proxy,
            "role": catalog._normalize_role(proxy),
            "sucursal_ids": sorted(set(b + ([u.sucursal_id] if u.sucursal_id else []))),
            "warehouse_operator": warehouse.get(u.id),
            "planning_operator": planning.get(u.id),
            "allow_ticket_delete_all": catalog.os.getenv(
                "ALLOW_TICKET_DELETE_ALL", ""
            ).strip().lower() in {"1", "true", "yes", "si", "sí"},
            "pm_scoped_read": u.id in scoped_read,
        }
    return result


def _bulk_grants(users, actions):
    """Solo proyección de grants; nunca se usan para enforcement."""
    ids, action_ids = [u.id for u in users], [a.id for a in actions]
    if not ids or not action_ids:
        return {}
    roles = {catalog._normalize_role(u) for u in users}
    query = PermissionGrantORM.query.filter(
        PermissionGrantORM.action_id.in_(action_ids),
        PermissionGrantORM.is_active.is_(True),
        PermissionGrantORM.deleted_at.is_(None),
        or_(
            and_(PermissionGrantORM.principal_type == "user",
                 PermissionGrantORM.principal_user_id.in_(ids)),
            and_(PermissionGrantORM.principal_type == "role",
                 PermissionGrantORM.principal_role_key.in_(roles)),
        ),
    ).order_by(PermissionGrantORM.updated_at.desc(), PermissionGrantORM.id.desc())
    latest = {}
    for grant in query.all():
        principal = (
            ("user", grant.principal_user_id) if grant.principal_type == "user"
            else ("role", grant.principal_role_key)
        )
        latest.setdefault((grant.action_id, *principal), grant)
    return latest


def _legacy_guard_result(user, action_key, context, document):
    """(allowed, source, reason). None = NO verificable; nunca interpretar como deny."""
    role = context["role"]
    if action_key == "track.read":
        return role in TRACK_READ, "track._require_track_read_role", "guard_de_rol_track"
    if action_key in {"track.run_daily_pipeline", "track.run_agregadoras"}:
        return role in TRACK_ADMIN, "track._require_track_admin_role", "guard_admin_track"
    if action_key in WAREHOUSE_FLAGS or action_key == "warehouse.catalogs":
        op = context["warehouse_operator"]
        if action_key == "warehouse.catalogs":
            result = bool(op and (op.can_view or op.can_upload))
        else:
            result = bool(op and getattr(op, WAREHOUSE_FLAGS[action_key], False))
        return result, "warehouse_access.require_warehouse_*", "allowlist_y_flag"
    if action_key in PLANNING_FLAGS:
        op = context["planning_operator"]
        return bool(op and op.is_active and getattr(op, PLANNING_FLAGS[action_key], False)), (
            "planning_access.require_planning_*"
        ), "operador_activo_y_flag"
    if action_key == "internal_documents.manage":
        doc_context = InternalDocumentUserContext(
            user_id=user.id, username=user.username, role=role,
            sucursal_id=user.sucursal_id, sucursales_ids=tuple(user.sucursales_ids),
            department_id=user.department_id,
        )
        return can_manage_internal_documents(doc_context), (
            "internal_documents_access.can_manage_internal_documents"
        ), "manager_legacy_verificado"
    if action_key == "internal_documents.view" and document is not None:
        doc_context = InternalDocumentUserContext(
            user_id=user.id, username=user.username, role=role,
            sucursal_id=user.sucursal_id, sucursales_ids=tuple(user.sucursales_ids),
            department_id=user.department_id,
        )
        return bool(can_view_internal_document(document, doc_context)), (
            "internal_documents_access.can_view_internal_document"
        ), "documento_y_visibilidad_evaluados"
    return None, "sin_predicado_legacy_seguro", (
        "requiere_guard_especifico_o_contexto_de_objeto"
    )


def _catalog_projection(action, context):
    # PM scoped read was prefetched in one query; do not trigger per-user queries.
    if action.full_key == "pm.read" and context["role"] in {
        "COMPRAS", "COORDINADOR_MANTENIMIENTO"
    }:
        allowed = context["pm_scoped_read"]
        return catalog._decision(
            allowed=allowed, source="individual_department_read_grant" if allowed
            else "legacy_pm_roles",
            reason="compras_maintenance_read_granted" if allowed else "pm_view_role_not_allowed",
            scope_type="branch_scope", scope_values=context["sucursal_ids"] if allowed else [],
        )
    return catalog._effective_action_decision(action, context["user"], context)


def evaluate_pair(user, action, context, grants=None, branch_id=None, document=None,
                  is_module_entry=False):
    """Único criterio de clasificación para usuario, módulo y acción."""
    grants = grants or {}
    diagnostic = _catalog_projection(action, context)
    candidate = grants.get((action.id, "user", user.id)) or grants.get(
        (action.id, "role", context["role"])
    )
    catalog_allowed = diagnostic["allowed"]
    catalog_source = diagnostic["source"]
    catalog_reason = diagnostic["reason"]
    if diagnostic["source"] == "unmapped_observability_v1" or not action.is_active:
        catalog_allowed = None
        catalog_reason = "accion_sin_proyeccion_mapeada_o_inactiva"
    if candidate:
        catalog_source = "grant_diagnostico_no_enforcement"
        catalog_reason = candidate.reason or "grant_sin_motivo"
        # Module-access V1 no evalúa alcance/ventana del grant. No adivinar.
        if candidate.scope_type != "global" or candidate.starts_at or candidate.expires_at:
            catalog_allowed = None
            catalog_reason = "grant_con_alcance_o_vigencia_no_resuelta"
        else:
            catalog_allowed = candidate.effect == "allow"
    legacy, legacy_source, legacy_reason = _legacy_guard_result(
        context["user"], action.full_key, context, document,
    )
    if document is not None and action.full_key == "internal_documents.view":
        # El catálogo no estima el acceso sobre este objeto documental.
        # No comparar su True genérico contra el guard por documento.
        catalog_allowed = None
        catalog_reason = "catalogo_no_modela_visibilidad_de_este_documento"
    if branch_id is not None:
        # La decisión base no certifica autorización sobre un registro/sucursal.
        # Solo Track/operadores globales no tienen el filtro de sucursal en sus guards base.
        if action.full_key not in (
            set(WAREHOUSE_FLAGS) | set(PLANNING_FLAGS) |
            {"warehouse.catalogs", "track.read", "track.run_daily_pipeline",
             "track.run_agregadoras", "internal_documents.manage", "internal_documents.view"}
        ):
            legacy, legacy_reason = None, "branch_guard_no_evaluable_sin_recurso"
        # Documentos mantienen sus propios controles, no heredados del filtro global.
    comparison = (
        "coincide" if legacy == catalog_allowed else "diferencia"
    ) if legacy is not None and catalog_allowed is not None else "no_concluyente"
    status = "permitido" if legacy is True else "denegado" if legacy is False else "no_concluyente"
    return {
        "user_id": user.id, "username": user.username, "role": context["role"],
        "primary_branch_id": user.sucursal_id,
        "branch_ids": context["sucursal_ids"],
        "action_id": action.id, "action_key": action.full_key, "action_name": action.name,
        "module_key": action.module.key if action.module else None,
        "module_name": action.module.name if action.module else None,
        "module_entry": is_module_entry, "legacy_allowed": legacy,
        "legacy_source": legacy_source, "legacy_reason": legacy_reason,
        "catalog_allowed": catalog_allowed, "catalog_source": catalog_source,
        "catalog_reason": catalog_reason, "comparison": comparison,
        "status": status,
        "scope": "global" if legacy is not None and action.full_key in (
            set(WAREHOUSE_FLAGS) | set(PLANNING_FLAGS) |
            {"warehouse.catalogs", "track.read", "track.run_daily_pipeline",
             "track.run_agregadoras", "internal_documents.manage"}
        ) else "documento" if document and action.full_key == "internal_documents.view"
        else "requiere_contexto",
        "context": {"branch_id": branch_id, "document_id": getattr(document, "id", None)},
        "diagnostic_only": True,
    }


def _user_query():
    query = UserORM.query
    q = (request.args.get("q") or "").strip()[:120]
    role = (request.args.get("role") or "").strip().upper()[:50]
    if q:
        term = "%" + q.replace("%", r"\%").replace("_", r"\_") + "%"
        query = query.filter(or_(
            UserORM.username.ilike(term, escape="\\"),
            UserORM.email.ilike(term, escape="\\"),
            UserORM.rol.ilike(term, escape="\\"),
        ))
    if role:
        query = query.filter(db.func.upper(UserORM.rol) == role)
    return query


@permissions_visual_audit_bp.route("/matrix", methods=["GET"])
@jwt_required()
def visual_audit_matrix():
    _, error = catalog._current_admin_user_or_error()
    if error:
        return error
    perspective = request.args.get("view", "user")
    if perspective not in {"user", "module", "action"}:
        return jsonify({"error": "view inválida"}), 400
    try:
        user_id = _optional_positive("user_id")
        branch_id = _optional_positive("branch_id")
        document_id = _optional_positive("document_id")
        limit, offset = _pagination()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    module_key = (request.args.get("module_key") or "").strip()[:120]
    action_key = (request.args.get("action_key") or "").strip()[:240]
    document = None
    if document_id:
        document = InternalDocumentORM.query.options(
            selectinload(InternalDocumentORM.links),
            selectinload(InternalDocumentORM.visibility_rules),
        ).filter_by(id=document_id).first()
        if document is None:
            return jsonify({"error": "Documento no encontrado"}), 404
    module = None
    if module_key:
        module = PermissionModuleORM.query.options(
            joinedload(PermissionModuleORM.base_action).joinedload(PermissionActionORM.module)
        ).filter_by(key=module_key).first()
        if not module:
            return jsonify({"error": "Módulo no encontrado"}), 404
    if perspective == "user" and not user_id:
        return jsonify({"error": "Selecciona user_id"}), 400
    if perspective == "module" and not module:
        return jsonify({"error": "Selecciona module_key"}), 400
    if perspective == "action" and not action_key:
        return jsonify({"error": "Selecciona action_key"}), 400
    if document_id and action_key != "internal_documents.view":
        return jsonify({"error": "Selecciona internal_documents.view para evaluar document_id"}), 400

    actions_query = PermissionActionORM.query.options(joinedload(PermissionActionORM.module))
    actions_query = actions_query.filter(PermissionActionORM.is_active.is_(True))
    if module:
        actions_query = actions_query.filter(PermissionActionORM.module_id == module.id)
    if action_key:
        actions_query = actions_query.filter(PermissionActionORM.full_key == action_key)
    if perspective == "module" and not action_key:
        if module.base_action_id is None:
            actions_query = actions_query.filter(PermissionActionORM.id == -1)
        else:
            actions_query = actions_query.filter(PermissionActionORM.id == module.base_action_id)
    if perspective == "user":
        total = actions_query.count()
        actions = actions_query.order_by(PermissionActionORM.full_key).offset(offset).limit(limit).all()
        users = UserORM.query.filter_by(id=user_id).all()
        if not users:
            return jsonify({"error": "Usuario no encontrado"}), 404
    else:
        actions = actions_query.order_by(PermissionActionORM.full_key).limit(1).all()
        if not actions:
            # Un módulo sin acción base no concede acceso conocido.
            if not (perspective == "module" and module and not action_key):
                return jsonify({"error": "Acción no encontrada en el módulo"}), 404
        user_query = _user_query()
        total = user_query.count()
        users = user_query.order_by(UserORM.username, UserORM.id).offset(offset).limit(limit).all()
    contexts = _batch_context(users)
    grants = _bulk_grants(users, actions)
    rows = []
    for user in users:
        for action in actions:
            context = contexts[user.id]
            # Entrada real del módulo no depende de cuál perspectiva se eligió.
            entry = bool(action.module and action.module.base_action_id == action.id)
            rows.append(evaluate_pair(
                user, action, context, grants, branch_id, document, entry,
            ))
        if perspective == "module" and module and not actions:
            rows.append({
                "user_id": user.id, "username": user.username, "role": contexts[user.id]["role"],
                "primary_branch_id": user.sucursal_id, "branch_ids": contexts[user.id]["sucursal_ids"],
                "module_key": module.key, "module_name": module.name,
                "module_entry": True, "action_key": None, "action_id": None,
                "action_name": "Entrada al módulo", "legacy_allowed": None,
                "catalog_allowed": None, "comparison": "no_concluyente",
                "status": "no_concluyente", "legacy_source": "sin_accion_base",
                "legacy_reason": "modulo_sin_accion_base",
                "catalog_source": "sin_accion_base", "catalog_reason": "modulo_sin_accion_base",
                "scope": "requiere_contexto", "context": {"branch_id": branch_id, "document_id": document_id},
                "diagnostic_only": True,
            })
    return jsonify({
        "status": "ok", "mode": "visual_audit_readonly_v1",
        "note": "Solo consulta. Legacy comprobado únicamente en predicados declarados; no reemplaza enforcement.",
        "view": perspective, "rows": rows,
        "summary": {
            "total": total, "limit": limit, "offset": offset,
            "evaluated": sum(row["legacy_allowed"] is not None for row in rows),
            "allowed": sum(row["legacy_allowed"] is True for row in rows),
            "denied": sum(row["legacy_allowed"] is False for row in rows),
            "unknown": sum(row["legacy_allowed"] is None for row in rows),
            "differences": sum(row["comparison"] == "diferencia" for row in rows),
            "matches": sum(row["comparison"] == "coincide" for row in rows),
        },
        "coverage": {
            "catalog_partial": True,
            "message": "Catálogo parcial: ausencia de mapeo no demuestra ausencia de guard.",
        },
    }), 200
