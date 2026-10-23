"""Fase A: pruebas aisladas de autorización de auditoría sensible A-12.

Los usuarios, documentos y logs son ficticios. Nunca se abre la base productiva.
"""
from types import SimpleNamespace

from flask import Flask

import app.routes.internal_documents_routes as routes
from app.utils import internal_documents_access as access


def _context(username="SISTEMAS_QA", role="SISTEMAS"):
    return access.InternalDocumentUserContext(
        user_id=88,
        username=username,
        role=role,
        sucursal_id=None,
        sucursales_ids=tuple(),
        department_id=None,
    )


def _document(title="Consolidado de agregadoras"):
    return SimpleNamespace(
        id=900,
        title=title,
        status=access.InternalDocumentStatus.PUBLISHED,
        visibility_mode=access.InternalDocumentVisibilityMode.CUSTOM,
        is_sensitive=True,
        current_version_id=901,
        created_by=7,
        owner_user_id=None,
    )


def _only_admicorp(monkeypatch):
    monkeypatch.setattr(
        access,
        "_has_custom_visibility_access",
        lambda _document, context, _action: context.username == "ADMICORP",
    )


def test_a12_manager_without_document_view_cannot_read_sensitive_audit(monkeypatch):
    _only_admicorp(monkeypatch)
    document = _document()
    sistemas = _context()

    assert access.can_manage_internal_documents(sistemas) is True
    assert access.can_view_internal_document(document, sistemas) is False
    # CONTRATO DE SEGURIDAD PENDIENTE DE APROBACION:
    # la lectura de auditoria no debe escapar la restriccion por documento.
    assert access.can_view_internal_document_audit(document, sistemas) is False


def test_a12_sensitive_audit_endpoint_denies_document_without_view(monkeypatch):
    _only_admicorp(monkeypatch)
    document = _document()
    sistemas = _context()
    app = Flask(__name__)
    app.config["TESTING"] = True

    class _Column:
        def desc(self):
            return self

    class _AuditQuery:
        def filter_by(self, **_kwargs):
            return self

        def order_by(self, *_args):
            return self

        def all(self):
            return [SimpleNamespace(id=1)]

    monkeypatch.setattr(access, "get_current_internal_document_context", lambda: sistemas)
    monkeypatch.setattr(routes, "_get_document_or_404", lambda _id: document)
    monkeypatch.setattr(
        routes,
        "InternalDocumentAuditLogORM",
        SimpleNamespace(query=_AuditQuery(), created_at=_Column()),
    )
    monkeypatch.setattr(
        routes, "_serialize_audit_log", lambda _item: {"metadata": "QA_FICTICIO"}
    )

    with app.test_request_context("/api/internal-documents/900/audit"):
        endpoint = getattr(routes.get_internal_document_audit, "__wrapped__")
        response, status_code = endpoint(900)

    assert status_code == 403
    assert response.get_json().get("items") is None


def test_a12_admicorp_with_view_can_read_sensitive_audit(monkeypatch):
    _only_admicorp(monkeypatch)
    document = _document()
    admicorp = _context("ADMICORP", "LECTOR_GLOBAL")

    assert access.can_manage_internal_documents(admicorp) is True
    assert access.can_view_internal_document(document, admicorp) is True
    assert access.can_view_internal_document_audit(document, admicorp) is True


def test_a12_manager_keeps_audit_access_for_ordinary_document():
    document = _document(title="Manual operativo")
    document.visibility_mode = access.InternalDocumentVisibilityMode.PRIVATE
    document.is_sensitive = False
    sistemas = _context()

    assert access.can_manage_internal_documents(sistemas) is True
    assert access.can_view_internal_document(document, sistemas) is True
    assert access.can_view_internal_document_audit(document, sistemas) is True


def test_a12_sensitive_document_must_be_published_for_audit(monkeypatch):
    _only_admicorp(monkeypatch)
    document = _document()
    document.status = access.InternalDocumentStatus.DRAFT
    admicorp = _context("ADMICORP", "LECTOR_GLOBAL")

    assert access.can_view_internal_document(document, admicorp) is False
    assert access.can_view_internal_document_audit(document, admicorp) is False
