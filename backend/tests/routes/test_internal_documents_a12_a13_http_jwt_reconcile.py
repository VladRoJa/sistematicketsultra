"""A-12/A-13: conciliación HTTP/JWT de reglas ya integradas en main.

Documentos y actores sintéticos. Flask usa @jwt_required real, pero el usuario
DB y las queries de documentos/auditoría son doubles aislados, nunca producción.
NO modifica la política de visibilidad ni ejecuta mutaciones.
"""
import sqlite3
from types import SimpleNamespace

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token
from sqlalchemy import String, column

import app.routes.internal_documents_routes as routes
from app.utils import internal_documents_access as access


def _user(uid, username, role):
    return SimpleNamespace(
        id=uid, username=username, rol=role,
        sucursal_id=None, sucursales_ids=[], sucursales=[],
        department_id=None,
    )


ACTORS = {
    47: _user(47, "ADMICORP", "LECTOR_GLOBAL"),
    88: _user(88, "SISTEMAS_QA", "SISTEMAS"),
    99: _user(99, "GERENTE_QA", "GERENTE"),
}


def _document(doc_id=900, title="Consolidado de agregadoras"):
    return SimpleNamespace(
        id=doc_id, title=title,
        status=access.InternalDocumentStatus.PUBLISHED,
        visibility_mode=access.InternalDocumentVisibilityMode.CUSTOM,
        is_sensitive=True, current_version_id=doc_id + 100,
        created_by=1, owner_user_id=None,
    )


def _app(monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="a12-a13-fixtures-only")
    JWTManager(app)
    app.register_blueprint(
        routes.internal_documents_bp, url_prefix="/api/internal-documents"
    )
    monkeypatch.setattr(
        access.UserORM, "get_by_id",
        classmethod(lambda cls, uid: ACTORS.get(int(uid))),
    )
    monkeypatch.setattr(
        access, "_has_custom_visibility_access",
        lambda doc, context, action: (
            context.username == "ADMICORP" and action == "view"
        ),
    )
    return app


def _headers(app, actor_id):
    if actor_id is None:
        return {}
    with app.app_context():
        token = create_access_token(identity=str(actor_id))
    return {"Authorization": f"Bearer {token}"}


class _AuditQuery:
    def __init__(self):
        self.read_count = 0

    def filter_by(self, **_kw):
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        self.read_count += 1
        return [SimpleNamespace(id=55)]


class _Sort:
    def desc(self):
        return self


@pytest.mark.parametrize("title", [
    "Consolidado de agregadoras",
    "CONSOLIDADO DE AGREGADORAS",
    "  consolidado de agregadoras  ",
])
@pytest.mark.parametrize("actor_id,expected", [
    (None, 401),
    (88, 403),   # manager SISTEMAS, sin vista CUSTOM
    (99, 403),   # no es manager, aunque sea gerente
    (47, 200),   # ADMICORP con regla CUSTOM positiva
])
def test_a12_http_jwt_never_leaks_restricted_audit(
    monkeypatch, title, actor_id, expected,
):
    app = _app(monkeypatch)
    document = _document(title=title)
    audit_query = _AuditQuery()
    monkeypatch.setattr(routes, "_get_document_or_404", lambda _id: document)
    monkeypatch.setattr(
        routes, "InternalDocumentAuditLogORM",
        SimpleNamespace(query=audit_query, created_at=_Sort()),
    )
    monkeypatch.setattr(
        routes, "_serialize_audit_log",
        lambda item: {"id": item.id, "metadata_json": {"fixture": True}},
    )
    result = app.test_client().get(
        "/api/internal-documents/900/audit", headers=_headers(app, actor_id),
    )
    assert result.status_code == expected
    if expected == 200:
        assert result.get_json()["items"] == [
            {"id": 55, "metadata_json": {"fixture": True}}
        ]
        assert audit_query.read_count == 1
    else:
        assert "items" not in (result.get_json() or {})
        assert audit_query.read_count == 0


def test_a12_http_jwt_normal_document_keeps_sistemas_manager_audit(monkeypatch):
    app = _app(monkeypatch)
    document = _document(title="Manual operativo")
    document.visibility_mode = access.InternalDocumentVisibilityMode.PRIVATE
    document.is_sensitive = False
    audit_query = _AuditQuery()
    monkeypatch.setattr(routes, "_get_document_or_404", lambda _id: document)
    monkeypatch.setattr(
        routes, "InternalDocumentAuditLogORM",
        SimpleNamespace(query=audit_query, created_at=_Sort()),
    )
    monkeypatch.setattr(routes, "_serialize_audit_log", lambda item: {"id": item.id})
    result = app.test_client().get(
        "/api/internal-documents/900/audit", headers=_headers(app, 88),
    )
    assert result.status_code == 200
    assert audit_query.read_count == 1


class _ListQuery:
    """Evalúa expresiones SQLAlchemy sobre SQLite efímero para A-13."""
    def __init__(self, docs):
        self.docs = docs
        self.filters = []
        self.offset_value = 0
        self.limit_value = None

    def options(self, *_args):
        return self

    def filter(self, *expr):
        self.filters.extend(expr)
        return self

    def order_by(self, *_args):
        return self

    def offset(self, offset):
        self.offset_value = offset
        return self

    def limit(self, limit):
        self.limit_value = limit
        return self

    def _allowed(self, doc):
        with sqlite3.connect(":memory:") as con:
            for expr in self.filters:
                sql = str(expr.compile(compile_kwargs={"literal_binds": True}))
                if not con.execute(
                    f"SELECT 1 FROM (SELECT ? AS title, ? AS status) WHERE {sql}",
                    (doc.title, doc.status),
                ).fetchone():
                    return False
        return True

    def _matching(self):
        return [doc for doc in self.docs if self._allowed(doc)]

    def count(self):
        return len(self._matching())

    def all(self):
        result = self._matching()[self.offset_value:]
        return result if self.limit_value is None else result[:self.limit_value]


def _setup_list(monkeypatch, docs):
    app = _app(monkeypatch)
    q = _ListQuery(docs)
    monkeypatch.setattr(routes, "InternalDocumentORM", SimpleNamespace(
        query=q, title=column("title", String()),
        status=column("status", String()),
        created_at=_Sort(), id=_Sort(),
        category=object(), current_version=object(),
        owner_user=object(), owner_department=object(),
    ))
    monkeypatch.setattr(routes, "joinedload", lambda _column: None)
    monkeypatch.setattr(
        routes, "_resolve_document_period_filter",
        lambda: ({"period": "all", "date_from": None, "date_to": None}, None),
    )
    monkeypatch.setattr(routes, "_apply_document_period_filter", lambda query, _: query)
    monkeypatch.setattr(routes, "_apply_document_filters", lambda query: query)
    monkeypatch.setattr(
        routes, "_serialize_document",
        lambda document, **kwargs: {"id": document.id, "title": document.title},
    )
    return app


@pytest.mark.parametrize("title", [
    "Consolidado de agregadoras",
    "CONSOLIDADO DE AGREGADORAS",
    "   CONSOLIDADO DE AGREGADORAS   ",
])
def test_a13_http_jwt_filter_precedes_count_and_page(monkeypatch, title):
    docs = [_document(900, title), _document(901, "Manual operativo")]
    app = _setup_list(monkeypatch, docs)
    client = app.test_client()

    unauthorized = client.get("/api/internal-documents?period=all&page_size=1")
    assert unauthorized.status_code == 401

    result = client.get(
        "/api/internal-documents?period=all&page=1&page_size=1",
        headers=_headers(app, 88),
    )
    assert result.status_code == 200
    payload = result.get_json()
    assert payload["total"] == 1
    assert payload["items"] == [{"id": 901, "title": "Manual operativo"}]

    # La segunda página no debe anunciar ni exponer el documento oculto.
    page_two = client.get(
        "/api/internal-documents?period=all&page=2&page_size=1",
        headers=_headers(app, 88),
    )
    assert page_two.status_code == 200
    assert page_two.get_json()["total"] == 1
    assert page_two.get_json()["items"] == []


def test_a13_http_jwt_admicorp_keeps_special_listing(monkeypatch):
    app = _setup_list(monkeypatch, [
        _document(900, " CONSOLIDADO DE AGREGADORAS "),
    ])
    result = app.test_client().get(
        "/api/internal-documents?period=all",
        headers=_headers(app, 47),
    )
    assert result.status_code == 200
    assert result.get_json()["total"] == 1
    assert result.get_json()["items"][0]["id"] == 900
