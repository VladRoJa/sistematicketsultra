"""Fase A Planning: vigencia del operador y flags independientes vs catálogo.

Operadores/JWT son fixtures. Se ejecutan los helpers reales, no endpoints
de Planeación ni PostgreSQL. can_edit no se infiere de can_view y viceversa.
"""
from types import SimpleNamespace

import pytest
from flask import Flask

from app.routes import permissions_catalog_routes as catalog
from app.utils import planning_access as planning


class _ActiveOperatorQuery:
    def __init__(self, operator, user_id=501):
        self.operator = operator
        self.user_id = user_id
        self.calls = []

    def filter_by(self, **kwargs):
        self.calls.append(kwargs)
        return self

    def first(self):
        if not self.calls or self.calls[-1] != {
            "user_id": self.user_id, "is_active": True
        }:
            return None
        if self.operator is None or not self.operator.is_active:
            return None
        return self.operator


class _EmptyWarehouseQuery:
    def filter_by(self, **_kwargs):
        return self

    def first(self):
        return None


def _operator(**flags):
    defaults = dict(
        is_active=True, can_view=False, can_edit=False,
        can_submit=False, can_approve=False, can_publish=False,
        can_configure_model=False,
    )
    defaults.update(flags)
    return SimpleNamespace(**defaults)


def _fixture(monkeypatch, operator, jwt="501", role="RECEPCIONISTA"):
    operator_query = _ActiveOperatorQuery(operator)
    monkeypatch.setattr(planning, "get_jwt_identity", lambda: jwt)
    fake_model = SimpleNamespace(query=operator_query)
    monkeypatch.setattr(planning, "PlanningOperatorORM", fake_model)
    monkeypatch.setattr(catalog, "PlanningOperatorORM", fake_model)
    monkeypatch.setattr(
        catalog, "WarehouseOperatorORM",
        SimpleNamespace(query=_EmptyWarehouseQuery()),
    )
    return (
        SimpleNamespace(id=501, rol=role, sucursal_id=7, sucursales_ids=[7]),
        operator_query,
    )


def _legacy_status(guard):
    response = guard()
    return 200 if response is None else response[1]


ACTION_GUARDS = [
    ("planning.read", planning.require_planning_operator, "can_view"),
    ("planning.edit", planning.require_planning_edit, "can_edit"),
    ("planning.submit", planning.require_planning_submit, "can_submit"),
    ("planning.approve", planning.require_planning_approve, "can_approve"),
    ("planning.publish", planning.require_planning_publish, "can_publish"),
    ("planning.configure_model", planning.require_planning_model_config,
     "can_configure_model"),
]


@pytest.mark.parametrize("action,guard,flag", ACTION_GUARDS)
@pytest.mark.parametrize(
    "flags",
    [
        None,
        {"is_active": False, "can_view": True, "can_edit": True,
         "can_submit": True, "can_approve": True,
         "can_publish": True, "can_configure_model": True},
        {"can_view": True},
        {"can_edit": True},
        {"can_submit": True},
        {"can_approve": True},
        {"can_publish": True},
        {"can_configure_model": True},
        {"can_view": True, "can_edit": True, "can_submit": True,
         "can_approve": True, "can_publish": True,
         "can_configure_model": True},
    ],
    ids=[
        "no_operator", "inactive_all_flags", "view_only", "edit_only",
        "submit_only", "approve_only", "publish_only", "model_only",
        "active_all_flags",
    ],
)
def test_planning_action_flag_parity_with_active_operator(
    monkeypatch, flags, action, guard, flag
):
    operator = None if flags is None else _operator(**flags)
    app = Flask(__name__)
    user, query = _fixture(monkeypatch, operator)
    with app.test_request_context():
        legacy = _legacy_status(guard) == 200
        observed = catalog._effective_action_decision(
            SimpleNamespace(full_key=action),
            user,
            catalog._get_target_context(user),
        )

    expected = bool(operator and operator.is_active and getattr(operator, flag))
    assert legacy is expected
    assert observed["allowed"] is expected
    assert observed["source"] == "planning_operator"
    assert observed["scope_type"] == ("global" if expected else "none")
    assert query.calls and all(
        call == {"user_id": 501, "is_active": True} for call in query.calls
    )


@pytest.mark.parametrize("flags,read,edit", [
    ({"can_view": False, "can_edit": True}, False, True),
    ({"can_view": True, "can_edit": False}, True, False),
    ({"can_view": False, "can_edit": False}, False, False),
])
def test_planning_base_access_is_not_required_by_every_action(
    monkeypatch, flags, read, edit
):
    operator = _operator(**flags)
    app = Flask(__name__)
    user, _ = _fixture(monkeypatch, operator)
    with app.test_request_context():
        assert (_legacy_status(planning.require_planning_operator) == 200) is read
        assert (_legacy_status(planning.require_planning_edit) == 200) is edit
        ctx = catalog._get_target_context(user)
        assert catalog._effective_action_decision(
            SimpleNamespace(full_key="planning.read"), user, ctx
        )["allowed"] is read
        assert catalog._effective_action_decision(
            SimpleNamespace(full_key="planning.edit"), user, ctx
        )["allowed"] is edit
    # El guard de una ruta concreta puede requerir comprobaciones adicionales.


@pytest.mark.parametrize("active", [False, True])
def test_planning_access_payload_respects_active_flag(monkeypatch, active):
    operator = _operator(
        is_active=active, can_view=True, can_edit=True,
        can_submit=True, can_approve=True, can_publish=True,
        can_configure_model=True,
    )
    app = Flask(__name__)
    _fixture(monkeypatch, operator)
    with app.test_request_context():
        payload = planning.get_current_planning_access_payload()
    assert payload["has_access"] is active
    for flag in (
        "can_view", "can_edit", "can_submit", "can_approve",
        "can_publish", "can_configure_model",
    ):
        assert payload[flag] is active


@pytest.mark.parametrize("jwt", [None, "", "abc", "0", "-5"])
def test_planning_invalid_identity_cannot_retrieve_active_operator(
    monkeypatch, jwt
):
    app = Flask(__name__)
    user, query = _fixture(monkeypatch, _operator(can_view=True), jwt=jwt)
    with app.test_request_context():
        assert planning.get_current_planning_operator() is None
        assert _legacy_status(planning.require_planning_operator) == 403
    assert query.calls == []


@pytest.mark.parametrize("role", ["ADMINISTRADOR", "SISTEMAS", "LECTOR_GLOBAL"])
def test_planning_role_does_not_bypass_missing_operator(monkeypatch, role):
    app = Flask(__name__)
    user, _ = _fixture(monkeypatch, None, role=role)
    with app.test_request_context():
        assert _legacy_status(planning.require_planning_operator) == 403
        context = catalog._get_target_context(user)
        for action, guard, _flag in ACTION_GUARDS:
            assert _legacy_status(guard) == 403
            assert catalog._effective_action_decision(
                SimpleNamespace(full_key=action), user, context
            )["allowed"] is False
