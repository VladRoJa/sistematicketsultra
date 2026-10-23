"""Fase A Warehouse: operador y flags contra observabilidad, sin PostgreSQL.

Los objetos ORM, el usuario JWT y la request son ficticios.
No altera grants ni permisos.
"""
from types import SimpleNamespace

import pytest
from flask import Flask

from app.routes import permissions_catalog_routes as catalog
from app.utils import warehouse_access as warehouse


class _OperatorQuery:
    def __init__(self, operator, user_id=501):
        self.operator = operator
        self.user_id = user_id
        self.last_filter = None

    def filter_by(self, **kwargs):
        self.last_filter = kwargs
        return self

    def first(self):
        return self.operator if self.last_filter == {"user_id": self.user_id} else None


def _fixture(monkeypatch, operator, *, jwt="501", role="RECEPCIONISTA"):
    warehouse_query = _OperatorQuery(operator)
    planning_query = _OperatorQuery(None)
    monkeypatch.setattr(warehouse, "get_jwt_identity", lambda: jwt)
    fake_wh_model = SimpleNamespace(query=warehouse_query)
    monkeypatch.setattr(warehouse, "WarehouseOperatorORM", fake_wh_model)
    monkeypatch.setattr(catalog, "WarehouseOperatorORM", fake_wh_model)
    monkeypatch.setattr(
        catalog, "PlanningOperatorORM", SimpleNamespace(query=planning_query)
    )
    user = SimpleNamespace(
        id=501, rol=role, sucursal_id=7, sucursales_ids=[7]
    )
    return user, warehouse_query


def _legacy_status(fn):
    response = fn()
    return 200 if response is None else response[1]


@pytest.mark.parametrize(
    "flags",
    [
        None,
        (False, False, False),
        (True, False, False),
        (False, True, False),
        (False, False, True),
        (True, True, False),
        (True, True, True),
    ],
    ids=[
        "no_operator", "registered_no_flags", "view_only",
        "upload_only", "archive_only", "view_upload", "all_flags",
    ],
)
@pytest.mark.parametrize(
    "action,guard",
    [
        ("warehouse.view", warehouse.require_warehouse_view),
        ("warehouse.upload", warehouse.require_warehouse_upload),
        ("warehouse.archive", warehouse.require_warehouse_archive),
        ("warehouse.catalogs", warehouse.require_warehouse_catalogs),
    ],
)
def test_warehouse_action_flags_match_real_guards(monkeypatch, flags, action, guard):
    operator = (
        None if flags is None else SimpleNamespace(
            can_view=flags[0], can_upload=flags[1], can_archive=flags[2]
        )
    )
    app = Flask(__name__)
    user, query = _fixture(monkeypatch, operator)
    with app.test_request_context():
        legacy = _legacy_status(guard) == 200
        context = catalog._get_target_context(user)
        observed = catalog._effective_action_decision(
            SimpleNamespace(full_key=action), user, context
        )

    view = bool(flags and flags[0])
    upload = bool(flags and flags[1])
    archive = bool(flags and flags[2])
    expected = {
        "warehouse.view": view,
        "warehouse.upload": upload,
        "warehouse.archive": archive,
        "warehouse.catalogs": view or upload,
    }[action]
    assert legacy is expected
    assert observed["allowed"] is expected
    assert observed["source"] == "warehouse_operator"
    assert observed["scope_type"] == ("global" if expected else "none")
    assert query.last_filter == {"user_id": 501}


@pytest.mark.parametrize("flags,expected", [
    (None, False),
    ((False, False, False), True),
    ((False, False, True), True),
    ((True, True, False), True),
])
def test_warehouse_base_allowlist_guard_is_not_same_as_view_action(
    monkeypatch, flags, expected
):
    operator = (
        None if flags is None else SimpleNamespace(
            can_view=flags[0], can_upload=flags[1], can_archive=flags[2]
        )
    )
    app = Flask(__name__)
    user, _ = _fixture(monkeypatch, operator)
    with app.test_request_context():
        assert (_legacy_status(warehouse.require_warehouse_operator) == 200) is expected
        observed = catalog._effective_action_decision(
            SimpleNamespace(full_key="warehouse.view"),
            user,
            catalog._get_target_context(user),
        )
    assert observed["allowed"] is bool(flags and flags[0])
    # No comparar el check de pertenencia con el derecho de lectura.


@pytest.mark.parametrize("role", ["ADMINISTRADOR", "SISTEMAS", "LECTOR_GLOBAL"])
def test_warehouse_role_does_not_bypass_missing_operator(monkeypatch, role):
    app = Flask(__name__)
    user, _ = _fixture(monkeypatch, None, role=role)
    with app.test_request_context():
        assert _legacy_status(warehouse.require_warehouse_view) == 403
        ctx = catalog._get_target_context(user)
        for action in ("warehouse.view", "warehouse.upload", "warehouse.archive"):
            assert catalog._effective_action_decision(
                SimpleNamespace(full_key=action), user, ctx
            )["allowed"] is False


@pytest.mark.parametrize("jwt", [None, "abc", "", "no-es-numero"])
def test_warehouse_invalid_jwt_cannot_resolve_operator(monkeypatch, jwt):
    app = Flask(__name__)
    user, query = _fixture(
        monkeypatch, SimpleNamespace(can_view=True, can_upload=True, can_archive=True),
        jwt=jwt,
    )
    with app.test_request_context():
        assert warehouse.get_current_warehouse_operator() is None
        assert _legacy_status(warehouse.require_warehouse_view) == 403
    assert query.last_filter is None
