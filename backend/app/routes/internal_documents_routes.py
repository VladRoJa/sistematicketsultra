# backend/app/routes/internal_documents_routes.py

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_jwt_extended import jwt_required
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import (
    InternalDocumentAuditLogORM,
    InternalDocumentCategoryORM,
    InternalDocumentORM,
    InternalDocumentStatus,
    InternalDocumentVersionORM,
    InternalDocumentVisibilityMode,
    InternalDocumentVisibilityORM,
    InternalDocumentVisibilityType,
    WarehouseUploadORM,
)
from app.utils.internal_documents_access import (
    build_internal_document_capabilities,
    can_download_historical_internal_document_version,
    can_view_internal_document,
    can_view_internal_document_audit,
    get_current_internal_document_context,
    require_internal_document_audit_access,
    require_internal_document_download_access,
    require_internal_document_manager,
    require_internal_document_view_access,
    validate_internal_document_publish_preconditions,
)
from app.warehouse.services.warehouse_document_upload_service import (
    WarehouseDocumentUploadError,
    WarehouseDocumentValidationError,
    create_warehouse_document_upload,
)


internal_documents_bp = Blueprint("internal_documents", __name__)

INTERNAL_DOCUMENTS_REPORT_TYPE_KEY = "internal_documents"
INTERNAL_DOCUMENTS_LOCAL_TZ = ZoneInfo("America/Tijuana")
INTERNAL_DOCUMENT_MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024

INTERNAL_DOCUMENT_ALLOWED_EXTENSIONS = {
    "xlsx",
    "xls",
    "csv",
    "pdf",
    "txt",
    "docx",
    "pptx",
    "png",
    "jpg",
    "jpeg",
}


def _now_tijuana() -> datetime:
    return datetime.now(INTERNAL_DOCUMENTS_LOCAL_TZ)


def _today_tijuana() -> date:
    return _now_tijuana().date()


def _json_error(error: str, detail: str, status_code: int):
    return jsonify({"error": error, "detail": detail}), status_code


def _parse_positive_int(
    raw_value: Any,
    *,
    default: int,
    minimum: int = 1,
    maximum: int | None = None,
) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = default

    value = max(value, minimum)

    if maximum is not None:
        value = min(value, maximum)

    return value


def _parse_optional_int(raw_value: Any) -> int | None:
    if raw_value is None or raw_value == "":
        return None

    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return None

    return value if value > 0 else None


def _parse_bool(raw_value: Any, *, default: bool = False) -> bool:
    if raw_value is None:
        return default

    if isinstance(raw_value, bool):
        return raw_value

    value = str(raw_value).strip().lower()

    if value in {"1", "true", "t", "yes", "y", "si", "sí"}:
        return True

    if value in {"0", "false", "f", "no", "n"}:
        return False

    return default


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_upper(value: Any) -> str:
    return _normalize_text(value).upper()


def _get_file_extension(filename: str) -> str:
    value = _normalize_text(filename)
    if "." not in value:
        return ""
    return value.rsplit(".", 1)[-1].lower()


def _read_uploaded_file_or_error(uploaded_file):
    if not uploaded_file or not uploaded_file.filename:
        return None, _json_error(
            "Archivo inválido",
            "El archivo enviado no tiene nombre válido.",
            400,
        )

    extension = _get_file_extension(uploaded_file.filename)
    if extension not in INTERNAL_DOCUMENT_ALLOWED_EXTENSIONS:
        return None, _json_error(
            "Extensión no permitida",
            f"La extensión '{extension or 'sin extensión'}' no está permitida para Nube Corporativa.",
            400,
        )

    file_bytes = uploaded_file.read()
    if not file_bytes:
        return None, _json_error(
            "Archivo vacío",
            "El archivo enviado está vacío.",
            400,
        )

    if len(file_bytes) > INTERNAL_DOCUMENT_MAX_FILE_SIZE_BYTES:
        return None, _json_error(
            "Archivo demasiado grande",
            "El archivo excede el tamaño máximo permitido de 50 MB para Nube Corporativa.",
            400,
        )

    return file_bytes, None


def _get_json_payload() -> dict[str, Any]:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _get_current_user_id_or_response():
    context = get_current_internal_document_context()
    if context is None:
        return None, _json_error(
            "Sesión inválida",
            "No se pudo resolver el usuario autenticado actual.",
            401,
        )

    return context.user_id, None


def _get_document_or_404(document_id: int) -> InternalDocumentORM | None:
    return (
        InternalDocumentORM.query.options(
            joinedload(InternalDocumentORM.category),
            joinedload(InternalDocumentORM.current_version).joinedload(
                InternalDocumentVersionORM.warehouse_upload
            ),
            joinedload(InternalDocumentORM.owner_user),
            joinedload(InternalDocumentORM.owner_department),
            joinedload(InternalDocumentORM.creator),
            joinedload(InternalDocumentORM.publisher),
            joinedload(InternalDocumentORM.archiver),
        )
        .filter_by(id=document_id)
        .first()
    )


def _get_category_or_error(category_id: int | None):
    if category_id is None:
        return None, _json_error(
            "Categoría requerida",
            "Debes seleccionar una categoría válida.",
            400,
        )

    category = InternalDocumentCategoryORM.query.filter_by(
        id=category_id,
        is_active=True,
    ).first()

    if not category:
        return None, _json_error(
            "Categoría no encontrada",
            f"No existe una categoría activa con id {category_id}.",
            404,
        )

    return category, None


def _serialize_category(category: InternalDocumentCategoryORM) -> dict[str, Any]:
    return {
        "id": category.id,
        "key": category.key,
        "name": category.name,
        "description": category.description,
        "is_active": category.is_active,
        "sort_order": category.sort_order,
    }


def _serialize_user_snapshot(user) -> dict[str, Any] | None:
    if not user:
        return None

    return {
        "id": getattr(user, "id", None),
        "username": getattr(user, "username", None),
        "rol": getattr(user, "rol", None),
    }


def _serialize_department_snapshot(department) -> dict[str, Any] | None:
    if not department:
        return None

    return {
        "id": getattr(department, "id", None),
        "nombre": getattr(department, "nombre", None),
    }


def _serialize_upload_snapshot(upload: WarehouseUploadORM | None) -> dict[str, Any] | None:
    if not upload:
        return None

    return {
        "id": upload.id,
        "original_filename": upload.original_filename,
        "stored_filename": upload.stored_filename,
        "file_size_bytes": upload.file_size_bytes,
        "file_hash_sha256": upload.file_hash_sha256,
        "mime_type": upload.mime_type,
        "extension": upload.extension,
        "report_type_id": upload.report_type_id,
        "period_type": upload.period_type,
        "cutoff_date": upload.cutoff_date.isoformat() if upload.cutoff_date else None,
        "date_from": upload.date_from.isoformat() if upload.date_from else None,
        "date_to": upload.date_to.isoformat() if upload.date_to else None,
        "status": upload.status,
    }


def _serialize_version(
    version: InternalDocumentVersionORM,
    *,
    include_upload: bool = False,
) -> dict[str, Any]:
    payload = {
        "id": version.id,
        "document_id": version.document_id,
        "warehouse_upload_id": version.warehouse_upload_id,
        "version_label": version.version_label,
        "version_number": version.version_number,
        "original_filename": version.original_filename,
        "file_mime_type": version.file_mime_type,
        "file_size_bytes": version.file_size_bytes,
        "file_hash_sha256": version.file_hash_sha256,
        "change_notes": version.change_notes,
        "is_current": version.is_current,
        "is_hidden_from_users": version.is_hidden_from_users,
        "created_by": version.created_by,
        "created_at": version.created_at.isoformat() if version.created_at else None,
    }

    if include_upload:
        payload["warehouse_upload"] = _serialize_upload_snapshot(
            version.warehouse_upload
        )

    return payload


def _serialize_visibility_rule(
    rule: InternalDocumentVisibilityORM,
) -> dict[str, Any]:
    return {
        "id": rule.id,
        "document_id": rule.document_id,
        "visibility_type": rule.visibility_type,
        "role": rule.role,
        "department_id": rule.department_id,
        "sucursal_id": rule.sucursal_id,
        "user_id": rule.user_id,
        "can_view": rule.can_view,
        "can_download": rule.can_download,
        "is_active": rule.is_active,
        "created_by": rule.created_by,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
    }


def _serialize_audit_log(item: InternalDocumentAuditLogORM) -> dict[str, Any]:
    return {
        "id": item.id,
        "document_id": item.document_id,
        "version_id": item.version_id,
        "actor_user_id": item.actor_user_id,
        "action": item.action,
        "old_value_json": item.old_value_json,
        "new_value_json": item.new_value_json,
        "metadata_json": item.metadata_json,
        "ip_address": item.ip_address,
        "user_agent": item.user_agent,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _serialize_document(
    document: InternalDocumentORM,
    *,
    include_details: bool = False,
    include_versions: bool = False,
    include_visibility: bool = False,
) -> dict[str, Any]:
    capabilities = build_internal_document_capabilities(document)

    payload = {
        "id": document.id,
        "title": document.title,
        "description": document.description,
        "category_id": document.category_id,
        "category": _serialize_category(document.category) if document.category else None,
        "document_type": document.document_type,
        "owner_user_id": document.owner_user_id,
        "owner_department_id": document.owner_department_id,
        "owner_user": _serialize_user_snapshot(document.owner_user),
        "owner_department": _serialize_department_snapshot(document.owner_department),
        "status": document.status,
        "is_sensitive": document.is_sensitive,
        "current_version_id": document.current_version_id,
        "visibility_mode": document.visibility_mode,
        "published_by": document.published_by,
        "published_at": document.published_at.isoformat() if document.published_at else None,
        "archived_by": document.archived_by,
        "archived_at": document.archived_at.isoformat() if document.archived_at else None,
        "created_by": document.created_by,
        "updated_by": document.updated_by,
        "created_at": document.created_at.isoformat() if document.created_at else None,
        "updated_at": document.updated_at.isoformat() if document.updated_at else None,
        "capabilities": capabilities,
    }

    if document.current_version:
        payload["current_version"] = _serialize_version(
            document.current_version,
            include_upload=include_details,
        )
    else:
        payload["current_version"] = None

    if include_versions:
        versions = (
            InternalDocumentVersionORM.query.options(
                joinedload(InternalDocumentVersionORM.warehouse_upload)
            )
            .filter_by(document_id=document.id)
            .order_by(InternalDocumentVersionORM.version_number.asc())
            .all()
        )

        payload["versions"] = [
            _serialize_version(version, include_upload=True)
            for version in versions
        ]

    if include_visibility:
        rules = (
            InternalDocumentVisibilityORM.query.filter_by(document_id=document.id)
            .order_by(InternalDocumentVisibilityORM.id.asc())
            .all()
        )
        payload["visibility_rules"] = [
            _serialize_visibility_rule(rule)
            for rule in rules
        ]

    return payload


def _log_document_audit(
    *,
    document_id: int,
    actor_user_id: int | None,
    action: str,
    version_id: int | None = None,
    old_value_json: dict[str, Any] | None = None,
    new_value_json: dict[str, Any] | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> None:
    db.session.add(
        InternalDocumentAuditLogORM(
            document_id=document_id,
            version_id=version_id,
            actor_user_id=actor_user_id,
            action=action,
            old_value_json=old_value_json,
            new_value_json=new_value_json,
            metadata_json=metadata_json,
            ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
            user_agent=request.headers.get("User-Agent"),
        )
    )


def _build_safe_file_path(upload: WarehouseUploadORM) -> Path | None:
    if not upload or not upload.stored_path or not upload.stored_filename:
        return None

    base_dir = Path(current_app.root_path).parent.parent.resolve()
    file_path = (base_dir / upload.stored_path / upload.stored_filename).resolve()

    try:
        file_path.relative_to(base_dir)
    except ValueError:
        return None

    if not file_path.exists() or not file_path.is_file():
        return None

    return file_path


def _next_version_number(document_id: int) -> int:
    max_version = (
        db.session.query(db.func.max(InternalDocumentVersionORM.version_number))
        .filter(InternalDocumentVersionORM.document_id == document_id)
        .scalar()
    )

    return int(max_version or 0) + 1


def _default_version_label(version_number: int) -> str:
    if version_number <= 1:
        return "1.0"

    return f"1.{version_number - 1}"


def _apply_document_filters(query):
    q = _normalize_text(request.args.get("q"))
    category_id = _parse_optional_int(request.args.get("category_id"))
    owner_department_id = _parse_optional_int(request.args.get("owner_department_id"))
    is_sensitive_raw = request.args.get("is_sensitive")

    if q:
        search_pattern = f"%{q}%"
        query = query.filter(
            or_(
                InternalDocumentORM.title.ilike(search_pattern),
                InternalDocumentORM.description.ilike(search_pattern),
                InternalDocumentORM.document_type.ilike(search_pattern),
            )
        )

    if category_id is not None:
        query = query.filter(InternalDocumentORM.category_id == category_id)

    if owner_department_id is not None:
        query = query.filter(
            InternalDocumentORM.owner_department_id == owner_department_id
        )

    if is_sensitive_raw is not None and str(is_sensitive_raw).strip() != "":
        query = query.filter(
            InternalDocumentORM.is_sensitive == _parse_bool(is_sensitive_raw)
        )

    return query


def _paginate_python_items(items: list[Any], *, page: int, page_size: int):
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    paged_items = items[start:end]
    total_pages = (total + page_size - 1) // page_size if total else 0

    return {
        "items": paged_items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }


@internal_documents_bp.route("/access", methods=["GET"])
@jwt_required()
def internal_documents_access():
    context = get_current_internal_document_context()
    if context is None:
        return _json_error(
            "Sesión inválida",
            "No se pudo resolver el usuario autenticado actual.",
            401,
        )

    allowed_roles = {"ADMIN", "ADMINISTRADOR", "SUPER_ADMIN", "SISTEMAS"}
    allowed = context.role in allowed_roles

    return jsonify(
        {
            "allowed": allowed,
            "module": "internal_documents",
            "user": {
                "id": context.user_id,
                "username": context.username,
                "role": context.role,
                "sucursal_id": context.sucursal_id,
                "sucursales_ids": list(context.sucursales_ids),
                "department_id": context.department_id,
            },
            "can_manage": allowed,
        }
    ), 200


@internal_documents_bp.route("/categories", methods=["GET"])
@jwt_required()
def list_internal_document_categories():
    categories = (
        InternalDocumentCategoryORM.query.filter_by(is_active=True)
        .order_by(
            InternalDocumentCategoryORM.sort_order.asc(),
            InternalDocumentCategoryORM.name.asc(),
        )
        .all()
    )

    return jsonify({"items": [_serialize_category(item) for item in categories]}), 200


@internal_documents_bp.route("", methods=["GET"])
@jwt_required()
def list_internal_documents():
    context = get_current_internal_document_context()
    if context is None:
        return _json_error(
            "Sesión inválida",
            "No se pudo resolver el usuario autenticado actual.",
            401,
        )

    page = _parse_positive_int(
        request.args.get("page"),
        default=1,
        minimum=1,
    )
    page_size = _parse_positive_int(
        request.args.get("page_size"),
        default=25,
        minimum=1,
        maximum=100,
    )

    query = InternalDocumentORM.query.options(
        joinedload(InternalDocumentORM.category),
        joinedload(InternalDocumentORM.current_version),
        joinedload(InternalDocumentORM.owner_user),
        joinedload(InternalDocumentORM.owner_department),
    )

    query = _apply_document_filters(query)

    requested_status = _normalize_upper(request.args.get("status"))

    can_manage = context.role in {"ADMIN", "ADMINISTRADOR", "SUPER_ADMIN", "SISTEMAS"}

    if can_manage:
        if requested_status and requested_status != "ALL":
            query = query.filter(InternalDocumentORM.status == requested_status)
    else:
        query = query.filter(InternalDocumentORM.status == InternalDocumentStatus.PUBLISHED)

    query = query.order_by(InternalDocumentORM.created_at.desc())

    if can_manage:
        pagination = query.paginate(
            page=page,
            per_page=page_size,
            error_out=False,
        )

        return jsonify(
            {
                "items": [
                    _serialize_document(item)
                    for item in pagination.items
                ],
                "page": pagination.page,
                "page_size": pagination.per_page,
                "total": pagination.total,
                "total_pages": pagination.pages,
                "has_next": pagination.has_next,
                "has_prev": pagination.has_prev,
            }
        ), 200

    visible_items = [
        item
        for item in query.all()
        if can_view_internal_document(item, context)
    ]

    paginated = _paginate_python_items(
        visible_items,
        page=page,
        page_size=page_size,
    )

    return jsonify(
        {
            **paginated,
            "items": [
                _serialize_document(item)
                for item in paginated["items"]
            ],
        }
    ), 200


@internal_documents_bp.route("/<int:document_id>", methods=["GET"])
@jwt_required()
def get_internal_document_detail(document_id: int):
    document = _get_document_or_404(document_id)

    if not document:
        return _json_error(
            "Documento no encontrado",
            f"No existe un documento interno con id {document_id}.",
            404,
        )

    forbidden = require_internal_document_view_access(document)
    if forbidden:
        return forbidden

    include_admin_data = can_view_internal_document_audit(document)

    return jsonify(
        _serialize_document(
            document,
            include_details=True,
            include_versions=include_admin_data,
            include_visibility=include_admin_data,
        )
    ), 200


@internal_documents_bp.route("", methods=["POST"])
@jwt_required()
def create_internal_document():
    forbidden = require_internal_document_manager()
    if forbidden:
        return forbidden

    current_user_id, error_response = _get_current_user_id_or_response()
    if error_response:
        return error_response

    if "file" not in request.files:
        return _json_error(
            "Archivo requerido",
            "Debes enviar un archivo en el campo 'file'.",
            400,
        )

    uploaded_file = request.files["file"]
    file_bytes, file_error = _read_uploaded_file_or_error(uploaded_file)
    if file_error:
        return file_error

    title = _normalize_text(request.form.get("title"))
    if not title:
        return _json_error(
            "Título requerido",
            "El título del documento es obligatorio.",
            400,
        )

    category_id = _parse_optional_int(request.form.get("category_id"))
    category, category_error = _get_category_or_error(category_id)
    if category_error:
        return category_error

    description = _normalize_text(request.form.get("description")) or None
    document_type = _normalize_text(request.form.get("document_type")) or None
    owner_user_id = _parse_optional_int(request.form.get("owner_user_id"))
    owner_department_id = _parse_optional_int(request.form.get("owner_department_id"))
    is_sensitive = _parse_bool(request.form.get("is_sensitive"), default=False)
    version_label = _normalize_text(request.form.get("version_label")) or "1.0"
    change_notes = _normalize_text(request.form.get("change_notes")) or "Versión inicial"

    cutoff_date_raw = _normalize_text(request.form.get("cutoff_date"))
    cutoff_date = cutoff_date_raw or _today_tijuana().isoformat()

    try:
        upload_result = create_warehouse_document_upload(
            report_type_key=INTERNAL_DOCUMENTS_REPORT_TYPE_KEY,
            original_filename=uploaded_file.filename,
            content_type=uploaded_file.mimetype,
            file_bytes=file_bytes,
            uploaded_by_user_id=current_user_id,
            cutoff_date=cutoff_date,
            audit_details={
                "upload_origin": "internal_documents_portal",
                "portal_document_title": title,
            },
        )
    except WarehouseDocumentValidationError as exc:
        return _json_error("No se pudo crear el upload", str(exc), 400)
    except WarehouseDocumentUploadError as exc:
        current_app.logger.exception(
            "Error controlado creando upload para Nube Corporativa."
        )
        return _json_error("No se pudo crear el upload", str(exc), 500)
    except Exception:
        current_app.logger.exception(
            "Error inesperado creando upload para Nube Corporativa."
        )
        return _json_error(
            "No se pudo crear el upload",
            "Ocurrió un error al guardar el archivo en Warehouse.",
            500,
        )

    upload = WarehouseUploadORM.query.filter_by(
        id=upload_result["warehouse_upload_id"]
    ).first()

    if not upload:
        return _json_error(
            "Upload no encontrado",
            "Warehouse creó el upload, pero no se pudo cargar el registro generado.",
            500,
        )

    try:
        document = InternalDocumentORM(
            title=title,
            description=description,
            category_id=category.id,
            document_type=document_type,
            owner_user_id=owner_user_id,
            owner_department_id=owner_department_id,
            status=InternalDocumentStatus.DRAFT,
            is_sensitive=is_sensitive,
            visibility_mode=InternalDocumentVisibilityMode.PRIVATE,
            created_by=current_user_id,
            updated_by=current_user_id,
        )

        db.session.add(document)
        db.session.flush()

        version = InternalDocumentVersionORM(
            document_id=document.id,
            warehouse_upload_id=upload.id,
            version_label=version_label,
            version_number=1,
            original_filename=upload.original_filename,
            file_mime_type=upload.mime_type,
            file_size_bytes=upload.file_size_bytes,
            file_hash_sha256=upload.file_hash_sha256,
            change_notes=change_notes,
            is_current=True,
            is_hidden_from_users=False,
            created_by=current_user_id,
        )

        db.session.add(version)
        db.session.flush()

        document.current_version_id = version.id

        _log_document_audit(
            document_id=document.id,
            version_id=version.id,
            actor_user_id=current_user_id,
            action="DOCUMENT_CREATED",
            new_value_json={
                "title": document.title,
                "category_id": document.category_id,
                "status": document.status,
                "warehouse_upload_id": upload.id,
            },
        )
        _log_document_audit(
            document_id=document.id,
            version_id=version.id,
            actor_user_id=current_user_id,
            action="DOCUMENT_VERSION_CREATED",
            new_value_json={
                "version_label": version.version_label,
                "version_number": version.version_number,
                "warehouse_upload_id": upload.id,
            },
        )

        db.session.commit()

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Error creando documento interno después de crear upload en Warehouse."
        )
        return _json_error(
            "Documento no creado",
            "El archivo quedó registrado en Warehouse, pero falló la creación de la publicación documental.",
            500,
        )

    document = _get_document_or_404(document.id)

    return jsonify(
        {
            "message": "Documento creado como borrador",
            "item": _serialize_document(
                document,
                include_details=True,
                include_versions=True,
                include_visibility=True,
            ),
        }
    ), 201


@internal_documents_bp.route("/<int:document_id>", methods=["PATCH"])
@jwt_required()
def update_internal_document_metadata(document_id: int):
    forbidden = require_internal_document_manager()
    if forbidden:
        return forbidden

    current_user_id, error_response = _get_current_user_id_or_response()
    if error_response:
        return error_response

    document = _get_document_or_404(document_id)
    if not document:
        return _json_error(
            "Documento no encontrado",
            f"No existe un documento interno con id {document_id}.",
            404,
        )

    payload = _get_json_payload()
    old_values: dict[str, Any] = {}
    new_values: dict[str, Any] = {}

    allowed_fields = {
        "title",
        "description",
        "category_id",
        "document_type",
        "owner_user_id",
        "owner_department_id",
        "is_sensitive",
    }

    for field in allowed_fields:
        if field not in payload:
            continue

        old_values[field] = getattr(document, field)

        if field in {"category_id", "owner_user_id", "owner_department_id"}:
            setattr(document, field, _parse_optional_int(payload.get(field)))
        elif field == "is_sensitive":
            setattr(document, field, _parse_bool(payload.get(field)))
        else:
            setattr(document, field, _normalize_text(payload.get(field)) or None)

        new_values[field] = getattr(document, field)

    if "title" in payload and not _normalize_text(document.title):
        return _json_error(
            "Título requerido",
            "El título del documento no puede quedar vacío.",
            400,
        )

    if "category_id" in payload:
        category, category_error = _get_category_or_error(document.category_id)
        if category_error:
            return category_error

    document.updated_by = current_user_id

    _log_document_audit(
        document_id=document.id,
        actor_user_id=current_user_id,
        action="DOCUMENT_METADATA_UPDATED",
        old_value_json=old_values,
        new_value_json=new_values,
    )

    db.session.commit()

    document = _get_document_or_404(document.id)

    return jsonify(
        {
            "message": "Metadata actualizada",
            "item": _serialize_document(
                document,
                include_details=True,
                include_versions=True,
                include_visibility=True,
            ),
        }
    ), 200


@internal_documents_bp.route("/<int:document_id>/publish", methods=["POST"])
@jwt_required()
def publish_internal_document(document_id: int):
    forbidden = require_internal_document_manager()
    if forbidden:
        return forbidden

    current_user_id, error_response = _get_current_user_id_or_response()
    if error_response:
        return error_response

    document = _get_document_or_404(document_id)
    if not document:
        return _json_error(
            "Documento no encontrado",
            f"No existe un documento interno con id {document_id}.",
            404,
        )

    errors = validate_internal_document_publish_preconditions(document)
    if errors:
        return jsonify(
            {
                "error": "No se puede publicar",
                "detail": "El documento no cumple los requisitos para publicarse.",
                "errors": errors,
            }
        ), 400

    old_status = document.status

    document.status = InternalDocumentStatus.PUBLISHED
    document.published_by = current_user_id
    document.published_at = _now_tijuana()
    document.updated_by = current_user_id

    _log_document_audit(
        document_id=document.id,
        actor_user_id=current_user_id,
        action="DOCUMENT_PUBLISHED",
        old_value_json={"status": old_status},
        new_value_json={
            "status": document.status,
            "published_by": document.published_by,
            "published_at": document.published_at.isoformat(),
        },
    )

    db.session.commit()

    document = _get_document_or_404(document.id)

    return jsonify(
        {
            "message": "Documento publicado",
            "item": _serialize_document(document, include_details=True),
        }
    ), 200


@internal_documents_bp.route("/<int:document_id>/archive", methods=["POST"])
@jwt_required()
def archive_internal_document(document_id: int):
    forbidden = require_internal_document_manager()
    if forbidden:
        return forbidden

    current_user_id, error_response = _get_current_user_id_or_response()
    if error_response:
        return error_response

    document = _get_document_or_404(document_id)
    if not document:
        return _json_error(
            "Documento no encontrado",
            f"No existe un documento interno con id {document_id}.",
            404,
        )

    if document.status == InternalDocumentStatus.ARCHIVED:
        return _json_error(
            "Documento ya archivado",
            "El documento ya se encuentra archivado.",
            400,
        )

    old_status = document.status

    document.status = InternalDocumentStatus.ARCHIVED
    document.archived_by = current_user_id
    document.archived_at = _now_tijuana()
    document.updated_by = current_user_id

    _log_document_audit(
        document_id=document.id,
        actor_user_id=current_user_id,
        action="DOCUMENT_ARCHIVED",
        old_value_json={"status": old_status},
        new_value_json={
            "status": document.status,
            "archived_by": document.archived_by,
            "archived_at": document.archived_at.isoformat(),
        },
    )

    db.session.commit()

    document = _get_document_or_404(document.id)

    return jsonify(
        {
            "message": "Documento archivado",
            "item": _serialize_document(document, include_details=True),
        }
    ), 200


@internal_documents_bp.route("/<int:document_id>/versions", methods=["POST"])
@jwt_required()
def replace_internal_document_version(document_id: int):
    forbidden = require_internal_document_manager()
    if forbidden:
        return forbidden

    current_user_id, error_response = _get_current_user_id_or_response()
    if error_response:
        return error_response

    document = _get_document_or_404(document_id)
    if not document:
        return _json_error(
            "Documento no encontrado",
            f"No existe un documento interno con id {document_id}.",
            404,
        )

    if "file" not in request.files:
        return _json_error(
            "Archivo requerido",
            "Debes enviar un archivo en el campo 'file'.",
            400,
        )

    uploaded_file = request.files["file"]
    file_bytes, file_error = _read_uploaded_file_or_error(uploaded_file)
    if file_error:
        return file_error

    change_notes = _normalize_text(request.form.get("change_notes"))
    if not change_notes:
        return _json_error(
            "Notas de cambio requeridas",
            "Debes indicar notas de cambio para reemplazar la versión.",
            400,
        )

    next_version_number = _next_version_number(document.id)
    version_label = (
        _normalize_text(request.form.get("version_label"))
        or _default_version_label(next_version_number)
    )

    cutoff_date_raw = _normalize_text(request.form.get("cutoff_date"))
    cutoff_date = cutoff_date_raw or _today_tijuana().isoformat()

    try:
        upload_result = create_warehouse_document_upload(
            report_type_key=INTERNAL_DOCUMENTS_REPORT_TYPE_KEY,
            original_filename=uploaded_file.filename,
            content_type=uploaded_file.mimetype,
            file_bytes=file_bytes,
            uploaded_by_user_id=current_user_id,
            cutoff_date=cutoff_date,
            audit_details={
                "upload_origin": "internal_documents_portal_version_replace",
                "portal_document_id": document.id,
                "portal_document_title": document.title,
            },
        )
    except WarehouseDocumentValidationError as exc:
        return _json_error("No se pudo crear el upload", str(exc), 400)
    except WarehouseDocumentUploadError as exc:
        current_app.logger.exception(
            "Error controlado creando upload de nueva versión documental."
        )
        return _json_error("No se pudo crear el upload", str(exc), 500)
    except Exception:
        current_app.logger.exception(
            "Error inesperado creando upload de nueva versión documental."
        )
        return _json_error(
            "No se pudo crear el upload",
            "Ocurrió un error al guardar la nueva versión en Warehouse.",
            500,
        )

    upload = WarehouseUploadORM.query.filter_by(
        id=upload_result["warehouse_upload_id"]
    ).first()

    if not upload:
        return _json_error(
            "Upload no encontrado",
            "Warehouse creó el upload, pero no se pudo cargar el registro generado.",
            500,
        )

    old_version_id = document.current_version_id

    current_version = document.current_version
    if current_version:
        current_version.is_current = False
        current_version.is_hidden_from_users = True

    version = InternalDocumentVersionORM(
        document_id=document.id,
        warehouse_upload_id=upload.id,
        version_label=version_label,
        version_number=next_version_number,
        original_filename=upload.original_filename,
        file_mime_type=upload.mime_type,
        file_size_bytes=upload.file_size_bytes,
        file_hash_sha256=upload.file_hash_sha256,
        change_notes=change_notes,
        is_current=True,
        is_hidden_from_users=False,
        created_by=current_user_id,
    )

    db.session.add(version)
    db.session.flush()

    document.current_version_id = version.id
    document.updated_by = current_user_id

    _log_document_audit(
        document_id=document.id,
        version_id=version.id,
        actor_user_id=current_user_id,
        action="DOCUMENT_VERSION_REPLACED",
        old_value_json={"current_version_id": old_version_id},
        new_value_json={
            "current_version_id": version.id,
            "version_label": version.version_label,
            "version_number": version.version_number,
            "warehouse_upload_id": upload.id,
        },
    )

    db.session.commit()

    document = _get_document_or_404(document.id)

    return jsonify(
        {
            "message": "Versión reemplazada",
            "item": _serialize_document(
                document,
                include_details=True,
                include_versions=True,
            ),
        }
    ), 201


@internal_documents_bp.route("/<int:document_id>/versions", methods=["GET"])
@jwt_required()
def list_internal_document_versions(document_id: int):
    document = _get_document_or_404(document_id)
    if not document:
        return _json_error(
            "Documento no encontrado",
            f"No existe un documento interno con id {document_id}.",
            404,
        )

    forbidden = require_internal_document_view_access(document)
    if forbidden:
        return forbidden

    can_see_historical = can_download_historical_internal_document_version(document)

    query = InternalDocumentVersionORM.query.options(
        joinedload(InternalDocumentVersionORM.warehouse_upload)
    ).filter_by(document_id=document.id)

    if not can_see_historical:
        query = query.filter(
            InternalDocumentVersionORM.is_current.is_(True),
            InternalDocumentVersionORM.is_hidden_from_users.is_(False),
        )

    versions = query.order_by(
        InternalDocumentVersionORM.version_number.asc()
    ).all()

    return jsonify(
        {
            "items": [
                _serialize_version(version, include_upload=can_see_historical)
                for version in versions
            ]
        }
    ), 200


@internal_documents_bp.route("/<int:document_id>/visibility", methods=["PUT"])
@jwt_required()
def update_internal_document_visibility(document_id: int):
    forbidden = require_internal_document_manager()
    if forbidden:
        return forbidden

    current_user_id, error_response = _get_current_user_id_or_response()
    if error_response:
        return error_response

    document = _get_document_or_404(document_id)
    if not document:
        return _json_error(
            "Documento no encontrado",
            f"No existe un documento interno con id {document_id}.",
            404,
        )

    payload = _get_json_payload()
    visibility_mode = _normalize_upper(payload.get("visibility_mode"))

    if visibility_mode not in InternalDocumentVisibilityMode.ALL:
        return _json_error(
            "Visibilidad inválida",
            "visibility_mode debe ser PRIVATE, CUSTOM o GLOBAL.",
            400,
        )

    if document.is_sensitive and visibility_mode == InternalDocumentVisibilityMode.GLOBAL:
        return _json_error(
            "Visibilidad no permitida",
            "Un documento sensible no puede tener visibilidad global.",
            400,
        )

    old_visibility = {
        "visibility_mode": document.visibility_mode,
        "rules": [
            _serialize_visibility_rule(rule)
            for rule in InternalDocumentVisibilityORM.query.filter_by(
                document_id=document.id,
                is_active=True,
            ).all()
        ],
    }

    existing_rules = InternalDocumentVisibilityORM.query.filter_by(
        document_id=document.id,
        is_active=True,
    ).all()

    for rule in existing_rules:
        rule.is_active = False

    document.visibility_mode = visibility_mode
    document.updated_by = current_user_id

    created_rules: list[InternalDocumentVisibilityORM] = []

    if visibility_mode == InternalDocumentVisibilityMode.CUSTOM:
        rules_payload = payload.get("rules")

        if not isinstance(rules_payload, list) or not rules_payload:
            return _json_error(
                "Reglas requeridas",
                "La visibilidad CUSTOM requiere al menos una regla.",
                400,
            )

        for raw_rule in rules_payload:
            if not isinstance(raw_rule, dict):
                return _json_error(
                    "Regla inválida",
                    "Cada regla de visibilidad debe ser un objeto.",
                    400,
                )

            visibility_type = _normalize_upper(raw_rule.get("visibility_type"))

            if visibility_type not in InternalDocumentVisibilityType.ALL:
                return _json_error(
                    "Tipo de visibilidad inválido",
                    "visibility_type debe ser ROLE, DEPARTMENT, SUCURSAL, USER o GLOBAL.",
                    400,
                )

            if visibility_type == InternalDocumentVisibilityType.GLOBAL and document.is_sensitive:
                return _json_error(
                    "Regla no permitida",
                    "Un documento sensible no puede usar regla GLOBAL.",
                    400,
                )

            rule = InternalDocumentVisibilityORM(
                document_id=document.id,
                visibility_type=visibility_type,
                role=_normalize_upper(raw_rule.get("role")) or None,
                department_id=_parse_optional_int(raw_rule.get("department_id")),
                sucursal_id=_parse_optional_int(raw_rule.get("sucursal_id")),
                user_id=_parse_optional_int(raw_rule.get("user_id")),
                can_view=_parse_bool(raw_rule.get("can_view"), default=True),
                can_download=_parse_bool(raw_rule.get("can_download"), default=True),
                is_active=True,
                created_by=current_user_id,
            )

            if visibility_type == InternalDocumentVisibilityType.ROLE and not rule.role:
                return _json_error(
                    "Rol requerido",
                    "Las reglas ROLE requieren role.",
                    400,
                )

            if visibility_type == InternalDocumentVisibilityType.DEPARTMENT and not rule.department_id:
                return _json_error(
                    "Departamento requerido",
                    "Las reglas DEPARTMENT requieren department_id.",
                    400,
                )

            if visibility_type == InternalDocumentVisibilityType.SUCURSAL and not rule.sucursal_id:
                return _json_error(
                    "Sucursal requerida",
                    "Las reglas SUCURSAL requieren sucursal_id.",
                    400,
                )

            if visibility_type == InternalDocumentVisibilityType.USER and not rule.user_id:
                return _json_error(
                    "Usuario requerido",
                    "Las reglas USER requieren user_id.",
                    400,
                )

            db.session.add(rule)
            created_rules.append(rule)

    _log_document_audit(
        document_id=document.id,
        actor_user_id=current_user_id,
        action="DOCUMENT_VISIBILITY_UPDATED",
        old_value_json=old_visibility,
        new_value_json={
            "visibility_mode": document.visibility_mode,
            "rules": [
                {
                    "visibility_type": rule.visibility_type,
                    "role": rule.role,
                    "department_id": rule.department_id,
                    "sucursal_id": rule.sucursal_id,
                    "user_id": rule.user_id,
                    "can_view": rule.can_view,
                    "can_download": rule.can_download,
                }
                for rule in created_rules
            ],
        },
    )

    db.session.commit()

    document = _get_document_or_404(document.id)

    return jsonify(
        {
            "message": "Visibilidad actualizada",
            "item": _serialize_document(
                document,
                include_details=True,
                include_versions=True,
                include_visibility=True,
            ),
        }
    ), 200


@internal_documents_bp.route("/<int:document_id>/download", methods=["GET"])
@jwt_required()
def download_current_internal_document(document_id: int):
    document = _get_document_or_404(document_id)
    if not document:
        return _json_error(
            "Documento no encontrado",
            f"No existe un documento interno con id {document_id}.",
            404,
        )

    forbidden = require_internal_document_download_access(document)
    if forbidden:
        return forbidden

    version = document.current_version
    if not version:
        return _json_error(
            "Versión no encontrada",
            "El documento no tiene una versión vigente.",
            404,
        )

    upload = version.warehouse_upload
    file_path = _build_safe_file_path(upload)

    if file_path is None:
        return _json_error(
            "Archivo no encontrado",
            "No se encontró el archivo físico asociado al documento.",
            404,
        )

    return send_file(
        file_path,
        as_attachment=True,
        download_name=upload.original_filename,
        mimetype=upload.mime_type or "application/octet-stream",
    )


@internal_documents_bp.route(
    "/<int:document_id>/versions/<int:version_id>/download",
    methods=["GET"],
)
@jwt_required()
def download_internal_document_version(document_id: int, version_id: int):
    document = _get_document_or_404(document_id)
    if not document:
        return _json_error(
            "Documento no encontrado",
            f"No existe un documento interno con id {document_id}.",
            404,
        )

    if not can_download_historical_internal_document_version(document):
        return _json_error(
            "No autorizado",
            "No autorizado para descargar versiones históricas.",
            403,
        )

    version = (
        InternalDocumentVersionORM.query.options(
            joinedload(InternalDocumentVersionORM.warehouse_upload)
        )
        .filter_by(id=version_id, document_id=document.id)
        .first()
    )

    if not version:
        return _json_error(
            "Versión no encontrada",
            f"No existe una versión {version_id} para este documento.",
            404,
        )

    upload = version.warehouse_upload
    file_path = _build_safe_file_path(upload)

    if file_path is None:
        return _json_error(
            "Archivo no encontrado",
            "No se encontró el archivo físico asociado a la versión.",
            404,
        )

    return send_file(
        file_path,
        as_attachment=True,
        download_name=upload.original_filename,
        mimetype=upload.mime_type or "application/octet-stream",
    )


@internal_documents_bp.route("/<int:document_id>/audit", methods=["GET"])
@jwt_required()
def get_internal_document_audit(document_id: int):
    document = _get_document_or_404(document_id)
    if not document:
        return _json_error(
            "Documento no encontrado",
            f"No existe un documento interno con id {document_id}.",
            404,
        )

    forbidden = require_internal_document_audit_access(document)
    if forbidden:
        return forbidden

    items = (
        InternalDocumentAuditLogORM.query.filter_by(document_id=document.id)
        .order_by(InternalDocumentAuditLogORM.created_at.desc())
        .all()
    )

    return jsonify({"items": [_serialize_audit_log(item) for item in items]}), 200