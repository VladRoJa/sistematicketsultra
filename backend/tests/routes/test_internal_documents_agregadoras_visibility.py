from types import SimpleNamespace

from flask import Flask
from sqlalchemy import column

import app.routes.internal_documents_routes as routes
from app.utils import internal_documents_access as access


class _FakeColumn:
    def __init__(self, name):
        self.name = name

    def __ne__(self, other):
        return f"{self.name} != {other!r}"

    def __eq__(self, other):
        return f"{self.name} == {other!r}"

    def desc(self):
        return f"{self.name} DESC"

    def is_(self, other):
        return f"{self.name} IS {other!r}"


class _FakeQuery:
    def __init__(self):
        self.filters = []

    def options(self, *_args):
        return self

    def filter(self, *expressions):
        self.filters.extend(expressions)
        return self

    def order_by(self, *_args):
        return self

    def count(self):
        return 0

    def offset(self, _value):
        return self

    def limit(self, _value):
        return self

    def all(self):
        return []


def _unwrapped(endpoint):
    value = getattr(endpoint, "__wrapped__", None)
    assert value is not None
    return value


def test_list_hides_agregadoras_from_non_admicorp_manager(
    monkeypatch,
):
    app = Flask(__name__)
    app.config["TESTING"] = True

    fake_query = _FakeQuery()
    fake_model = SimpleNamespace(
        query=fake_query,
        title=column("internal_documents.title"),
        status=_FakeColumn("internal_documents.status"),
        created_at=_FakeColumn("internal_documents.created_at"),
        id=_FakeColumn("internal_documents.id"),
        category=object(),
        current_version=object(),
        owner_user=object(),
        owner_department=object(),
    )
    monkeypatch.setattr(
        routes,
        "InternalDocumentORM",
        fake_model,
    )
    monkeypatch.setattr(
        routes,
        "joinedload",
        lambda _attribute: None,
    )
    monkeypatch.setattr(
        routes,
        "get_current_internal_document_context",
        lambda: SimpleNamespace(
            user_id=88,
            username="SISTEMAS_USER",
            role="SISTEMAS",
            sucursal_id=None,
            sucursales_ids=tuple(),
            department_id=None,
        ),
    )
    monkeypatch.setattr(
        routes,
        "can_manage_internal_documents",
        lambda _context: True,
    )
    monkeypatch.setattr(
        routes,
        "_resolve_document_period_filter",
        lambda: (
            {
                "period": "all",
                "date_from": None,
                "date_to": None,
            },
            None,
        ),
    )
    monkeypatch.setattr(
        routes,
        "_apply_document_period_filter",
        lambda query, _period: query,
    )
    monkeypatch.setattr(
        routes,
        "_apply_document_filters",
        lambda query: query,
    )

    with app.test_request_context(
        "/api/internal-documents?period=all"
    ):
        response, status_code = _unwrapped(
            routes.list_internal_documents
        )()

    assert status_code == 200
    assert response.get_json()["total"] == 0

    rendered_filters = [
        str(expression)
        for expression in fake_query.filters
    ]

    assert any(
        "upper(trim(internal_documents.title))" in expression.lower()
        and "!=" in expression
        for expression in rendered_filters
    )


def test_by_link_does_not_expose_agregadoras_metadata_to_sistemas(monkeypatch):
    """
    Fase A: reproducir la diferencia entre permiso de administrar Nube y
    visibilidad de un documento sensible con reglas propias.

    Este test es deliberadamente RED si /by-link omite la comprobación
    de can_view_internal_document() para usuarios manager.
    """
    app = Flask(__name__)
    app.config["TESTING"] = True

    context = access.InternalDocumentUserContext(
        user_id=88,
        username="SISTEMAS_USER",
        role="SISTEMAS",
        sucursal_id=None,
        sucursales_ids=tuple(),
        department_id=None,
    )
    document = SimpleNamespace(
        id=900,
        title="Consolidado de agregadoras",
        status=access.InternalDocumentStatus.PUBLISHED,
        visibility_mode=access.InternalDocumentVisibilityMode.CUSTOM,
        is_sensitive=True,
        current_version_id=901,
        created_by=7,
        owner_user_id=None,
    )

    # El documento está restringido a ADMICORP mediante su visibilidad.
    monkeypatch.setattr(
        access,
        "_has_custom_visibility_access",
        lambda _document, user, _action: user.username == "ADMICORP",
    )
    assert access.can_manage_internal_documents(context) is True
    assert access.can_view_internal_document(document, context) is False

    class _LinkedDocumentQuery(_FakeQuery):
        def join(self, *_args):
            return self

        def all(self):
            # Simula un documento que sí tiene vínculo GENERAL activo.
            return [document]

    fake_query = _LinkedDocumentQuery()
    fake_model = SimpleNamespace(
        query=fake_query,
        id=_FakeColumn("internal_documents.id"),
        status=_FakeColumn("internal_documents.status"),
        created_at=_FakeColumn("internal_documents.created_at"),
        category=object(),
        current_version=object(),
        owner_user=object(),
        owner_department=object(),
    )
    fake_link_model = SimpleNamespace(
        document_id=_FakeColumn("internal_document_links.document_id"),
        entity_type=_FakeColumn("internal_document_links.entity_type"),
        is_active=_FakeColumn("internal_document_links.is_active"),
        entity_id=_FakeColumn("internal_document_links.entity_id"),
        entity_key=_FakeColumn("internal_document_links.entity_key"),
        link_role=_FakeColumn("internal_document_links.link_role"),
        is_primary=_FakeColumn("internal_document_links.is_primary"),
        created_at=_FakeColumn("internal_document_links.created_at"),
    )

    monkeypatch.setattr(routes, "InternalDocumentORM", fake_model)
    monkeypatch.setattr(routes, "InternalDocumentLinkORM", fake_link_model)
    monkeypatch.setattr(routes, "joinedload", lambda _attribute: None)
    monkeypatch.setattr(
        routes, "get_current_internal_document_context", lambda: context
    )
    monkeypatch.setattr(
        routes,
        "_serialize_document",
        lambda item, **_kwargs: {"id": item.id, "title": item.title},
    )

    with app.test_request_context(
        "/api/internal-documents/by-link?entity_type=GENERAL"
    ):
        response, status_code = _unwrapped(
            routes.list_internal_documents_by_link
        )()

    assert status_code == 200
    assert response.get_json()["items"] == []
