from types import SimpleNamespace

import pytest
from flask_jwt_extended import create_access_token, jwt_required
from werkzeug.security import generate_password_hash

from app import create_app
from app.config import Config
from app.models.user_model import UserORM
from app.routes import marketing_sales_funnel_routes as funnel
from app.services.funnel_provider_access import AUTH_OPERATIONS, FUNNEL_OPERATION, PROVEEDOR_FUNNEL_ORIGINAL
from app.services.marketing_access import MarketingAuthorizationError, resolve_marketing_access


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.setattr(Config, "SQLALCHEMY_DATABASE_URI", "sqlite://")
    monkeypatch.setattr(Config, "AUTH_REFRESH_ENABLED", False)
    app = create_app()
    app.config.update(TESTING=True, JWT_SECRET_KEY="synthetic-provider-test-secret-32-characters")
    actor = SimpleNamespace(
        id=17, username="external-test", rol=PROVEEDOR_FUNNEL_ORIGINAL,
        sucursal_id=1000, sucursales_ids=[2, 7], department_id=1,
    )
    monkeypatch.setattr(UserORM, "get_by_id", classmethod(lambda cls, uid: actor))
    @app.get('/api/provider-test/jwt-only')
    @jwt_required()
    def jwt_only():
        return {"ok": True}
    with app.app_context():
        # Deliberately stale admin claims: the persisted role must win.
        token = create_access_token(identity="17", additional_claims={"rol": "ADMINISTRADOR"})
    return app, app.test_client(), actor, {"Authorization": f"Bearer {token}"}


def test_assigned_scope_only_and_no_implicit_primary_or_global(harness):
    _, _, actor, _ = harness
    access = resolve_marketing_access(actor)
    assert access.branch_ids == (2, 7)
    assert not access.is_global
    assert not any((access.can_edit_inputs, access.can_manage_campaigns, access.can_view_reactivation))
    actor.sucursales_ids = []
    with pytest.raises(MarketingAuthorizationError):
        resolve_marketing_access(actor)


def test_all_registered_non_allowlisted_operations_are_denied(harness):
    app, client, _, headers = harness
    checked = 0
    for rule in app.url_map.iter_rules():
        values = {name: (1 if converter.__class__.__name__ == 'IntegerConverter' else 'test')
                  for name, converter in rule._converters.items()}
        built = rule.build(values)
        assert built is not None
        path = built[1]
        for method in rule.methods - {"OPTIONS"}:
            if (method, rule.endpoint) in AUTH_OPERATIONS | {FUNNEL_OPERATION}:
                continue
            response = client.open(path, method=method, headers=headers)
            assert response.status_code == 403, (method, path, response.status_code)
            checked += 1
    assert checked > 100


@pytest.mark.parametrize("query", [
    "", "?visit_mode=adjusted", "?visit_mode=registered_only&visit_mode=adjusted",
    "?visit_mode=registered_only&branch_id=999", "?visit_mode=registered_only&branch_ids=2&branch_ids=999",
])
def test_adjusted_and_ambiguous_parameters_denied(harness, query):
    _, client, _, headers = harness
    assert client.get('/api/marketing/sales-funnel' + query, headers=headers).status_code == 403


def test_original_filters_and_cutoff_use_assigned_scope(harness, monkeypatch):
    _, client, actor, headers = harness
    calls = []
    monkeypatch.setattr(funnel, "load_visible_marketing_branches", lambda access: ([], access.branch_ids, {}))
    monkeypatch.setattr(funnel, "_load_scope_options", lambda access: [{"sucursal_id": b} for b in access.branch_ids])
    def build(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(payload={
            "summary": {}, "branches": [{"sucursal_id": b} for b in kwargs['access'].branch_ids],
            "data_quality": {"crm_history_available": False},
            "selected_cutoff_date": kwargs['cutoff_date'],
        })
    monkeypatch.setattr(funnel, "build_marketing_sales_funnel_at_cutoff", build)
    url = '/api/marketing/sales-funnel?visit_mode=registered_only&month=2026-10&cutoff_date=2026-10-29'
    result = client.get(url + '&branch_ids=7', headers=headers)
    assert result.status_code == 200
    assert result.json['branches'] == [{"sucursal_id": 7, **{key: None for key in funnel.HISTORICAL_CRM_VISIT_CONVERSION_FIELDS}}]
    assert result.json['scope_options'] == [{"sucursal_id": 2}, {"sucursal_id": 7}]
    assert calls[0]['include_direct_purchases'] is False
    assert calls[0]['access'].branch_ids == (7,)
    assert client.get(url + '&branch_ids=999', headers=headers).status_code == 403
    assert len(calls) == 1
    actor.sucursales_ids = []
    assert client.get(url, headers=headers).status_code == 403


def test_login_session_and_existing_role_access(harness, monkeypatch):
    _, client, actor, headers = harness
    password_user = UserORM(username='external-test', password=generate_password_hash('test-password'),
                            rol=actor.rol, sucursal_id=1000, department_id=1)
    actor.verify_password = password_user.verify_password
    monkeypatch.setattr(UserORM, "get_by_username", classmethod(lambda cls, name: actor))
    result = client.post('/api/auth/login', json={"username": actor.username, "password": "test-password"})
    assert result.status_code == 200
    assert result.json['user']['rol'] == PROVEEDOR_FUNNEL_ORIGINAL
    login_headers = {"Authorization": 'Bearer ' + result.json['token']}
    assert client.get('/api/auth/session-info', headers=login_headers).status_code == 200
    assert client.get('/api/provider-test/jwt-only', headers=login_headers).status_code == 403
    for role in ('ADMINISTRADOR', 'LECTOR_GLOBAL', 'MARKETING', 'GERENTE'):
        actor.rol = role
        assert client.get('/api/provider-test/jwt-only', headers=headers).status_code == 200


def test_provider_named_admicorp_still_cannot_export_individual_or_historical_data(harness):
    _, client, actor, headers = harness
    actor.username = 'ADMICORP'
    for suffix in ('detail', 'detail/export', 'export/weekly'):
        assert client.get('/api/marketing/sales-funnel/' + suffix, headers=headers).status_code == 403


def test_refresh_and_logout_remain_available(harness, monkeypatch):
    from app.routes import auth_routes
    app, client, actor, headers = harness
    app.config['AUTH_REFRESH_ENABLED'] = True
    monkeypatch.setattr(auth_routes, '_origin_allowed', lambda: True)
    monkeypatch.setattr(auth_routes, 'rotate_refresh', lambda cookie: (actor, 'synthetic-cookie', 12))
    revoked = []
    monkeypatch.setattr(auth_routes, 'revoke_refresh', lambda cookie: revoked.append(cookie))
    response = client.post('/api/auth/refresh', headers=headers)
    assert response.status_code == 200
    assert response.json['user']['rol'] == PROVEEDOR_FUNNEL_ORIGINAL
    assert client.post('/api/auth/logout', headers=headers).status_code == 200
    assert len(revoked) == 1
