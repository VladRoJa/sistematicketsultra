"""#1178: tickets.notify — control del POST, sin fuga de ticket ni envío real.

Pruebas HTTP con JWT y usuarios sintéticos: nunca mandan correo ni
acceden a PostgreSQL productivo.
"""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import ticket_routes as tickets


def _client(enabled=False):
    app = Flask(__name__)
    app.config.update(
        TESTING=True, JWT_SECRET_KEY="qa-tickets-notify-action",
        PERMISSIONS_TICKETS_NOTIFY_GRANTS_ENABLED=enabled,
    )
    JWTManager(app)
    app.register_blueprint(tickets.ticket_bp)
    with app.app_context():
        token = create_access_token(identity="47")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def _user():
    return SimpleNamespace(id=47, username="QA_NOTIFICAR", rol="GERENTE",
                           sucursal_id=1, sucursales_ids=[1])


def _ticket():
    return SimpleNamespace(id=80, to_dict=lambda: {"id": 80})


class ScopeQuery:
    def __init__(self, result):
        self.result = result

    def filter(self, *_):
        return self

    def first(self):
        return self.result


PAYLOAD = {"channels": ["email"], "emails": ["qa@invalid.example"]}


def test_notify_requires_jwt_before_any_query():
    api, _ = _client(enabled=True)
    with patch.object(tickets.UserORM, "get_by_id") as lookup:
        response = api.post("/api/tickets/notify/80", json=PAYLOAD)
    assert response.status_code == 401
    lookup.assert_not_called()


def test_notify_deny_blocks_before_ticket_lookup_and_email():
    from app.routes import permissions_catalog_routes as catalog
    api, auth = _client(enabled=True)
    with api.application.app_context(), \
         patch.object(tickets.UserORM, "get_by_id", return_value=_user()), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=False) as grant, \
         patch.object(tickets.Ticket, "query", SimpleNamespace(get=Mock())) as query, \
         patch.object(tickets, "send_email_html") as mail:
        response = api.post("/api/tickets/notify/80", headers=auth, json=PAYLOAD)
    assert response.status_code == 403
    assert grant.call_args.kwargs["action_full_key"] == "tickets.notify"
    query.get.assert_not_called()
    mail.assert_not_called()


def test_notify_allow_cannot_bypass_user_ticket_scope():
    from app.routes import permissions_catalog_routes as catalog
    api, auth = _client(enabled=True)
    with api.application.app_context(), \
         patch.object(tickets.UserORM, "get_by_id", return_value=_user()), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True), \
         patch.object(tickets.Ticket, "query", SimpleNamespace(get=lambda _: _ticket())), \
         patch.object(tickets, "filtrar_tickets_por_usuario",
                      return_value=ScopeQuery(None)), \
         patch.object(tickets, "send_email_html") as mail:
        response = api.post("/api/tickets/notify/80", headers=auth, json=PAYLOAD)
    assert response.status_code == 403
    assert "No autorizado" in response.json["mensaje"]
    mail.assert_not_called()


def test_notify_allow_can_reach_authorized_ticket_without_sending_real_mail():
    from app.routes import permissions_catalog_routes as catalog
    api, auth = _client(enabled=True)
    item = _ticket()
    with api.application.app_context(), \
         patch.object(tickets.UserORM, "get_by_id", return_value=_user()), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True), \
         patch.object(tickets.Ticket, "query", SimpleNamespace(get=lambda _: item)), \
         patch.object(tickets, "filtrar_tickets_por_usuario",
                      return_value=ScopeQuery(item)), \
         patch.object(tickets, "render_ticket_html", return_value="<p>Sintético</p>"), \
         patch.object(tickets, "send_email_html") as mail:
        response = api.post("/api/tickets/notify/80", headers=auth, json=PAYLOAD)
    assert response.status_code == 200
    assert response.json["results"]["email"]["ok"] is True
    mail.assert_called_once()


def test_notify_flag_off_keeps_existing_guard_without_grant_query():
    from app.routes import permissions_catalog_routes as catalog
    api, auth = _client(enabled=False)
    with api.application.app_context(), \
         patch.object(tickets.UserORM, "get_by_id", return_value=_user()), \
         patch.object(catalog, "_simple_global_action_grant_override") as grant, \
         patch.object(tickets.Ticket, "query", SimpleNamespace(get=lambda _: None)), \
         patch.object(tickets, "send_email_html") as mail:
        response = api.post("/api/tickets/notify/80", headers=auth, json=PAYLOAD)
    assert response.status_code == 404
    grant.assert_not_called()
    mail.assert_not_called()


def test_notify_flag_default_off():
    app = Flask(__name__)
    with app.app_context():
        assert tickets.tickets_notify_grants_enabled() is False


@pytest.mark.parametrize("effect,expected", [("deny", False), ("allow", True)])
def test_notify_matrix_certifies_only_http_entry(effect, expected):
    from app.routes import permissions_visual_audit_routes as visual
    user = _user()
    action = SimpleNamespace(
        id=55, full_key="tickets.notify", name="Notificar ticket",
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
    app.config["PERMISSIONS_TICKETS_NOTIFY_GRANTS_ENABLED"] = True
    with app.app_context():
        row = visual.evaluate_pair(user, action, context, {(55, "user", 47): grant})
        scoped = visual.evaluate_pair(user, action, context,
                                      {(55, "user", 47): grant}, branch_id=999)
    assert row["legacy_allowed"] is expected
    assert row["catalog_allowed"] is expected
    assert row["catalog_source"] == "tickets_notify_grant_operativo"
    assert scoped["legacy_allowed"] is None
    assert scoped["comparison"] == "no_concluyente"
