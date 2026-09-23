from __future__ import annotations

from dataclasses import dataclass

from flask_jwt_extended import get_jwt_identity

from app.models.user_model import UserORM


CONTACT_CENTER_INITIAL_USERS = frozenset({
    "ADMICORP",
    "SANDRA",
})

CONTACT_CENTER_INITIAL_ROLES = frozenset({
    "SANDRA",
})


class ContactCenterAuthorizationError(PermissionError):
    pass


@dataclass(frozen=True)
class ContactCenterAccess:
    user_id: int
    username: str
    role: str
    is_supervisor: bool


def _normalize(value: object) -> str:
    return str(value or "").strip().upper()


def has_contact_center_access(user: UserORM | None) -> bool:
    if user is None:
        return False

    username = _normalize(user.username)
    role = _normalize(user.rol)

    return (
        username in CONTACT_CENTER_INITIAL_USERS
        or role in CONTACT_CENTER_INITIAL_ROLES
    )


def resolve_contact_center_access(user: UserORM | None) -> ContactCenterAccess:
    if user is None:
        raise ContactCenterAuthorizationError("Usuario no encontrado.")

    if not has_contact_center_access(user):
        raise ContactCenterAuthorizationError(
            "El usuario no tiene acceso a Contact Center."
        )

    username = _normalize(user.username)
    role = _normalize(user.rol)

    return ContactCenterAccess(
        user_id=int(user.id),
        username=username,
        role=role,
        is_supervisor=username == "ADMICORP",
    )


def get_current_contact_center_user() -> tuple[UserORM, ContactCenterAccess]:
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError) as exc:
        raise ContactCenterAuthorizationError(
            "Identidad de usuario inválida."
        ) from exc

    user = UserORM.get_by_id(user_id)
    access = resolve_contact_center_access(user)
    return user, access
