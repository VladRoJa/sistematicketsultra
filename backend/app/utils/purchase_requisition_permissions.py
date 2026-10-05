from __future__ import annotations

from flask_jwt_extended import get_jwt_identity

from app.models.user_model import UserORM


REVIEW_ROLES = frozenset({
    "GERENCIA DEPORTIVA",
    "ADMINISTRADOR",
})
MAINTENANCE_ROLES = frozenset({
    "MANTENIMIENTO",
    "SR_MANTENIMIENTO",
    "AUX_MANTENIMIENTO",
})
GLOBAL_READ_ROLES = frozenset({
    "GERENCIA DEPORTIVA",
    "ADMINISTRADOR",
    "LECTOR_GLOBAL",
})
NO_CREATE_ROLES = frozenset({
    "LECTOR_GLOBAL",
})


class PurchaseRequisitionAuthorizationError(PermissionError):
    pass


def normalize_role(value: object) -> str:
    return str(value or "").strip().upper()


def _positive_int(value: object) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def assigned_branch_ids(user: UserORM | None) -> tuple[int, ...]:
    if user is None:
        return tuple()

    role = normalize_role(getattr(user, "rol", None))
    primary = _positive_int(getattr(user, "sucursal_id", None))

    if role == "GERENTE_REGIONAL":
        values = {
            branch_id
            for branch_id in (
                _positive_int(value)
                for value in (getattr(user, "sucursales_ids", None) or [])
            )
            if branch_id is not None
        }
        if primary is not None and primary not in {100, 1000}:
            values.add(primary)
        return tuple(sorted(values))

    return (primary,) if primary is not None else tuple()


def can_purchase_requisition_access(user: UserORM | None) -> bool:
    return user is not None


def can_purchase_requisition_create(user: UserORM | None) -> bool:
    if user is None:
        return False
    return normalize_role(getattr(user, "rol", None)) not in NO_CREATE_ROLES


def can_purchase_requisition_review(user: UserORM | None) -> bool:
    if user is None:
        return False
    return normalize_role(getattr(user, "rol", None)) in REVIEW_ROLES


def can_purchase_requisition_manage_quotation(user: UserORM | None) -> bool:
    if user is None:
        return False
    role = normalize_role(getattr(user, "rol", None))
    return role == "ADMINISTRADOR" or role in MAINTENANCE_ROLES


def has_global_purchase_requisition_read(user: UserORM | None) -> bool:
    if user is None:
        return False
    return normalize_role(getattr(user, "rol", None)) in GLOBAL_READ_ROLES


def can_create_for_branch(user: UserORM | None, branch_id: int) -> bool:
    if not can_purchase_requisition_create(user):
        return False

    role = normalize_role(getattr(user, "rol", None))
    target = _positive_int(branch_id)
    if target is None:
        return False

    if role == "ADMINISTRADOR":
        return True

    return target in set(assigned_branch_ids(user))


def can_purchase_requisition_view(user: UserORM | None, requisition) -> bool:
    if user is None or requisition is None:
        return False

    user_id = _positive_int(getattr(user, "id", None))
    creator_id = _positive_int(getattr(requisition, "created_by_user_id", None))
    if user_id is not None and user_id == creator_id:
        return True

    if has_global_purchase_requisition_read(user):
        return True

    role = normalize_role(getattr(user, "rol", None))
    status = str(getattr(requisition, "status", None) or "").strip().upper()
    if role in MAINTENANCE_ROLES:
        return status == "IN_QUOTATION"

    branch_id = _positive_int(getattr(requisition, "sucursal_id", None))
    return branch_id is not None and branch_id in set(assigned_branch_ids(user))


def get_current_purchase_requisition_user() -> UserORM:
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError) as exc:
        raise PurchaseRequisitionAuthorizationError(
            "Identidad de usuario inválida."
        ) from exc

    user = UserORM.get_by_id(user_id)
    if user is None:
        raise PurchaseRequisitionAuthorizationError(
            "Usuario no encontrado."
        )
    if not can_purchase_requisition_access(user):
        raise PurchaseRequisitionAuthorizationError(
            "El usuario no tiene acceso a Requisiciones."
        )
    return user


def can_upload_purchase_requisition_attachment(
    user: UserORM | None,
    requisition,
    attachment_type: str,
) -> bool:
    if user is None or requisition is None:
        return False
    if normalize_role(getattr(user, "rol", None)) == "LECTOR_GLOBAL":
        return False

    normalized_type = str(attachment_type or "").strip().upper()
    status = str(getattr(requisition, "status", None) or "").strip().upper()
    user_id = _positive_int(getattr(user, "id", None))
    creator_id = _positive_int(
        getattr(requisition, "created_by_user_id", None)
    )
    role = normalize_role(getattr(user, "rol", None))

    if (
        user_id is not None
        and user_id == creator_id
        and status in {"PENDING_REVIEW", "NEEDS_INFO"}
    ):
        return normalized_type in {"EVIDENCE", "OTHER"}

    if (
        status == "IN_QUOTATION"
        and can_purchase_requisition_manage_quotation(user)
    ):
        return normalized_type in {"QUOTE", "OTHER"}

    return False
