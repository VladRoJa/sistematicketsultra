from __future__ import annotations

from types import SimpleNamespace

from app.services.marketing_access import (
    resolve_marketing_access,
)


def test_manager_scope_uses_only_primary_branch():
    access = resolve_marketing_access(
        SimpleNamespace(
            rol="GERENTE",
            sucursal_id=7,
            sucursales_ids=[7, 8, 9],
        )
    )

    assert access.type == "PRIMARY_BRANCH"
    assert access.branch_ids == (7,)
    assert access.can_edit_inputs is False


def test_regional_manager_scope_uses_assigned_pool():
    access = resolve_marketing_access(
        SimpleNamespace(
            rol="GERENTE_REGIONAL",
            sucursal_id=1,
            sucursales_ids=[3, 2, 3],
        )
    )

    assert access.type == "ASSIGNED_BRANCHES"
    assert access.branch_ids == (2, 3)
    assert access.can_edit_inputs is False


def test_global_scope_materializes_available_branches():
    access = resolve_marketing_access(
        SimpleNamespace(
            rol="ADMIN",
            sucursal_id=1000,
            sucursales_ids=[],
        )
    )

    assert access.type == "GLOBAL"
    assert access.is_global is True
    assert access.visible_branch_ids([3, 1, 2]) == (1, 2, 3)
    assert access.can_edit_inputs is True


def test_existing_marketing_role_can_edit_only_its_scope():
    access = resolve_marketing_access(
        SimpleNamespace(
            rol="MARKETING",
            sucursal_id=1,
            sucursales_ids=[1, 2],
        )
    )

    assert access.type == "ASSIGNED_BRANCHES"
    assert access.branch_ids == (1, 2)
    assert access.can_edit_inputs is True
