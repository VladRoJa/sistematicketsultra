"""#1178: tickets.create controla solo entrada, no sucursal o reglas de negocio.

JWT y usuarios sintéticos; las pruebas jamás crean tickets ni tocan producción.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import ticket_routes as tickets


def _client(*, enabled=False):
    app = Flask(__name__)
    app.config.update(
        TESTING=True, JWT_SECRET_KEY="qa-tickets-create-action",
        PERMISSIONS_TICKETS_CREATE_GRANTS_ENABLED=enabled,
    )
    JWTManager(app)
    app.register_blueprint(tickets.ticket_bp)
    with app.app_context():
        token = create_access_token(identity="47")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def _user():
    return SimpleNamespace(id=47, username="QA", rol="ADMINISTRADOR",
                           sucursal_id=1000, sucursales_ids=[])


def test_tickets_create_keeps_jwt_401_without_identity():
    client, _ = _client(enabled=True)
    with patch.object(tickets.UserORM, "get_by_id") as read:
        response = client.post("/api/tickets/create", json={})
    assert response.status_code == 401
    read.assert_not_called()


def test_tickets_create_deny_403_before_payload_or_mutation():
    from app.routes import permissions_catalog_routes as catalog
    client, headers = _client(enabled=True)
    with patch.object(tickets.UserORM, "get_by_id", return_value=_user()), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=False) as decision, \
         patch.object(tickets.db.session, "add") as add:
        response = client.post("/api/tickets/create", headers=headers, json={})
    assert response.status_code == 403
    assert "No autorizado" in response.json["mensaje"]
    decision.assert_called_once()
    assert decision.call_args.kwargs["action_full_key"] == "tickets.create"
    add.assert_not_called()


def test_tickets_create_allow_still_requires_admin_destination_branch():
    from app.routes import permissions_catalog_routes as catalog
    client, headers = _client(enabled=True)
    with patch.object(tickets.UserORM, "get_by_id", return_value=_user()), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True), \
         patch.object(tickets.db.session, "add") as add:
        response = client.post("/api/tickets/create", headers=headers, json={
            "descripcion": "QA",
            "departamento_id": 1,
            "criticidad": 2,
            # Sin sucursal_id_destino, incluso con allow: falla por regla real.
        })
    assert response.status_code == 400
    assert "sucursal_id_destino" in response.json["mensaje"]
    add.assert_not_called()


@pytest.mark.parametrize("grant", [None, True, False])
def test_tickets_create_off_does_not_consult_grants(grant):
    from app.routes import permissions_catalog_routes as catalog
    client, headers = _client(enabled=False)
    with patch.object(tickets.UserORM, "get_by_id", return_value=_user()), \
         patch.object(catalog, "_simple_global_action_grant_override") as decision:
        response = client.post("/api/tickets/create", headers=headers, json={})
    assert response.status_code == 400  # validación actual de campos numéricos
    decision.assert_not_called()


def test_tickets_create_flag_default_off():
    app = Flask(__name__)
    with app.app_context():
        assert tickets.tickets_create_grants_enabled() is False


def test_tickets_create_matrix_only_claims_entry_not_branch_access():
    from app.routes import permissions_visual_audit_routes as visual
    user = _user()
    action = SimpleNamespace(
        id=51, full_key="tickets.create", name="Crear ticket",
        is_active=True,
        module=SimpleNamespace(id=5, key="tickets", name="Tickets", base_action_id=51),
    )
    context = {
        "user": user, "role": "ADMINISTRADOR",
        "sucursal_ids": [], "warehouse_operator": None,
        "planning_operator": None, "allow_ticket_delete_all": False,
        "pm_scoped_read": False,
    }
    grant = SimpleNamespace(
        id=300, action_id=51, effect="deny", scope_type="global",
        scope_branch_id=None, scope_branch_ids=[],
        scope_department_id=None, scope_payload=None,
        starts_at=None, expires_at=None, reason="QA",
    )
    app = Flask(__name__)
    app.config.update(PERMISSIONS_TICKETS_CREATE_GRANTS_ENABLED=True)
    with app.app_context():
        entry = visual.evaluate_pair(user, action, context, {(51, "user", 47): grant})
        scoped = visual.evaluate_pair(
            user, action, context, {(51, "user", 47): grant}, branch_id=999,
        )
    assert entry["legacy_allowed"] is False
    assert entry["catalog_allowed"] is False
    assert entry["catalog_source"] == "tickets_create_grant_operativo"
    assert scoped["legacy_allowed"] is None
    assert scoped["legacy_reason"] == "sucursal_destino_se_valida_en_endpoint"
