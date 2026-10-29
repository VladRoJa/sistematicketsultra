"""Matriz de auditoría V2: lectura acotada, no autoriza operaciones ni cambia grants.

Las tres perspectivas usan evaluate_pair(). Las verificaciones legacy solo reutilizan
predicados puros de guards identificados; el resto queda como no concluyente.
"""
from collections import defaultdict
from types import SimpleNamespace

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.user_model import UserORM, usuario_sucursal
from app.models.permissions import PermissionModuleORM, PermissionActionORM, PermissionGrantORM
from app.models.warehouse import WarehouseOperatorORM
from app.models.planning_targets import PlanningOperatorORM
from app.models.internal_documents import InternalDocumentORM
from app.models.permiso_model import Permiso
from app.routes import permissions_catalog_routes as catalog
from app.routes.track_routes import track_read_grants_enabled
from app.routes.openings_routes import OPENINGS_READ_ROLES, openings_read_grants_enabled
from app.utils.pm_permissions import (
    PM_VIEW_ROLES, PM_EXECUTE_ROLES, PM_VALIDATE_ROLES,
    PM_CONFIGURE_ROLES, SCOPED_MAINTENANCE_READER_ROLES,
)
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



MAX_AUDIT_CANDIDATES = 3000
SORT_FIELDS = {"user", "role", "module", "action", "legacy", "catalog", "comparison"}
GROUP_MODES = {
    "none", "module", "role", "legacy_permitido", "legacy_denegado",
    "legacy_no_concluyente", "catalog_permitido", "catalog_denegado",
    "comparison_diferencia", "comparison_coincide",
}
DECISION_MODES = {"todos", "permitido", "denegado", "no_concluyente", "diferencia"}


def _matrix_controls():
    sort_by = request.args.get("sort_by", "action")
    sort_dir = request.args.get("sort_dir", "asc")
    group_by = request.args.get("group_by", "none")
    decision = request.args.get("decision", "todos")
    if (sort_by not in SORT_FIELDS or sort_dir not in {"asc", "desc"}
            or group_by not in GROUP_MODES or decision not in DECISION_MODES):
        raise ValueError("Orden, agrupación o filtro de decisión inválido")
    return sort_by, sort_dir, group_by, decision


def _decision_label(value):
    return "Permitidos comprobados" if value is True else (
        "Denegados comprobados" if value is False else "Sin comprobar"
    )


def _group_identity(row, group_by):
    """Clave, etiqueta y prioridad estables; las agrupaciones no conceden acceso."""
    if group_by == "module":
        label = row.get("module_name") or row.get("module_key") or "Sin módulo"
        return "module:" + (row.get("module_key") or ""), label, (0, label.casefold())
    if group_by == "role":
        label = row.get("role") or "Sin rol"
        return "role:" + label, label, (0, label.casefold())
    if group_by.startswith(("legacy_", "catalog_")):
        field = "legacy_allowed" if group_by.startswith("legacy_") else "catalog_allowed"
        value = row[field]
        status = "permitido" if value is True else "denegado" if value is False else "no_concluyente"
        first = group_by.removeprefix("legacy_").removeprefix("catalog_")
        order = [first] + [item for item in ("permitido", "denegado", "no_concluyente") if item != first]
        label = _decision_label(value)
        if field == "catalog_allowed":
            label += " · catálogo estimado"
        return field + ":" + status, label, (order.index(status), "")
    if group_by.startswith("comparison_"):
        status = row["comparison"]
        first = group_by.removeprefix("comparison_")
        order = [first] + [item for item in ("diferencia", "coincide", "no_concluyente") if item != first]
        label = {
            "diferencia": "Diferencias comprobables",
            "coincide": "Coincidencias",
            "no_concluyente": "Comparación no concluyente",
        }[status]
        return "comparison:" + status, label, (order.index(status), "")
    return "", "", (0, "")


def _sort_value(row, sort_by):
    """Triage consistente del triestado; None siempre distinto de False."""
    if sort_by in {"legacy", "catalog"}:
        value = row["legacy_allowed" if sort_by == "legacy" else "catalog_allowed"]
        return 0 if value is True else 1 if value is False else 2
    if sort_by == "comparison":
        return {"diferencia": 0, "coincide": 1, "no_concluyente": 2}[row["comparison"]]
    field = {
        "user": "username", "role": "role", "module": "module_name",
        "action": "action_name",
    }[sort_by]
    return (row.get(field) or "").casefold()


def _prepare_rows(rows, sort_by, sort_dir, group_by, decision):
    """Filtra/ordena el universo ANTES de paginar; nunca ordena solo la página."""
    filtered = [
        dict(row) for row in rows
        if decision == "todos" or (
            row["comparison"] == "diferencia" if decision == "diferencia"
            else row["status"] == decision
        )
    ]
    # Empates deterministas para evitar duplicados/saltos entre páginas.
    filtered.sort(key=lambda row: (
        (row.get("username") or "").casefold(), row["user_id"],
        (row.get("module_key") or "").casefold(),
        (row.get("action_key") or "").casefold(), row.get("action_id") or 0,
    ))
    filtered.sort(key=lambda row: _sort_value(row, sort_by), reverse=sort_dir == "desc")
    group_counts = {}
    if group_by != "none":
        for row in filtered:
            key, label, priority = _group_identity(row, group_by)
            row["group_key"], row["group_label"] = key, label
            row["_group_priority"] = priority
            group_counts[key] = group_counts.get(key, 0) + 1
        filtered.sort(key=lambda row: row["_group_priority"])
        for row in filtered:
            del row["_group_priority"]
    else:
        for row in filtered:
            row["group_key"], row["group_label"] = "", ""
    return filtered, group_counts


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
                "ALLOW_TICKET_DELETE_ALL", "false"
            ).lower() == "true",
            "pm_scoped_read": u.id in scoped_read,
        }
    return result


def _bulk_grants(users, actions):
    """Proyecta grants; track.read comparte selección con su guard operativo."""
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
    runtime_read_ids = {
        action.id for action in actions
        if action.full_key in {"track.read", "openings.read"}
    }
    for grant in query.all():
        principal = (
            ("user", grant.principal_user_id) if grant.principal_type == "user"
            else ("role", grant.principal_role_key)
        )
        key = (grant.action_id, *principal)
        if grant.action_id in runtime_read_ids:
            # El guard Track solo interpreta globales indefinidos; deny gana
            # dentro del mismo principal aunque haya duplicados antiguos.
            if not catalog._is_simple_global_module_grant(grant):
                continue
            previous = latest.get(key)
            if previous is None or (
                previous.effect != "deny" and grant.effect == "deny"
            ):
                latest[key] = grant
        else:
            latest.setdefault(key, grant)
    return latest


def _legacy_guard_result(user, action_key, context, document, branch_id=None):
    """(allowed, source, reason). None = NO verificable; nunca interpretar como deny."""
    role = context["role"]
    if action_key == "track.read":
        return role in TRACK_READ, "track._require_track_read_role", "guard_de_rol_track"
    if action_key == "openings.read":
        return role in OPENINGS_READ_ROLES, "openings._require_openings_read", "guard_de_rol_aperturas"
    if action_key == "openings.comment":
        return role in OPENINGS_READ_ROLES, "openings._require_openings_comment", "guard_de_comentarios_aperturas"
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
    # Predicados de puerta de entrada únicamente; no simulan mutaciones ni
    # evaluación final de un ticket/equipo. Los contextos de sucursal PM siguen
    # requiriendo la validación del recurso y nunca se promueven a true.
    if action_key in {"pm.read", "pm.execute", "pm.validate", "pm.configure"}:
        pm_roles = {
            "pm.read": PM_VIEW_ROLES,
            "pm.execute": PM_EXECUTE_ROLES,
            "pm.validate": PM_VALIDATE_ROLES,
            "pm.configure": PM_CONFIGURE_ROLES,
        }
        if branch_id is not None:
            return None, "pm_permissions.role_gate", "pm_sucursal_requiere_validacion_de_recurso"
        allowed = role in pm_roles[action_key]
        if action_key == "pm.read" and role in SCOPED_MAINTENANCE_READER_ROLES:
            # PM /access exige además alguna sucursal M:N para lecturas
            # individualmente concedidas; la sucursal corporativa no cuenta.
            allowed = bool(context.get("pm_scoped_read") and user.sucursales_ids)
        return allowed, "pm_permissions.can_pm_*", "pm_gate_rol_o_lectura_individual"

    if action_key == "inventory.master_write":
        # _require_inventory_global_write: solo rol, sin argumento de objeto.
        allowed = role in catalog.LEGACY_INVENTORY_GLOBAL_WRITE_ROLES
        return allowed, "inventarios._require_inventory_global_write", "inventario_guard_global_rol"

    if action_key == "inventory.movement_write":
        # La operación exige sucursal_id; sin ella sería erróneo certificar
        # acceso a cualquier movimiento o sucursal.
        if branch_id is None:
            return None, "inventarios._require_inventory_movement_write", "inventario_movimiento_requiere_sucursal"
        if role in catalog.LEGACY_INVENTORY_GLOBAL_WRITE_ROLES:
            allowed = True
        elif role == "AUX_MANTENIMIENTO":
            allowed = user.sucursal_id is not None and int(user.sucursal_id) == branch_id
        elif role == "SR_MANTENIMIENTO":
            # M:N precargada desde usuario_sucursal. NO usar sucursal_id
            # principal como fallback para SR: el guard real tampoco lo hace.
            allowed = branch_id in user.sucursales_ids
        else:
            allowed = False
        return allowed, "inventarios._require_inventory_movement_write", "inventario_movimiento_guard_sucursal"

    if action_key == "tickets.delete_all":
        # La ruta DELETE /eliminar-todos requiere admin y literalmente
        # ALLOW_TICKET_DELETE_ALL=true; no ejecutamos la operación.
        allowed = str(user.rol or "").upper() in TRACK_ADMIN and context["allow_ticket_delete_all"]
        return allowed, "ticket_routes._require_ticket_admin_action+env", "tickets_borrado_masivo_guard_doble"

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
        context["user"], action.full_key, context, document, branch_id=branch_id,
    )
    if action.full_key == "track.read" and track_read_grants_enabled():
        # Track aplica estos grants globales al guard HTTP real solo con flag ON. La matriz
        # muestra su misma decisión efectiva y no solo el rol base.
        if candidate is not None and catalog._is_simple_global_module_grant(candidate):
            legacy = candidate.effect == "allow"
            legacy_source = "track._require_track_read_role+grant"
            legacy_reason = "grant_global_track_aplicado_al_guard_real"
            catalog_allowed = legacy
            catalog_source = "track_grant_operativo"
            catalog_reason = "check_track_refleja_autorizacion_real"
    if action.full_key == "openings.read" and openings_read_grants_enabled():
        if candidate is not None and catalog._is_simple_global_module_grant(candidate):
            legacy = candidate.effect == "allow"
            legacy_source = "openings._require_openings_read+grant"
            legacy_reason = "grant_global_aperturas_aplicado_al_guard_real"
            catalog_allowed = legacy
            catalog_source = "openings_grant_operativo"
            catalog_reason = "check_openings_refleja_autorizacion_real"
    if action.full_key == "internal_documents.view":
        # Ni la proyección genérica True ni un grant de entrada equivalen
        # a permiso sobre un documento concreto. Sin objeto también es
        # no concluyente; con objeto el guard legacy decide por documento.
        catalog_allowed = None
        catalog_reason = (
            "catalogo_no_modela_visibilidad_de_este_documento"
            if document is not None else "document_id_required_for_comparison"
        )
    if branch_id is not None:
        # La decisión base no certifica autorización sobre un registro/sucursal.
        # Solo Track/operadores globales no tienen el filtro de sucursal en sus guards base.
        if action.full_key not in (
            set(WAREHOUSE_FLAGS) | set(PLANNING_FLAGS) |
            {"warehouse.catalogs", "track.read", "track.run_daily_pipeline",
             "track.run_agregadoras", "internal_documents.manage", "internal_documents.view",
             "inventory.master_write", "inventory.movement_write", "tickets.delete_all"}
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
             "track.run_agregadoras", "internal_documents.manage",
             "inventory.master_write", "tickets.delete_all"}
        ) else "sucursal" if legacy is not None and action.full_key == "inventory.movement_write" and branch_id is not None
        else "guard_rol_base" if legacy is not None and action.full_key in {
            "pm.read", "pm.execute", "pm.validate", "pm.configure"
        } else "documento" if document and action.full_key == "internal_documents.view"
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
        sort_by, sort_dir, group_by, decision = _matrix_controls()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    module_key = (request.args.get("module_key") or "").strip()[:120]
    action_key = (request.args.get("action_key") or "").strip()[:240]
    document = None
    if document_id:
        # links y visibility_rules son lazy="dynamic"; selectinload no admite
        # estas relaciones y provocaba InvalidRequestError / HTTP 500.
        # El guard de Nube consulta visibilidad por su predicado legacy.
        document = InternalDocumentORM.query.filter_by(id=document_id).first()
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
        candidates = actions_query.count()
        if candidates > MAX_AUDIT_CANDIDATES:
            return jsonify({"error": "Demasiadas acciones; filtra por módulo/acción"}), 422
        actions = actions_query.order_by(PermissionActionORM.full_key).all()
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
        candidates = user_query.count()
        if candidates > MAX_AUDIT_CANDIDATES:
            return jsonify({"error": "Demasiados usuarios; usa búsqueda o rol para acotar"}), 422
        users = user_query.order_by(UserORM.username, UserORM.id).all()
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
    unfiltered_total = len(rows)
    filtered, group_counts = _prepare_rows(rows, sort_by, sort_dir, group_by, decision)
    page = filtered[offset:offset + limit]
    return jsonify({
        "status": "ok", "mode": "visual_audit_readonly_v1",
        "track_read_grants_enabled": track_read_grants_enabled(),
        "openings_read_grants_enabled": openings_read_grants_enabled(),
        "note": "Solo consulta. Legacy comprobado únicamente en predicados declarados; no reemplaza enforcement.",
        "view": perspective, "rows": page, "group_counts": group_counts,
        "sorting": {"sort_by": sort_by, "sort_dir": sort_dir, "group_by": group_by, "decision": decision},
        "summary": {
            "total": len(filtered), "unfiltered_total": unfiltered_total,
            "limit": limit, "offset": offset,
            "evaluated": sum(row["legacy_allowed"] is not None for row in filtered),
            "allowed": sum(row["legacy_allowed"] is True for row in filtered),
            "denied": sum(row["legacy_allowed"] is False for row in filtered),
            "unknown": sum(row["legacy_allowed"] is None for row in filtered),
            "differences": sum(row["comparison"] == "diferencia" for row in filtered),
            "matches": sum(row["comparison"] == "coincide" for row in filtered),
        },
        "coverage": {
            "catalog_partial": True,
            "message": "Catálogo parcial: ausencia de mapeo no demuestra ausencia de guard.",
        },
    }), 200
