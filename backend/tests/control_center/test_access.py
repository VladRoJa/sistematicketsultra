from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.control_center.access import (
    ControlAuthorizationError,
    resolve_control_access,
    resolve_effective_scope,
)


CUTOFF = date(2026, 9, 12)


def _user(*, role, sucursal_id=None, sucursales_ids=None):
    return SimpleNamespace(
        rol=role,
        sucursal_id=sucursal_id,
        sucursales_ids=sucursales_ids or [],
    )


def test_lector_global_resolves_global_scope():
    access = resolve_control_access(
        _user(role="LECTOR_GLOBAL"),
        as_of_date=CUTOFF,
    )

    assert access.max_scope == "GLOBAL"
    assert access.authorized_scope.type == "GLOBAL"
    assert access.authorized_scope.branch_ids == ()


@patch("app.control_center.access._filter_analytical_branch_ids")
def test_manager_resolves_fixed_branch_scope(filter_analytical):
    filter_analytical.return_value = (17,)

    access = resolve_control_access(
        _user(role="GERENTE", sucursal_id=17),
        as_of_date=CUTOFF,
    )

    assert access.max_scope == "BRANCH"
    assert access.authorized_scope.type == "BRANCH"
    assert access.authorized_scope.branch_ids == (17,)
    filter_analytical.assert_called_once_with((17,))


@patch("app.control_center.access._filter_analytical_branch_ids")
def test_manager_demo_branch_is_not_authorized_for_control(filter_analytical):
    filter_analytical.return_value = ()

    with pytest.raises(ControlAuthorizationError):
        resolve_control_access(
            _user(role="GERENTE", sucursal_id=999),
            as_of_date=CUTOFF,
        )


@patch("app.control_center.access._load_region_keys_by_branch")
@patch("app.control_center.access._filter_analytical_branch_ids")
def test_regional_single_region_resolves_region_scope(
    filter_analytical,
    load_regions,
):
    filter_analytical.return_value = (1, 2, 3)
    load_regions.return_value = {
        1: ("MXL_SL",),
        2: ("MXL_SL",),
        3: ("MXL_SL",),
    }

    access = resolve_control_access(
        _user(
            role="GERENTE_REGIONAL",
            sucursales_ids=[1, 2, 3],
        ),
        as_of_date=CUTOFF,
    )

    assert access.max_scope == "REGION"
    assert access.authorized_scope.type == "REGION"
    assert access.authorized_scope.region_keys == ("MXL_SL",)
    assert access.authorized_scope.branch_ids == (1, 2, 3)


@patch("app.control_center.access._load_region_keys_by_branch")
@patch("app.control_center.access._filter_analytical_branch_ids")
def test_regional_demo_assignment_is_removed_from_control_scope(
    filter_analytical,
    load_regions,
):
    filter_analytical.return_value = (1, 2)
    load_regions.return_value = {
        1: ("MXL_SL",),
        2: ("MXL_SL",),
    }

    access = resolve_control_access(
        _user(
            role="GERENTE_REGIONAL",
            sucursales_ids=[1, 2, 999],
        ),
        as_of_date=CUTOFF,
    )

    assert access.authorized_scope.type == "REGION"
    assert access.authorized_scope.branch_ids == (1, 2)
    load_regions.assert_called_once_with((1, 2), as_of_date=CUTOFF)


@patch("app.control_center.access._load_region_keys_by_branch")
@patch("app.control_center.access._filter_analytical_branch_ids")
def test_regional_mixed_assignments_resolves_branch_pool(
    filter_analytical,
    load_regions,
):
    filter_analytical.return_value = (1, 2, 20)
    load_regions.return_value = {
        1: ("MXL_SL",),
        2: ("MXL_SL",),
        20: ("TIJ_COSTA",),
    }

    access = resolve_control_access(
        _user(
            role="GERENTE_REGIONAL",
            sucursales_ids=[1, 2, 20],
        ),
        as_of_date=CUTOFF,
    )

    assert access.max_scope == "BRANCH_POOL"
    assert access.authorized_scope.type == "BRANCH_POOL"
    assert access.authorized_scope.region_keys == (
        "MXL_SL",
        "TIJ_COSTA",
    )
    assert access.authorized_scope.branch_ids == (1, 2, 20)


@patch("app.control_center.access._load_region_keys_by_branch")
@patch("app.control_center.access._filter_analytical_branch_ids")
def test_regional_cannot_request_global_scope(
    filter_analytical,
    load_regions,
):
    filter_analytical.return_value = (1, 2)
    load_regions.return_value = {
        1: ("MXL_SL",),
        2: ("MXL_SL",),
    }
    access = resolve_control_access(
        _user(
            role="GERENTE_REGIONAL",
            sucursales_ids=[1, 2],
        ),
        as_of_date=CUTOFF,
    )

    with pytest.raises(ControlAuthorizationError):
        resolve_effective_scope(
            access,
            as_of_date=CUTOFF,
            requested_scope_type="GLOBAL",
        )
