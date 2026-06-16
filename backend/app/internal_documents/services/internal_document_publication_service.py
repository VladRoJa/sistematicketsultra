# backend/app/internal_documents/services/internal_document_publication_service.py

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.extensions import db
from app.models import (
    InternalDocumentAuditLogORM,
    InternalDocumentCategoryORM,
    InternalDocumentLinkEntityType,
    InternalDocumentLinkORM,
    InternalDocumentLinkRole,
    InternalDocumentORM,
    InternalDocumentStatus,
    InternalDocumentVersionORM,
    InternalDocumentVisibilityMode,
    InternalDocumentVisibilityORM,
    InternalDocumentVisibilityType,
    WarehouseUploadORM,
)

LOCAL_TZ = ZoneInfo("America/Tijuana")


class InternalDocumentPublicationError(RuntimeError):
    """Error creando una publicación documental interna desde Warehouse."""


def _now_tijuana() -> datetime:
    return datetime.now(LOCAL_TZ)


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_upper(value: Any) -> str:
    return _normalize_text(value).upper()


def _parse_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None

    return parsed if parsed > 0 else None


def _parse_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    normalized = str(value).strip().lower()

    if normalized in {"1", "true", "t", "yes", "y", "si", "sí"}:
        return True

    if normalized in {"0", "false", "f", "no", "n"}:
        return False

    return default


def _resolve_category_by_key(category_key: str) -> InternalDocumentCategoryORM:
    resolved_key = _normalize_upper(category_key)

    if not resolved_key:
        raise InternalDocumentPublicationError("category_key es requerido.")

    category = InternalDocumentCategoryORM.query.filter_by(
        key=resolved_key,
        is_active=True,
    ).first()

    if not category:
        raise InternalDocumentPublicationError(
            f"No existe una categoría activa con key={resolved_key!r}."
        )

    return category


def _resolve_warehouse_upload(warehouse_upload_id: int) -> WarehouseUploadORM:
    upload_id = _parse_positive_int(warehouse_upload_id)

    if not upload_id:
        raise InternalDocumentPublicationError(
            "warehouse_upload_id debe ser un entero positivo."
        )

    upload = WarehouseUploadORM.query.filter_by(id=upload_id).first()

    if not upload:
        raise InternalDocumentPublicationError(
            f"No existe WarehouseUploadORM con id={upload_id}."
        )

    return upload


def _find_existing_document_by_upload(
    warehouse_upload_id: int,
) -> tuple[InternalDocumentORM, InternalDocumentVersionORM] | None:
    version = InternalDocumentVersionORM.query.filter_by(
        warehouse_upload_id=warehouse_upload_id
    ).first()

    if not version:
        return None

    document = InternalDocumentORM.query.filter_by(id=version.document_id).first()

    if not document:
        return None

    return document, version


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
            ip_address=None,
            user_agent="reports_scheduler",
        )
    )


def _build_visibility_rule(
    *,
    document_id: int,
    raw_rule: dict[str, Any],
    created_by_user_id: int,
) -> InternalDocumentVisibilityORM:
    visibility_type = _normalize_upper(raw_rule.get("visibility_type"))

    if visibility_type not in InternalDocumentVisibilityType.ALL:
        raise InternalDocumentPublicationError(
            "visibility_type debe ser ROLE, DEPARTMENT, SUCURSAL, USER o GLOBAL."
        )

    rule = InternalDocumentVisibilityORM(
        document_id=document_id,
        visibility_type=visibility_type,
        role=_normalize_upper(raw_rule.get("role")) or None,
        department_id=_parse_positive_int(raw_rule.get("department_id")),
        sucursal_id=_parse_positive_int(raw_rule.get("sucursal_id")),
        user_id=_parse_positive_int(raw_rule.get("user_id")),
        can_view=_parse_bool(raw_rule.get("can_view"), default=True),
        can_download=_parse_bool(raw_rule.get("can_download"), default=True),
        is_active=True,
        created_by=created_by_user_id,
    )

    if visibility_type == InternalDocumentVisibilityType.ROLE and not rule.role:
        raise InternalDocumentPublicationError("Regla ROLE requiere role.")

    if (
        visibility_type == InternalDocumentVisibilityType.DEPARTMENT
        and not rule.department_id
    ):
        raise InternalDocumentPublicationError(
            "Regla DEPARTMENT requiere department_id."
        )

    if visibility_type == InternalDocumentVisibilityType.SUCURSAL and not rule.sucursal_id:
        raise InternalDocumentPublicationError("Regla SUCURSAL requiere sucursal_id.")

    if visibility_type == InternalDocumentVisibilityType.USER and not rule.user_id:
        raise InternalDocumentPublicationError("Regla USER requiere user_id.")

    return rule


def _build_document_link(
    *,
    document_id: int,
    raw_link: dict[str, Any],
    created_by_user_id: int,
) -> InternalDocumentLinkORM:
    entity_type = _normalize_upper(raw_link.get("entity_type"))
    link_role = _normalize_upper(raw_link.get("link_role"))

    if entity_type not in InternalDocumentLinkEntityType.ALL:
        raise InternalDocumentPublicationError(
            "entity_type debe ser PROJECT, OPENING, TASK, SUCURSAL, DEPARTMENT o GENERAL."
        )

    if link_role not in InternalDocumentLinkRole.ALL:
        raise InternalDocumentPublicationError(
            "link_role debe ser PLANO, PERMISO, CONTRATO, COTIZACION, CHECKLIST, "
            "EVIDENCIA, MANUAL, FINANCIERO, CONSTRUCCION, OPERACION u OTRO."
        )

    entity_id = _parse_positive_int(raw_link.get("entity_id"))
    entity_key = _normalize_upper(raw_link.get("entity_key")) or None

    if entity_type == InternalDocumentLinkEntityType.GENERAL:
        entity_id = None
        entity_key = entity_key or "GENERAL"

    if entity_type != InternalDocumentLinkEntityType.GENERAL and not entity_id and not entity_key:
        raise InternalDocumentPublicationError(
            "Los links no GENERAL requieren entity_id o entity_key."
        )

    return InternalDocumentLinkORM(
        document_id=document_id,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_key=entity_key,
        link_role=link_role,
        label=_normalize_text(raw_link.get("label")) or None,
        is_primary=_parse_bool(raw_link.get("is_primary"), default=False),
        is_active=True,
        created_by=created_by_user_id,
        updated_by=created_by_user_id,
    )


def publish_internal_document_from_warehouse_upload(
    *,
    warehouse_upload_id: int,
    title: str,
    category_key: str,
    created_by_user_id: int,
    description: str | None = None,
    document_type: str | None = None,
    owner_user_id: int | None = None,
    owner_department_id: int | None = None,
    is_sensitive: bool = False,
    visibility_mode: str = InternalDocumentVisibilityMode.PRIVATE,
    visibility_rules: list[dict[str, Any]] | None = None,
    links: list[dict[str, Any]] | None = None,
    publish_now: bool = False,
    version_label: str | None = None,
    change_notes: str | None = None,
    audit_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Crea una publicación de Nube Corporativa a partir de un upload existente.

    Este servicio NO crea archivos físicos.
    El archivo debe existir primero como WarehouseUploadORM.
    """

    resolved_title = _normalize_text(title)
    if not resolved_title:
        raise InternalDocumentPublicationError("title es requerido.")

    creator_id = _parse_positive_int(created_by_user_id)
    if not creator_id:
        raise InternalDocumentPublicationError(
            "created_by_user_id debe ser un entero positivo."
        )

    upload = _resolve_warehouse_upload(warehouse_upload_id)

    existing = _find_existing_document_by_upload(upload.id)
    if existing:
        document, version = existing

        return {
            "created": False,
            "document_id": document.id,
            "version_id": version.id,
            "warehouse_upload_id": upload.id,
            "status": document.status,
            "visibility_mode": document.visibility_mode,
            "message": "Ya existía una publicación documental para este upload.",
        }

    category = _resolve_category_by_key(category_key)

    resolved_visibility_mode = _normalize_upper(visibility_mode)

    if resolved_visibility_mode not in InternalDocumentVisibilityMode.ALL:
        raise InternalDocumentPublicationError(
            "visibility_mode debe ser PRIVATE, CUSTOM o GLOBAL."
        )

    if bool(is_sensitive) and resolved_visibility_mode == InternalDocumentVisibilityMode.GLOBAL:
        raise InternalDocumentPublicationError(
            "Un documento sensible no puede tener visibilidad GLOBAL."
        )

    if resolved_visibility_mode == InternalDocumentVisibilityMode.CUSTOM and not visibility_rules:
        raise InternalDocumentPublicationError(
            "visibility_mode CUSTOM requiere visibility_rules."
        )

    now = _now_tijuana()
    status = (
        InternalDocumentStatus.PUBLISHED
        if publish_now
        else InternalDocumentStatus.DRAFT
    )

    try:
        document = InternalDocumentORM(
            title=resolved_title,
            description=_normalize_text(description) or None,
            category_id=category.id,
            document_type=_normalize_text(document_type) or None,
            owner_user_id=_parse_positive_int(owner_user_id),
            owner_department_id=_parse_positive_int(owner_department_id),
            status=status,
            is_sensitive=bool(is_sensitive),
            visibility_mode=resolved_visibility_mode,
            published_by=creator_id if publish_now else None,
            published_at=now if publish_now else None,
            created_by=creator_id,
            updated_by=creator_id,
        )

        db.session.add(document)
        db.session.flush()

        version = InternalDocumentVersionORM(
            document_id=document.id,
            warehouse_upload_id=upload.id,
            version_label=_normalize_text(version_label) or "1.0",
            version_number=1,
            original_filename=upload.original_filename,
            file_mime_type=upload.mime_type,
            file_size_bytes=upload.file_size_bytes,
            file_hash_sha256=upload.file_hash_sha256,
            change_notes=(
                _normalize_text(change_notes)
                or "Publicación automática desde Warehouse"
            ),
            is_current=True,
            is_hidden_from_users=False,
            created_by=creator_id,
        )

        db.session.add(version)
        db.session.flush()

        document.current_version_id = version.id

        created_visibility_rules: list[InternalDocumentVisibilityORM] = []
        if resolved_visibility_mode == InternalDocumentVisibilityMode.CUSTOM:
            for raw_rule in visibility_rules or []:
                rule = _build_visibility_rule(
                    document_id=document.id,
                    raw_rule=raw_rule,
                    created_by_user_id=creator_id,
                )

                if document.is_sensitive and rule.visibility_type == InternalDocumentVisibilityType.GLOBAL:
                    raise InternalDocumentPublicationError(
                        "Un documento sensible no puede usar regla GLOBAL."
                    )

                db.session.add(rule)
                created_visibility_rules.append(rule)

        created_links: list[InternalDocumentLinkORM] = []
        for raw_link in links or []:
            link = _build_document_link(
                document_id=document.id,
                raw_link=raw_link,
                created_by_user_id=creator_id,
            )
            db.session.add(link)
            created_links.append(link)

        _log_document_audit(
            document_id=document.id,
            version_id=version.id,
            actor_user_id=creator_id,
            action="DOCUMENT_CREATED",
            new_value_json={
                "title": document.title,
                "category_id": document.category_id,
                "status": document.status,
                "warehouse_upload_id": upload.id,
                "origin": "warehouse_publication_service",
            },
            metadata_json=audit_metadata,
        )

        _log_document_audit(
            document_id=document.id,
            version_id=version.id,
            actor_user_id=creator_id,
            action="DOCUMENT_VERSION_CREATED",
            new_value_json={
                "version_label": version.version_label,
                "version_number": version.version_number,
                "warehouse_upload_id": upload.id,
            },
            metadata_json=audit_metadata,
        )

        if created_visibility_rules:
            _log_document_audit(
                document_id=document.id,
                actor_user_id=creator_id,
                action="DOCUMENT_VISIBILITY_UPDATED",
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
                        for rule in created_visibility_rules
                    ],
                },
                metadata_json=audit_metadata,
            )

        for link in created_links:
            _log_document_audit(
                document_id=document.id,
                actor_user_id=creator_id,
                action="DOCUMENT_LINK_CREATED",
                new_value_json={
                    "entity_type": link.entity_type,
                    "entity_id": link.entity_id,
                    "entity_key": link.entity_key,
                    "link_role": link.link_role,
                    "label": link.label,
                    "is_primary": link.is_primary,
                },
                metadata_json=audit_metadata,
            )

        if publish_now:
            _log_document_audit(
                document_id=document.id,
                version_id=version.id,
                actor_user_id=creator_id,
                action="DOCUMENT_PUBLISHED",
                new_value_json={
                    "status": document.status,
                    "published_by": document.published_by,
                    "published_at": document.published_at.isoformat()
                    if document.published_at
                    else None,
                },
                metadata_json=audit_metadata,
            )

        db.session.commit()

        return {
            "created": True,
            "document_id": document.id,
            "version_id": version.id,
            "warehouse_upload_id": upload.id,
            "status": document.status,
            "visibility_mode": document.visibility_mode,
            "message": "Publicación documental creada.",
        }

    except Exception:
        db.session.rollback()
        raise