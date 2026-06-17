# backend/app/utils/internal_documents_access.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flask import jsonify
from flask_jwt_extended import get_jwt, get_jwt_identity
from sqlalchemy import text

from app import db
from app.models.user_model import UserORM
from app.models.internal_documents import (
    InternalDocumentORM,
    InternalDocumentStatus,
    InternalDocumentVisibilityMode,
    InternalDocumentVisibilityORM,
    InternalDocumentVisibilityType,
)


INTERNAL_DOCUMENT_MANAGER_ROLES = {
    "SISTEMAS",
}

INTERNAL_DOCUMENT_MANAGER_USERS = {
    "ADMICORP",
}
COBRANZA_RECURRENTE_TITLE_PREFIX = "COBRANZA RECURRENTE RECHAZADOS"

COBRANZA_RECURRENTE_ALLOWED_ROLES = {
    "GERENTE",
    "GERENTE_REGIONAL",
}

@dataclass(frozen=True)
class InternalDocumentUserContext:
    user_id: int
    username: str | None
    role: str
    sucursal_id: int | None
    sucursales_ids: tuple[int, ...]
    department_id: int | None


def _normalize_role(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None

    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None

    return normalized if normalized > 0 else None


def _normalize_int_tuple(values: Any) -> tuple[int, ...]:
    if values is None:
        return tuple()

    if isinstance(values, (str, int)):
        values = [values]

    normalized: list[int] = []
    seen: set[int] = set()

    try:
        iterator = iter(values)
    except TypeError:
        return tuple()

    for value in iterator:
        item = _normalize_optional_int(value)
        if item is not None and item not in seen:
            seen.add(item)
            normalized.append(item)

    return tuple(normalized)

def _normalize_access_key(value: Any) -> str:
    return str(value or "").strip().upper()


def _document_is_cobranza_recurrente(document: InternalDocumentORM) -> bool:
    title = _normalize_access_key(getattr(document, "title", None))

    return title.startswith(COBRANZA_RECURRENTE_TITLE_PREFIX)


def _get_document_sucursal_keys(document: InternalDocumentORM) -> set[str]:
    sucursal_keys: set[str] = set()

    for link in getattr(document, "links", []) or []:
        if not getattr(link, "is_active", True):
            continue

        entity_type = _normalize_access_key(getattr(link, "entity_type", None))
        entity_key = _normalize_access_key(getattr(link, "entity_key", None))

        if entity_type == "SUCURSAL" and entity_key:
            sucursal_keys.add(entity_key)

    return sucursal_keys


def _get_user_sucursal_keys(context: InternalDocumentUserContext) -> set[str]:
    """
    Devuelve llaves de sucursal del usuario para comparar contra vínculos documentales.

    Incluye:
    - ids de sucursal como texto
    - nombres de sucursal desde tabla sucursales

    Esto es necesario porque los documentos automáticos de cobranza se vinculan
    con entity_key textual, por ejemplo: VILLAS DEL REY.
    """
    sucursal_keys: set[str] = set()

    sucursal_ids: set[int] = set()

    if context.sucursal_id is not None:
        sucursal_ids.add(int(context.sucursal_id))

    for sucursal_id in context.sucursales_ids or tuple():
        if sucursal_id is not None:
            sucursal_ids.add(int(sucursal_id))

    for sucursal_id in sucursal_ids:
        sucursal_keys.add(str(sucursal_id).strip().upper())

    if not sucursal_ids:
        return sucursal_keys

    try:
        for sucursal_id in sucursal_ids:
            row = (
                db.session.execute(
                    text(
                        """
                        select nombre
                        from sucursales
                        where id = :sucursal_id
                        limit 1
                        """
                    ),
                    {"sucursal_id": sucursal_id},
                )
                .mappings()
                .first()
            )

            if row and row.get("nombre"):
                sucursal_keys.add(_normalize_access_key(row.get("nombre")))
    except Exception:
        # Si por algún motivo no se puede resolver el nombre, no rompemos Nube.
        # El acceso seguirá intentando cruzar por id.
        return sucursal_keys

    return sucursal_keys


def can_view_cobranza_recurrente_document(
    document: InternalDocumentORM,
    context: InternalDocumentUserContext,
) -> bool:
    if document is None or context is None:
        return False

    if not _document_is_cobranza_recurrente(document):
        return False

    role = _normalize_access_key(context.role)
    if role not in COBRANZA_RECURRENTE_ALLOWED_ROLES:
        return False

    document_sucursales = _get_document_sucursal_keys(document)
    user_sucursales = _get_user_sucursal_keys(context)

    if not document_sucursales or not user_sucursales:
        return False

    return bool(document_sucursales.intersection(user_sucursales))

def get_current_user_id() -> int | None:
    """
    Obtiene el user_id actual desde el JWT.

    Este helper debe ejecutarse dentro de rutas protegidas con @jwt_required().
    """
    try:
        identity = get_jwt_identity()
    except Exception:
        return None

    return _normalize_optional_int(identity)


def get_current_user() -> UserORM | None:
    """
    Carga el usuario actual desde DB.

    Se usa DB como respaldo real para evitar depender únicamente de claims viejos.
    """
    user_id = get_current_user_id()
    if user_id is None:
        return None

    return UserORM.get_by_id(user_id)


def get_current_internal_document_context() -> InternalDocumentUserContext | None:
    """
    Construye contexto de permisos para Nube Corporativa.

    Fuente primaria:
    - JWT claims para rol/sucursal/sucursales/department_id.

    Respaldo:
    - DB user si algún claim falta o llega incompleto.
    """
    user_id = get_current_user_id()
    if user_id is None:
        return None

    try:
        claims = get_jwt() or {}
    except Exception:
        claims = {}

    user = UserORM.get_by_id(user_id)

    role = _normalize_role(claims.get("rol"))
    if not role and user is not None:
        role = _normalize_role(getattr(user, "rol", None))

    username = getattr(user, "username", None) if user is not None else None

    sucursal_id = _normalize_optional_int(claims.get("sucursal_id"))
    if sucursal_id is None and user is not None:
        sucursal_id = _normalize_optional_int(getattr(user, "sucursal_id", None))

    sucursales_ids = _normalize_int_tuple(claims.get("sucursales_ids"))
    if not sucursales_ids and user is not None:
        sucursales_ids = _normalize_int_tuple(getattr(user, "sucursales_ids", None))

    if sucursal_id is not None and sucursal_id not in sucursales_ids:
        sucursales_ids = tuple([sucursal_id, *sucursales_ids])

    department_id = _normalize_optional_int(claims.get("department_id"))
    if department_id is None and user is not None:
        department_id = _normalize_optional_int(getattr(user, "department_id", None))

    return InternalDocumentUserContext(
        user_id=user_id,
        username=username,
        role=role,
        sucursal_id=sucursal_id,
        sucursales_ids=sucursales_ids,
        department_id=department_id,
    )


def is_internal_document_admin(
    context: InternalDocumentUserContext | None = None,
) -> bool:
    context = context or get_current_internal_document_context()
    if context is None:
        return False

    role = _normalize_role(context.role)
    username = _normalize_role(context.username)

    return (
        role in INTERNAL_DOCUMENT_MANAGER_ROLES
        or username in INTERNAL_DOCUMENT_MANAGER_USERS
    )


def is_internal_document_publisher(
    context: InternalDocumentUserContext | None = None,
) -> bool:
    return is_internal_document_admin(context)


def can_manage_internal_documents(
    context: InternalDocumentUserContext | None = None,
) -> bool:
    """
    Permiso para crear, editar metadata, publicar, archivar,
    reemplazar versiones y administrar visibilidad.

    Regla actual:
    - ADMICORP
    - Rol SISTEMAS
    """
    return is_internal_document_admin(context)


def require_internal_document_manager():
    """
    Valida permisos administrativos de Nube Corporativa.

    Debe usarse dentro de rutas protegidas con @jwt_required().
    Devuelve None si puede continuar.
    Devuelve response 403 si no está autorizado.
    """
    if not can_manage_internal_documents():
        return jsonify(
            {
                "error": "Forbidden",
                "detail": "No autorizado para administrar documentos internos.",
            }
        ), 403

    return None


def _is_document_creator(
    document: InternalDocumentORM,
    context: InternalDocumentUserContext,
) -> bool:
    return document.created_by is not None and int(document.created_by) == context.user_id


def _is_document_owner_user(
    document: InternalDocumentORM,
    context: InternalDocumentUserContext,
) -> bool:
    return (
        document.owner_user_id is not None
        and int(document.owner_user_id) == context.user_id
    )


def _document_has_active_visibility_rules(document_id: int) -> bool:
    return (
        InternalDocumentVisibilityORM.query.filter_by(
            document_id=document_id,
            is_active=True,
        ).first()
        is not None
    )


def _rule_matches_context(
    rule: InternalDocumentVisibilityORM,
    context: InternalDocumentUserContext,
) -> bool:
    visibility_type = _normalize_role(rule.visibility_type)

    if visibility_type == InternalDocumentVisibilityType.GLOBAL:
        return True

    if visibility_type == InternalDocumentVisibilityType.ROLE:
        return _normalize_role(rule.role) == context.role

    if visibility_type == InternalDocumentVisibilityType.DEPARTMENT:
        if context.department_id is None or rule.department_id is None:
            return False
        return int(rule.department_id) == int(context.department_id)

    if visibility_type == InternalDocumentVisibilityType.SUCURSAL:
        if rule.sucursal_id is None:
            return False
        return int(rule.sucursal_id) in context.sucursales_ids

    if visibility_type == InternalDocumentVisibilityType.USER:
        if rule.user_id is None:
            return False
        return int(rule.user_id) == context.user_id

    return False


def _rule_allows_action(
    rule: InternalDocumentVisibilityORM,
    action: str,
) -> bool:
    action = str(action or "").strip().lower()

    if action == "download":
        return bool(rule.can_view and rule.can_download)

    return bool(rule.can_view)


def _has_custom_visibility_access(
    document: InternalDocumentORM,
    context: InternalDocumentUserContext,
    action: str,
) -> bool:
    rules = (
        InternalDocumentVisibilityORM.query.filter_by(
            document_id=document.id,
            is_active=True,
        )
        .order_by(InternalDocumentVisibilityORM.id.asc())
        .all()
    )

    for rule in rules:
        if _rule_matches_context(rule, context) and _rule_allows_action(rule, action):
            return True

    return False


def _has_global_visibility_access(
    document: InternalDocumentORM,
    action: str,
) -> bool:
    """
    GLOBAL abierto solo aplica para documentos no sensibles.

    Si un documento sensible se marca GLOBAL, este helper lo bloquea.
    """
    if bool(document.is_sensitive):
        return False

    action = str(action or "").strip().lower()

    if action == "download":
        return True

    return True


def has_document_visibility_access(
    document: InternalDocumentORM,
    context: InternalDocumentUserContext,
    action: str = "view",
) -> bool:
    """
    Resuelve si el usuario tiene acceso por visibilidad documental.

    No evalúa estado del documento.
    Solo responde si las reglas de visibilidad le dan acceso.
    """
    if document is None or context is None:
        return False

    visibility_mode = _normalize_role(document.visibility_mode)

    if visibility_mode == InternalDocumentVisibilityMode.GLOBAL:
        return _has_global_visibility_access(document, action)

    if visibility_mode == InternalDocumentVisibilityMode.CUSTOM:
        return _has_custom_visibility_access(document, context, action)

    if visibility_mode == InternalDocumentVisibilityMode.PRIVATE:
        return _is_document_creator(document, context) or _is_document_owner_user(
            document,
            context,
        )

    return False


def can_view_internal_document(
    document: InternalDocumentORM,
    context: InternalDocumentUserContext | None = None,
) -> bool:
    """
    Permiso final para ver metadata/detalle de documento.

    Reglas F1:
    - Admin/Sistemas ve todo.
    - BORRADOR solo admin o creador.
    - ARCHIVADO solo admin.
    - PUBLICADO requiere visibilidad.
    - Sensible bloquea GLOBAL y requiere regla específica o admin.
    """
    context = context or get_current_internal_document_context()
    if document is None or context is None:
        return False

    if is_internal_document_admin(context):
        return True

    if document.status == InternalDocumentStatus.DRAFT:
        return _is_document_creator(document, context)

    if document.status == InternalDocumentStatus.ARCHIVED:
        return False

    if document.status != InternalDocumentStatus.PUBLISHED:
        return False

    if can_view_cobranza_recurrente_document(document, context):
        return True

    return has_document_visibility_access(document, context, action="view")


def can_download_internal_document(
    document: InternalDocumentORM,
    context: InternalDocumentUserContext | None = None,
) -> bool:
    """
    Permiso final para descargar documento.

    F1:
    - Si puede ver y tiene regla de descarga, descarga.
    - Para GLOBAL no sensible, descarga.
    - Para sensibles, no se permite GLOBAL abierto.
    """
    context = context or get_current_internal_document_context()
    if document is None or context is None:
        return False

    if is_internal_document_admin(context):
        return document.current_version_id is not None

    if document.current_version_id is None:
        return False

    if document.status != InternalDocumentStatus.PUBLISHED:
        return False

    if not can_view_internal_document(document, context):
        return False

    if can_view_cobranza_recurrente_document(document, context):
        return True

    return has_document_visibility_access(document, context, action="download")


def can_edit_internal_document(
    document: InternalDocumentORM | None = None,
    context: InternalDocumentUserContext | None = None,
) -> bool:
    return can_manage_internal_documents(context)


def can_publish_internal_document(
    document: InternalDocumentORM | None = None,
    context: InternalDocumentUserContext | None = None,
) -> bool:
    return can_manage_internal_documents(context)


def can_archive_internal_document(
    document: InternalDocumentORM | None = None,
    context: InternalDocumentUserContext | None = None,
) -> bool:
    return can_manage_internal_documents(context)


def can_replace_internal_document_version(
    document: InternalDocumentORM | None = None,
    context: InternalDocumentUserContext | None = None,
) -> bool:
    return can_manage_internal_documents(context)


def can_manage_internal_document_visibility(
    document: InternalDocumentORM | None = None,
    context: InternalDocumentUserContext | None = None,
) -> bool:
    return can_manage_internal_documents(context)


def can_view_internal_document_audit(
    document: InternalDocumentORM | None = None,
    context: InternalDocumentUserContext | None = None,
) -> bool:
    return can_manage_internal_documents(context)


def can_download_historical_internal_document_version(
    document: InternalDocumentORM | None = None,
    context: InternalDocumentUserContext | None = None,
) -> bool:
    return can_manage_internal_documents(context)


def build_internal_document_capabilities(
    document: InternalDocumentORM,
    context: InternalDocumentUserContext | None = None,
) -> dict[str, bool]:
    """
    Capacidades calculadas por backend para que Angular oculte/enseñe acciones.

    Importante:
    Aunque el frontend oculte botones, cada endpoint debe volver a validar.
    """
    context = context or get_current_internal_document_context()

    return {
        "can_view": can_view_internal_document(document, context),
        "can_download": can_download_internal_document(document, context),
        "can_edit": can_edit_internal_document(document, context),
        "can_publish": can_publish_internal_document(document, context),
        "can_archive": can_archive_internal_document(document, context),
        "can_replace_version": can_replace_internal_document_version(
            document,
            context,
        ),
        "can_manage_visibility": can_manage_internal_document_visibility(
            document,
            context,
        ),
        "can_view_audit": can_view_internal_document_audit(document, context),
        "can_download_historical_versions": (
            can_download_historical_internal_document_version(document, context)
        ),
    }


def require_internal_document_view_access(document: InternalDocumentORM):
    if not can_view_internal_document(document):
        return jsonify(
            {
                "error": "Forbidden",
                "detail": "No autorizado para ver este documento.",
            }
        ), 403

    return None


def require_internal_document_download_access(document: InternalDocumentORM):
    if not can_download_internal_document(document):
        return jsonify(
            {
                "error": "Forbidden",
                "detail": "No autorizado para descargar este documento.",
            }
        ), 403

    return None


def require_internal_document_audit_access(document: InternalDocumentORM):
    if not can_view_internal_document_audit(document):
        return jsonify(
            {
                "error": "Forbidden",
                "detail": "No autorizado para consultar auditoría de este documento.",
            }
        ), 403

    return None


def validate_internal_document_publish_preconditions(
    document: InternalDocumentORM,
) -> list[str]:
    """
    Validaciones previas a publicar.

    Devuelve lista de errores legibles.
    Si devuelve lista vacía, el documento puede publicarse.
    """
    errors: list[str] = []

    if document is None:
        return ["Documento no encontrado."]

    if not str(document.title or "").strip():
        errors.append("El título es obligatorio.")

    if not str(document.description or "").strip():
        errors.append("La descripción es obligatoria para publicar.")

    if document.category_id is None:
        errors.append("La categoría es obligatoria.")

    if document.owner_user_id is None and document.owner_department_id is None:
        errors.append("El dueño documental es obligatorio.")

    if document.current_version_id is None:
        errors.append("El documento debe tener una versión vigente.")

    visibility_mode = _normalize_role(document.visibility_mode)

    if visibility_mode == InternalDocumentVisibilityMode.PRIVATE:
        errors.append("Configura la visibilidad antes de publicar.")

    if visibility_mode == InternalDocumentVisibilityMode.CUSTOM:
        if not _document_has_active_visibility_rules(document.id):
            errors.append("Configura al menos una regla de visibilidad activa.")

    if bool(document.is_sensitive) and visibility_mode == InternalDocumentVisibilityMode.GLOBAL:
        errors.append("Un documento sensible no puede publicarse con visibilidad global.")

    if visibility_mode not in InternalDocumentVisibilityMode.ALL:
        errors.append("La visibilidad del documento no es válida.")

    if document.status == InternalDocumentStatus.ARCHIVED:
        errors.append("Un documento archivado no puede publicarse sin restaurarse primero.")

    return errors