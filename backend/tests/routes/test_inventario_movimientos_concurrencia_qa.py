"""QA-08: consistencia al registrar movimientos, sin conexión a PostgreSQL."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import inventarios as routes


@pytest.fixture
def movimiento_qa(monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="qa08-synthetic")
    JWTManager(app)
    app.register_blueprint(routes.inventario_bp)
    monkeypatch.setattr(routes, "_get_current_user_id_required", lambda: (91, None))
    monkeypatch.setattr(routes, "_require_inventory_movement_write", lambda _id: None)

    with app.app_context():
        token = create_access_token(identity="91")
    client = app.test_client()

    def ejecutar(tipo, lineas, stocks, *, inventarios_existentes=None, fail_flush=False):
        if inventarios_existentes is None:
            inventarios_existentes = {item["inventario_id"] for item in lineas}

        inventario_query = Mock()
        stock_query = Mock()
        bloqueos = []
        stock_existente = {
            inventario_id: SimpleNamespace(stock=stock)
            for inventario_id, stock in stocks.items()
        }
        nuevas_filas = []

        def consultar_inventario(**params):
            inventario_id = params["id"]
            consulta = Mock()
            consulta.with_for_update.return_value.first.return_value = (
                SimpleNamespace(
                    id=inventario_id,
                    unidad_medida="pieza",
                    unidad_compra=None,
                    factor_compra=1,
                )
                if inventario_id in inventarios_existentes else None
            )
            bloqueos.append(("articulo", inventario_id))
            return consulta

        def consultar_stock(**params):
            assert params["sucursal_id"] == 1
            inventario_id = params["inventario_id"]
            consulta = Mock()
            consulta.with_for_update.return_value.first.return_value = (
                stock_existente.get(inventario_id)
            )
            bloqueos.append(("stock", inventario_id))
            return consulta

        inventario_query.filter_by.side_effect = consultar_inventario
        stock_query.filter_by.side_effect = consultar_stock

        class SucursalSintetica:
            query = stock_query

            def __init__(self, **campos):
                for key, value in campos.items():
                    setattr(self, key, value)
                nuevas_filas.append(self)

        class MovimientoSintetico:
            def __init__(self, **campos):
                self.id = 500
                for key, value in campos.items():
                    setattr(self, key, value)

        class DetalleSintetico:
            def __init__(self, **campos):
                for key, value in campos.items():
                    setattr(self, key, value)

        monkeypatch.setattr(
            routes, "InventarioGeneral", SimpleNamespace(query=inventario_query)
        )
        monkeypatch.setattr(routes, "InventarioSucursal", SucursalSintetica)
        monkeypatch.setattr(routes, "MovimientoInventario", MovimientoSintetico)
        monkeypatch.setattr(routes, "DetalleMovimiento", DetalleSintetico)

        session = Mock()
        if fail_flush:
            session.flush.side_effect = RuntimeError("flush sintético")
        monkeypatch.setattr(routes, "db", SimpleNamespace(session=session))
        monkeypatch.setattr(
            routes, "manejar_error",
            lambda _exception, _context: ({"error": "sintético"}, 500),
        )
        response = client.post(
            "/api/inventario/movimientos",
            json={
                "tipo_movimiento": tipo,
                "sucursal_id": 1,
                "inventarios": lineas,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        return response, session, stock_existente, nuevas_filas, bloqueos

    return ejecutar


def linea(inventario_id, cantidad):
    return {"inventario_id": inventario_id, "cantidad": cantidad}


def test_salida_valida_bloquea_stock_y_confirma_una_vez(movimiento_qa):
    response, session, stocks, _, bloqueos = movimiento_qa(
        "salida", [linea(5, 7)], {5: 10},
    )
    assert response.status_code == 200
    assert stocks[5].stock == 3
    assert bloqueos == [("articulo", 5), ("stock", 5)]
    assert session.add.call_count == 2  # Movimiento + detalle
    session.flush.assert_called_once()
    session.commit.assert_called_once()
    session.rollback.assert_not_called()


def test_segunda_salida_no_puede_usar_el_stock_ya_consumido(movimiento_qa):
    response, session, stocks, _, bloqueos = movimiento_qa(
        "salida", [linea(5, 7)], {5: 3},
    )
    assert response.status_code == 409
    assert stocks[5].stock == 3
    assert bloqueos == [("articulo", 5), ("stock", 5)]
    session.add.assert_not_called()
    session.flush.assert_not_called()
    session.commit.assert_not_called()
    session.rollback.assert_called_once()


def test_dos_lineas_del_mismo_articulo_se_suman_antes_de_validar(movimiento_qa):
    response, session, stocks, _, bloqueos = movimiento_qa(
        "salida", [linea(5, 7), linea(5, 7)], {5: 10},
    )
    assert response.status_code == 409
    assert stocks[5].stock == 10
    assert bloqueos == [("articulo", 5), ("stock", 5)]
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_lote_con_segundo_articulo_sin_stock_es_atomico(movimiento_qa):
    response, session, stocks, _, bloqueos = movimiento_qa(
        "salida", [linea(9, 7), linea(5, 3)], {5: 8, 9: 2},
    )
    assert response.status_code == 409
    assert stocks[5].stock == 8
    assert stocks[9].stock == 2
    assert bloqueos == [
        ("articulo", 5), ("articulo", 9), ("stock", 5), ("stock", 9),
    ]
    session.add.assert_not_called()
    session.commit.assert_not_called()
    session.rollback.assert_called_once()


def test_salida_sin_fila_de_existencias_se_rechaza(movimiento_qa):
    response, session, _, nuevas, bloqueos = movimiento_qa(
        "salida", [linea(5, 1)], {},
    )
    assert response.status_code == 409
    assert nuevas == []
    assert bloqueos == [("articulo", 5), ("stock", 5)]
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_entrada_inicial_bloquea_articulo_y_crea_una_fila(movimiento_qa):
    response, session, _, nuevas, bloqueos = movimiento_qa(
        "entrada", [linea(5, 7), linea(5, 3)], {},
    )
    assert response.status_code == 200
    assert len(nuevas) == 1
    assert nuevas[0].stock == 10
    assert bloqueos == [("articulo", 5), ("stock", 5)]
    assert session.add.call_count == 4  # movimiento, dos detalles y fila stock
    session.commit.assert_called_once()
    session.rollback.assert_not_called()


def test_error_en_flush_hace_rollback(movimiento_qa):
    response, session, stocks, _, _ = movimiento_qa(
        "salida", [linea(5, 4)], {5: 10}, fail_flush=True,
    )
    assert response.status_code == 500
    assert stocks[5].stock == 10
    session.commit.assert_not_called()
    session.rollback.assert_called_once()


def test_inventario_inexistente_no_crea_movimiento(movimiento_qa):
    response, session, _, _, _ = movimiento_qa(
        "entrada", [linea(5, 1)], {}, inventarios_existentes=set(),
    )
    assert response.status_code == 400
    session.add.assert_not_called()
    session.commit.assert_not_called()
    session.rollback.assert_called_once()
