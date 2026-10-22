"""QA-22C: el historial entrega los descriptores sin depender del catálogo Angular.

Pruebas sintéticas sin usar la BD de producción.
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import inventarios as routes


@pytest.fixture
def qa_historial(monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="inventory-history-qa22c-only")
    JWTManager(app)
    app.register_blueprint(routes.inventario_bp)

    monkeypatch.setattr(
        routes, "_resolve_inventory_read_sucursal_ids",
        lambda _requested: (None, None),
    )

    with app.app_context():
        token = create_access_token(identity="47")

    def ejecutar(categoria_catalogo):
        inv = SimpleNamespace(
            id=1827,
            nombre="2 tier dumbell rack",
            marca="JW SPORT",
            proveedor=None,
            categoria="Categoría heredada",
            categoria_inventario=categoria_catalogo,
            codigo_interno="07PLJW36",
            no_equipo=None,
        )
        detalle = SimpleNamespace(
            inventario_id=1827,
            cantidad=1,
            unidad_medida="Unidad",
            inventario=inv,
        )
        mov = SimpleNamespace(
            id=6,
            tipo_movimiento="entrada",
            fecha=datetime(2026, 9, 12, 16, 12),
            usuario_id=47,
            sucursal_id=99,
            observaciones="prueba",
            anulado=True,
            anulado_por_usuario_id=47,
            anulado_en_utc=datetime(2026, 10, 22, 22, 4),
            motivo_anulacion="QA-21: Anulación controlada del movimiento DEMO.",
        )
        query = Mock()
        query.order_by.return_value.all.return_value = [mov]
        movement_model = SimpleNamespace(query=query, fecha=Mock())
        monkeypatch.setattr(routes, "MovimientoInventario", movement_model)
        detalle_model = SimpleNamespace(query=Mock())
        detalle_model.query.filter_by.return_value.all.return_value = [detalle]
        monkeypatch.setattr(routes, "DetalleMovimiento", detalle_model)
        branch_model = SimpleNamespace(query=Mock())
        branch_model.query.get.return_value = SimpleNamespace(sucursal="ULTRA DEMO")
        monkeypatch.setattr(routes, "Sucursal", branch_model)
        user_model = SimpleNamespace(query=Mock())
        user_model.query.get.return_value = SimpleNamespace(username="ADMICORP")
        monkeypatch.setattr(routes, "UserORM", user_model)

        response = app.test_client().get(
            "/api/inventario/movimientos",
            headers={"Authorization": f"Bearer {token}"},
        )
        return response, detalle_model

    return ejecutar


def test_historial_entrega_identidad_completa_de_articulo_anulado(qa_historial):
    respuesta, detalle_model = qa_historial(
        SimpleNamespace(nombre="Peso Libre")
    )
    assert respuesta.status_code == 200
    resultado = respuesta.get_json()
    assert len(resultado) == 1
    mov = resultado[0]
    assert mov["id"] == 6
    assert mov["anulado"] is True
    assert mov["usuario_anulacion"] == "ADMICORP"
    assert mov["motivo_anulacion"].startswith("QA-21")
    assert len(mov["inventarios"]) == 1
    articulo = mov["inventarios"][0]
    assert articulo == {
        "inventario_id": 1827,
        "cantidad": 1,
        "unidad_medida": "Unidad",
        "codigo_interno": "07PLJW36",
        "no_equipo": None,
        "nombre": "2 tier dumbell rack",
        "marca": "JW SPORT",
        "proveedor": None,
        "categoria": "Peso Libre",
    }
    detalle_model.query.filter_by.assert_called_once_with(movimiento_id=6)


def test_historial_usa_categoria_legado_si_no_hay_catalogo(qa_historial):
    respuesta, _ = qa_historial(None)
    assert respuesta.status_code == 200
    articulo = respuesta.get_json()[0]["inventarios"][0]
    assert articulo["nombre"] == "2 tier dumbell rack"
    assert articulo["categoria"] == "Categoría heredada"
