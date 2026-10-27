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
        username="GERE_OUTSIDE_PILOT",
        role="GERENTE",
        sucursal_id=14,
    )

    assert has_contact_center_access(user) is False

    with pytest.raises(ContactCenterAuthorizationError):
        resolve_contact_center_access(user)

def test_edmundo_regional_pilot_sees_all_thirteen_authorized_branches():
    user = _user(
        user_id=55,
        username="EDMUNDO",
        role="GERENTE_REGIONAL",
        sucursal_id=1000,
        sucursales_ids=list(range(1, 14)),
    )
    assert has_contact_center_access(user) is True
    assert has_contact_center_operator_access(user) is False

    access = resolve_contact_center_access(user)
    assert access.is_supervisor is False
    assert access.is_manager is True
    assert access.allowed_branch_ids == tuple(range(1, 14))
    assert set(access.allowed_branch_ids).isdisjoint({14, 20, 26, 1000})


@pytest.mark.parametrize("user_id,username,role,branches", [
    (56, "OTRO_REGIONAL", "GERENTE_REGIONAL", [1, 7, 9]),
    (56, "EDMUNDO", "GERENTE_REGIONAL", [1, 7, 9]),
    (55, "OTRO_REGIONAL", "GERENTE_REGIONAL", [1, 7, 9]),
    (55, "EDMUNDO", "GERENTE_REGIONAL", [14, 15, 16, 17, 18]),
    (55, "EDMUNDO", "SISTEMAS", [1, 7, 9]),
])
def test_regional_pilot_does_not_enable_other_id_username_roles_or_branches(
    user_id, username, role, branches,
):
    user = _user(
        user_id=user_id,
        username=username,
        role=role,
        sucursal_id=1000,
        sucursales_ids=branches,
    )
    assert has_contact_center_access(user) is False
    with pytest.raises(ContactCenterAuthorizationError):
        resolve_contact_center_access(user)


def test_edmundo_regional_manager_is_not_operator_or_global_branch_writer():
    from app.routes import contact_center_routes as routes

    user = _user(
        user_id=55,
        username="EDMUNDO",
        role="GERENTE_REGIONAL",
        sucursal_id=1000,
        sucursales_ids=list(range(1, 14)),
    )
    access = resolve_contact_center_access(user)
    with pytest.raises(ContactCenterAuthorizationError, match="operadores"):
        routes._assert_operator_access(access)

    permitted_case = SimpleNamespace(sucursal_id=7, assigned_user_id=55)
    prohibited_case = SimpleNamespace(sucursal_id=14, assigned_user_id=55)
    routes._assert_case_access(permitted_case, user, access)
    with pytest.raises(ContactCenterAuthorizationError, match="sucursal autorizada"):
        routes._assert_case_access(prohibited_case, user, access)

    permitted_appointment = SimpleNamespace(sucursal_id=1)
    prohibited_appointment = SimpleNamespace(sucursal_id=14)
    routes._assert_appointment_access(permitted_appointment, user, access)
    with pytest.raises(ContactCenterAuthorizationError, match="sucursal autorizada"):
        routes._assert_appointment_access(prohibited_appointment, user, access)


def test_contact_center_access_endpoint_exposes_exact_regional_scope(monkeypatch):
    from flask import Flask
    from flask_jwt_extended import JWTManager, create_access_token
    from app.routes import contact_center_routes as routes

    user = _user(
        user_id=55,
        username="EDMUNDO",
        role="GERENTE_REGIONAL",
        sucursal_id=1000,
        sucursales_ids=list(range(1, 14)),
    )
    access = resolve_contact_center_access(user)
    monkeypatch.setattr(
        routes, "get_current_contact_center_user", lambda: (user, access)
    )

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="test-contact-center-regional-pilot",
    )
    JWTManager(app)
    app.register_blueprint(routes.contact_center_bp, url_prefix="/api/contact-center")
    with app.app_context():
        token = create_access_token(identity="55")
        response = app.test_client().get(
            "/api/contact-center/access",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.get_json() == {
        "allowed": True,
        "user": {
            "id": 55,
            "username": "EDMUNDO",
            "role": "GERENTE_REGIONAL",
        },
        "is_supervisor": False,
        "is_manager": True,
        "allowed_branch_ids": list(range(1, 14)),
    }


@pytest.mark.parametrize("branch_id", [2, 3, 4, 5, 6])
def test_mexicali_and_san_luis_managers_enter_pilot_only_for_own_branch(branch_id):
    user = _user(
        user_id=300 + branch_id,
        username=f"GERE_PILOT_{branch_id}",
        role="GERENTE",
        sucursal_id=branch_id,
        sucursales_ids=[branch_id],
    )
    assert has_contact_center_access(user) is True
    assert has_contact_center_operator_access(user) is False
    access = resolve_contact_center_access(user)
    assert access.is_manager is True
    assert access.is_supervisor is False
    assert access.allowed_branch_ids == (branch_id,)


def test_manager_scope_intersects_assigned_branches_with_pilot():
    user = _user(
        user_id=600,
        username="GERE_MIXED",
        role="GERENTE",
        sucursal_id=14,
        sucursales_ids=[3, 6, 14, 20],
    )
    access = resolve_contact_center_access(user)
    assert access.is_manager
    assert access.allowed_branch_ids == (3, 6)


@pytest.mark.parametrize("role", ["GERENTE_REGIONAL", "LECTOR_GLOBAL", "ADMINISTRADOR"])
def test_other_roles_do_not_get_manager_pilot_access_from_branch_assignment(role):
    user = _user(
        user_id=901, username="NO_PILOT", role=role, sucursal_id=6,
        sucursales_ids=[1, 2, 3, 4, 5, 6],
    )
    assert has_contact_center_access(user) is False
    with pytest.raises(ContactCenterAuthorizationError):
        resolve_contact_center_access(user)


@pytest.mark.parametrize("branch_id", [2, 3, 4, 5, 6])
def test_mexicali_san_luis_manager_guard_denies_other_branch_cases(branch_id):
    from app.routes import contact_center_routes as routes

    actor = _user(
        user_id=700 + branch_id, username=f"GERE{branch_id}",
        role="GERENTE", sucursal_id=branch_id,
    )
    access = resolve_contact_center_access(actor)
    own_case = SimpleNamespace(
        sucursal_id=branch_id, assigned_user_id=actor.id,
    )
    other_case = SimpleNamespace(
        sucursal_id=14, assigned_user_id=actor.id,
    )
    routes._assert_case_access(own_case, actor, access)
    with pytest.raises(ContactCenterAuthorizationError, match="sucursal autorizada"):
        routes._assert_case_access(other_case, actor, access)
    with pytest.raises(ContactCenterAuthorizationError, match="operadores"):
        routes._assert_operator_access(access)
