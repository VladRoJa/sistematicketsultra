from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

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
