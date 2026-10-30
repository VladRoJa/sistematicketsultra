"""#1178: veto accion update_status preserva JWT, rol, sucursal y doble check.

HTTP Flask con JWT y tickets sinteticos, sin PostgreSQL ni mutaciones reales.
"""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import ticket_routes as tickets


def _client(*, enabled=False):
    app = Flask(__name__)
    app.config.update(
        TESTING=True, JWT_SECRET_KEY="qa-tickets-status-action",
        PERMISSIONS_TICKETS_UPDATE_STATUS_GRANTS_ENABLED=enabled,
    )
    JWTManager(app)
    app.register_blueprint(tickets.ticket_bp)
    with app.app_context():
        token = create_access_token(identity="47")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def _user(role="GERENTE"):
    return SimpleNamespace(id=47, username="QA", rol=role, sucursal_id=1,
                           sucursales_ids=[1])


def _ticket():
    return SimpleNamespace(
        id=80, estado="abierto", departamento_id=1,
        fecha_solucion=None, fecha_en_progreso=None,
        historial_fechas=[], requiere_aprobacion=False,
    )


class ScopeQuery:
    def __init__(self, result):
        self.result = result
    def filter(self, *_):
        return self
    def first(self):
        return self.result


def test_update_status_no_jwt_is_401_even_with_grant_allow():
    api, _ = _client(enabled=True)
    with patch.object(tickets.UserORM, "get_by_id") as get_user:
        response = api.put("/api/tickets/update/80", json={"estado": "en progreso"})
    assert response.status_code == 401
    get_user.assert_not_called()


def test_status_deny_403_before_ticket_lookup():
    from app.routes import permissions_catalog_routes as catalog
    api, auth = _client(enabled=True)
    with patch.object(tickets.UserORM, "get_by_id", return_value=_user()), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=False) as decision, \
         patch.object(tickets.Ticket, "query", SimpleNamespace(get=Mock())) as ticket_query, \
         patch.object(tickets.db.session, "commit") as commit:
        response = api.put("/api/tickets/update/80", headers=auth,
                           json={"estado": "en progreso"})
        ticket_query.get.assert_not_called()
    assert response.status_code == 403
    assert "No autorizado" in response.json["mensaje"]
    assert decision.call_args.kwargs["action_full_key"] == "tickets.update_status"
    commit.assert_not_called()


def test_status_allow_cannot_bypass_lectora_global_role_decorator():
    from app.routes import permissions_catalog_routes as catalog
    api, auth = _client(enabled=True)
    with patch.object(tickets.UserORM, "get_by_id",
                      return_value=_user("LECTOR_GLOBAL")), \
         patch.object(catalog, "_simple_global_action_grant_override") as decision, \
         patch.object(tickets.Ticket, "query", SimpleNamespace(get=Mock())) as ticket_query:
        response = api.put("/api/tickets/update/80", headers=auth,
                           json={"estado": "en progreso"})
        ticket_query.get.assert_not_called()
    assert response.status_code == 403
    decision.assert_not_called()  # guard legacy antes que grant


def test_status_allow_cannot_bypass_ticket_scope():
    from app.routes import permissions_catalog_routes as catalog
    api, auth = _client(enabled=True)
    current = _ticket()
    with patch.object(tickets.UserORM, "get_by_id", return_value=_user()), \
         patch.object(catalog, "_simple_global_action_grant_override", return_value=True), \
         patch.object(tickets.Ticket, "query", SimpleNamespace(get=lambda _: current)), \
         patch.object(tickets, "filtrar_tickets_por_usuario",
                      return_value=ScopeQuery(None)), \
         patch.object(tickets.db.session, "commit") as commit:
        response = api.put("/api/tickets/update/80", headers=auth,
                           json={"estado": "en progreso"})
    assert response.status_code == 403
    assert "No autorizado" in response.json["mensaje"]
    commit.assert_not_called()


def test_status_allow_cannot_finalize_without_double_check():
    from app.routes import permissions_catalog_routes as catalog
    api, auth = _client(enabled=True)
    current = _ticket()
    with patch.object(tickets.UserORM, "get_by_id", return_value=_user()), \
         patch.object(catalog, "_simple_global_action_grant_override", return_value=True), \
         patch.object(tickets.Ticket, "query", SimpleNamespace(get=lambda _: current)), \
         patch.object(tickets, "filtrar_tickets_por_usuario",
                      return_value=ScopeQuery(current)), \
         patch.object(tickets.db.session, "commit") as commit:
        response = api.put("/api/tickets/update/80", headers=auth,
                           json={"estado": "finalizado"})
    assert response.status_code == 400
    assert "doble check" in response.json["mensaje"]
    assert current.estado == "abierto"
    commit.assert_not_called()


def test_status_flag_off_keeps_legacy_and_avoids_grants():
    from app.routes import permissions_catalog_routes as catalog
    api, auth = _client(enabled=False)
    with patch.object(tickets.UserORM, "get_by_id", return_value=_user()), \
         patch.object(catalog, "_simple_global_action_grant_override") as decision, \
         patch.object(tickets.Ticket, "query", SimpleNamespace(get=lambda _: None)):
        response = api.put("/api/tickets/update/80", headers=auth,
                           json={"estado": "en progreso"})
    assert response.status_code == 404
    decision.assert_not_called()


def test_status_flag_default_off():
    app = Flask(__name__)
    with app.app_context():
        assert tickets.tickets_update_status_grants_enabled() is False


@pytest.mark.parametrize("role,effect,expected", [
    ("GERENTE", "deny", False),
    ("GERENTE", "allow", True),
    ("LECTOR_GLOBAL", "allow", False),
])
def test_status_matrix_never_overrides_legacy_lector_block(role, effect, expected):
    from app.routes import permissions_visual_audit_routes as visual
    user = _user(role)
    action = SimpleNamespace(
        id=55, full_key="tickets.update_status", name="Cambiar estado ticket",
        is_active=True,
        module=SimpleNamespace(id=1, key="tickets", name="Tickets", base_action_id=51),
    )
    context = {
        "user": user, "role": role,
        "sucursal_ids": [1], "warehouse_operator": None,
        "planning_operator": None, "allow_ticket_delete_all": False,
        "pm_scoped_read": False,
    }
    grant = SimpleNamespace(
        id=300, action_id=55, effect=effect, scope_type="global",
        scope_branch_id=None, scope_branch_ids=[],
        scope_department_id=None, scope_payload=None,
        starts_at=None, expires_at=None, reason="QA",
    )
    app = Flask(__name__)
    app.config["PERMISSIONS_TICKETS_UPDATE_STATUS_GRANTS_ENABLED"] = True
    with app.app_context():
        row = visual.evaluate_pair(user, action, context, {(55, "user", 47): grant})
        scoped = visual.evaluate_pair(
            user, action, context, {(55, "user", 47): grant}, branch_id=999,
        )
    assert row["legacy_allowed"] is expected
    assert row["catalog_allowed"] is expected
    assert row["catalog_source"] == "tickets_update_status_grant_operativo"
    assert scoped["legacy_allowed"] is None
