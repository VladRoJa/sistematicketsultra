"""Cuenta regional 45: Tickets, Planner, PM, permisos y flujo sin técnico."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import Integer, String, column

from app.utils.maintenance_regional_lead import (
    MAINTENANCE_LEAD_BRANCH_IDS,
    can_regional_maintenance_lead_request_legacy_closure,
    is_regional_maintenance_lead,
    regional_maintenance_lead_branches,
    regional_maintenance_lead_owns_ticket,
)
from app.utils import ticket_filters
from app.utils import tickets_maintenance_permissions as coordination_policy
from app.routes.pm_routes import _verificar_permiso_sucursal
from app.maintenance_planner import service as planner


BRANCHES = sorted(MAINTENANCE_LEAD_BRANCH_IDS)


def chief(branches=None):
    return SimpleNamespace(
        id=45, username="MANTENIMIENTO", rol="MANTENIMIENTO",
        department_id=1, sucursal_id=100,
        sucursales_ids=list(BRANCHES if branches is None else branches),
    )


def ticket(branch=1, mode=None, assignee=None):
    return SimpleNamespace(
        departamento_id=1, sucursal_id=100, sucursal_id_destino=branch,
        tipo_atencion=mode, asignado_a=assignee, estado="en progreso",
    )


def test_exact_account_and_branch_intersection_deny_corporate_fallback():
    user = chief(branches=[100, 1, 6, 9, 26, 1000])
    assert is_regional_maintenance_lead(user)
    assert regional_maintenance_lead_branches(user) == (1, 6, 26)
    assert regional_maintenance_lead_owns_ticket(user, ticket(26))
    assert not regional_maintenance_lead_owns_ticket(user, ticket(9))
    assert not regional_maintenance_lead_owns_ticket(user, ticket(100))
    assert not regional_maintenance_lead_owns_ticket(user, ticket(1000))
    assert not regional_maintenance_lead_owns_ticket(
        user, SimpleNamespace(departamento_id=7, sucursal_id_destino=1)
    )
    assert regional_maintenance_lead_branches(chief(branches=[100])) == ()


@pytest.mark.parametrize("change", [
    {"id": 46}, {"username": "OTRO"}, {"rol": "SR_MANTENIMIENTO"},
    {"department_id": 7},
])
def test_regional_privilege_is_never_granted_by_role_only(change):
    user = chief()
    for key, value in change.items():
        setattr(user, key, value)
    assert not is_regional_maintenance_lead(user)
    assert regional_maintenance_lead_branches(user) == ()


@pytest.mark.parametrize("branch", BRANCHES)
def test_pm_execute_only_in_14_authorized_branches(branch):
    assert _verificar_permiso_sucursal(chief(), branch) is None


@pytest.mark.parametrize("branch", [7, 8, 9, 10, 11, 12, 13, 19, 21, 22, 23, 25, 100, 1000])
def test_pm_denies_other_branches_even_with_corporate_primary(branch):
    assert _verificar_permiso_sucursal(chief(), branch)[1] == 403


def test_pm_legacy_lead_fails_closed_before_migration():
    assert _verificar_permiso_sucursal(chief(branches=[100]), 1)[1] == 403


def test_legacy_close_only_own_undelegated_tickets():
    lead = chief()
    assert can_regional_maintenance_lead_request_legacy_closure(lead, ticket(20))
    assert not can_regional_maintenance_lead_request_legacy_closure(lead, ticket(9))
    assert not can_regional_maintenance_lead_request_legacy_closure(
        lead, ticket(20, "INTERNA", "SR_MANT")
    )
    assert not can_regional_maintenance_lead_request_legacy_closure(
        lead, ticket(20, "EXTERNA", None)
    )


def test_lead_coordination_grant_does_not_force_assignment():
    with patch.object(coordination_policy, "can_pm_view", return_value=True), patch.object(
        coordination_policy, "_has_active_user_grant", return_value=True
    ) as lookup:
        assert coordination_policy.has_maintenance_coordination_permission(chief()) is False
        lookup.assert_not_called()


def test_tickets_query_has_strict_branch_filter_no_author_fallback(monkeypatch):
    query = MagicMock()
    query.filter.return_value = query
    fake = SimpleNamespace(
        query=query, departamento_id=column("departamento_id", Integer),
        sucursal_id_destino=column("sucursal_id_destino", Integer),
        sucursal_id=column("sucursal_id", Integer),
        username=column("username", String),
    )
    monkeypatch.setattr(ticket_filters, "Ticket", fake)
    lead = chief(branches=[1, 6, 26, 9, 100])
    assert ticket_filters.filtrar_tickets_por_usuario(lead) is query
    clause = str(query.filter.call_args.args[0].compile(
        compile_kwargs={"literal_binds": True}
    ))
    assert "departamento_id = 1" in clause
    assert "IN (1, 6, 26)" in clause
    assert "username" not in clause.lower()
    assert "IN (9" not in clause and "100)" not in clause
    query.reset_mock()
    ticket_filters.filtrar_tickets_por_usuario(chief(branches=[100]))
    query.filter.assert_called_once_with(False)


def test_planner_lead_schedule_scope_and_separate_coordinator():
    lead = chief(branches=[1, 20, 9, 100])
    assert planner._can_schedule_maintenance(lead)
    query = MagicMock()
    planner._apply_planner_role_scope(query, lead)
    sql = str(query.filter.call_args.args[0].compile(
        compile_kwargs={"literal_binds": True}
    ))
    assert "IN (1, 20)" in sql
    assert planner._can_schedule_maintenance(chief(branches=[100])) is False
    query = MagicMock()
    planner._apply_planner_role_scope(query, chief(branches=[100]))
    query.filter.assert_called_once_with(False)


def test_planner_route_shows_legacy_closure_without_coordination_grant():
    from app.maintenance_planner.routes import _can_request_maintenance_closure
    assert _can_request_maintenance_closure(chief()) is True
    assert _can_request_maintenance_closure(chief(branches=[100])) is False


@pytest.mark.parametrize("handler_name,path", [
    ("pm_listar_bitacoras", "/bitacoras"),
    ("pm_listar_configuraciones", "/configuraciones"),
    ("pm_calendario", "/calendario?anio=2026&mes=10"),
])
def test_pm_unfiltered_list_queries_still_intersect_regional_scope(
    monkeypatch, handler_name, path,
):
    from flask import Flask
    from sqlalchemy import func, and_
    from app.routes import pm_routes

    query = MagicMock()
    query.join.return_value = query
    query.outerjoin.return_value = query
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = []

    session = SimpleNamespace(query=MagicMock(return_value=query))
    monkeypatch.setattr(pm_routes, "db", SimpleNamespace(
        session=session, func=func, and_=and_,
    ))
    monkeypatch.setattr(pm_routes, "get_jwt_identity", lambda: "45")
    monkeypatch.setattr(
        pm_routes, "_obtener_usuario_actual_pm",
        lambda _uid: (chief(branches=[1, 20, 9, 100]), None),
    )
    monkeypatch.setattr(pm_routes, "require_pm_view", lambda _: None)

    app = Flask(__name__)
    with app.test_request_context(path):
        # Invocamos el handler real tras omitir solo @jwt_required en QA.
        response, code = getattr(pm_routes, handler_name).__wrapped__()
    assert code == 200
    assert response is not None
    compiled = [
        str(call.args[0].compile(compile_kwargs={"literal_binds": True}))
        for call in query.filter.call_args_list
    ]
    assert any("IN (1, 20)" in sql and "sucursal_id" in sql for sql in compiled), compiled
    assert all("IN (9" not in sql for sql in compiled)


def test_chief_cannot_create_ticket_for_outside_branch(monkeypatch):
    from flask import Flask
    from unittest.mock import Mock
    from app.routes import ticket_routes

    actor = chief()
    monkeypatch.setattr(ticket_routes, "get_jwt_identity", lambda: "45")
    monkeypatch.setattr(ticket_routes.UserORM, "get_by_id", lambda _: actor)
    insert = Mock()
    monkeypatch.setattr(ticket_routes.Ticket, "create_ticket", insert)

    app = Flask(__name__)
    payload = {
        "descripcion": "Ticket QA no guardado", "departamento_id": 1,
        "criticidad": 2, "clasificacion_id": 3, "sucursal_id_destino": 9,
    }
    with app.test_request_context("/api/tickets/create", method="POST", json=payload):
        response, code = ticket_routes.create_ticket.__wrapped__()
    assert code == 403
    assert "fuera del alcance" in response.get_json()["mensaje"]
    insert.assert_not_called()


@pytest.mark.parametrize("handler_name,path,args", [
    ("historial_equipo", "/historial-equipo/12", (12,)),
    ("historial_por_equipo", "/historial-por-equipo/12", (12,)),
    ("historial_global", "/historial-global", ()),
    ("historial_aparato", "/historial/12", (12,)),
])
def test_chief_legacy_history_endpoints_always_use_scope(
    monkeypatch, handler_name, path, args,
):
    from flask import Flask
    from sqlalchemy import Integer, DateTime, column
    from app.routes import ticket_routes

    actor = chief()
    monkeypatch.setattr(ticket_routes, "get_jwt_identity", lambda: "45")
    monkeypatch.setattr(ticket_routes.UserORM, "get_by_id", lambda _: actor)
    # El grant assigned-only no forma parte del caso; no consultar la DB
    # real desde esta prueba en memoria de las rutas de historial.
    monkeypatch.setattr(
        ticket_routes, "has_assigned_only_maintenance_scope", lambda _: False
    )

    query = MagicMock()
    query.filter.return_value = query
    query.filter_by.return_value = query
    query.order_by.return_value = query
    query.all.return_value = []
    fake_ticket = SimpleNamespace(
        query=MagicMock(),
        aparato_id=column("aparato_id", Integer),
        fecha_creacion=column("fecha_creacion", DateTime),
    )
    monkeypatch.setattr(ticket_routes, "Ticket", fake_ticket)
    scoped = MagicMock(return_value=query)
    monkeypatch.setattr(ticket_routes, "filtrar_tickets_por_usuario", scoped)

    if handler_name == "historial_aparato":
        from app.models import inventario
        details = MagicMock()
        details.query.filter_by.return_value.all.return_value = []
        monkeypatch.setattr(inventario, "DetalleMovimiento", details)

    app = Flask(__name__)
    with app.test_request_context(path):
        response, code = getattr(ticket_routes, handler_name).__wrapped__(*args)
    assert code == 200
    assert response is not None
    scoped.assert_called_once_with(actor)
