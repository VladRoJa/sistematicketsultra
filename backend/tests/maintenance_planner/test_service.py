from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.maintenance_planner import service
from app.utils.scope_utils import CORPORATE_BRANCH_ID, ROOT_BRANCH_ID
from app.utils.sucursal_audience import is_selectable_sucursal


def test_resolve_window_accepts_explicit_range():
    window = service._resolve_window("2026-09-07", "2026-09-13")

    assert window.start == date(2026, 9, 7)
    assert window.end == date(2026, 9, 13)


def test_default_window_runs_sunday_to_saturday():
    window = service._default_window(date(2026, 9, 12))

    assert window.start == date(2026, 9, 6)
    assert window.end == date(2026, 9, 12)


def test_resolve_window_rejects_inverted_range():
    with pytest.raises(service.MaintenancePlannerError):
        service._resolve_window("2026-09-13", "2026-09-07")


def test_planner_status_marks_overdue_ticket():
    ticket = SimpleNamespace(
        estado="en progreso",
        fecha_solucion=datetime(2026, 9, 10, 14, 0, tzinfo=timezone.utc),
    )

    assert service._planner_status(ticket, date(2026, 9, 11)) == "VENCIDO"


def test_calendar_ticket_sort_prioritizes_highest_criticality():
    rows = [
        {"ticket_id": 30, "criticidad": 2},
        {"ticket_id": 20, "criticidad": 5},
        {"ticket_id": 10, "criticidad": 5},
        {"ticket_id": 40, "criticidad": 1},
        {"ticket_id": 50, "criticidad": 4},
    ]

    ordered = sorted(rows, key=service._calendar_ticket_sort_key)

    assert [row["ticket_id"] for row in ordered] == [10, 20, 50, 30, 40]


def test_schedule_ticket_reuses_ticket_and_appends_traceable_history():
    ticket = SimpleNamespace(
        id=99,
        estado="abierto",
        fecha_solucion=None,
        fecha_en_progreso=None,
        historial_fechas=[],
    )
    user = SimpleNamespace(username="mantenimiento")

    with (
        patch.object(service, "_scoped_maintenance_ticket", return_value=ticket),
        patch.object(service, "flag_modified") as flag_modified,
    ):
        result = service.schedule_ticket(
            99,
            user,
            due_date="2026-09-15",
            reason="Acuerdo de junta",
        )

    assert result is ticket
    assert ticket.estado == "en progreso"
    assert ticket.fecha_solucion is not None
    assert ticket.fecha_en_progreso is not None
    assert ticket.historial_fechas[-1]["motivo"] == "Acuerdo de junta"
    assert ticket.historial_fechas[-1]["origen"] == "maintenance_planner_v2"
    flag_modified.assert_called_once_with(ticket, "historial_fechas")


def test_technical_sucursales_are_not_selectable():
    root = SimpleNamespace(sucursal_id=ROOT_BRANCH_ID)
    corporate = SimpleNamespace(sucursal_id=CORPORATE_BRANCH_ID)

    assert is_selectable_sucursal(root) is False
    assert is_selectable_sucursal(corporate) is False


def test_physical_and_demo_sucursales_are_selectable():
    physical = SimpleNamespace(sucursal_id=3, is_demo=False)
    demo = SimpleNamespace(sucursal_id=1001, is_demo=True)

    assert is_selectable_sucursal(physical) is True
    assert is_selectable_sucursal(demo) is True


def test_regional_scope_ids_are_strict_normalized_and_ignore_technical_nodes():
    user = SimpleNamespace(
        rol="GERENTE_REGIONAL",
        sucursales_ids=[3, "5", 3, ROOT_BRANCH_ID, CORPORATE_BRANCH_ID, None, "x"],
    )

    assert service._user_scope_branch_ids(user) == [3, 5]


def test_regional_branch_catalog_comes_from_assignments_not_ticket_activity():
    user = SimpleNamespace(
        rol="GERENTE_REGIONAL",
        sucursales_ids=[8, 3, 5],
    )
    query = MagicMock()

    result = service._branch_catalog_ids(user, query)

    assert result == [3, 5, 8]
    query.with_entities.assert_not_called()


def test_regional_planner_scope_adds_strict_branch_filter():
    user = SimpleNamespace(
        rol="GERENTE_REGIONAL",
        sucursales_ids=[3, 5],
    )
    query = MagicMock()
    scoped_query = MagicMock()
    query.filter.return_value = scoped_query

    result = service._apply_planner_role_scope(query, user)

    assert result is scoped_query
    query.filter.assert_called_once()


def test_regional_planner_without_assignments_returns_empty_scope():
    user = SimpleNamespace(
        rol="GERENTE_REGIONAL",
        sucursales_ids=[],
    )
    query = MagicMock()
    empty_query = MagicMock()
    query.filter.return_value = empty_query

    result = service._apply_planner_role_scope(query, user)

    assert result is empty_query
    query.filter.assert_called_once_with(False)
