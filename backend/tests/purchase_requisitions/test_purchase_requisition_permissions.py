from __future__ import annotations

from types import SimpleNamespace

from app import create_app
from app.utils.purchase_requisition_permissions import (
    assigned_branch_ids,
    can_create_for_branch,
    can_purchase_requisition_create,
    can_purchase_requisition_manage_quotation,
    can_purchase_requisition_review,
    can_purchase_requisition_view,
    has_global_purchase_requisition_read,
)


def _user(
    *,
    user_id=1,
    role="RECEPCIONISTA",
    branch_id=10,
    branch_ids=(),
    username="USER",
):
    return SimpleNamespace(
        id=user_id,
        rol=role,
        sucursal_id=branch_id,
        sucursales_ids=list(branch_ids),
        username=username,
    )


def _requisition(
    *,
    creator_id=99,
    branch_id=10,
    status="PENDING_REVIEW",
):
    return SimpleNamespace(
        created_by_user_id=creator_id,
        sucursal_id=branch_id,
        status=status,
    )


def test_review_roles_are_exactly_contract_roles():
    assert can_purchase_requisition_review(
        _user(role="GERENCIA DEPORTIVA")
    )
    assert can_purchase_requisition_review(
        _user(role="ADMINISTRADOR")
    )

    for role in (
        "GERENTE",
        "MANTENIMIENTO",
        "RECEPCIONISTA",
        "LECTOR_GLOBAL",
        "SR_MANTENIMIENTO",
        "AUX_MANTENIMIENTO",
    ):
        assert not can_purchase_requisition_review(
            _user(role=role)
        )


def test_admicorp_is_authorized_by_role_not_username():
    admicorp = _user(
        user_id=7,
        role="ADMINISTRADOR",
        username="ADMICORP",
    )
    other_admin = _user(
        user_id=8,
        role="ADMINISTRADOR",
        username="OTRO_ADMIN",
    )
    assert can_purchase_requisition_review(admicorp)
    assert can_purchase_requisition_review(other_admin)


def test_lector_global_reads_globally_but_never_writes():
    lector = _user(
        role="LECTOR_GLOBAL",
        branch_id=1,
    )
    foreign = _requisition(
        branch_id=99,
        status="PENDING_REVIEW",
    )

    assert has_global_purchase_requisition_read(lector)
    assert can_purchase_requisition_view(lector, foreign)
    assert not can_purchase_requisition_create(lector)
    assert not can_purchase_requisition_review(lector)
    assert not can_purchase_requisition_manage_quotation(lector)


def test_regular_user_create_scope_is_primary_branch():
    user = _user(
        role="RECEPCIONISTA",
        branch_id=10,
        branch_ids=(10, 11),
    )
    assert can_purchase_requisition_create(user)
    assert can_create_for_branch(user, 10)
    assert not can_create_for_branch(user, 11)


def test_regional_manager_scope_uses_assigned_branches():
    user = _user(
        role="GERENTE_REGIONAL",
        branch_id=1000,
        branch_ids=(10, 11, 12),
    )
    assert assigned_branch_ids(user) == (10, 11, 12)
    assert can_create_for_branch(user, 11)
    assert not can_create_for_branch(user, 20)
    assert can_purchase_requisition_view(
        user,
        _requisition(branch_id=12),
    )
    assert not can_purchase_requisition_view(
        user,
        _requisition(branch_id=20),
    )


def test_administrator_can_create_for_any_valid_branch():
    admin = _user(
        role="ADMINISTRADOR",
        branch_id=1000,
    )
    assert can_create_for_branch(admin, 1)
    assert can_create_for_branch(admin, 999)


def test_maintenance_visibility_starts_only_after_approval():
    maintenance = _user(
        role="MANTENIMIENTO",
        branch_id=1000,
    )
    pending = _requisition(
        branch_id=10,
        status="PENDING_REVIEW",
    )
    needs_info = _requisition(
        branch_id=10,
        status="NEEDS_INFO",
    )
    rejected = _requisition(
        branch_id=10,
        status="REJECTED",
    )
    quotation = _requisition(
        branch_id=10,
        status="IN_QUOTATION",
    )

    assert not can_purchase_requisition_view(
        maintenance,
        pending,
    )
    assert not can_purchase_requisition_view(
        maintenance,
        needs_info,
    )
    assert not can_purchase_requisition_view(
        maintenance,
        rejected,
    )
    assert can_purchase_requisition_view(
        maintenance,
        quotation,
    )
    assert can_purchase_requisition_manage_quotation(
        maintenance
    )


def test_creator_keeps_visibility_even_if_maintenance_role():
    creator = _user(
        user_id=55,
        role="MANTENIMIENTO",
        branch_id=1000,
    )
    requisition = _requisition(
        creator_id=55,
        branch_id=10,
        status="PENDING_REVIEW",
    )
    assert can_purchase_requisition_view(
        creator,
        requisition,
    )


def test_access_route_is_registered_under_independent_namespace():
    app = create_app()
    rules = {
        rule.rule: sorted(rule.methods)
        for rule in app.url_map.iter_rules()
    }
    assert "/api/purchase-requisitions/access" in rules
    assert "GET" in rules[
        "/api/purchase-requisitions/access"
    ]
