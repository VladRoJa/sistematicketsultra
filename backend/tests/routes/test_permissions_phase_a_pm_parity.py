"""P08-P10 — capacidad PM vs autorización por sucursal y ACL legacy.

Casos con usuarios/sucursales ficticios salvo constantes del código. Los
grants ACL se simulan con query falsa, sin conectarse a PostgreSQL.
"""
from types import SimpleNamespace

import pytest

from app.models import permiso_model
from app.routes import permissions_catalog_routes as catalog
from app.routes import pm_routes as pm
from app.utils import maintenance_regional_lead as regional
from app.utils import pm_permissions as pm_permissions


def _user(role, *, primary=100, branches=None, user_id=-701,
          username="QA_FICTICIO", department=1):
    return SimpleNamespace(
        id=user_id,
        username=username,
        rol=role,
        sucursal_id=primary,
        sucursales_ids=list(branches or []),
        department_id=department,
    )


def _preview(user, action_key):
    context = {
        "role": catalog._normalize_role(user),
        "sucursal_ids": catalog._get_user_assigned_sucursal_ids(user),
        "warehouse_operator": None,
        "planning_operator": None,
        "allow_ticket_delete_all": False,
    }
    return catalog._effective_action_decision(
        SimpleNamespace(full_key=action_key), user, context
    )


def _acl(monkeypatch, enabled):
    class _Query:
        kwargs = None

        def filter_by(self, **kwargs):
            self.kwargs = kwargs
            return self

        def first(self):
            assert self.kwargs == {
                "user_id": -701, "departamento_id": 1, "es_admin": False
            }
            return SimpleNamespace() if enabled else None

    monkeypatch.setattr(
        permiso_model, "Permiso", SimpleNamespace(query=_Query())
    )


@pytest.mark.parametrize(
    "branch_id,allowed",
    [(1, True), (2, True), (7, False), (100, False), (77, False)],
)
def test_p08_regional_lead_restricts_by_identity_and_allowed_branch_intersection(
    branch_id, allowed
):
    # ID 45/username/role/dept son la excepción nominalizada en backend.
    # La lista M:N de esta prueba incluye sucursales fuera de la allowlist.
    user = _user(
        "MANTENIMIENTO", primary=100, branches=[1, 2, 7, 100],
        user_id=45, username="MANTENIMIENTO",
    )
    assert regional.is_regional_maintenance_lead(user) is True
    assert regional.regional_maintenance_lead_branches(user) == (1, 2)
    assert (pm._verificar_permiso_sucursal(user, branch_id) is None) is allowed
    assert pm_permissions.can_pm_view(user) is True

    observed = _preview(user, "pm.read")
    assert observed["allowed"] is True
    assert observed["scope_values"] == [1, 2, 7, 100]
    # 7 y 100: falsos positivos de scope diagnóstico, no acceso legacy.


def test_p08_regional_lead_requires_exact_identity_not_only_role():
    user = _user(
        "MANTENIMIENTO", primary=100, branches=[1],
        user_id=-702, username="NO_ES_JEFE",
    )
    assert regional.is_regional_maintenance_lead(user) is False
    # La política legacy para otros MANTENIMIENTO es global en PM.
    assert pm._verificar_permiso_sucursal(user, 77) is None


@pytest.mark.parametrize("role,acl_enabled,expected_read", [
    ("COORDINADOR_MANTENIMIENTO", True, True),
    ("COORDINADOR_MANTENIMIENTO", False, False),
    ("COMPRAS", True, True),
    ("COMPRAS", False, False),
])
def test_p09_acl_read_only_and_not_primary_corporate(
    monkeypatch, role, acl_enabled, expected_read
):
    _acl(monkeypatch, acl_enabled)
    user = _user(role, primary=100, branches=[7, 8])
    assert pm_permissions.has_scoped_maintenance_read_grant(user) is acl_enabled
    assert pm_permissions.can_pm_view(user) is expected_read
    assert pm_permissions.can_pm_execute(user) is False
    assert pm_permissions.can_pm_validate(user) is False
    assert pm_permissions.can_pm_configure(user) is False

    assert pm._verificar_permiso_sucursal(user, 7) is None
    assert pm._verificar_permiso_sucursal(user, 100)[1] == 403
    assert pm._verificar_permiso_sucursal(user, 99)[1] == 403

    observed_read = _preview(user, "pm.read")
    assert observed_read["allowed"] is expected_read
    assert observed_read["scope_type"] == "branch_scope"
    if acl_enabled:
        assert observed_read["scope_values"] == [7, 8]
    for action in ("pm.execute", "pm.validate", "pm.configure"):
        assert _preview(user, action)["allowed"] is False


@pytest.mark.parametrize(
    "branch,allowed",
    [(7, True), (9, True), (8, False), (100, False)]
)
def test_p10_manager_pm_read_requires_branch_even_when_role_allowed(
    branch, allowed
):
    user = _user("GERENTE", primary=9, branches=[7])
    assert pm_permissions.can_pm_view(user) is True
    assert (pm._verificar_permiso_sucursal(user, branch) is None) is allowed

    observed = _preview(user, "pm.read")
    assert observed["scope_type"] == "branch_scope"
    assert observed["scope_values"] == [7, 9]
    assert observed["allowed"] is True
    assert pm_permissions.can_pm_execute(user) is False


def test_p10_lector_global_catalog_global_read_is_not_global_branch_authority():
    user = _user("LECTOR_GLOBAL", primary=9, branches=[7])
    assert pm_permissions.can_pm_view(user) is True
    assert pm._verificar_permiso_sucursal(user, 7) is None
    assert pm._verificar_permiso_sucursal(user, 77)[1] == 403

    observed = _preview(user, "pm.read")
    assert observed["allowed"] is True
    assert observed["scope_type"] == "global"
    # El catálogo sobrerrepresenta alcance: el guard real deniega 77.
