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

# Piloto gerencial inicial. Villas del Rey es sucursal_id=1.
# Cuando el piloto se valide, este alcance puede ampliarse de forma explícita.
CONTACT_CENTER_MANAGER_PILOT_BRANCH_IDS = frozenset({1})


class ContactCenterAuthorizationError(PermissionError):
    pass


@dataclass(frozen=True)
class ContactCenterAccess:
    user_id: int
    username: str
    role: str
    is_supervisor: bool
    is_manager: bool
    allowed_branch_ids: tuple[int, ...]


def _normalize(value: object) -> str:
    return str(value or "").strip().upper()


def _user_branch_ids(user: UserORM) -> tuple[int, ...]:
    values: set[int] = set()

    primary = getattr(user, "sucursal_id", None)
    try:
        if primary is not None:
            values.add(int(primary))
    except (TypeError, ValueError):
        pass

    for raw_value in getattr(user, "sucursales_ids", None) or []:
        try:
            values.add(int(raw_value))
        except (TypeError, ValueError):
            continue

    return tuple(sorted(value for value in values if value > 0))


def _manager_allowed_branch_ids(user: UserORM) -> tuple[int, ...]:
    if _normalize(getattr(user, "rol", None)) != "GERENTE":
        return tuple()

    return tuple(
        branch_id
        for branch_id in _user_branch_ids(user)
        if branch_id in CONTACT_CENTER_MANAGER_PILOT_BRANCH_IDS
    )


def has_contact_center_operator_access(user: UserORM | None) -> bool:
    if user is None:
        return False

    username = _normalize(user.username)
    role = _normalize(user.rol)

    return (
        username in CONTACT_CENTER_INITIAL_USERS
        or role in CONTACT_CENTER_INITIAL_ROLES
    )


def has_contact_center_access(user: UserORM | None) -> bool:
    if user is None:
        return False

    return (
        has_contact_center_operator_access(user)
        or bool(_manager_allowed_branch_ids(user))
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
    is_supervisor = username == "ADMICORP"
    is_manager = role == "GERENTE" and not is_supervisor
    allowed_branch_ids = (
        _manager_allowed_branch_ids(user)
        if is_manager
        else tuple()
    )

    return ContactCenterAccess(
        user_id=int(user.id),
        username=username,
        role=role,
        is_supervisor=is_supervisor,
        is_manager=is_manager,
        allowed_branch_ids=allowed_branch_ids,
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