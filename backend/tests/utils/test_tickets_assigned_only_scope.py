"""Permiso individual de bandeja asignada; ninguna excepción por creador."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy import Integer, String, column

from app.utils import ticket_filters


def user(role="SR_MANTENIMIENTO"):
    return SimpleNamespace(
        id=68,
        username="SR_MANT_TIJ",
        rol=role,
        sucursal_id=100,
        department_id=1,
        sucursales_ids=[7, 8, 9],
    )


def fake_query(monkeypatch):
    q = MagicMock()
    fake_ticket = SimpleNamespace(
        query=q,
        departamento_id=column("departamento_id", Integer),
        asignado_a=column("asignado_a", String),
        sucursal_id_destino=column("sucursal_id_destino", Integer),
        sucursal_id=column("sucursal_id", Integer),
        username=column("username", String),
    )
    monkeypatch.setattr(ticket_filters, "Ticket", fake_ticket)
    return q


def compiled_where(query):
    expression = query.filter.call_args.args[0]
    return str(expression.compile(compile_kwargs={"literal_binds": True}))


def test_assigned_only_no_incluye_creador_ni_sucursal(monkeypatch):
    query = fake_query(monkeypatch)
    monkeypatch.setattr(
        ticket_filters,
        "has_assigned_only_maintenance_scope",
        lambda target: True,
    )

    ticket_filters.filtrar_tickets_por_usuario(user())
    sql = compiled_where(query)

    assert "departamento_id = 1" in sql
    assert "lower(asignado_a) = 'sr_mant_tij'" in sql
    assert "sucursal_id_destino" not in sql
    assert "lower(username)" not in sql
    assert " OR " not in sql


def test_otros_supervisores_mantienen_scope_preexistente(monkeypatch):
    query = fake_query(monkeypatch)
    monkeypatch.setattr(
        ticket_filters,
        "has_assigned_only_maintenance_scope",
        lambda target: False,
    )

    ticket_filters.filtrar_tickets_por_usuario(user())
    sql = compiled_where(query)

    assert "departamento_id = 1" in sql
    assert "IN (7, 8, 9)" in sql
    assert "asignado_a" not in sql
    assert " OR " in sql


def test_admin_conserva_lectura_global(monkeypatch):
    query = fake_query(monkeypatch)
    monkeypatch.setattr(
        ticket_filters,
        "has_assigned_only_maintenance_scope",
        lambda target: True,
    )

    result = ticket_filters.filtrar_tickets_por_usuario(user(role="ADMINISTRADOR"))

    assert result is query
    query.filter.assert_not_called()
