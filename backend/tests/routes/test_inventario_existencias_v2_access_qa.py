"""Inventarios V2: aislamiento de lectura por rol/sucursal sin alterar V1.

QA sintético con JWT y modelos simulados; no requiere PostgreSQL.
El endpoint V1 conserva intencionalmente su semántica legacy.
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import inventarios as routes


def _client():
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="inventarios-v2-gate-qa")
    JWTManager(app)
    app.register_blueprint(routes.inventario_bp)
    with app.app_context():
        token = create_access_token(identity="501")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def _user(role, *, primary=9, branches=None):
    return SimpleNamespace(
        id=501, rol=role, sucursal_id=primary,
        sucursales_ids=list(branches or []),
    )


def _fake_inventory(stocks):
    query = Mock()
    query.filter.return_value = query
    query.all.return_value = [
        SimpleNamespace(inventario_id=200 + i, sucursal_id=branch, stock=1)
        for i, branch in enumerate(stocks)
    ]
    master = Mock()
    master.query.get.return_value = None
    branches = Mock()
    branches.query.get.side_effect = lambda branch: SimpleNamespace(
        sucursal=f"Sucursal {branch}"
    )
    inventory = SimpleNamespace(
        query=query,
        sucursal_id=SimpleNamespace(in_=lambda ids: ids),
    )
    return query, inventory, master, branches


@pytest.mark.parametrize("role", [
    "GERENTE", "GERENTE_REGIONAL", "COORDINADOR_MANTENIMIENTO",
    "COMPRAS", "LECTOR_GLOBAL", "RECEPCIONISTA", "USUARIO",
])
def test_v2_deniega_roles_no_liberados_aun_con_sucursal_valida(role):
    client, headers = _client()
    with patch.object(routes, "_get_current_inventory_user", return_value=_user(role)):
        response = client.get("/api/inventario/v2/existencias?sucursal_id=9", headers=headers)
    assert response.status_code == 403
    assert response.get_json()["error"] == "Forbidden"


def test_v2_requiere_jwt_y_usuario_real():
    client, headers = _client()
    assert client.get("/api/inventario/v2/existencias").status_code == 401
    with patch.object(routes, "_get_current_inventory_user", return_value=None):
        response = client.get("/api/inventario/v2/existencias", headers=headers)
    assert response.status_code == 401


@pytest.mark.parametrize("raw", ["abc", "0", "-1", "2.3", ""])
def test_v2_rechaza_sucursal_invalida_sin_ampliar_a_global(raw):
    client, headers = _client()
    with patch.object(routes, "_get_current_inventory_user", return_value=_user("ADMINISTRADOR")):
        response = client.get(
            f"/api/inventario/v2/existencias?sucursal_id={raw}", headers=headers
        )
    assert response.status_code == 400


@pytest.mark.parametrize("role", [
    "ADMIN", "ADMINISTRADOR", "SUPER_ADMIN",
    "MANTENIMIENTO", "SISTEMAS", "TECNICO",
])
def test_v2_roles_globales_respetan_filtro_sql(role):
    client, headers = _client()
    query, inventory, master, branches = _fake_inventory([25])
    with patch.object(routes, "_get_current_inventory_user", return_value=_user(role)), \\
         patch.object(routes, "InventarioSucursal", inventory), \\
         patch.object(routes, "InventarioGeneral", master), \\
         patch.object(routes, "Sucursal", branches):
        response = client.get(
            "/api/inventario/v2/existencias?sucursal_id=25", headers=headers
        )
    assert response.status_code == 200
    assert response.get_json()[0]["sucursal_id"] == 25
    query.filter.assert_called_once_with([25])


def test_v2_sr_mantenimiento_solo_sucursales_m2m_no_hereda_primaria():
    client, headers = _client()
    user = _user("SR_MANTENIMIENTO", primary=9, branches=[7, 8])
    query, inventory, master, branches = _fake_inventory([8])
    with patch.object(routes, "_get_current_inventory_user", return_value=user), \\
         patch.object(routes, "InventarioSucursal", inventory), \\
         patch.object(routes, "InventarioGeneral", master), \\
         patch.object(routes, "Sucursal", branches):
        denied = client.get(
            "/api/inventario/v2/existencias?sucursal_id=9", headers=headers
        )
        allowed = client.get(
            "/api/inventario/v2/existencias?sucursal_id=8", headers=headers
        )
    assert denied.status_code == 403
    assert allowed.status_code == 200
    query.filter.assert_called_once_with([8])


def test_v2_aux_mantenimiento_solo_sucursal_primaria():
    client, headers = _client()
    user = _user("AUX_MANTENIMIENTO", primary=7, branches=[7, 8])
    query, inventory, master, branches = _fake_inventory([7])
    with patch.object(routes, "_get_current_inventory_user", return_value=user), \\
         patch.object(routes, "InventarioSucursal", inventory), \\
         patch.object(routes, "InventarioGeneral", master), \\
         patch.object(routes, "Sucursal", branches):
        denied = client.get(
            "/api/inventario/v2/existencias?sucursal_id=8", headers=headers
        )
        allowed = client.get(
            "/api/inventario/v2/existencias?sucursal_id=7", headers=headers
        )
    assert denied.status_code == 403
    assert allowed.status_code == 200
    query.filter.assert_called_once_with([7])


def test_v1_legacy_permanece_sin_cambios_para_consumidores_existentes():
    # No se afirma que la API V1 bloquee GERENTE: es deuda contractual
    # distinta y cambiarla ahora podria romper clientes ya existentes.
    client, headers = _client()
    query, inventory, master, branches = _fake_inventory([9])
    with patch.object(routes, "_get_current_inventory_user", return_value=_user("GERENTE")), \\
         patch.object(routes, "InventarioSucursal", inventory), \\
         patch.object(routes, "InventarioGeneral", master), \\
         patch.object(routes, "Sucursal", branches):
        response = client.get("/api/inventario/existencias?sucursal_id=9", headers=headers)
    assert response.status_code == 200
    query.filter.assert_called_once_with([9])
