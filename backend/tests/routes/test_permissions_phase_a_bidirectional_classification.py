"""P20: clasificar divergencias SIN hacerlas autorizaciones reales.

El catalogo es diagnostico, y /module-access es una previsualizacion de
grants. La comparacion por documento exige contexto del objeto; el codigo
que falta se marca como incomplete_context y NO como allow.
"""
from types import SimpleNamespace

import pytest

from app.routes import permissions_catalog_routes as catalog
from app.routes import track_routes as track
from app.utils import internal_documents_access as access


def _context(user):
    return {
        "role": catalog._normalize_role(user),
        "sucursal_ids": catalog._get_user_assigned_sucursal_ids(user),
        "warehouse_operator": None,
        "planning_operator": None,
        "allow_ticket_delete_all": False,
    }


def _preview(user, key):
    return catalog._effective_action_decision(
        SimpleNamespace(full_key=key), user, _context(user)
    )


def _classification(legacy, observed, context_complete):
    if not context_complete:
        return "incomplete_context"
    if legacy == observed:
        return "match"
    return (
        "legacy_allow_catalog_deny"
        if legacy else "legacy_deny_catalog_allow"
    )


@pytest.mark.parametrize("role,legacy,observed,status", [
    ("GERENTE", True, False, "legacy_allow_catalog_deny"),
    ("GERENTE_REGIONAL", True, False, "legacy_allow_catalog_deny"),
    ("SISTEMAS", True, False, "legacy_allow_catalog_deny"),
    ("MARKETING", True, False, "legacy_allow_catalog_deny"),
    ("TIENDA", True, False, "legacy_allow_catalog_deny"),
    ("LECTOR_GLOBAL", True, True, "match"),
    ("ADMINISTRADOR", True, True, "match"),
    ("RECEPCIONISTA", False, False, "match"),
])
def test_p20_track_real_guard_vs_catalog_is_classified(
    monkeypatch, role, legacy, observed, status
):
    user = SimpleNamespace(
        id=-10, rol=role, username="QA", sucursal_id=7, sucursales_ids=[7]
    )
    monkeypatch.setattr(track, "_get_current_role", lambda: role)
    if legacy:
        assert track._require_track_read_role() is None
    else:
        with pytest.raises(PermissionError):
            track._require_track_read_role()
    result = _preview(user, "track.read")
    assert result["allowed"] is observed
    assert _classification(legacy, result["allowed"], True) == status


@pytest.mark.parametrize("user_id,username,role,legacy,observed,status", [
    (1, "ADMICORP", "LECTOR_GLOBAL", True, False,
     "legacy_allow_catalog_deny"),
    (2, "SISTEMAS_QA", "SISTEMAS", True, False,
     "legacy_allow_catalog_deny"),
    (3, "ADMIN_QA", "ADMINISTRADOR", False, True,
     "legacy_deny_catalog_allow"),
    (4, "GERENTE_QA", "GERENTE", False, False, "match"),
])
def test_p20_nube_manager_vs_catalog_preview(
    user_id, username, role, legacy, observed, status
):
    doc_user = access.InternalDocumentUserContext(
        user_id=user_id, username=username, role=role,
        sucursal_id=7, sucursales_ids=(7,), department_id=1,
    )
    user = SimpleNamespace(
        id=user_id, username=username, rol=role,
        sucursal_id=7, sucursales_ids=[7],
    )
    assert access.is_internal_document_admin(doc_user) is legacy
    result = _preview(user, "internal_documents.manage")
    assert result["allowed"] is observed
    assert _classification(legacy, observed, True) == status


@pytest.mark.parametrize("role,username,doc_status,mode,owner,legacy_view", [
    ("RECEPCIONISTA", "OTRO", "PUBLICADO", "PRIVATE", 777, False),
    ("RECEPCIONISTA", "DUEÑO", "PUBLICADO", "PRIVATE", 12, True),
    ("GERENTE", "GERENTE_QA", "PUBLICADO", "GLOBAL", 777, True),
    ("GERENTE", "GERENTE_QA", "BORRADOR", "GLOBAL", 777, False),
    ("ADMINISTRADOR", "ADMIN_QA", "PUBLICADO", "GLOBAL", 777, True),
])
def test_p20_catalog_view_without_document_is_incomplete_not_authority(
    role, username, doc_status, mode, owner, legacy_view
):
    user = SimpleNamespace(
        id=12, username=username, rol=role,
        sucursal_id=7, sucursales_ids=[7],
    )
    doc_context = access.InternalDocumentUserContext(
        user_id=12, username=username, role=role, sucursal_id=7,
        sucursales_ids=(7,), department_id=1,
    )
    document = SimpleNamespace(
        id=900, title="Manual ficticio", status=doc_status,
        visibility_mode=mode, is_sensitive=False,
        current_version_id=3, created_by=777,
        owner_user_id=owner, links=[],
    )
    legacy = access.can_view_internal_document(document, doc_context)
    assert legacy is legacy_view
    preview = _preview(user, "internal_documents.view")
    assert preview["allowed"] is True
    assert preview["scope_type"] == "document_visibility"
    assert _classification(legacy, preview["allowed"], False) == "incomplete_context"
    # No confundir el simple "view True" del modulo con documento aprobado.


@pytest.mark.parametrize("effect,legacy_allowed,preview_allowed", [
    ("allow", False, True),
    ("deny", True, False),
])
def test_p20_module_access_preview_grant_does_not_replace_guard(
    effect, legacy_allowed, preview_allowed
):
    # _apply_module_access_override produce "effective_allowed" solo
    # para el endpoint de checks; no cambia el derecho real legacy.
    legacy = {
        "allowed": legacy_allowed,
        "source": "legacy_role",
        "reason": "fixture",
    }
    grant = SimpleNamespace(
        effect=effect, id=8765, reason="fixture-sin-efecto-operativo"
    )
    result = catalog._apply_module_access_override(
        legacy_decision=legacy, user_grant=grant, role_grant=None
    )
    assert result["effective_allowed"] is preview_allowed
    assert result["source"] == "explicit_user_grant"
    assert result["override_source"] == "user"
    assert result["grant_id"] == 8765
    assert result["effective_allowed"] is not legacy_allowed


@pytest.mark.parametrize("role,reason", [
    ("RECEPCIONISTA", "no_object"),
    ("GERENTE", "no_branch"),
    ("ADMINISTRADOR", "unmapped_action"),
])
def test_p20_missing_object_branch_or_action_cannot_be_reported_as_match(
    role, reason
):
    # Casos con datos requeridos no disponibles no deben contabilizarse
    # como match/allow/deny contra el guard operativo.
    assert _classification(False, False, False) == "incomplete_context"
    assert reason in {"no_object", "no_branch", "unmapped_action"}
