from types import SimpleNamespace

from flask import Flask

import app.routes.internal_documents_routes as routes


class _FakeColumn:
    def __init__(self, name):
        self.name = name

    def __ne__(self, other):
        return f"{self.name} != {other!r}"

    def __eq__(self, other):
        return f"{self.name} == {other!r}"

    def desc(self):
        return f"{self.name} DESC"


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
        title=_FakeColumn("internal_documents.title"),
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
        "internal_documents.title" in expression
        and "!=" in expression
        for expression in rendered_filters
    )
