"""#1178: pm.validate sólo veta POST /validaciones, no concede autorización.

Flask/JWT y objetos sintéticos: no conecta a datos productivos.
"""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import pm_routes as pm


URL = "/api/pm/validaciones"


def payload(decision="VALIDADO", motivo=None):
    result = {"bitacora_pm_id": 78, "decision": decision}
    if motivo is not None:
        result["motivo"] = motivo
    return result


def actor(role="ADMINISTRADOR", branches=(7,), primary=7):
    return SimpleNamespace(id=47, username="QA", rol=role,
                           sucursal_id=primary, sucursales_ids=list(branches),
                           department_id=1)


def bitacora(*, branch=7, creator=19, already_validated=False):
    return SimpleNamespace(
        id=78, sucursal_id=branch, created_by_user_id=creator,
        pm_validacion=SimpleNamespace(id=99) if already_validated else None,
    )


def fake_db(b):
    session = SimpleNamespace(
        get=Mock(return_value=b), add=Mock(), commit=Mock(),
    )
    return SimpleNamespace(session=session)


def client(enabled=True):
    app = Flask(__name__)
    app.config.update(
        TESTING=True, JWT_SECRET_KEY="synthetic-pm-validate-1181",
        PERMISSIONS_PM_VALIDATE_GRANTS_ENABLED=enabled,
    )
    JWTManager(app)
    app.register_blueprint(pm.pm_bp, url_prefix="/api/pm")
    with app.app_context():
        token = create_access_token(identity="47")
    return app.test_client(), {"Authorization": "Bearer " + token}


def test_validate_requires_jwt():
    api, _ = client()
    assert api.post(URL, json=payload()).status_code == 401


def test_denied_veto_blocks_validation_before_scope_and_db_writes():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    db = fake_db(bitacora())
    with api.application.app_context(), \
         patch.object(pm, "db", db), \
         patch.object(pm.UserORM, "get_by_id", return_value=actor()), \
         patch.object(pm, "_verificar_permiso_sucursal") as scope, \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=False) as grant:
        r = api.post(URL, json=payload(), headers=headers)
    assert r.status_code == 403
    assert r.json["detail"] == "No tienes habilitada la validación de bitácoras PM."
    grant.assert_called_once()
    assert grant.call_args.kwargs["action_full_key"] == "pm.validate"
    scope.assert_not_called()
    db.session.add.assert_not_called()
    db.session.commit.assert_not_called()


def test_allow_cannot_promote_execute_only_role_to_validator():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    db = fake_db(bitacora())
    with api.application.app_context(), \
         patch.object(pm, "db", db), \
         patch.object(pm.UserORM, "get_by_id",
                      return_value=actor("AUX_MANTENIMIENTO")), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True) as grant:
        r = api.post(URL, json=payload(), headers=headers)
    assert r.status_code == 403
    grant.assert_not_called()
    db.session.add.assert_not_called()


def test_allow_does_not_bypass_branch_scope():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    db = fake_db(bitacora(branch=999))
    with api.application.app_context(), \
         patch.object(pm, "db", db), \
         patch.object(pm.UserORM, "get_by_id",
                      return_value=actor("SR_MANTENIMIENTO")), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True) as grant:
        r = api.post(URL, json=payload(), headers=headers)
    assert r.status_code == 403
    grant.assert_called_once()
    db.session.add.assert_not_called()


def test_allow_does_not_bypass_duplicate_validation():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    db = fake_db(bitacora(already_validated=True))
    with api.application.app_context(), \
         patch.object(pm, "db", db), \
         patch.object(pm.UserORM, "get_by_id", return_value=actor()), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True) as grant:
        r = api.post(URL, json=payload(), headers=headers)
    assert r.status_code == 409
    assert "ya cuenta con validación" in r.json["detail"]
    grant.assert_called_once()
    db.session.add.assert_not_called()


def test_allow_does_not_bypass_self_validation():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    db = fake_db(bitacora(creator=47))
    with api.application.app_context(), \
         patch.object(pm, "db", db), \
         patch.object(pm.UserORM, "get_by_id", return_value=actor()), \
         patch.object(catalog, "_simple_global_action_grant_override",
                      return_value=True) as grant:
        r = api.post(URL, json=payload(), headers=headers)
    assert r.status_code == 403
    assert "tu propia bitácora" in r.json["detail"]
    grant.assert_called_once()
    db.session.add.assert_not_called()


@pytest.mark.parametrize("body,detail_fragment", [
    ({"bitacora_pm_id": 78, "decision": "RECHAZADO"}, "motivo es obligatorio"),
    ({"bitacora_pm_id": 78, "decision": "PENDIENTE"}, "VALIDADO o RECHAZADO"),
    ({"bitacora_pm_id": "incorrecto", "decision": "VALIDADO"}, "debe ser entero"),
])
def test_validation_payload_checks_still_apply_before_grants(body, detail_fragment):
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client()
    with api.application.app_context(), \
         patch.object(catalog, "_simple_global_action_grant_override") as grant:
        r = api.post(URL, json=body, headers=headers)
    assert r.status_code == 400
    assert detail_fragment in r.json["detail"]
    grant.assert_not_called()


def test_flag_off_preserves_legacy_and_never_reads_grants():
    from app.routes import permissions_catalog_routes as catalog
    api, headers = client(enabled=False)
    db = fake_db(bitacora(already_validated=True))
    with api.application.app_context(), \
         patch.object(pm, "db", db), \
         patch.object(pm.UserORM, "get_by_id", return_value=actor()), \
         patch.object(catalog, "_simple_global_action_grant_override") as grant:
        r = api.post(URL, json=payload(), headers=headers)
    assert r.status_code == 409
    grant.assert_not_called()
    db.session.add.assert_not_called()


def test_validate_flag_off_by_default():
    with Flask(__name__).app_context():
        assert pm.pm_validate_grants_enabled() is False


@pytest.mark.parametrize("effect,branch,legacy,catalog_allowed", [
    ("deny", None, False, False),
    ("deny", 7, False, False),
    ("allow", None, True, True),
    ("allow", 7, None, None),
])
def test_matrix_global_veto_does_not_certify_object(
    effect, branch, legacy, catalog_allowed,
):
    from app.routes import permissions_visual_audit_routes as visual
    user = actor()
    action = SimpleNamespace(
        id=87, full_key="pm.validate", name="Validar PM", is_active=True,
        module=SimpleNamespace(id=4, key="pm", name="PM", base_action_id=80),
    )
    context = {
        "user": user, "role": user.rol, "sucursal_ids": [7],
        "warehouse_operator": None, "planning_operator": None,
        "allow_ticket_delete_all": False, "pm_scoped_read": False,
    }
    grant = SimpleNamespace(
        id=88, effect=effect, scope_type="global", starts_at=None,
        expires_at=None, reason="QA", action_id=87,
        scope_branch_id=None, scope_branch_ids=[],
        scope_department_id=None, scope_payload=None,
    )
    app = Flask(__name__)
    app.config["PERMISSIONS_PM_VALIDATE_GRANTS_ENABLED"] = True
    with app.app_context():
        row = visual.evaluate_pair(
            user, action, context, {(87, "user", 47): grant}, branch_id=branch,
        )
    assert row["legacy_allowed"] is legacy
    assert row["catalog_allowed"] is catalog_allowed
    assert row["catalog_source"] == "pm_validate_grant_operativo"
