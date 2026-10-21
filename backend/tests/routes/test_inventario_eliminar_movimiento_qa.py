"""QA-05 sintético: borrar movimientos nunca desajusta stock ni toca DB real."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import inventarios as routes


@pytest.fixture
def qa_delete(monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="inventory-delete-qa-synthetic")
    JWTManager(app)
    app.register_blueprint(routes.inventario_bp)
    monkeypatch.setattr(routes, "_require_inventory_movement_write", lambda _sid: None)

    with app.app_context():
        token = create_access_token(identity="91")

    def execute(tipo, cantidades, stock_values, *, movimiento_presente=True):
        detalles = [
            SimpleNamespace(inventario_id=inventario_id, cantidad=cantidad)
            for inventario_id, cantidad in cantidades
        ]
        mov = SimpleNamespace(
            sucursal_id=1, tipo_movimiento=tipo, detalles=detalles
        )
        movimiento_query = Mock()
        movimiento_query.filter_by.return_value.with_for_update.return_value.first.return_value = (
            mov if movimiento_presente else None
        )
        monkeypatch.setattr(
            routes, "MovimientoInventario",
            SimpleNamespace(query=movimiento_query),
        )

        stocks = {
            inventario_id: SimpleNamespace(stock=value)
            for inventario_id, value in stock_values.items()
        }
        stock_query = Mock()
        stock_cursors = []

        def get_stock_query(**kwargs):
            assert kwargs["sucursal_id"] == 1
            cursor = Mock()
            cursor.with_for_update.return_value.first.return_value = stocks.get(
                kwargs["inventario_id"]
            )
            stock_cursors.append(cursor)
            return cursor

        stock_query.filter_by.side_effect = get_stock_query
        monkeypatch.setattr(
            routes, "InventarioSucursal", SimpleNamespace(query=stock_query)
        )

        session = Mock()
        monkeypatch.setattr(routes, "db", SimpleNamespace(session=session))
        response = app.test_client().delete(
            "/api/inventario/movimientos/88",
            headers={"Authorization": f"Bearer {token}"},
        )
        movimiento_query.filter_by.assert_called_once_with(id=88)
        movimiento_query.filter_by.return_value.with_for_update.assert_called_once()
        for cursor in stock_cursors:
            cursor.with_for_update.assert_called_once()
        return response, session, stocks, mov

    return execute


@pytest.mark.parametrize(
    "tipo,cantidades,existencias",
    [
        ("entrada", [(5, 10)], {5: 3}),
        ("entrada", [(5, 2), (7, 10)], {5: 8, 7: 9}),
        ("entrada", [(5, 4), (5, 4)], {5: 7}),
        ("entrada", [(5, 1)], {}),
        ("salida", [(5, 1)], {}),
        ("entrada", [(5, -2)], {5: 8}),
        ("entrada", [(5, 3)], {5: -1}),
        ("salida", [(5, 3)], {5: -1}),
    ],
)
def test_reversion_invalida_es_409_sin_escrituras(
    qa_delete, tipo, cantidades, existencias
):
    response, session, stocks, _ = qa_delete(tipo, cantidades, existencias)
    assert response.status_code == 409
    assert {k: row.stock for k, row in stocks.items()} == existencias
    session.delete.assert_not_called()
    session.commit.assert_not_called()
    session.rollback.assert_called_once()


@pytest.mark.parametrize(
    "tipo,cantidades,existencias,esperado",
    [
        ("entrada", [(5, 3)], {5: 8}, {5: 5}),
        ("salida", [(5, 3)], {5: 8}, {5: 11}),
        ("entrada", [(5, 2), (5, 4)], {5: 10}, {5: 4}),
        ("entrada", [(5, 1), (7, 2)], {5: 4, 7: 5}, {5: 3, 7: 3}),
    ],
)
def test_reversion_valida_modifica_y_confirma_una_vez(
    qa_delete, tipo, cantidades, existencias, esperado
):
    response, session, stocks, movement = qa_delete(
        tipo, cantidades, existencias
    )
    assert response.status_code == 200
    assert {k: row.stock for k, row in stocks.items()} == esperado
    assert session.delete.call_count == len(cantidades) + 1
    session.delete.assert_any_call(movement)
    session.commit.assert_called_once()
    session.rollback.assert_not_called()


def test_movimiento_inexistente_es_404(qa_delete):
    response, session, _, _ = qa_delete(
        "entrada", [], {}, movimiento_presente=False
    )
    assert response.status_code == 404
    session.delete.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.parametrize("tipo,detalles", [("entrada", []), ("ajuste", [(5, 2)])])
def test_movimiento_sin_detalles_o_tipo_invalido_no_se_elimina(
    qa_delete, tipo, detalles
):
    response, session, _, _ = qa_delete(tipo, detalles, {5: 10})
    assert response.status_code == 409
    session.delete.assert_not_called()
    session.commit.assert_not_called()
