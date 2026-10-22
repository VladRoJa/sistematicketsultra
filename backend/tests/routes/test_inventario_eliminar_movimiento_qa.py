"""QA-21: anular movimientos conserva historial, revierte stock una sola vez.

Pruebas sintéticas: no utilizan PostgreSQL ni borran datos reales.
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask, jsonify
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import inventarios as routes


@pytest.fixture
def qa_anular(monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="inventory-qa21-only")
    JWTManager(app)
    app.register_blueprint(routes.inventario_bp)

    monkeypatch.setattr(routes, "_get_current_user_id_required", lambda: (91, None))
    monkeypatch.setattr(routes, "_require_inventory_movement_write", lambda _: None)

    with app.app_context():
        token = create_access_token(identity="91")

    def ejecutar(
        tipo, cantidades, existencias, *, movimiento_presente=True, anulado=False,
        motivo="Corrección documentada en el registro",
        autorizacion=False,
    ):
        detalles = [
            SimpleNamespace(inventario_id=inv_id, cantidad=cantidad)
            for inv_id, cantidad in cantidades
        ]
        mov = SimpleNamespace(
            id=88, sucursal_id=1, tipo_movimiento=tipo,
            detalles=detalles, anulado=anulado,
            anulado_por_usuario_id=None, anulado_en_utc=None,
            motivo_anulacion=None,
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
            inv_id: SimpleNamespace(stock=value)
            for inv_id, value in existencias.items()
        }
        stock_query = Mock()
        stock_cursors = []

        def consultar_existencias(**kwargs):
            assert kwargs["sucursal_id"] == 1
            cursor = Mock()
            cursor.with_for_update.return_value.first.return_value = stocks.get(
                kwargs["inventario_id"]
            )
            stock_cursors.append(cursor)
            return cursor

        stock_query.filter_by.side_effect = consultar_existencias
        monkeypatch.setattr(
            routes, "InventarioSucursal",
            SimpleNamespace(query=stock_query),
        )

        if autorizacion:
            monkeypatch.setattr(
                routes, "_require_inventory_movement_write",
                lambda _: (jsonify({"detail": "Sucursal no autorizada"}), 403),
            )
        else:
            monkeypatch.setattr(routes, "_require_inventory_movement_write", lambda _: None)

        session = Mock()
        monkeypatch.setattr(routes, "db", SimpleNamespace(session=session))
        cliente = app.test_client()

        def enviar(motivo_enviado=motivo):
            return cliente.post(
                "/api/inventario/movimientos/88/anular",
                json={"motivo": motivo_enviado},
                headers={"Authorization": f"Bearer {token}"},
            )

        def borrar_legacy():
            return cliente.delete(
                "/api/inventario/movimientos/88",
                headers={"Authorization": f"Bearer {token}"},
            )

        return SimpleNamespace(
            enviar=enviar, borrar_legacy=borrar_legacy, session=session,
            stocks=stocks, movimiento=mov, query=movimiento_query,
            stock_cursors=stock_cursors, detalles=detalles,
        )

    return ejecutar


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
def test_anulacion_imposible_409_sin_cambiar_stock_ni_historial(
    qa_anular, tipo, cantidades, existencias
):
    ctx = qa_anular(tipo, cantidades, existencias)
    respuesta = ctx.enviar()
    assert respuesta.status_code == 409
    assert {k: fila.stock for k, fila in ctx.stocks.items()} == existencias
    assert ctx.movimiento.anulado is False
    assert ctx.movimiento.motivo_anulacion is None
    ctx.session.delete.assert_not_called()
    ctx.session.commit.assert_not_called()
    ctx.session.rollback.assert_called_once()


@pytest.mark.parametrize(
    "tipo,cantidades,existencias,esperado",
    [
        ("entrada", [(5, 3)], {5: 8}, {5: 5}),
        ("salida", [(5, 3)], {5: 8}, {5: 11}),
        ("entrada", [(5, 2), (5, 4)], {5: 10}, {5: 4}),
        ("entrada", [(5, 1), (7, 2)], {5: 4, 7: 5}, {5: 3, 7: 3}),
    ],
)
def test_anulacion_valida_restaura_stock_y_preserva_detalles(
    qa_anular, tipo, cantidades, existencias, esperado
):
    ctx = qa_anular(tipo, cantidades, existencias)
    respuesta = ctx.enviar()
    assert respuesta.status_code == 200
    assert respuesta.get_json()["anulado"] is True
    assert {k: fila.stock for k, fila in ctx.stocks.items()} == esperado
    assert ctx.movimiento.anulado is True
    assert ctx.movimiento.anulado_por_usuario_id == 91
    assert ctx.movimiento.motivo_anulacion == "Corrección documentada en el registro"
    assert ctx.movimiento.anulado_en_utc.tzinfo is not None
    assert ctx.movimiento.detalles is ctx.detalles
    assert ctx.movimiento.detalles == ctx.detalles
    ctx.session.delete.assert_not_called()
    ctx.session.commit.assert_called_once()
    ctx.session.rollback.assert_not_called()
    ctx.query.filter_by.return_value.with_for_update.assert_called_once()
    for cursor in ctx.stock_cursors:
        cursor.with_for_update.assert_called_once()


def test_una_segunda_anulacion_no_revierte_stock_por_segunda_vez(qa_anular):
    ctx = qa_anular("entrada", [(5, 2)], {5: 3})
    primera = ctx.enviar()
    assert primera.status_code == 200
    assert ctx.stocks[5].stock == 1
    segunda = ctx.enviar()
    assert segunda.status_code == 409
    assert ctx.stocks[5].stock == 1
    ctx.session.commit.assert_called_once()
    ctx.session.delete.assert_not_called()


@pytest.mark.parametrize("motivo", ["", "  ", "muy corto", "x" * 1001, None, 123])
def test_motivo_obligatorio_y_acotado_no_toca_base(qa_anular, motivo):
    ctx = qa_anular("entrada", [(5, 1)], {5: 3})
    respuesta = ctx.enviar(motivo)
    assert respuesta.status_code == 400
    assert ctx.stocks[5].stock == 3
    ctx.query.filter_by.assert_not_called()
    ctx.session.commit.assert_not_called()


def test_movimiento_inexistente_404(qa_anular):
    ctx = qa_anular("entrada", [], {}, movimiento_presente=False)
    assert ctx.enviar().status_code == 404
    ctx.session.commit.assert_not_called()


@pytest.mark.parametrize("tipo,detalles", [("entrada", []), ("ajuste", [(5, 2)])])
def test_movimiento_malformado_409(qa_anular, tipo, detalles):
    ctx = qa_anular(tipo, detalles, {5: 10})
    assert ctx.enviar().status_code == 409
    ctx.session.commit.assert_not_called()


def test_anulacion_con_sucursal_no_autorizada_403(qa_anular):
    ctx = qa_anular("salida", [(5, 1)], {5: 2}, autorizacion=True)
    assert ctx.enviar().status_code == 403
    assert ctx.stocks[5].stock == 2
    ctx.session.commit.assert_not_called()
    ctx.session.rollback.assert_called_once()


def test_delete_legacy_405_nunca_borra_registros(qa_anular):
    ctx = qa_anular("entrada", [(5, 1)], {5: 2})
    resp = ctx.borrar_legacy()
    assert resp.status_code == 405
    assert "borrado definitivo" in resp.get_json()["error"]
    ctx.query.filter_by.assert_not_called()
    ctx.session.delete.assert_not_called()
    ctx.session.commit.assert_not_called()
