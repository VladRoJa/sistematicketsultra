"""Autogestión de Yuliana: propietario explícito, transición y aislamiento.

Pruebas sintéticas, sin consultas a producción.
"""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services import ticket_maintenance_coordination_service as service
from test_ticket_maintenance_coordination_service import (
    NOW, actor, ticket, setup_queries, payload,
)


def yuliana(*, branches=(8,)):
    return SimpleNamespace(
        id=91, username="MANT_YULIANA", rol="COORDINADOR_MANTENIMIENTO",
        department_id=1, sucursal_id=100, sucursales_ids=list(branches),
    )


def test_self_management_identity_requires_exact_user():
    assert service.is_yuliana_self_management_actor(yuliana())
    for changes in (
        {"id": 92}, {"username": "OTRA_COORDINADORA"},
        {"rol": "ADMINISTRADOR"}, {"department_id": 6},
    ):
        user = yuliana()
        for k, v in changes.items():
            setattr(user, k, v)
        assert not service.is_yuliana_self_management_actor(user)
    assert not service.is_yuliana_self_management_actor(actor())


def test_yuliana_autoassigns_herself_when_scheduling(monkeypatch):
    t = ticket(branch=8)
    setup_queries(monkeypatch, t)
    monkeypatch.setattr(service, "has_maintenance_coordination_permission", lambda _: True)
    event = {**payload("AUTOGESTION", None), "motivo": "Lo resolveré personalmente"}
    result = service.prepare_maintenance_coordination(501, yuliana(), event, now=NOW)
    assert result is t
    assert t.estado == "en progreso"
    assert t.tipo_atencion == "AUTOGESTION"
    assert t.asignado_a == "MANT_YULIANA"
    assert t.fecha_solucion is not None
    assert t.fecha_en_progreso == NOW
    assert t.historial_fechas[0]["tipo_atencion_nuevo"] == "AUTOGESTION"
    assert t.historial_fechas[0]["asignado_nuevo"] == "MANT_YULIANA"


@pytest.mark.parametrize("bad_actor", [
    lambda: actor(),
    lambda: SimpleNamespace(id=92, username="OTRA", rol="COORDINADOR_MANTENIMIENTO",
                            department_id=1, sucursales_ids=[8]),
    lambda: SimpleNamespace(id=1, username="ADMICORP", rol="ADMINISTRADOR",
                            department_id=1, sucursales_ids=[8]),
])
def test_other_users_cannot_claim_self_management(monkeypatch, bad_actor):
    t = ticket()
    setup_queries(monkeypatch, t)
    monkeypatch.setattr(service, "has_maintenance_coordination_permission", lambda _: True)
    with pytest.raises(service.TicketCoordinationForbidden):
        service.prepare_maintenance_coordination(
            501, bad_actor(), payload("AUTOGESTION", None), now=NOW,
        )
    assert t.estado == "abierto" and t.asignado_a is None and t.historial_fechas == []


@pytest.mark.parametrize("wrong_assignee", [68, 91, True, "91"])
def test_self_management_rejects_client_chosen_assignee(monkeypatch, wrong_assignee):
    t = ticket()
    setup_queries(monkeypatch, t)
    monkeypatch.setattr(service, "has_maintenance_coordination_permission", lambda _: True)
    with pytest.raises(service.TicketCoordinationError, match="automáticamente"):
        service.prepare_maintenance_coordination(
            501, yuliana(), payload("AUTOGESTION", wrong_assignee), now=NOW,
        )
    assert t.asignado_a is None and t.historial_fechas == []


def test_yuliana_self_management_is_branch_scoped(monkeypatch):
    t = ticket(branch=1)
    setup_queries(monkeypatch, t)
    monkeypatch.setattr(service, "has_maintenance_coordination_permission", lambda _: True)
    with pytest.raises(service.TicketCoordinationNotFound):
        service.prepare_maintenance_coordination(
            501, yuliana(), payload("AUTOGESTION", None), now=NOW,
        )
    assert t.tipo_atencion is None


def test_self_management_requires_coordination_grant(monkeypatch):
    t = ticket()
    query = setup_queries(monkeypatch, t)
    monkeypatch.setattr(service, "has_maintenance_coordination_permission", lambda _: False)
    with pytest.raises(service.TicketCoordinationForbidden):
        service.prepare_maintenance_coordination(
            501, yuliana(), payload("AUTOGESTION", None), now=NOW,
        )
    query.filter.assert_not_called()


def test_reassign_internal_to_autogestion_preserves_deadline_and_invalidates_review(monkeypatch):
    t = ticket(state="en progreso")
    t.tipo_atencion = "INTERNA"
    t.asignado_a = "SR_MANT_TIJ"
    t.estado_cierre = service.MAINTENANCE_WORK_REVIEW_PENDING
    t.fecha_solucion = datetime(2026, 10, 25, tzinfo=timezone.utc)
    previous_due = t.fecha_solucion
    setup_queries(monkeypatch, t)
    monkeypatch.setattr(service, "has_maintenance_coordination_permission", lambda _: True)
    service.prepare_maintenance_reassignment(
        501, yuliana(),
        {"tipo_atencion": "AUTOGESTION", "asignado_user_id": None,
         "motivo": "Atención directa de coordinación"}, now=NOW,
    )
    assert t.tipo_atencion == "AUTOGESTION"
    assert t.asignado_a == "MANT_YULIANA"
    assert t.estado == "en progreso"
    assert t.fecha_solucion == previous_due
    assert t.estado_cierre is None
    assert t.historial_fechas[0]["revision_tecnica_invalidada"] is True


def test_reassign_autogestion_to_external_or_internal_preserves_contract(monkeypatch):
    t = ticket(state="en progreso")
    t.tipo_atencion = "AUTOGESTION"
    t.asignado_a = "MANT_YULIANA"
    t.fecha_solucion = datetime(2026, 10, 25, tzinfo=timezone.utc)
    setup_queries(monkeypatch, t)
    monkeypatch.setattr(service, "has_maintenance_coordination_permission", lambda _: True)
    service.prepare_maintenance_reassignment(
        501, yuliana(),
        {"tipo_atencion": "EXTERNA", "asignado_user_id": None,
         "motivo": "Requiere proveedor"}, now=NOW,
    )
    assert t.asignado_a is None and t.tipo_atencion == "EXTERNA"
    assert t.fecha_solucion == datetime(2026, 10, 25, tzinfo=timezone.utc)
    service.prepare_maintenance_reassignment(
        501, yuliana(),
        {"tipo_atencion": "INTERNA", "asignado_user_id": 68,
         "motivo": "Se asigna al SR"}, now=NOW,
    )
    assert t.asignado_a == "SR_MANT_TIJ" and t.tipo_atencion == "INTERNA"


@pytest.mark.parametrize("bad_actor", [actor, lambda: SimpleNamespace(
    id=92, username="OTRA", rol="COORDINADOR_MANTENIMIENTO",
    department_id=1, sucursales_ids=[8]
)])
def test_reassign_self_management_denied_to_other_coordinators(monkeypatch, bad_actor):
    t = ticket(state="en progreso")
    setup_queries(monkeypatch, t)
    monkeypatch.setattr(service, "has_maintenance_coordination_permission", lambda _: True)
    with pytest.raises(service.TicketCoordinationForbidden):
        service.prepare_maintenance_reassignment(
            501, bad_actor(),
            {"tipo_atencion": "AUTOGESTION", "asignado_user_id": None,
             "motivo": "No es Yuliana"}, now=NOW,
        )
    assert t.tipo_atencion is None and t.historial_fechas == []
