from types import SimpleNamespace

import pytest

from app.utils.contact_center_access import (
    ContactCenterAuthorizationError,
    has_contact_center_access,
    has_contact_center_operator_access,
    resolve_contact_center_access,
)


def _user(
    *,
    user_id=1,
    username="usuario",
    role="USUARIO",
    sucursal_id=None,
    sucursales_ids=None,
):
    return SimpleNamespace(
        id=user_id,
        username=username,
        rol=role,
        sucursal_id=sucursal_id,
        sucursales_ids=sucursales_ids or [],
    )


def test_admicorp_has_contact_center_access_as_supervisor():
    user = _user(username=" admicorp ", role="ADMINISTRADOR")

    assert has_contact_center_access(user) is True

    access = resolve_contact_center_access(user)

    assert access.username == "ADMICORP"
    assert access.is_supervisor is True


def test_sandra_username_has_contact_center_access():
    user = _user(username="Sandra", role="USUARIO")

    assert has_contact_center_access(user) is True

    access = resolve_contact_center_access(user)

    assert access.username == "SANDRA"
    assert access.is_supervisor is False


def test_sandra_profile_has_contact_center_access():
    user = _user(username="contactcenter01", role="sandra")

    assert has_contact_center_access(user) is True

    access = resolve_contact_center_access(user)

    assert access.role == "SANDRA"
    assert access.is_supervisor is False


def test_candy_username_has_same_operator_access_as_sandra():
    user = _user(username="Candy", role="USUARIO")

    assert has_contact_center_access(user) is True
    assert has_contact_center_operator_access(user) is True

    access = resolve_contact_center_access(user)

    assert access.username == "CANDY"
    assert access.is_supervisor is False
    assert access.is_manager is False


def test_candy_profile_has_same_operator_access_as_sandra():
    user = _user(username="contactcenter02", role="candy")

    assert has_contact_center_access(user) is True
    assert has_contact_center_operator_access(user) is True

    access = resolve_contact_center_access(user)

    assert access.role == "CANDY"
    assert access.is_supervisor is False
    assert access.is_manager is False


def test_other_users_are_rejected():
    user = _user(username="otro", role="ADMINISTRADOR")

    assert has_contact_center_access(user) is False

    with pytest.raises(ContactCenterAuthorizationError):
        resolve_contact_center_access(user)

def test_villas_manager_keeps_access_but_is_not_operator():
    user = _user(
        username="GEREVREY",
        role="GERENTE",
        sucursal_id=1,
    )

    assert has_contact_center_access(user) is True
    assert has_contact_center_operator_access(user) is False

    access = resolve_contact_center_access(user)

    assert access.is_supervisor is False
    assert access.is_manager is True
    assert access.allowed_branch_ids == (1,)


@pytest.mark.parametrize("branch_id", [7, 8, 9, 10, 11, 12, 13])
def test_costa_bc_managers_have_appointment_access(branch_id):
    user = _user(
        username=f"GERE{branch_id}",
        role="GERENTE",
        sucursal_id=branch_id,
    )

    assert has_contact_center_access(user) is True
    assert has_contact_center_operator_access(user) is False

    access = resolve_contact_center_access(user)

    assert access.is_supervisor is False
    assert access.is_manager is True
    assert access.allowed_branch_ids == (branch_id,)


def test_manager_outside_rollout_is_rejected():
    user = _user(
        username="GEREVVER",
        role="GERENTE",
        sucursal_id=2,
    )

    assert has_contact_center_access(user) is False

    with pytest.raises(ContactCenterAuthorizationError):
        resolve_contact_center_access(user)