from types import SimpleNamespace
from unittest.mock import MagicMock

from flask import Blueprint, Flask
from sqlalchemy import Integer, String, column

from app.models import permiso_model
from app.maintenance_planner import service as planner
from app.routes.pm_routes import _verificar_permiso_sucursal
from app.utils import pm_permissions
from app.utils import ticket_filters
from app.utils import maintenance_ticket_update_guard as ticket_guard
from app.utils.maintenance_ticket_update_guard import (
    generic_pm_update_is_forbidden,
)


def _compras(*, user_id=901, branches=(3, 5)):
    return SimpleNamespace(
        id=user_id,
        username="compras_baja_test",
        rol="COMPRAS",
        department_id=6,
        sucursal_id=100,
        sucursales_ids=list(branches),
    )


def _mock_grant(monkeypatch, *, allowed):
    query = MagicMock()
    query.filter_by.return_value.first.return_value = object() if allowed else None
    monkeypatch.setattr(permiso_model, "Permiso", SimpleNamespace(query=query))
    return query


def _mock_tickets_query(monkeypatch):
    query = MagicMock()
    fake_ticket = SimpleNamespace(
        query=query,
        departamento_id=column("departamento_id", Integer),
        sucursal_id_destino=column("sucursal_id_destino", Integer),
        sucursal_id=column("sucursal_id", Integer),
        username=column("username", String),
    )
    monkeypatch.setattr(ticket_filters, "Ticket", fake_ticket)
    return query


def test_compras_requires_individual_read_grant(monkeypatch):
    user = _compras()
    query = _mock_grant(monkeypatch, allowed=False)

    assert pm_permissions.can_pm_view(user) is False
    assert pm_permissions.can_pm_execute(user) is False
    query.filter_by.assert_called_once_with(
        user_id=901,
        departamento_id=1,
        es_admin=False,
    )


def test_granted_compras_is_read_only(monkeypatch):
    user = _compras()
    _mock_grant(monkeypatch, allowed=True)

    assert pm_permissions.can_pm_view(user) is True
    assert pm_permissions.can_pm_execute(user) is False
    assert pm_permissions.can_pm_validate(user) is False
    assert pm_permissions.can_pm_configure(user) is False
    assert generic_pm_update_is_forbidden(
        user,
        SimpleNamespace(departamento_id=1),
    ) is True


def test_compras_with_grant_sees_only_assigned_maintenance_branches(monkeypatch):
    _mock_grant(monkeypatch, allowed=True)
    query = _mock_tickets_query(monkeypatch)
    result = MagicMock()
    query.filter.return_value = result

    filtered = ticket_filters.filtrar_tickets_por_usuario(_compras())
    compiled = str(
        query.filter.call_args.args[0].compile(
            compile_kwargs={"literal_binds": True}
        )
    )

    assert filtered is result
    assert "departamento_id = 1" in compiled
    assert "IN (3, 5)" in compiled
    assert "departamento_id = 6" in compiled
    # No allow-all para Compras; Mantenimiento exige region asignada.
    assert "AND" in compiled and "OR" in compiled


def test_compras_without_branches_gets_no_maintenance_scope(monkeypatch):
    _mock_grant(monkeypatch, allowed=True)
    query = _mock_tickets_query(monkeypatch)

    ticket_filters.filtrar_tickets_por_usuario(_compras(branches=()))
    compiled = str(
        query.filter.call_args.args[0].compile(
            compile_kwargs={"literal_binds": True}
        )
    )

    assert "departamento_id = 1" not in compiled
    assert "departamento_id = 6" in compiled


def test_compras_pm_branch_scope_ignores_corporate_primary():
    user = _compras()
    assert _verificar_permiso_sucursal(user, 3) is None
    assert _verificar_permiso_sucursal(user, 5) is None
    assert _verificar_permiso_sucursal(user, 99)[1] == 403
    assert _verificar_permiso_sucursal(user, 100)[1] == 403


def test_compras_planner_uses_strict_branches():
    user = _compras()
    query = MagicMock()
    result = planner._apply_planner_role_scope(query, user)

    assert result is query.filter.return_value
    assert planner._branch_catalog_ids(user, query) == [3, 5]

    no_branches = _compras(branches=())
    empty_query = MagicMock()
    planner._apply_planner_role_scope(empty_query, no_branches)
    empty_query.filter.assert_called_once_with(False)


def test_compras_cannot_close_maintenance_ticket_via_legacy_endpoint(monkeypatch):
    app = Flask(__name__)
    tickets = Blueprint("tickets", __name__)

    @tickets.route("/cierre/solicitar/<int:ticket_id>", methods=["POST"])
    def cierre_solicitar(ticket_id):
        return "unexpected write", 200

    app.register_blueprint(tickets)

    actor = _compras()
    maintenance_ticket = SimpleNamespace(departamento_id=1)
    monkeypatch.setattr(ticket_guard, "verify_jwt_in_request", lambda: None)
    monkeypatch.setattr(ticket_guard, "get_jwt_identity", lambda: actor.id)
    monkeypatch.setattr(ticket_guard.UserORM, "get_by_id", lambda _id: actor)
    monkeypatch.setattr(
        ticket_guard,
        "Ticket",
        SimpleNamespace(query=SimpleNamespace(get=lambda _id: maintenance_ticket)),
    )
    ticket_guard.register_maintenance_ticket_update_guard(app)

    response = app.test_client().post("/cierre/solicitar/99")

    assert response.status_code == 403
    assert "Compras tiene acceso de consulta" in response.get_json()["mensaje"]


def test_compras_guard_does_not_block_other_department_ticket(monkeypatch):
    app = Flask(__name__)
    tickets = Blueprint("tickets", __name__)

    @tickets.route("/cierre/solicitar/<int:ticket_id>", methods=["POST"])
    def cierre_solicitar(ticket_id):
        return "allowed by legacy route", 200

    app.register_blueprint(tickets)

    actor = _compras()
    other_ticket = SimpleNamespace(departamento_id=6)
    monkeypatch.setattr(ticket_guard, "verify_jwt_in_request", lambda: None)
    monkeypatch.setattr(ticket_guard, "get_jwt_identity", lambda: actor.id)
    monkeypatch.setattr(ticket_guard.UserORM, "get_by_id", lambda _id: actor)
    monkeypatch.setattr(
        ticket_guard,
        "Ticket",
        SimpleNamespace(query=SimpleNamespace(get=lambda _id: other_ticket)),
    )
    ticket_guard.register_maintenance_ticket_update_guard(app)

    assert app.test_client().post("/cierre/solicitar/99").status_code == 200
