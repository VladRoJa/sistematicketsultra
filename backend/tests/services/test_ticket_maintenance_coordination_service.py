"""Regresiones sin DB para el servicio de coordinación de Tickets V1."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import Integer, column

from app.services import ticket_maintenance_coordination_service as coordination


NOW = datetime(2026, 10, 17, 19, 0, tzinfo=timezone.utc)


def actor(branches=(7, 8, 9)):
    return SimpleNamespace(
        id=91,
        username="COORDINADORA_TEST",
        rol="COMPRAS",
        sucursales_ids=list(branches),
    )


def ticket(branch=8, state="abierto"):
    return SimpleNamespace(
        id=501,
        sucursal_id=100,
        sucursal_id_destino=branch,
        departamento_id=1,
        estado=state,
        asignado_a=None,
        tipo_atencion=None,
        fecha_solucion=None,
        fecha_en_progreso=None,
        necesita_refaccion=False,
        descripcion_refaccion=None,
        historial_fechas=[],
    )


def setup_queries(monkeypatch, target):
    query = MagicMock()
    query.filter.return_value.first.return_value = target
    fake_ticket = SimpleNamespace(
        id=column("id", Integer),
        departamento_id=column("departamento_id", Integer),
        query=query,
    )
    monkeypatch.setattr(coordination, "Ticket", fake_ticket)
    monkeypatch.setattr(coordination, "flag_modified", lambda *args: None)
    maintenance_user = SimpleNamespace(
        id=68,
        username="SR_MANT_TIJ",
        department_id=1,
    )
    monkeypatch.setattr(
        coordination,
        "UserORM",
        SimpleNamespace(get_by_id=lambda user_id: maintenance_user if user_id == 68 else None),
    )
    return query


def payload(mode="INTERNA", assigned_id=68):
    return {
        "tipo_atencion": mode,
        "asignado_user_id": assigned_id,
        "due_date": "2026-10-19",
        "motivo": "Programación Costa",
        "necesita_refaccion": False,
    }


def test_asignacion_interna_y_compromiso_en_una_preparacion(monkeypatch):
    t = ticket()
    setup_queries(monkeypatch, t)
    monkeypatch.setattr(
        coordination, "has_maintenance_coordination_permission", lambda user: True
    )

    result = coordination.prepare_maintenance_coordination(
        501, actor(), payload(), now=NOW
    )

    assert result is t
    assert t.tipo_atencion == "INTERNA"
    assert t.asignado_a == "SR_MANT_TIJ"
    assert t.estado == "en progreso"
    assert t.fecha_solucion is not None
    assert t.fecha_en_progreso == NOW
    assert len(t.historial_fechas) == 1
    assert t.historial_fechas[0]["asignado_nuevo"] == "SR_MANT_TIJ"
    assert t.historial_fechas[0]["cambiadoPor"] == "COORDINADORA_TEST"


def test_externo_no_inventa_usuario_y_conserva_rastro(monkeypatch):
    t = ticket(state="en progreso")
    t.tipo_atencion = "INTERNA"
    t.asignado_a = "SR_MANT_TIJ"
    setup_queries(monkeypatch, t)
    monkeypatch.setattr(
        coordination, "has_maintenance_coordination_permission", lambda user: True
    )

    coordination.prepare_maintenance_coordination(
        501, actor(), payload("EXTERNA", None), now=NOW
    )

    assert t.tipo_atencion == "EXTERNA"
    assert t.asignado_a is None
    assert t.historial_fechas[-1]["asignado_anterior"] == "SR_MANT_TIJ"
    assert t.historial_fechas[-1]["tipo_atencion_nuevo"] == "EXTERNA"


def test_usuario_sin_grant_no_consulta_tickets(monkeypatch):
    query = setup_queries(monkeypatch, ticket())
    monkeypatch.setattr(
        coordination, "has_maintenance_coordination_permission", lambda user: False
    )

    with pytest.raises(coordination.TicketCoordinationForbidden):
        coordination.prepare_maintenance_coordination(
            501, actor(), payload(), now=NOW
        )

    query.filter.assert_not_called()


def test_ticket_fuera_de_sucursales_denegado(monkeypatch):
    t = ticket(branch=3)
    setup_queries(monkeypatch, t)
    monkeypatch.setattr(
        coordination, "has_maintenance_coordination_permission", lambda user: True
    )

    with pytest.raises(coordination.TicketCoordinationNotFound):
        coordination.prepare_maintenance_coordination(
            501, actor(), payload(), now=NOW
        )

    assert t.estado == "abierto"
    assert t.asignado_a is None


def test_ticket_finalizado_no_se_reabre(monkeypatch):
    t = ticket(state="finalizado")
    setup_queries(monkeypatch, t)
    monkeypatch.setattr(
        coordination, "has_maintenance_coordination_permission", lambda user: True
    )

    with pytest.raises(coordination.TicketCoordinationError):
        coordination.prepare_maintenance_coordination(
            501, actor(), payload(), now=NOW
        )
    assert t.estado == "finalizado"


@pytest.mark.parametrize(
    "changes",
    [
        {"motivo": ""},
        {"due_date": "2026-10-15"},
        {"due_date": "2026-99-19"},
        {"tipo_atencion": "OTRA"},
        {"asignado_user_id": None},
        {"asignado_user_id": True},
    ],
)
def test_payload_invalido_no_muta_ticket(monkeypatch, changes):
    t = ticket()
    setup_queries(monkeypatch, t)
    monkeypatch.setattr(
        coordination, "has_maintenance_coordination_permission", lambda user: True
    )

    with pytest.raises(coordination.TicketCoordinationError):
        coordination.prepare_maintenance_coordination(
            501, actor(), {**payload(), **changes}, now=NOW
        )

    assert t.tipo_atencion is None
    assert t.asignado_a is None
    assert t.fecha_solucion is None
    assert t.historial_fechas == []


def test_externo_con_user_id_es_invalido(monkeypatch):
    t = ticket()
    setup_queries(monkeypatch, t)
    monkeypatch.setattr(
        coordination, "has_maintenance_coordination_permission", lambda user: True
    )
    with pytest.raises(coordination.TicketCoordinationError):
        coordination.prepare_maintenance_coordination(
            501, actor(), payload("EXTERNA", 68), now=NOW
        )


def test_usuarios_fuera_de_mantenimiento_no_son_asignables(monkeypatch):
    t = ticket()
    setup_queries(monkeypatch, t)
    monkeypatch.setattr(
        coordination, "has_maintenance_coordination_permission", lambda user: True
    )
    monkeypatch.setattr(
        coordination,
        "UserORM",
        SimpleNamespace(get_by_id=lambda user_id: SimpleNamespace(username="SISTEMAS", department_id=7)),
    )

    with pytest.raises(coordination.TicketCoordinationError):
        coordination.prepare_maintenance_coordination(
            501, actor(), payload(), now=NOW
        )
    assert t.asignado_a is None


def test_admin_no_limitado_por_sucursales_del_coordinador(monkeypatch):
    t = ticket(branch=3)
    setup_queries(monkeypatch, t)
    monkeypatch.setattr(
        coordination, "has_maintenance_coordination_permission", lambda user: True
    )

    admin = SimpleNamespace(id=1, username="ADMIN", rol="ADMINISTRADOR", sucursales_ids=[])
    coordination.prepare_maintenance_coordination(
        501, admin, payload(), now=NOW
    )
    assert t.asignado_a == "SR_MANT_TIJ"


def test_reasignar_mantenimiento_mantiene_ticket_y_audita_cambio(monkeypatch):
    """Un responsable de Mexicali puede corregirse a Tijuana sin abrir otro ticket."""
    t = ticket(branch=8, state="en progreso")
    t.tipo_atencion = "INTERNA"
    t.asignado_a = "SR_MANT_MXL"
    setup_queries(monkeypatch, t)
    monkeypatch.setattr(
        coordination, "has_maintenance_coordination_permission", lambda user: True
    )

    result = coordination.prepare_maintenance_coordination(
        501,
        actor(),
        {**payload(), "motivo": "Corrección de responsable regional"},
        now=NOW,
    )

    assert result is t
    assert t.id == 501
    assert t.estado == "en progreso"
    assert t.tipo_atencion == "INTERNA"
    assert t.asignado_a == "SR_MANT_TIJ"
    assert len(t.historial_fechas) == 1
    assert t.historial_fechas[0]["asignado_anterior"] == "SR_MANT_MXL"
    assert t.historial_fechas[0]["asignado_nuevo"] == "SR_MANT_TIJ"
    assert t.historial_fechas[0]["motivo"] == "Corrección de responsable regional"
