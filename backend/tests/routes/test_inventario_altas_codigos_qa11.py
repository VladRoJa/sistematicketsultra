"""QA-11F: altas de aparatos con códigos distintos y rechazo de colisiones."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token
from sqlalchemy import column

from app.routes import inventarios as routes


@pytest.fixture
def entorno():
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="qa11-seriales-test")
    JWTManager(app)
    app.register_blueprint(routes.inventario_bp)
    with app.app_context():
        token = create_access_token(identity="91")

    sesiones = Mock()
    consulta = Mock()
    articulos = []

    class ArticuloSintetico:
        codigo_interno = column("codigo_interno")
        query = consulta

        def __init__(self, **campos):
            self.__dict__.update(campos)
            self.id = 9000 + len(articulos)
            articulos.append(self)

    consulta.filter.return_value.first.return_value = None
    consulta.filter_by.return_value.first.return_value = None

    with patch.object(routes, "_require_inventory_global_write", return_value=None), \
         patch.object(routes, "InventarioGeneral", ArticuloSintetico), \
         patch.object(routes, "db", SimpleNamespace(session=sesiones)):
        yield app.test_client(), token, articulos, consulta, sesiones


def _alta(client, token, codigo, tipo="Aparatos", nombre="Caminadora", marca="Fitness"):
    return client.post(
        "/api/inventario/",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "nombre": nombre,
            "marca": marca,
            "categoria": "Cardio",
            "tipo": tipo,
            "unidad_medida": "Unidad",
            "codigo_interno": codigo,
        },
    )


def test_caminadoras_con_mismo_nombre_marca_y_codigo_distinto_se_crean(entorno):
    client, token, articulos, consulta, sesiones = entorno
    resp = _alta(client, token, " 11ccjw22 ")

    assert resp.status_code == 200
    assert resp.get_json()["inventario_id"] == 9000
    assert len(articulos) == 1
    assert articulos[0].codigo_interno == "11CCJW22"
    assert articulos[0].nombre == "Caminadora"
    assert sesiones.commit.call_count == 1
    consulta.filter.assert_called_once()
    consulta.filter_by.assert_not_called()

    condicion = str(consulta.filter.call_args.args[0]).lower()
    assert "upper" in condicion and "trim" in condicion


def test_codigo_ya_utilizado_se_rechaza_con_409_y_sin_escrituras(entorno):
    client, token, articulos, consulta, sesiones = entorno
    consulta.filter.return_value.first.return_value = SimpleNamespace(
        id=100, codigo_interno="11CCJW21"
    )

    resp = _alta(client, token, "11ccjw21")
    assert resp.status_code == 409
    assert "11CCJW21" in resp.get_json()["error"]
    assert not articulos
    sesiones.add.assert_not_called()
    sesiones.commit.assert_not_called()


@pytest.mark.parametrize("tipo", ["Aparatos", "Sistemas", "Dispositivos"])
def test_tipos_fisicos_exigen_codigo_interno(entorno, tipo):
    client, token, articulos, consulta, sesiones = entorno
    resp = _alta(client, token, "", tipo=tipo)
    assert resp.status_code == 400
    assert "obligatorio" in resp.get_json()["error"].lower()
    consulta.filter.assert_not_called()
    assert not articulos
    sesiones.commit.assert_not_called()


def test_producto_generico_sin_codigo_conserva_regla_nombre_marca(entorno):
    client, token, articulos, consulta, sesiones = entorno
    consulta.filter_by.return_value.first.return_value = SimpleNamespace(id=13)

    resp = _alta(
        client, token, codigo="", tipo="Producto",
        nombre="Guantes", marca="Fitness",
    )
    assert resp.status_code == 409
    assert "nombre y marca" in resp.get_json()["error"]
    consulta.filter_by.assert_called_once_with(
        nombre="Guantes", marca="Fitness"
    )
    assert not articulos
    sesiones.commit.assert_not_called()


def test_alta_no_crea_stock_ni_movimiento(entorno):
    client, token, articulos, consulta, sesiones = entorno
    resp = _alta(client, token, "11CCJW23")
    assert resp.status_code == 200
    assert articulos[0].codigo_interno == "11CCJW23"
    assert sesiones.add.call_count == 1
    assert sesiones.commit.call_count == 1
    # Solo se creó InventarioGeneral, jamás InventarioSucursal ni Movimiento.
    assert isinstance(sesiones.add.call_args.args[0], type(articulos[0]))
