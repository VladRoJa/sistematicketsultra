"""QA-10E: GET existencias incluye el código interno real sin alterar stock."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import inventarios as routes


def _cliente_qa():
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="qa10e-synthetic")
    JWTManager(app)
    app.register_blueprint(routes.inventario_bp)
    with app.app_context():
        token = create_access_token(identity="91")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def test_existencias_incluye_codigo_interno_real_y_mantiene_stock():
    client, headers = _cliente_qa()

    stock = SimpleNamespace(inventario_id=27, sucursal_id=1, stock=3)
    articulo = SimpleNamespace(
        id=27,
        nombre="Mouse",
        codigo_interno="VDR-033-RECMOU",
        marca=None,
        proveedor=None,
        categoria="Equipo recepcion",
        tipo="Dispositivos",
        unidad_medida="Unidad",
    )
    sucursal = SimpleNamespace(sucursal="Villas del rey")

    stock_query = Mock()
    stock_query.filter.return_value = stock_query
    stock_query.all.return_value = [stock]
    master_query = Mock()
    master_query.get.return_value = articulo
    sucursal_query = Mock()
    sucursal_query.get.return_value = sucursal

    with patch.object(routes, "_resolve_inventory_read_sucursal_ids", return_value=([1], None)), \
         patch.object(routes, "InventarioSucursal", SimpleNamespace(
             query=stock_query, sucursal_id=SimpleNamespace(in_=lambda ids: ids)
         )), \
         patch.object(routes, "InventarioGeneral", SimpleNamespace(query=master_query)), \
         patch.object(routes, "Sucursal", SimpleNamespace(query=sucursal_query)):
        response = client.get("/api/inventario/existencias", headers=headers)

    assert response.status_code == 200
    assert response.get_json() == [{
        "inventario_id": 27,
        "nombre": "Mouse",
        "codigo_interno": "VDR-033-RECMOU",
        "categoria": "Equipo recepcion",
        "tipo": "Dispositivos",
        "marca": None,
        "proveedor": None,
        "unidad_medida": "Unidad",
        "sucursal_id": 1,
        "sucursal_nombre": "Villas del rey",
        "stock": 3,
        "descripcion_larga": "Mouse - Equipo recepcion - ID:27",
    }]
    assert stock.stock == 3
    stock_query.filter.assert_called_once_with([1])


def test_existencias_sin_articulo_maestro_entrega_codigo_nulo():
    client, headers = _cliente_qa()
    stock = SimpleNamespace(inventario_id=999, sucursal_id=1, stock=0)

    stocks = Mock()
    stocks.all.return_value = [stock]
    masters = Mock()
    masters.get.return_value = None
    sucursales = Mock()
    sucursales.get.return_value = SimpleNamespace(sucursal="Villas del rey")

    with patch.object(routes, "_resolve_inventory_read_sucursal_ids", return_value=(None, None)), \
         patch.object(routes, "InventarioSucursal", SimpleNamespace(query=stocks)), \
         patch.object(routes, "InventarioGeneral", SimpleNamespace(query=masters)), \
         patch.object(routes, "Sucursal", SimpleNamespace(query=sucursales)):
        response = client.get("/api/inventario/existencias", headers=headers)

    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 1
    assert data[0]["codigo_interno"] is None
    assert data[0]["stock"] == 0
