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


def test_reassign_only_updates_assignee_and_history(monkeypatch):
    t = ticket(branch=8, state="en progreso")
    t.asignado_a = "SR_MANT_MXL"
    t.tipo_atencion = "INTERNA"
    t.fecha_solucion = datetime(2026, 10, 24, 14, 0, tzinfo=timezone.utc)
    t.fecha_en_progreso = datetime(2026, 10, 18, 17, 0, tzinfo=timezone.utc)
    t.necesita_refaccion = True
    t.descripcion_refaccion = "Se mandó comprar puerta"
    t.historial_fechas = [{"tipo": "legacy", "fechaCambio": "2026-10-16T01:00:00+00:00"}]
    setup_queries(monkeypatch, t)
    monkeypatch.setattr(coordination, "has_maintenance_coordination_permission", lambda _u: True)

    original_due = t.fecha_solucion
    original_in_progress = t.fecha_en_progreso
    original_history = t.historial_fechas[0].copy()
    result = coordination.prepare_maintenance_reassignment(
        t.id,
        actor(),
        {
            "tipo_atencion": "INTERNA",
            "asignado_user_id": 68,
            "motivo": "Responsable incorrecto de Mexicali",
        },
        now=NOW,
    )

    assert result is t
    assert t.asignado_a == "SR_MANT_TIJ"
    assert t.tipo_atencion == "INTERNA"
    assert t.fecha_solucion == original_due
    assert t.fecha_en_progreso == original_in_progress
    assert t.estado == "en progreso"
    assert t.necesita_refaccion is True
    assert t.descripcion_refaccion == "Se mandó comprar puerta"
    assert t.historial_fechas[1] == original_history
    assert t.historial_fechas[0]["tipo"] == "maintenance_reassignment_v1"
    assert t.historial_fechas[0]["asignado_anterior"] == "SR_MANT_MXL"
    assert t.historial_fechas[0]["asignado_nuevo"] == "SR_MANT_TIJ"


def test_reassign_can_change_to_external_without_touching_date(monkeypatch):
    t = ticket(branch=8, state="en progreso")
    t.tipo_atencion = "INTERNA"
    t.asignado_a = "SR_MANT_MXL"
    t.fecha_solucion = datetime(2026, 10, 24, tzinfo=timezone.utc)
    setup_queries(monkeypatch, t)
    monkeypatch.setattr(coordination, "has_maintenance_coordination_permission", lambda _u: True)

    coordination.prepare_maintenance_reassignment(
        t.id,
        actor(),
        {"tipo_atencion": "EXTERNA", "asignado_user_id": None, "motivo": "Se contratará proveedor"},
        now=NOW,
    )
    assert t.asignado_a is None
    assert t.tipo_atencion == "EXTERNA"
    assert t.fecha_solucion == datetime(2026, 10, 24, tzinfo=timezone.utc)


@pytest.mark.parametrize("changes", [
    {"motivo": " "},
    {"motivo": None},
    {"motivo": "x" * 501},
    {"asignado_user_id": True},
    {"asignado_user_id": None},
    {"asignado_user_id": 999},
    {"tipo_atencion": "CUALQUIERA"},
    {"due_date": "2026-12-25"},
    {"estado": "finalizado"},
    {"necesita_refaccion": False},
])
def test_reassign_rejects_invalid_or_extra_fields_without_mutation(monkeypatch, changes):
    t = ticket(branch=8, state="en progreso")
    t.asignado_a = "SR_MANT_MXL"
    t.tipo_atencion = "INTERNA"
    t.fecha_solucion = datetime(2026, 10, 24, tzinfo=timezone.utc)
    setup_queries(monkeypatch, t)
    monkeypatch.setattr(coordination, "has_maintenance_coordination_permission", lambda _u: True)
    valid = {
        "tipo_atencion": "INTERNA",
        "asignado_user_id": 68,
        "motivo": "Corrección de responsable",
    }

    with pytest.raises(coordination.TicketCoordinationError):
        coordination.prepare_maintenance_reassignment(
            t.id, actor(), {**valid, **changes}, now=NOW
        )

    assert t.asignado_a == "SR_MANT_MXL"
    assert t.tipo_atencion == "INTERNA"
    assert t.fecha_solucion == datetime(2026, 10, 24, tzinfo=timezone.utc)
    assert t.historial_fechas == []


def test_reassign_requires_scope_and_does_not_reopen_closed_tickets(monkeypatch):
    t = ticket(branch=3, state="en progreso")
    t.asignado_a = "SR_MANT_MXL"
    setup_queries(monkeypatch, t)
    monkeypatch.setattr(coordination, "has_maintenance_coordination_permission", lambda _u: True)

    with pytest.raises(coordination.TicketCoordinationNotFound):
        coordination.prepare_maintenance_reassignment(
            t.id, actor(),
            {"tipo_atencion": "INTERNA", "asignado_user_id": 68, "motivo": "Corrección"},
            now=NOW,
        )

    t.sucursal_id_destino = 8
    t.estado = "finalizado"
    with pytest.raises(coordination.TicketCoordinationError):
        coordination.prepare_maintenance_reassignment(
            t.id, actor(),
            {"tipo_atencion": "INTERNA", "asignado_user_id": 68, "motivo": "Corrección"},
            now=NOW,
        )
    assert t.asignado_a == "SR_MANT_MXL"


def test_reassign_denies_actor_without_coordination_capability(monkeypatch):
    q = setup_queries(monkeypatch, ticket())
    monkeypatch.setattr(coordination, "has_maintenance_coordination_permission", lambda _u: False)
    with pytest.raises(coordination.TicketCoordinationForbidden):
        coordination.prepare_maintenance_reassignment(
            501, actor(),
            {"tipo_atencion": "INTERNA", "asignado_user_id": 68, "motivo": "Corrección"},
            now=NOW,
        )
    q.filter.assert_not_called()


def test_reassign_ignores_noop_and_does_not_pollute_audit(monkeypatch):
    t = ticket(branch=8, state="en progreso")
    t.tipo_atencion = "INTERNA"
    t.asignado_a = "SR_MANT_TIJ"
    setup_queries(monkeypatch, t)
    monkeypatch.setattr(coordination, "has_maintenance_coordination_permission", lambda _u: True)
    with pytest.raises(coordination.TicketCoordinationError, match="distinto"):
        coordination.prepare_maintenance_reassignment(
            t.id, actor(),
            {"tipo_atencion": "INTERNA", "asignado_user_id": 68, "motivo": "Repetir"},
            now=NOW,
        )
    assert t.historial_fechas == []


def test_tecnico_interno_declara_trabajo_terminado_sin_cerrar_ni_costear(monkeypatch):
    t = ticket(state="en progreso")
    t.tipo_atencion = "INTERNA"
    t.asignado_a = "SR_MANT_TIJ"
    t.estado_cierre = None
    t.costo_solucion = 275
    t.fecha_finalizado = None
    setup_queries(monkeypatch, t)
    tecnico = SimpleNamespace(
        id=68, username="SR_MANT_TIJ", rol="SR_MANTENIMIENTO", department_id=1,
    )

    result = coordination.prepare_maintenance_work_completion(
        501, tecnico, {"notas_trabajo": "Se reemplazo pieza y funciona"}, now=NOW,
    )

    assert result is t
    assert t.estado == "en progreso"
    assert t.estado_cierre == coordination.MAINTENANCE_WORK_REVIEW_PENDING
    assert t.costo_solucion == 275
    assert t.fecha_finalizado is None
    assert t.historial_fechas[0]["tipo"] == "maintenance_work_completed_v1"
    assert t.historial_fechas[0]["cambiadoPor"] == "SR_MANT_TIJ"
    assert t.historial_fechas[0]["motivo"] == "Se reemplazo pieza y funciona"


@pytest.mark.parametrize(
    "assignment,mode,notes",
    [
        ("OTRO_TECNICO", "INTERNA", {"notas_trabajo": "Reparado"}),
        ("SR_MANT_TIJ", "EXTERNA", {"notas_trabajo": "Reparado"}),
        ("SR_MANT_TIJ", "INTERNA", {"notas_trabajo": ""}),
        ("SR_MANT_TIJ", "INTERNA", {"notas_trabajo": "Reparado", "costo_solucion": 0}),
    ],
)
def test_trabajo_terminado_invalido_no_cambia_ticket(
    monkeypatch, assignment, mode, notes,
):
    t = ticket(state="en progreso")
    t.tipo_atencion = mode
    t.asignado_a = assignment
    t.estado_cierre = None
    setup_queries(monkeypatch, t)
    tecnico = SimpleNamespace(
        id=68, username="SR_MANT_TIJ", rol="SR_MANTENIMIENTO", department_id=1,
    )

    with pytest.raises(coordination.TicketCoordinationError):
        coordination.prepare_maintenance_work_completion(
            501, tecnico, notes, now=NOW,
        )

    assert t.estado == "en progreso"
    assert t.estado_cierre is None
    assert t.historial_fechas == []


def test_trabajo_terminado_repetido_no_duplica_historial(monkeypatch):
    t = ticket(state="en progreso")
    t.tipo_atencion = "INTERNA"
    t.asignado_a = "SR_MANT_TIJ"
    t.estado_cierre = coordination.MAINTENANCE_WORK_REVIEW_PENDING
    setup_queries(monkeypatch, t)
    tecnico = SimpleNamespace(
        id=68, username="SR_MANT_TIJ", rol="SR_MANTENIMIENTO", department_id=1,
    )

    with pytest.raises(coordination.TicketCoordinationError):
        coordination.prepare_maintenance_work_completion(
            501, tecnico, {"notas_trabajo": "Reparado otra vez"}, now=NOW,
        )
    assert t.historial_fechas == []


def test_yuliana_devuelve_trabajo_interno_sin_borrar_asignacion(monkeypatch):
    t = ticket(state="en progreso")
    t.tipo_atencion = "INTERNA"
    t.asignado_a = "SR_MANT_TIJ"
    t.estado_cierre = coordination.MAINTENANCE_WORK_REVIEW_PENDING
    t.fecha_solucion = NOW
    t.costo_solucion = 145
    setup_queries(monkeypatch, t)
    monkeypatch.setattr(
        coordination, "has_maintenance_coordination_permission", lambda _user: True,
    )

    coordination.prepare_maintenance_work_return(
        501, actor(), {"motivo": "Falta colocar la cubierta"}, now=NOW,
    )

    assert t.estado == "en progreso"
    assert t.estado_cierre is None
    assert t.asignado_a == "SR_MANT_TIJ"
    assert t.fecha_solucion == NOW
    assert t.costo_solucion == 145
    assert t.historial_fechas[0]["tipo"] == "maintenance_work_returned_v1"
    assert t.historial_fechas[0]["motivo"] == "Falta colocar la cubierta"
    assert t.historial_fechas[0]["cambiadoPor"] == "COORDINADORA_TEST"


@pytest.mark.parametrize(
    "branch,review_state,body",
    [
        (17, coordination.MAINTENANCE_WORK_REVIEW_PENDING, {"motivo": "Rehacer"}),
        (8, None, {"motivo": "Rehacer"}),
        (8, coordination.MAINTENANCE_WORK_REVIEW_PENDING, {"motivo": ""}),
        (8, coordination.MAINTENANCE_WORK_REVIEW_PENDING, {"motivo": "Rehacer", "estado": "finalizado"}),
    ],
)
def test_devolucion_ilegal_no_muta_ticket(
    monkeypatch, branch, review_state, body,
):
    t = ticket(branch=branch, state="en progreso")
    t.tipo_atencion = "INTERNA"
    t.asignado_a = "SR_MANT_TIJ"
    t.estado_cierre = review_state
    setup_queries(monkeypatch, t)
    monkeypatch.setattr(
        coordination, "has_maintenance_coordination_permission", lambda _user: True,
    )

    with pytest.raises(coordination.TicketCoordinationError):
        coordination.prepare_maintenance_work_return(
            501, actor(), body, now=NOW,
        )

    assert t.estado_cierre == review_state
    assert t.historial_fechas == []
