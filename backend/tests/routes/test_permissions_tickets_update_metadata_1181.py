"""#1178: tickets.update es veto de metadatos/compromiso, NO de estados.

Pruebas HTTP con JWT y mocks sintéticos. No escribe ni contacta servicios reales.
"""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import ticket_routes as tickets


def _client(*, metadata_enabled=False, status_enabled=False):
    app = Flask(__name__)
    app.config.update(
        TESTING=True, JWT_SECRET_KEY="qa-tickets-metadata-1181",
        PERMISSIONS_TICKETS_UPDATE_GRANTS_ENABLED=metadata_enabled,
        PERMISSIONS_TICKETS_UPDATE_STATUS_GRANTS_ENABLED=status_enabled,
    )
    JWTManager(app)
    app.register_blueprint(tickets.ticket_bp)
    with app.app_context():
        token = create_access_token(identity="47")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def _user():
    return SimpleNamespace(id=47, username="QA", rol="GERENTE", sucursal_id=1,
                           sucursales_ids=[1])


def _ticket():
    return SimpleNamespace(id=80, estado="abierto", departamento_id=1,
                           fecha_solucion=None, fecha_en_progreso=None,
                           historial_fechas=[], requiere_aprobacion=False)


class Scope:
    def __init__(self, value):
        self.value = value

    def filter(self, *_):
        return self

    def first(self):
        return self.value


def test_update_requires_jwt_before_metadata_grant():
    api, _ = _client(metadata_enabled=True)
    with patch.object(tickets.UserORM, "get_by_id") as lookup:
        r = api.put("/api/tickets/compromiso/80", json={"fecha_solucion": "2026-11-03T10:00:00Z"})
    assert r.status_code == 401
    lookup.assert_not_called()


def test_metadata_deny_blocks_compromiso_before_ticket_query():
    from app.routes import permissions_catalog_routes as catalog

    api, auth = _client(metadata_enabled=True)
    with api.application.app_context(), \
         patch.object(tickets.UserORM, "get_by_id", return_value=_user()), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=False) as grant, \
         patch.object(tickets.Ticket, "query", SimpleNamespace(get=Mock())) as query, \
         patch.object(tickets.db.session, "commit") as commit:
        result = api.put("/api/tickets/compromiso/80", headers=auth,
                         json={"fecha_solucion": "2026-11-03T10:00:00Z"})
    assert result.status_code == 403
    assert grant.call_args.kwargs["action_full_key"] == "tickets.update"
    query.get.assert_not_called()
    commit.assert_not_called()


def test_metadata_allow_keeps_compromiso_jefatura_guard():
    from app.routes import permissions_catalog_routes as catalog

    api, auth = _client(metadata_enabled=True)
    with api.application.app_context(), \
         patch.object(tickets.UserORM, "get_by_id", return_value=_user()), \
         patch.object(catalog, "_simple_global_action_grant_override", return_value=True), \
         patch.object(tickets.Ticket, "query", SimpleNamespace(get=lambda _: _ticket())), \
         patch.object(tickets, "_es_admin_o_corporativo", return_value=False), \
         patch.object(tickets, "_es_jefe_depto", return_value=False), \
         patch.object(tickets.db.session, "commit") as commit:
        result = api.put("/api/tickets/compromiso/80", headers=auth,
                         json={"necesita_refaccion": True})
    assert result.status_code == 403
    commit.assert_not_called()


def test_metadata_denial_in_shared_update_stops_before_any_mutation():
    from app.routes import permissions_catalog_routes as catalog

    api, auth = _client(metadata_enabled=True, status_enabled=False)
    ticket = _ticket()
    with api.application.app_context(), \
         patch.object(tickets.UserORM, "get_by_id", return_value=_user()), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=False) as grant, \
         patch.object(tickets.Ticket, "query", SimpleNamespace(get=lambda _: ticket)), \
         patch.object(tickets, "filtrar_tickets_por_usuario", return_value=Scope(ticket)), \
         patch.object(tickets.db.session, "commit") as commit:
        result = api.put("/api/tickets/update/80", headers=auth, json={
            "estado": "en progreso",
            "fecha_solucion": "2026-11-03T10:00:00Z",
            "historial_fechas": [{"fecha": "2026-11-03T10:00:00Z"}],
        })
    assert result.status_code == 403
    assert grant.call_args.kwargs["action_full_key"] == "tickets.update"
    assert ticket.estado == "abierto"
    commit.assert_not_called()


def test_status_only_request_does_not_consult_metadata_grant():
    from app.routes import permissions_catalog_routes as catalog

    api, auth = _client(metadata_enabled=True, status_enabled=False)
    ticket = _ticket()
    with api.application.app_context(), \
         patch.object(tickets.UserORM, "get_by_id", return_value=_user()), \
         patch.object(catalog, "_simple_global_action_grant_override") as grant, \
         patch.object(tickets.Ticket, "query", SimpleNamespace(get=lambda _: ticket)), \
         patch.object(tickets, "filtrar_tickets_por_usuario", return_value=Scope(ticket)), \
         patch.object(tickets.db.session, "commit") as commit:
        result = api.put("/api/tickets/update/80", headers=auth,
                         json={"estado": "finalizado"})
    assert result.status_code == 400
    assert "doble check" in result.json["mensaje"]
    grant.assert_not_called()
    assert ticket.estado == "abierto"
    commit.assert_not_called()


def test_flag_off_keeps_compromiso_legacy_without_grant_query():
    from app.routes import permissions_catalog_routes as catalog

    api, auth = _client(metadata_enabled=False)
    with api.application.app_context(), \
         patch.object(tickets.UserORM, "get_by_id", return_value=_user()), \
         patch.object(catalog, "_simple_global_action_grant_override") as grant, \
         patch.object(tickets.Ticket, "query", SimpleNamespace(get=lambda _: None)):
        result = api.put("/api/tickets/compromiso/80", headers=auth, json={})
    assert result.status_code == 404
    grant.assert_not_called()


def test_flag_default_off():
    app = Flask(__name__)
    with app.app_context():
        assert tickets.tickets_update_grants_enabled() is False


@pytest.mark.parametrize("payload,expected", [
    ({"estado": "en progreso"}, False),
    ({"estado": "en progreso", "fecha_en_progreso": "2026-11-02T16:00:00Z"}, False),
    ({"estado": "en progreso", "necesita_refaccion": False}, True),
    ({"estado": "en progreso", "descripcion_refaccion": ""}, True),
    ({"estado": "en progreso", "historial_fechas": [{"motivo": "QA"}]}, True),
    ({"estado": "en progreso", "fecha_solucion": "2026-11-03T10:00:00Z"}, True),
])
def test_shared_endpoint_metadata_classification(payload, expected):
    assert tickets._ticket_update_metadata_requested(payload) is expected


@pytest.mark.parametrize("effect,expected_legacy,expected_catalog", [
    ("deny", False, False),
    ("allow", None, True),
])
def test_matrix_does_not_claim_metadata_object_permission(
    effect, expected_legacy, expected_catalog,
):
    from app.routes import permissions_visual_audit_routes as visual

    user = _user()
    action = SimpleNamespace(
        id=55, full_key="tickets.update", name="Actualizar datos",
        is_active=True,
        module=SimpleNamespace(id=1, key="tickets", name="Tickets", base_action_id=51),
    )
    context = {
        "user": user, "role": "GERENTE", "sucursal_ids": [1],
        "warehouse_operator": None, "planning_operator": None,
        "allow_ticket_delete_all": False, "pm_scoped_read": False,
    }
    grant = SimpleNamespace(
        id=300, action_id=55, effect=effect, scope_type="global",
        scope_branch_id=None, scope_branch_ids=[],
        scope_department_id=None, scope_payload=None,
        starts_at=None, expires_at=None, reason="QA",
    )
    app = Flask(__name__)
    app.config["PERMISSIONS_TICKETS_UPDATE_GRANTS_ENABLED"] = True
    with app.app_context():
        row = visual.evaluate_pair(user, action, context, {(55, "user", 47): grant})
    assert row["legacy_allowed"] is expected_legacy
    assert row["catalog_allowed"] is expected_catalog
    assert row["catalog_source"] == "tickets_update_grant_operativo"
    if effect == "allow":
        assert row["comparison"] == "no_concluyente"
