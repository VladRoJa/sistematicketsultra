"""B2: acceso GET de Nube por documento, JWT e IDOR sin archivos reales.

Todos los actores, IDs, versiones y metadatos son sintéticos; se utilizan
los guards reales y se sustituyen únicamente las lecturas ORM/serialización.
Nunca se abre un archivo ni se conecta PostgreSQL.
"""
import csv
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask, Response
from flask_jwt_extended import JWTManager, create_access_token

import app.routes.internal_documents_routes as routes
from app.utils import internal_documents_access as access

ROOT = Path(__file__).resolve().parents[3]
P1 = ROOT / "docs/security/permissions_phase_a_p34_nube_pilot_p1_reads_20261027.csv"
BASE = "/api/internal-documents"
RESOURCE_PATHS = [
    "/900",
    "/900/versions",
    "/900/links",
    "/900/external-resources",
    "/900/download",
    "/900/versions/990/download",
    "/900/audit",
]
ACTORS = {
    47: SimpleNamespace(id=47, username="ADMICORP", rol="LECTOR_GLOBAL",
                        sucursal_id=7, sucursales_ids=[7], sucursales=[],
                        department_id=1),
    88: SimpleNamespace(id=88, username="SISTEMAS_QA", rol="SISTEMAS",
                        sucursal_id=7, sucursales_ids=[7], sucursales=[],
                        department_id=1),
    99: SimpleNamespace(id=99, username="GERENTE_QA", rol="GERENTE",
                        sucursal_id=8, sucursales_ids=[8], sucursales=[],
                        department_id=1),
}


def _document(*, special=False):
    return SimpleNamespace(
        id=900, title="Consolidado de agregadoras" if special else "Guía ficticia",
        status=access.InternalDocumentStatus.PUBLISHED,
        visibility_mode=(access.InternalDocumentVisibilityMode.CUSTOM if special
                         else access.InternalDocumentVisibilityMode.PRIVATE),
        is_sensitive=special,
        current_version_id=990,
        current_version=SimpleNamespace(
            warehouse_upload=SimpleNamespace(
                id=991, original_filename="synthetic.txt", mime_type="text/plain",
            )
        ),
        created_by=47, owner_user_id=47, owner_department_id=None,
        links=[], visibility_rules=[],
    )


@pytest.fixture
def site(monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="nube-b2-fixture-not-production")
    JWTManager(app)
    app.register_blueprint(routes.internal_documents_bp, url_prefix=BASE)
    monkeypatch.setattr(
        access.UserORM, "get_by_id",
        classmethod(lambda cls, user_id: ACTORS.get(int(user_id))),
    )
    monkeypatch.setattr(
        access, "_has_custom_visibility_access",
        lambda document, context, action: (
            context.username == "ADMICORP"
        ),
    )
    return app, app.test_client()


def _auth(app, uid):
    if uid is None:
        return {}
    with app.app_context():
        token = create_access_token(identity=str(uid))
    return {"Authorization": f"Bearer {token}"}


def test_b2_all_nine_p1_get_require_jwt_before_entering_handlers(site, monkeypatch):
    app, client = site
    calls = Mock(side_effect=AssertionError("handler attempted object access"))
    monkeypatch.setattr(routes, "_get_document_or_404", calls)
    with P1.open(encoding="utf-8", newline="") as file:
        data = list(csv.DictReader(file))
    assert len(data) == len({r["route"] for r in data}) == 9
    for row in data:
        assert row["method"] == "GET" and row["priority"] == "P1"
        path = row["route"].replace("<int:document_id>", "900")
        path = path.replace("<int:version_id>", "990")
        result = client.get(path)
        assert result.status_code == 401, row["route"]
    calls.assert_not_called()


@pytest.mark.parametrize("path", RESOURCE_PATHS)
@pytest.mark.parametrize("actor_id,special", [
    (99, False),  # gerente, documento privado de otro usuario/sucursal
    (88, True),   # SISTEMAS manager pero consolidado CUSTOM sin vista
])
def test_b2_foreign_or_special_document_denied_before_content_or_logs(
    site, monkeypatch, path, actor_id, special,
):
    app, client = site
    document = _document(special=special)
    lookup = Mock(return_value=document)
    never_send = Mock(side_effect=AssertionError("file read/response must be guarded"))
    never_path = Mock(side_effect=AssertionError("path must be guarded"))
    monkeypatch.setattr(routes, "_get_document_or_404", lookup)
    monkeypatch.setattr(routes, "send_file", never_send)
    monkeypatch.setattr(routes, "_build_safe_file_path", never_path)
    result = client.get(BASE + path, headers=_auth(app, actor_id))
    assert result.status_code == 403, (actor_id, path, result.get_json())
    lookup.assert_called_once_with(900)
    never_send.assert_not_called()
    never_path.assert_not_called()
    assert "items" not in (result.get_json() or {})


@pytest.mark.parametrize("path", RESOURCE_PATHS)
def test_b2_missing_document_returns_404_not_download_or_logs(site, monkeypatch, path):
    app, client = site
    monkeypatch.setattr(routes, "_get_document_or_404", Mock(return_value=None))
    send = Mock(side_effect=AssertionError("missing document cannot be downloaded"))
    monkeypatch.setattr(routes, "send_file", send)
    response = client.get(BASE + path, headers=_auth(app, 47))
    assert response.status_code == 404
    send.assert_not_called()


@pytest.mark.parametrize("actor_id", [47, 88])
def test_b2_authorized_ordinary_detail_uses_real_view_guard(
    site, monkeypatch, actor_id
):
    app, client = site
    monkeypatch.setattr(routes, "_get_document_or_404",
                        lambda doc_id: _document() if doc_id == 900 else None)
    serialize = Mock(return_value={"id": 900, "title": "synthetic"})
    monkeypatch.setattr(routes, "_serialize_document", serialize)
    res = client.get(BASE + "/900", headers=_auth(app, actor_id))
    assert res.status_code == 200
    assert res.get_json()["id"] == 900
    serialize.assert_called_once()


class _Sort:
    def asc(self):
        return self

    def desc(self):
        return self


class _Query:
    def __init__(self, row=None):
        self.row = row
        self.filter_args = None

    def options(self, *_args):
        return self

    def filter_by(self, **args):
        self.filter_args = args
        return self

    def order_by(self, *_args):
        return self

    def first(self):
        if self.filter_args is None:
            return None
        if self.filter_args.get("document_id") != 900:
            return None
        if self.filter_args.get("id") != 990:
            return None
        return self.row

    def all(self):
        return [self.row] if self.row is not None else []


def test_b2_historical_version_must_belong_to_requested_document(
    site, monkeypatch,
):
    app, client = site
    monkeypatch.setattr(routes, "_get_document_or_404", lambda _id: _document())
    version = SimpleNamespace(
        id=990, warehouse_upload=SimpleNamespace(
            original_filename="synthetic.txt", mime_type="text/plain",
        )
    )
    query = _Query(row=version)
    model = SimpleNamespace(query=query, warehouse_upload=object())
    monkeypatch.setattr(routes, "InternalDocumentVersionORM", model)
    monkeypatch.setattr(routes, "joinedload", lambda *_args: object())
    no_file = Mock(side_effect=AssertionError("unrelated historical version"))
    monkeypatch.setattr(routes, "send_file", no_file)
    monkeypatch.setattr(routes, "_build_safe_file_path", no_file)
    response = client.get(BASE + "/900/versions/991/download", headers=_auth(app, 47))
    assert response.status_code == 404
    assert query.filter_args == {"id": 991, "document_id": 900}
    no_file.assert_not_called()

    # Control positivo con la misma versión vinculada al documento.
    monkeypatch.setattr(routes, "_build_safe_file_path", lambda _: "/fixture/synthetic.txt")
    send = Mock(return_value=Response("synthetic", mimetype="text/plain"))
    monkeypatch.setattr(routes, "send_file", send)
    valid = client.get(BASE + "/900/versions/990/download", headers=_auth(app, 47))
    assert valid.status_code == 200
    assert query.filter_args == {"id": 990, "document_id": 900}
    send.assert_called_once()


def test_b2_current_download_requires_real_guard_then_can_return_synthetic(
    site, monkeypatch,
):
    app, client = site
    monkeypatch.setattr(routes, "_get_document_or_404", lambda _id: _document())
    monkeypatch.setattr(routes, "_build_safe_file_path", lambda _: "/fixture/synthetic.txt")
    send = Mock(return_value=Response("synthetic", mimetype="text/plain"))
    monkeypatch.setattr(routes, "send_file", send)
    result = client.get(BASE + "/900/download", headers=_auth(app, 47))
    assert result.status_code == 200
    send.assert_called_once()


def test_b2_audit_manager_only_after_document_guard(site, monkeypatch):
    app, client = site
    monkeypatch.setattr(routes, "_get_document_or_404", lambda _id: _document())
    audit_q = _Query(row=SimpleNamespace(id=77))
    fake = SimpleNamespace(query=audit_q, created_at=_Sort())
    monkeypatch.setattr(routes, "InternalDocumentAuditLogORM", fake)
    monkeypatch.setattr(routes, "_serialize_audit_log",
                        lambda log: {"id": log.id, "source": "synthetic"})
    allowed = client.get(BASE + "/900/audit", headers=_auth(app, 88))
    assert allowed.status_code == 200
    assert allowed.get_json()["items"] == [{"id": 77, "source": "synthetic"}]
    assert audit_q.filter_args == {"document_id": 900}


def test_b2_list_and_by_link_keep_visibility_filters_before_response():
    # These two collection endpoints use different ORM paths. Their existing
    # HTTP+JWT/SQLite fixture suites (A13 + special by-link) are part of CI B2.
    from inspect import getsource
    listing = getsource(routes.list_internal_documents)
    linked = getsource(routes.list_internal_documents_by_link)
    assert "can_view_internal_document(item, context)" in listing
    assert "can_view_internal_document(document, context)" in linked
    assert "visible_documents" in linked
    assert "query.count()" in listing


@pytest.mark.parametrize("path,kind,serializer,model_name", [
    ("/900/versions", "versions", "_serialize_version", "InternalDocumentVersionORM"),
    ("/900/links", "links", "_serialize_document_link", "InternalDocumentLinkORM"),
    ("/900/external-resources", "external", "_serialize_external_resource", "InternalDocumentExternalResourceORM"),
])
def test_b2_authorized_related_read_uses_parent_document_guard(
    site, monkeypatch, path, kind, serializer, model_name,
):
    app, client = site
    seen = Mock(return_value=_document())
    monkeypatch.setattr(routes, "_get_document_or_404", seen)
    row = SimpleNamespace(id=990, version_number=1)
    query = _Query(row=row)
    attrs = {"query": query}
    if kind == "versions":
        attrs.update(warehouse_upload=object(), version_number=_Sort())
        monkeypatch.setattr(routes, "joinedload", lambda *_args: object())
    elif kind == "links":
        attrs.update(
            entity_type=_Sort(), entity_key=_Sort(), link_role=_Sort(),
            is_primary=_Sort(), created_at=_Sort(),
        )
    else:
        attrs.update(is_primary=_Sort(), created_at=_Sort())
    monkeypatch.setattr(routes, model_name, SimpleNamespace(**attrs))
    render = Mock(return_value={"id": 990, "note": "synthetic"})
    monkeypatch.setattr(routes, serializer, render)
    result = client.get(BASE + path, headers=_auth(app, 88))
    assert result.status_code == 200
    assert result.get_json()["items"] == [{"id": 990, "note": "synthetic"}]
    assert query.filter_args["document_id"] == 900
    seen.assert_called_once_with(900)
    render.assert_called_once()
