"""#1178: tickets.close es un veto en tres operaciones de cierre, no una aprobación.

Usa peticiones HTTP Flask sintéticas con JWT; no se escriben tickets, no se
notifica a destinatarios y no se realizan cambios en producción.
"""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import ticket_routes as tickets


CLOSURE_URLS = (
    "/api/tickets/cierre/gerente-desde-cero/80",
    "/api/tickets/cierre/solicitar/80",
    "/api/tickets/cierre/aceptar-creador/80",
)


def client(enabled=False):
    app = Flask(__name__)
    app.config.update(
        TESTING=True, JWT_SECRET_KEY="qa-close-action-1181",
        PERMISSIONS_TICKETS_CLOSE_GRANTS_ENABLED=enabled,
    )
    JWTManager(app)
    app.register_blueprint(tickets.ticket_bp)
    with app.app_context():
        token = create_access_token(identity="47")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def actor():
    return SimpleNamespace(id=47, username="QA", rol="GERENTE",
                           sucursal_id=1, sucursales_ids=[1])


def item():
    return SimpleNamespace(id=80, departamento_id=2, estado="abierto",
                           estado_cierre="abierto", fecha_finalizado=None)


@pytest.mark.parametrize("url", CLOSURE_URLS)
def test_close_endpoints_require_jwt_even_with_flag(url):
    api, _ = client(enabled=True)
    with patch.object(tickets.UserORM, "get_by_id") as lookup:
        r = api.post(url, json={})
    assert r.status_code == 401
    lookup.assert_not_called()


@pytest.mark.parametrize("url", CLOSURE_URLS)
def test_close_deny_blocks_before_object_or_notification(url):
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client(enabled=True)
    with api.application.app_context(), \
         patch.object(tickets.UserORM, "get_by_id", return_value=actor()), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=False) as grant, \
         patch.object(tickets.Ticket, "query", SimpleNamespace(get=Mock())) as query, \
         patch.object(tickets.db.session, "commit") as commit, \
         patch.object(tickets, "_notificar_evento_ticket") as notify:
        r = api.post(url, headers=headers, json={"motivo": "QA"})
    assert r.status_code == 403
    assert grant.call_args.kwargs["action_full_key"] == "tickets.close"
    query.get.assert_not_called()
    commit.assert_not_called()
    notify.assert_not_called()


@pytest.mark.parametrize("url", CLOSURE_URLS)
def test_close_allow_never_bypasses_manager_or_legacy_review(url):
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client(enabled=True)
    with api.application.app_context(), \
         patch.object(tickets.UserORM, "get_by_id", return_value=actor()), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True), \
         patch.object(tickets.Ticket, "query", SimpleNamespace(get=lambda _: item())), \
         patch.object(tickets, "_puede_cerrar_ticket_desde_cero",
                      return_value=False), \
         patch.object(tickets, "_puede_validar_cierre_gerente",
                      return_value=False), \
         patch.object(tickets, "_es_admin_o_corporativo", return_value=False), \
         patch.object(tickets, "_es_jefe_depto", return_value=False), \
         patch.object(tickets.db.session, "commit") as commit, \
         patch.object(tickets, "_notificar_evento_ticket") as notify:
        r = api.post(url, headers=headers, json={})
    assert r.status_code == 403
    commit.assert_not_called()
    notify.assert_not_called()


@pytest.mark.parametrize("url", CLOSURE_URLS)
def test_close_flag_off_never_queries_action_grants(url):
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client(enabled=False)
    with api.application.app_context(), \
         patch.object(tickets.UserORM, "get_by_id", return_value=actor()), \
         patch.object(catalog, "_simple_global_action_grant_override") as grant, \
         patch.object(tickets.Ticket, "query", SimpleNamespace(get=lambda _: None)):
        r = api.post(url, headers=headers, json={})
    assert r.status_code == 404
    grant.assert_not_called()


@pytest.mark.parametrize("url", (
    "/api/tickets/cierre/rechazar-jefe/80",
    "/api/tickets/cierre/rechazar-creador/80",
))
def test_rejection_endpoints_are_not_governed_by_close_grant(url):
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client(enabled=True)
    with api.application.app_context(), \
         patch.object(tickets.UserORM, "get_by_id", return_value=actor()), \
         patch.object(catalog, "_simple_global_action_grant_override") as grant, \
         patch.object(tickets.Ticket, "query", SimpleNamespace(get=lambda _: item())), \
         patch.object(tickets, "_es_admin_o_corporativo", return_value=False), \
         patch.object(tickets, "_es_jefe_depto", return_value=False), \
         patch.object(tickets, "_puede_validar_cierre_gerente", return_value=False):
        r = api.post(url, headers=headers, json={})
    assert r.status_code == 403
    grant.assert_not_called()


def test_close_off_by_default():
    app = Flask(__name__)
    with app.app_context():
        assert tickets.tickets_close_grants_enabled() is False


@pytest.mark.parametrize("effect,legacy,catalog", [
    ("deny", False, False),
    ("allow", None, True),
])
def test_close_matrix_veto_is_conclusive_but_allow_not_object_permission(
    effect, legacy, catalog,
):
    from app.routes import permissions_visual_audit_routes as visual
    user = actor()
    action = SimpleNamespace(
        id=55, full_key="tickets.close", name="Cerrar ticket",
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
        starts_at=None, expires_at=None, reason="QA cierre",
    )
    app = Flask(__name__)
    app.config["PERMISSIONS_TICKETS_CLOSE_GRANTS_ENABLED"] = True
    with app.app_context():
        row = visual.evaluate_pair(user, action, context, {(55, "user", 47): grant})
        branch = visual.evaluate_pair(
            user, action, context, {(55, "user", 47): grant}, branch_id=999,
        )
    assert row["legacy_allowed"] is legacy
    assert row["catalog_allowed"] is catalog
    assert row["catalog_source"] == "tickets_close_grant_operativo"
    assert row["comparison"] == ("coincide" if effect == "deny" else "no_concluyente")
    assert branch["legacy_allowed"] is None
