"""Fase A - paridad por documento Nube, sin datos ni permisos productivos.

Tests sobre helpers importados reales, con documentos, contexto de usuario y
reglas CUSTOM sinteticas. El query de reglas y la resolucion de sucursales se
sustituyen in-memory: no se abre PostgreSQL, endpoints ni archivos.
"""
from types import SimpleNamespace

import pytest

from app.routes import permissions_catalog_routes as catalog
from app.utils import internal_documents_access as access


class _RuleOrdering:
    def asc(self):
        return self


class _VisibilityRulesQuery:
    def __init__(self, by_document):
        self.by_document = by_document
        self.filters = {}

    def filter_by(self, **kwargs):
        self.filters = kwargs
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        return [
            item
            for item in self.by_document.get(self.filters.get("document_id"), [])
            if bool(item.is_active) == bool(self.filters.get("is_active"))
        ]


def _ctx(key):
    users = {
        "admicorp": (1, "ADMICORP", "LECTOR_GLOBAL", 7, 9),
        "sistemas": (2, "SISTEMAS_QA", "SISTEMAS", 7, 9),
        "administrador": (3, "ADMIN_QA", "ADMINISTRADOR", 7, 9),
        "gerente": (4, "GERENTE_QA", "GERENTE", 7, 9),
        "gerente_fuera": (5, "GERENTE_OTRA", "GERENTE", 8, 8),
        "propietario": (6, "RECEPCION_QA", "RECEPCIONISTA", 7, 9),
        "externo": (7, "EXTERNO_QA", "RECEPCIONISTA", 8, 8),
    }
    user_id, username, role, branch, department = users[key]
    return access.InternalDocumentUserContext(
        user_id=user_id,
        username=username,
        role=role,
        sucursal_id=branch,
        sucursales_ids=(branch,),
        department_id=department,
    )


def _rule(
    visibility_type,
    *,
    user_id=None, role=None, department_id=None, sucursal_id=None,
    can_view=True, can_download=True, is_active=True,
):
    return SimpleNamespace(
        visibility_type=visibility_type,
        user_id=user_id,
        role=role,
        department_id=department_id,
        sucursal_id=sucursal_id,
        can_view=can_view,
        can_download=can_download,
        is_active=is_active,
    )


def _doc(
    number, title, *, status=None, mode=None, sensitive=False,
    current_version=901, owner=6, creator=6,
):
    return SimpleNamespace(
        id=number,
        title=title,
        status=status or access.InternalDocumentStatus.PUBLISHED,
        visibility_mode=mode or access.InternalDocumentVisibilityMode.GLOBAL,
        is_sensitive=sensitive,
        current_version_id=current_version,
        created_by=creator,
        owner_user_id=owner,
        links=[],
    )


def _documents_and_rules():
    published = access.InternalDocumentStatus.PUBLISHED
    draft = access.InternalDocumentStatus.DRAFT
    archived = access.InternalDocumentStatus.ARCHIVED
    global_mode = access.InternalDocumentVisibilityMode.GLOBAL
    private = access.InternalDocumentVisibilityMode.PRIVATE
    custom = access.InternalDocumentVisibilityMode.CUSTOM
    user_rule = access.InternalDocumentVisibilityType.USER

    docs = {
        "global": _doc(101, "Manual general"),
        "sensitive_global": _doc(102, "Balance confidencial", sensitive=True),
        "private": _doc(103, "Expediente privado", mode=private),
        "custom": _doc(104, "Reporte confidencial", mode=custom, sensitive=True),
        "consolidado": _doc(
            105, "  consolidado de agregadoras  ", mode=custom, sensitive=True
        ),
        "consolidado_viewonly": _doc(
            106, "Consolidado de agregadoras", mode=custom, sensitive=True
        ),
        "consolidado_draft": _doc(
            107, "Consolidado de agregadoras", status=draft,
            mode=custom, sensitive=True
        ),
        "archived": _doc(108, "Documento archivado", status=archived),
        "draft_private": _doc(
            109, "Borrador privado", status=draft, mode=private
        ),
        "no_current": _doc(110, "Manual sin version", current_version=None),
        "cobranza": _doc(
            111, "COBRANZA RECURRENTE RECHAZADOS OCT", mode=custom,
            sensitive=True,
        ),
    }
    by_document = {
        104: [
            _rule(user_rule, user_id=4, can_download=False),
            _rule(user_rule, user_id=1),
            _rule(user_rule, user_id=5, can_view=False),
        ],
        105: [_rule(user_rule, user_id=1)],
        106: [
            _rule(user_rule, user_id=1),
            _rule(user_rule, user_id=2, can_download=False),
        ],
        107: [_rule(user_rule, user_id=1)],
    }
    return docs, by_document


@pytest.fixture
def documents(monkeypatch):
    documents, rules = _documents_and_rules()
    fake_visibility = SimpleNamespace(
        query=_VisibilityRulesQuery(rules), id=_RuleOrdering()
    )
    monkeypatch.setattr(access, "InternalDocumentVisibilityORM", fake_visibility)
    # Solo afecta al caso COBRANZA: simula los aliases/documentos vinculados.
    monkeypatch.setattr(access, "_get_document_sucursal_ids", lambda _doc: {7})
    return documents


@pytest.mark.parametrize(
    "doc_key,user_key,expected",
    [
        ("global", "admicorp", (1, 1, 1, 1)),
        ("global", "sistemas", (1, 1, 1, 1)),
        ("global", "administrador", (1, 1, 0, 0)),
        ("global", "externo", (1, 1, 0, 0)),
        ("sensitive_global", "sistemas", (1, 1, 1, 1)),
        ("sensitive_global", "administrador", (0, 0, 0, 0)),
        ("sensitive_global", "propietario", (0, 0, 0, 0)),
        ("private", "propietario", (1, 1, 0, 0)),
        ("private", "externo", (0, 0, 0, 0)),
        ("private", "administrador", (0, 0, 0, 0)),
        ("private", "sistemas", (1, 1, 1, 1)),
        ("custom", "gerente", (1, 0, 0, 0)),
        ("custom", "gerente_fuera", (0, 0, 0, 0)),
        ("custom", "admicorp", (1, 1, 1, 1)),
        ("custom", "sistemas", (1, 1, 1, 1)),
        ("consolidado", "admicorp", (1, 1, 1, 1)),
        ("consolidado", "sistemas", (0, 0, 0, 0)),
        ("consolidado", "administrador", (0, 0, 0, 0)),
        ("consolidado", "gerente", (0, 0, 0, 0)),
        ("consolidado_viewonly", "sistemas", (1, 0, 1, 0)),
        ("consolidado_viewonly", "admicorp", (1, 1, 1, 1)),
        ("consolidado_draft", "admicorp", (0, 0, 0, 0)),
        ("consolidado_draft", "sistemas", (0, 0, 0, 0)),
        ("archived", "sistemas", (1, 1, 1, 1)),
        ("archived", "propietario", (0, 0, 0, 0)),
        ("draft_private", "propietario", (1, 0, 0, 0)),
        ("draft_private", "sistemas", (1, 1, 1, 1)),
        ("draft_private", "administrador", (0, 0, 0, 0)),
        ("no_current", "sistemas", (1, 0, 1, 1)),
        ("no_current", "externo", (1, 0, 0, 0)),
        ("cobranza", "gerente", (1, 1, 0, 0)),
        ("cobranza", "gerente_fuera", (0, 0, 0, 0)),
        ("cobranza", "propietario", (0, 0, 0, 0)),
        ("cobranza", "sistemas", (1, 1, 1, 1)),
    ],
)
def test_p19_object_level_view_download_audit_historical(
    documents, doc_key, user_key, expected
):
    document = documents[doc_key]
    context = _ctx(user_key)
    decisions = (
        access.can_view_internal_document(document, context),
        access.can_download_internal_document(document, context),
        access.can_view_internal_document_audit(document, context),
        access.can_download_historical_internal_document_version(
            document, context
        ),
    )
    assert decisions == tuple(bool(value) for value in expected)
    capabilities = access.build_internal_document_capabilities(document, context)
    assert (
        capabilities["can_view"], capabilities["can_download"],
        capabilities["can_view_audit"],
        capabilities["can_download_historical_versions"],
    ) == decisions


@pytest.mark.parametrize("user_key", ["admicorp", "sistemas"])
@pytest.mark.parametrize("doc_key,editable", [
    ("global", True), ("consolidado", True), ("archived", False),
    ("consolidado_draft", True),
])
def test_p19_document_mutation_capabilities_preserve_archived_hard_stop(
    documents, doc_key, editable, user_key
):
    doc = documents[doc_key]
    capabilities = access.build_internal_document_capabilities(doc, _ctx(user_key))
    for action in (
        "can_edit", "can_publish", "can_archive",
        "can_replace_version", "can_manage_visibility",
    ):
        assert capabilities[action] is editable


@pytest.mark.parametrize(
    "type_key,rule_values,user_key,view,download",
    [
        ("USER", {"user_id": 4}, "gerente", True, True),
        ("USER", {"user_id": 5}, "gerente", False, False),
        ("ROLE", {"role": "GERENTE", "can_download": False}, "gerente", True, False),
        ("ROLE", {"role": "GERENTE"}, "externo", False, False),
        ("DEPARTMENT", {"department_id": 9}, "gerente", True, True),
        ("DEPARTMENT", {"department_id": 9}, "gerente_fuera", False, False),
        ("SUCURSAL", {"sucursal_id": 7}, "gerente", True, True),
        ("SUCURSAL", {"sucursal_id": 7}, "gerente_fuera", False, False),
        ("GLOBAL", {"can_view": True, "can_download": False}, "externo", True, False),
        ("USER", {"user_id": 4, "is_active": False}, "gerente", False, False),
        ("USER", {"user_id": 4, "can_view": False}, "gerente", False, False),
    ],
)
def test_p19_custom_acl_types_active_flag_and_download_require_view(
    monkeypatch, type_key, rule_values, user_key, view, download
):
    # Usamos el helper real _has_custom_visibility_access, NO lo stubbeamos.
    rule = _rule(type_key, **rule_values)
    monkeypatch.setattr(
        access, "InternalDocumentVisibilityORM",
        SimpleNamespace(
            query=_VisibilityRulesQuery({300: [rule]}),
            id=_RuleOrdering(),
        ),
    )
    doc = _doc(300, "Privado por reglas", mode="CUSTOM", sensitive=True)
    context = _ctx(user_key)
    assert access.can_view_internal_document(doc, context) is view
    assert access.can_download_internal_document(doc, context) is download


def _catalog_decision(context, full_key):
    user = SimpleNamespace(
        id=context.user_id, username=context.username, rol=context.role,
        sucursal_id=context.sucursal_id, department_id=context.department_id,
    )
    return catalog._effective_action_decision(
        SimpleNamespace(full_key=full_key),
        user,
        {
            "role": context.role,
            "sucursal_ids": list(context.sucursales_ids),
            "warehouse_operator": None,
            "planning_operator": None,
            "allow_ticket_delete_all": False,
        },
    )


@pytest.mark.parametrize("user_key,legacy,catalog_allowed", [
    ("admicorp", True, True),
    ("sistemas", True, True),
    ("administrador", False, False),
    ("gerente", False, False),
])
def test_p19_manager_action_matches_observability_after_b1(
    user_key, legacy, catalog_allowed
):
    context = _ctx(user_key)
    assert access.can_manage_internal_documents(context) is legacy
    observed = _catalog_decision(context, "internal_documents.manage")
    assert observed["allowed"] is catalog_allowed
    assert observed["source"] == "legacy_internal_documents_manager"


@pytest.mark.parametrize("doc_key,user_key,expected_view", [
    ("global", "externo", True),
    ("private", "externo", False),
    ("sensitive_global", "administrador", False),
    ("consolidado", "sistemas", False),
    ("custom", "gerente", True),
    ("custom", "gerente_fuera", False),
])
def test_p19_catalog_view_is_coarse_not_document_access(
    documents, doc_key, user_key, expected_view
):
    document = documents[doc_key]
    context = _ctx(user_key)
    observed = _catalog_decision(context, "internal_documents.view")
    actual = access.can_view_internal_document(document, context)
    assert observed["allowed"] is True
    assert actual is expected_view
    assert observed["scope_type"] == "document_visibility"
    # Si document=None en el catálogo, la equivalencia por objeto es
    # incomplete_context, NO autorizar todos los docs por view=True.
