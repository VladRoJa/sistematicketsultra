"""Regresión M4.5: Planner deriva disponibilidad de cierre del avance oficial."""
from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.maintenance_planner.service import _serialize_ticket


class TicketStub:
    def __init__(self, tipo, recibidos, total=6):
        self.id = 3209
        self.tipo_trabajo = tipo
        self.estado = "en progreso"
        self.aparatos_asociados = [
            SimpleNamespace(recibido_en_utc=datetime.now(timezone.utc) if i < recibidos else None)
            for i in range(total)
        ]

    def __getattr__(self, name):
        return None


def test_planner_serializa_5_de_6_sin_autorizar_cierre():
    row = _serialize_ticket(TicketStub("TAPIZADO", 5), date(2026, 10, 26))
    assert row["tipo_trabajo"] == "TAPIZADO"
    assert row["avance_tapizado"]["recibidos"] == 5
    assert row["avance_tapizado"]["pendientes"] == 1
    assert row["avance_tapizado"]["completo"] is False


def test_planner_serializa_6_de_6_completo_y_revierte():
    ticket = TicketStub("TAPIZADO", 6)
    assert _serialize_ticket(ticket, date(2026, 10, 26))["avance_tapizado"]["completo"] is True
    ticket.aparatos_asociados[-1].recibido_en_utc = None
    assert _serialize_ticket(ticket, date(2026, 10, 26))["avance_tapizado"]["completo"] is False


def test_planner_no_habilita_sin_aparatos_y_no_modifica_ticket_legacy():
    empty = _serialize_ticket(TicketStub("TAPIZADO", 0, 0), date(2026, 10, 26))
    regular = _serialize_ticket(TicketStub(None, 0, 0), date(2026, 10, 26))
    assert empty["avance_tapizado"]["completo"] is False
    assert regular["avance_tapizado"] is None
