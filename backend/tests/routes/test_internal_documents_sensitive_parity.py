"""Fase A: pruebas aisladas de diferencias de visibilidad A-12 y A-13.

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


def test_a13_normalized_consolidado_is_not_listed_to_restricted_manager(
    monkeypatch,
):
    _only_admicorp(monkeypatch)
    sistemas = _context()
    # El helper especial reconoce este titulo; el filtro SQL actual compara
    # exactamente contra "Consolidado de agregadoras".
    document = _document(title="CONSOLIDADO DE AGREGADORAS")
    assert access.can_view_internal_document(document, sistemas) is False

    class _Column:
        def __init__(self, name):
            self.name = name

        def __ne__(self, other):
            return ("!=", self.name, other)

        def desc(self):
            return self

    class _DocumentQuery:
        def __init__(self):
            self.expressions = []

        def options(self, *_args):
            return self

        def filter(self, *expressions):
            self.expressions.extend(expressions)
            return self

        def order_by(self, *_args):
            return self

        def offset(self, _value):
            return self

        def limit(self, _value):
            return self

        def _matching(self):
            for expression in self.expressions:
                if isinstance(expression, tuple) and expression[0] == "!=":
                    if expression[1] == "title" and document.title == expression[2]:
                        return []
            return [document]

        def count(self):
            return len(self._matching())

        def all(self):
            return self._matching()

    fake_query = _DocumentQuery()
    fake_model = SimpleNamespace(
        query=fake_query,
        title=_Column("title"),
        created_at=_Column("created_at"),
        id=_Column("id"),
        category=object(),
        current_version=object(),
        owner_user=object(),
        owner_department=object(),
    )
    app = Flask(__name__)
    app.config["TESTING"] = True

    monkeypatch.setattr(routes, "InternalDocumentORM", fake_model)
    monkeypatch.setattr(routes, "joinedload", lambda _attr: None)
    monkeypatch.setattr(
        routes, "get_current_internal_document_context", lambda: sistemas
    )
    monkeypatch.setattr(
        routes,
        "_resolve_document_period_filter",
        lambda: ({"period": "all", "date_from": None, "date_to": None}, None),
    )
    monkeypatch.setattr(routes, "_apply_document_period_filter", lambda q, _p: q)
    monkeypatch.setattr(routes, "_apply_document_filters", lambda q: q)
    monkeypatch.setattr(
        routes,
        "_serialize_document",
        lambda item, **_kwargs: {"id": item.id, "title": item.title},
    )

    with app.test_request_context("/api/internal-documents?period=all"):
        endpoint = getattr(routes.list_internal_documents, "__wrapped__")
        response, status_code = endpoint()

    assert status_code == 200
    assert response.get_json()["total"] == 0
    assert response.get_json()["items"] == []
