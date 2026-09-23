from types import SimpleNamespace

import pytest

from app.utils.contact_center_access import (
    ContactCenterAuthorizationError,
    has_contact_center_access,
    resolve_contact_center_access,
)


def _user(*, user_id=1, username="usuario", role="USUARIO"):
    return SimpleNamespace(
        id=user_id,
        username=username,
        rol=role,
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


def test_other_users_are_rejected():
    user = _user(username="otro", role="ADMINISTRADOR")

    assert has_contact_center_access(user) is False

    with pytest.raises(ContactCenterAuthorizationError):
        resolve_contact_center_access(user)
