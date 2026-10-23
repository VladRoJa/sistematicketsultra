"""A-13: paridad entre el filtro SQL del listado y visibilidad especial.

Las consultas son SQL sobre SQLite EN MEMORIA, con documentos ficticios.
No se consulta ningun dato productivo ni se crea un archivo.
"""
import sqlite3
from types import SimpleNamespace

import pytest
from flask import Flask
from sqlalchemy import String, column

import app.routes.internal_documents_routes as routes
from app.utils import internal_documents_access as access


class _OrderingColumn:
    def __init__(self, name):
        self.name = name

    def desc(self):
        return self.name


class _DocumentQuery:
    def __init__(self, documents):
        self.documents = documents
        self.filters = []
        self._offset = 0
        self._limit = None

    def options(self, *_args):
        return self

    def filter(self, *expressions):
        self.filters.extend(expressions)
        return self

    def order_by(self, *_args):
        return self

    def offset(self, value):
        self._offset = value
        return self

    def limit(self, value):
        self._limit = value
        return self

    def _matches_filter(self, document, expression):
        # SQLAlchemy genera la misma expresion SQL para el guard que se usa
        # en PostgreSQL; aqui se evalua con SQLite solo en memoria.
        sql = str(expression.compile(compile_kwargs={"literal_binds": True}))
        with sqlite3.connect(":memory:") as con:
            value = con.execute(
                f"SELECT 1 FROM (SELECT ? AS title) WHERE {sql}",
                (document.title,),
            ).fetchone()
        return value is not None

    def _matching(self):
        return [
            document
            for document in self.documents
            if all(
                self._matches_filter(document, expression)
                for expression in self.filters
            )
        ]

    def count(self):
        return len(self._matching())

    def all(self):
        matches = self._matching()[self._offset :]
        return matches if self._limit is None else matches[: self._limit]


def _document(title, number):
    return SimpleNamespace(
        id=number,
        title=title,
        status=access.InternalDocumentStatus.PUBLISHED,
        visibility_mode=access.InternalDocumentVisibilityMode.CUSTOM,
        is_sensitive=True,
        current_version_id=number + 1000,
        created_by=7,
        owner_user_id=None,
    )


def _context(username, role):
    return access.InternalDocumentUserContext(
        user_id=88,
        username=username,
        role=role,
        sucursal_id=None,
        sucursales_ids=tuple(),
        department_id=None,
    )


def _list(monkeypatch, documents, username="SISTEMAS_QA", role="SISTEMAS", query_string=""):
    context = _context(username, role)
    fake_query = _DocumentQuery(documents)
    fake_model = SimpleNamespace(
        query=fake_query,
        title=column("title", String()),
        created_at=_OrderingColumn("created_at"),
        id=_OrderingColumn("id"),
        category=object(),
        current_version=object(),
        owner_user=object(),
        owner_department=object(),
    )
    app = Flask(__name__)
    app.config["TESTING"] = True

    monkeypatch.setattr(routes, "InternalDocumentORM", fake_model)
    monkeypatch.setattr(routes, "joinedload", lambda _attribute: None)
    monkeypatch.setattr(
        routes, "get_current_internal_document_context", lambda: context
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
        lambda doc, **_kw: {"id": doc.id, "title": doc.title},
    )
    monkeypatch.setattr(
        access,
        "_has_custom_visibility_access",
        lambda _doc, ctx, _action: ctx.username == "ADMICORP",
    )

    with app.test_request_context(f"/api/internal-documents?period=all&{query_string}"):
        response, status = getattr(routes.list_internal_documents, "__wrapped__")()

    return response.get_json(), status


@pytest.mark.parametrize(
    "title",
    [
        "Consolidado de agregadoras",
        "CONSOLIDADO DE AGREGADORAS",
        "  consolidado de agregadoras  ",
        "  CONSOLIDADO DE AGREGADORAS  ",
    ],
)
def test_a13_manager_list_excludes_consolidado_variants(monkeypatch, title):
    restricted = _document(title, 900)
    context = _context("SISTEMAS_QA", "SISTEMAS")
    assert access.can_view_internal_document(restricted, context) is False

    payload, status = _list(monkeypatch, [restricted])
    assert status == 200
    assert payload["total"] == 0
    assert payload["items"] == []


def test_a13_manager_list_preserves_normal_documents_and_pagination(monkeypatch):
    restricted = _document("CONSOLIDADO DE AGREGADORAS", 900)
    ordinary = _document("Manual operativo", 901)
    payload, status = _list(
        monkeypatch, [restricted, ordinary], query_string="page=1&page_size=1"
    )
    assert status == 200
    assert payload["total"] == 1
    assert payload["items"] == [{"id": 901, "title": "Manual operativo"}]


def test_a13_admicorp_preserves_special_document_listing(monkeypatch):
    restricted = _document("  CONSOLIDADO DE AGREGADORAS  ", 900)
    payload, status = _list(
        monkeypatch,
        [restricted],
        username="ADMICORP",
        role="LECTOR_GLOBAL",
    )
    assert status == 200
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == 900
