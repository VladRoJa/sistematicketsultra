"""QA-06 sintético: proteger artículos asociados a sucursales, tickets y PM.

Sin conexión a PostgreSQL ni escritura o borrado de registros reales.
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import inventarios as routes


@pytest.fixture
def qa_eliminar_articulo(monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="inventario-qa06-synthetic")
    JWTManager(app)
    app.register_blueprint(routes.inventario_bp)
    monkeypatch.setattr(routes, "_require_inventory_global_write", lambda: None)

    with app.app_context():
        token = create_access_token(identity="91")

    def ejecutar(dependencia=None, *, articulo_existe=True, stock=0):
        articulo = SimpleNamespace(id=901) if articulo_existe else None
        inventario = SimpleNamespace(query=Mock())
        inventario.query.filter_by.return_value.with_for_update.return_value.first.return_value = articulo

        modelos = {
            "movimiento": SimpleNamespace(query=Mock()),
            "sucursal": SimpleNamespace(query=Mock()),
            "ticket": SimpleNamespace(query=Mock()),
            "pm_bitacora": SimpleNamespace(query=Mock()),
            "pm_config": SimpleNamespace(query=Mock()),
        }
        for clave, modelo in modelos.items():
            modelo.query.filter_by.return_value.first.return_value = (
                SimpleNamespace(stock=stock) if clave == dependencia else None
            )

        monkeypatch.setattr(routes, "InventarioGeneral", inventario)
        monkeypatch.setattr(routes, "DetalleMovimiento", modelos["movimiento"])
        monkeypatch.setattr(routes, "InventarioSucursal", modelos["sucursal"])
        monkeypatch.setattr(routes, "Ticket", modelos["ticket"])
        monkeypatch.setattr(routes, "PmBitacoraORM", modelos["pm_bitacora"])
        monkeypatch.setattr(routes, "PmPreventivoConfigORM", modelos["pm_config"])

        session = Mock()
        monkeypatch.setattr(routes, "db", SimpleNamespace(session=session))
        respuesta = app.test_client().delete(
            "/api/inventario/901",
            headers={"Authorization": f"Bearer {token}"},
        )
        inventario.query.filter_by.assert_called_once_with(id=901)
        inventario.query.filter_by.return_value.with_for_update.assert_called_once()
        return respuesta, session, articulo, modelos

    return ejecutar


@pytest.mark.parametrize(
    "dependencia,stock,fragmento",
    [
        ("movimiento", 0, "movimientos"),
        ("sucursal", 10, "sucursales"),
        ("sucursal", 0, "sucursales"),
        ("ticket", 0, "tickets"),
        ("pm_bitacora", 0, "bitácoras"),
        ("pm_config", 0, "programación"),
    ],
)
def test_articulo_referenciado_no_se_elimina(
    qa_eliminar_articulo, dependencia, stock, fragmento
):
    respuesta, session, _, modelos = qa_eliminar_articulo(
        dependencia, stock=stock
    )

    assert respuesta.status_code == 409
    assert fragmento in respuesta.get_json()["error"]
    session.delete.assert_not_called()
    session.commit.assert_not_called()
    session.rollback.assert_called_once()

    modelo = modelos[dependencia]
    filtro = {"aparato_id": 901} if dependencia == "ticket" else {"inventario_id": 901}
    modelo.query.filter_by.assert_called_once_with(**filtro)


def test_articulo_sin_referencias_se_elimina_una_vez(qa_eliminar_articulo):
    respuesta, session, articulo, modelos = qa_eliminar_articulo()

    assert respuesta.status_code == 200
    session.delete.assert_called_once_with(articulo)
    session.commit.assert_called_once()
    session.rollback.assert_not_called()
    for modelo in modelos.values():
        modelo.query.filter_by.assert_called_once()


def test_articulo_inexistente_es_404_sin_borrado(qa_eliminar_articulo):
    respuesta, session, _, modelos = qa_eliminar_articulo(articulo_existe=False)

    assert respuesta.status_code == 404
    session.delete.assert_not_called()
    session.commit.assert_not_called()
    for modelo in modelos.values():
        modelo.query.filter_by.assert_not_called()
