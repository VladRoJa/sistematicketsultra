"""Fase B / B1 — paridad de Nube sin alterar autorización HTTP.

Los actores y documentos son sintéticos. La prueba verifica el mismo
predicado puro que el guard de producción, jamás edita permission_grants.
"""
from types import SimpleNamespace

import pytest

from app.routes import permissions_catalog_routes as catalog
from app.routes import permissions_visual_audit_routes as visual
from app.utils.internal_documents_access import (
    InternalDocumentUserContext,
    can_manage_internal_documents,
)


def actor(role, username):
    return SimpleNamespace(
        id=909, username=username, rol=role, sucursal_id=7,
        sucursales_ids=[7], department_id=1,
    )


def context(user):
    return {
        "user": user, "role": user.rol.upper(),
        "sucursal_ids": list(user.sucursales_ids),
        "warehouse_operator": None, "planning_operator": None,
        "pm_scoped_read": False, "allow_ticket_delete_all": False,
    }


def action(name):
    key = name.split(".", 1)[1]
    return SimpleNamespace(
        id=70, full_key=name, key=key, name=name,
        risk_level="high", is_active=True,
        module=SimpleNamespace(key="internal_documents", name="Nube Corporativa",
                               base_action_id=70),
    )


@pytest.mark.parametrize("role,username,allowed", [
    ("SISTEMAS", "SISTEMAS_QA", True),
    ("ADMINISTRADOR", "ADMICORP", True),
    ("LECTOR_GLOBAL", "ADMICORP", True),
    ("ADMINISTRADOR", "ADMIN_QA", False),
    ("SUPER_ADMIN", "SUPER_QA", False),
    ("GERENTE", "GERENTE_QA", False),
])
def test_b1_manager_diagnostics_equals_real_guard_in_both_surfaces(role, username, allowed):
    user = actor(role, username)
    expected = can_manage_internal_documents(InternalDocumentUserContext(
        user_id=user.id, username=user.username, role=user.rol,
        sucursal_id=7, sucursales_ids=(7,), department_id=1,
    ))
    assert expected is allowed
    item = action("internal_documents.manage")
    summary = catalog._serialize_effective_action(item, user, context(user))
    matrix = visual.evaluate_pair(user, item, context(user))
    assert summary["allowed"] is matrix["legacy_allowed"] is matrix["catalog_allowed"] is allowed
    assert summary["details"]["mode"] == "compare_only"
    assert matrix["comparison"] == "coincide"
    assert matrix["diagnostic_only"] is True
    assert matrix["scope"] == "global"


def test_b1_does_not_create_permission_for_only_a_context_role():
    # No se resuelve user_id ni username de una persona por inferencia del JWT.
    naked_role = {
        "role": "SISTEMAS", "sucursal_ids": [],
        "warehouse_operator": None, "planning_operator": None,
    }
    diagnostic = catalog._effective_action_decision(
        action("internal_documents.manage"), None, naked_role
    )
    assert diagnostic["allowed"] is False
    assert diagnostic["reason"] == "missing_user_identity_for_manager_comparison"


@pytest.mark.parametrize("role,username", [
    ("SISTEMAS", "SISTEMAS_QA"),
    ("ADMINISTRADOR", "ADMICORP"),
    ("GERENTE", "GERENTE_QA"),
])
def test_b1_document_view_without_resource_remains_unknown(role, username):
    user = actor(role, username)
    item = action("internal_documents.view")
    entry = catalog._serialize_effective_action(item, user, context(user))
    assert entry["details"]["object_access_certified"] is False
    assert entry["details"]["requires_document_id"] is True

    row = visual.evaluate_pair(user, item, context(user))
    assert row["legacy_allowed"] is None
    assert row["catalog_allowed"] is None
    assert row["catalog_reason"] == "document_id_required_for_comparison"
    assert row["status"] == "no_concluyente"
    assert row["comparison"] == "no_concluyente"


@pytest.mark.parametrize("guard_result", [False, True])
def test_b1_document_specific_guard_never_becomes_catalog_grant(monkeypatch, guard_result):
    user = actor("GERENTE", "GERENTE_QA")
    target = SimpleNamespace(id=345)
    seen = []
    def guard(document, ctx):
        seen.append((document.id, ctx.user_id))
        return guard_result
    monkeypatch.setattr(visual, "can_view_internal_document", guard)

    row = visual.evaluate_pair(user, action("internal_documents.view"),
                               context(user), document=target)
    assert seen == [(345, 909)]
    assert row["legacy_allowed"] is guard_result
    assert row["catalog_allowed"] is None
    assert row["comparison"] == "no_concluyente"
    assert row["status"] == ("permitido" if guard_result else "denegado")
    assert row["scope"] == "documento"


def test_b1_module_entry_and_action_use_identical_manager_resolver():
    user = actor("SISTEMAS", "SISTEMAS_QA")
    item = action("internal_documents.manage")
    by_user = visual.evaluate_pair(user, item, context(user), is_module_entry=False)
    by_module = visual.evaluate_pair(user, item, context(user), is_module_entry=True)
    by_action = visual.evaluate_pair(user, item, context(user), is_module_entry=False)
    for row in (by_user, by_module, by_action):
        assert row["legacy_allowed"] is True
        assert row["catalog_allowed"] is True
        assert row["comparison"] == "coincide"
    assert by_module["module_entry"] is True
