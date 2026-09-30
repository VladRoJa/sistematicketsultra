from types import SimpleNamespace

from flask import Flask

import app.routes.internal_documents_routes as routes


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
    monkeypatch.setattr(
        routes.InternalDocumentORM,
        "query",
        fake_query,
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
        lambda: ("all", None),
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
        "internal_documents.title" in expression
        and "!=" in expression
        for expression in rendered_filters
    )
