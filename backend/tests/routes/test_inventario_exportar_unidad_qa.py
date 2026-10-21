"""QA-03: exportar inventario con el atributo ORM unidad_medida."""

from datetime import date
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token
from openpyxl import load_workbook

from app.routes import reportes


def test_exportar_inventario_excel_usa_unidad_medida():
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="inventario-qa03-synthetic")
    JWTManager(app)
    app.register_blueprint(reportes.reportes_bp)

    producto = SimpleNamespace(
        id=17,
        tipo="producto",
        nombre="Producto QA",
        descripcion="Sintético",
        marca="Marca",
        proveedor="Proveedor",
        categoria="Consumibles",
        unidad_medida="pieza",
        codigo_interno="QA-17",
        no_equipo=None,
        gasto_sem=0,
        gasto_mes=0,
        pedido_mes=0,
        semana_pedido=None,
        fecha_inventario=date(2026, 10, 21),
    )
    with app.app_context():
        token = create_access_token(identity="1")

    with patch.object(reportes, "_require_inventory_report_admin", return_value=None), \
         patch.object(
             reportes,
             "_analytical_inventory_general_query",
             return_value=Mock(all=Mock(return_value=[producto])),
         ):
        response = app.test_client().get(
            "/api/reportes/exportar-inventario?sucursal_id=1",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    sheet = load_workbook(BytesIO(response.data), read_only=True).active
    assert sheet["H1"].value == "Unidad"
    assert sheet["H2"].value == "pieza"
