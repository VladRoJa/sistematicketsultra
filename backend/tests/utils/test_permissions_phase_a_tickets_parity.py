"""Fixtures de paridad Tickets sin cambiar guards ni tocar base productiva.

Separar "poder listar tickets" de "poder cerrar/editar"; el catalogo V1
todavia no declara una accion tickets.read en su seed inicial.
"""
import sqlite3
from types import SimpleNamespace

import pytest
from sqlalchemy import Integer, String, column

from app.routes import permissions_catalog_routes as catalog
from app.utils import ticket_filters as filters
from app.utils import tickets_maintenance_permissions as maintenance


class _FakeTicketQuery:
    def __init__(self, rows):
        self.rows = rows
        self.conditions = []

    def filter(self, condition):
        self.conditions.append(condition)
        return self

    def all(self):
        matched = []
        for ticket in self.rows:
            if not self.conditions:
                matched.append(ticket)
                continue
            with sqlite3.connect(":memory:") as con:
                passed = all(
                    con.execute(
                        "SELECT 1 FROM (SELECT ? AS departamento_id, "
                        "? AS asignado_a, ? AS username, ? AS sucursal_id, "
                        "? AS sucursal_id_destino) WHERE "
                        + str(cond.compile(compile_kwargs={"literal_binds": True})),
                        (
                            ticket.departamento_id,
                            ticket.asignado_a,
                            ticket.username,
                            ticket.sucursal_id,
                            ticket.sucursal_id_destino,
                        ),
                    ).fetchone()
                    is not None
                    for cond in self.conditions
                )
            if passed:
                matched.append(ticket)
        return matched

    def count(self):
        return len(self.all())


def _user(role, username="QA_OPERADOR", branch_id=11, department_id=1):
    return SimpleNamespace(
        id=-50,
        rol=role,
        username=username,
        sucursal_id=branch_id,
        sucursales_ids=[branch_id],
        department_id=department_id,
    )


def _ticket(number, assigned_to, creator, department=1, branch=11):
    return SimpleNamespace(
        id=number,
        departamento_id=department,
        asignado_a=assigned_to,
        username=creator,
        sucursal_id=branch,
        sucursal_id_destino=branch,
    )


def _mock_query(monkeypatch, rows):
    query = _FakeTicketQuery(rows)
    model = SimpleNamespace(
        query=query,
        departamento_id=column("departamento_id", Integer()),
        asignado_a=column("asignado_a", String()),
        username=column("username", String()),
        sucursal_id=column("sucursal_id", Integer()),
        sucursal_id_destino=column("sucursal_id_destino", Integer()),
    )
    monkeypatch.setattr(filters, "Ticket", model)
    return query


def _observed_ticket_action(role, action="tickets.close"):
    user = _user(role)
    return catalog._effective_action_decision(
        SimpleNamespace(full_key=action),
        user,
        {
            "role": role,
            "sucursal_ids": [11],
            "warehouse_operator": None,
            "planning_operator": None,
            "allow_ticket_delete_all": False,
        },
    )


@pytest.mark.parametrize("role", ["LECTOR_GLOBAL", "EDITOR_CORPORATIVO", "ADMINISTRADOR"])
def test_p04_p05_read_all_is_a_distinct_operation_from_catalog_write(
    monkeypatch, role
):
    query = _mock_query(monkeypatch, [
        _ticket(1, "OTRO", "OTRO", branch=11),
        _ticket(2, "OTRO", "OTRO", branch=12),
    ])
    result = filters.filtrar_tickets_por_usuario(_user(role))

    assert result is query
    assert query.conditions == []
    assert [item.id for item in result.all()] == [1, 2]

    observed_close = _observed_ticket_action(role, "tickets.close")
    if role == "LECTOR_GLOBAL":
        assert observed_close["allowed"] is False
        assert observed_close["scope_type"] == "none"
    else:
        assert observed_close["allowed"] is True

    # No equivalencia falsa: listar y cerrar son acciones distintas.
    # Sin "tickets.read" en el seed no hay comparacion uno-a-uno.


def test_p05_editor_corporativo_global_read_vs_branch_scope_catalog(monkeypatch):
    query = _mock_query(monkeypatch, [_ticket(1, "OTRO", "OTRO", branch=12)])
    user = _user("EDITOR_CORPORATIVO")

    assert filters.filtrar_tickets_por_usuario(user) is query
    assert query.count() == 1

    catalog_update = _observed_ticket_action("EDITOR_CORPORATIVO", "tickets.update")
    assert catalog_update["allowed"] is True
    assert catalog_update["scope_type"] == "branch_scope"
    assert catalog_update["scope_values"] == [11]
    # Acciones distintas: diferencia de alcance visible, no bug probado de update.


def test_p06_assigned_only_never_falls_back_to_creator_or_branch(monkeypatch):
    rows = [
        _ticket(1, "QA_OPERADOR", "OTRO", branch=11),
        _ticket(2, "qa_operador", "OTRO", branch=12),
        _ticket(3, "OTRO", "QA_OPERADOR", branch=11),
        _ticket(4, "QA_OPERADOR", "QA_OPERADOR", department=2, branch=11),
    ]
    _mock_query(monkeypatch, rows)
    monkeypatch.setattr(
        maintenance,
        "_has_active_user_grant",
        lambda user, action: action == maintenance.ASSIGNED_ONLY_ACTION,
    )

    user = _user("SR_MANTENIMIENTO")
    assert maintenance.has_assigned_only_maintenance_scope(user) is True

    visible = filters.filtrar_tickets_por_usuario(user).all()
    assert [item.id for item in visible] == [1, 2]
    # El ticket 2, aun de otra sucursal, entra por asignacion explicita.
    # No hay fallback por autor ni sucursal en la rama assigned_only.


@pytest.mark.parametrize(
    "role,has_grant,allowed",
    [
        ("ADMINISTRADOR", False, True),
        ("COORDINADOR_MANTENIMIENTO", True, True),
        ("COORDINADOR_MANTENIMIENTO", False, False),
        ("SR_MANTENIMIENTO", True, False),
        ("AUX_MANTENIMIENTO", True, False),
        ("TECNICO", True, False),
        ("MANTENIMIENTO", True, True),
    ],
)
def test_p07_coordination_is_not_inferred_from_ticket_role(
    monkeypatch, role, has_grant, allowed
):
    user = _user(role)
    monkeypatch.setattr(maintenance, "is_regional_maintenance_lead", lambda _u: False)
    monkeypatch.setattr(maintenance, "can_pm_view", lambda _u: True)
    monkeypatch.setattr(
        maintenance, "_has_active_user_grant", lambda _u, _action: has_grant
    )

    assert maintenance.has_maintenance_coordination_permission(user) is allowed


@pytest.mark.parametrize(
    "effects,allowed",
    [
        ([], False),
        (["allow"], True),
        (["deny"], False),
        (["allow", "deny"], False),
        (["allow", "allow"], True),
    ],
)
def test_p07_explicit_deny_outweighs_duplicate_allow(effects, allowed):
    assert maintenance._effects_allow(effects) is allowed


def test_p07_regional_lead_cannot_coordinate_even_with_grant(monkeypatch):
    user = _user("MANTENIMIENTO", username="MANTENIMIENTO")
    monkeypatch.setattr(maintenance, "is_regional_maintenance_lead", lambda _u: True)
    monkeypatch.setattr(maintenance, "can_pm_view", lambda _u: True)
    monkeypatch.setattr(
        maintenance, "_has_active_user_grant", lambda _u, _action: True
    )
    assert maintenance.has_maintenance_coordination_permission(user) is False
