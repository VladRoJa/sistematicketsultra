"""QA-09: sucursales reales en inventario maestro y límites de acceso."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import inventarios as routes


class ColumnaSintetica:
    def __init__(self, nombre):
        self.nombre = nombre

    def in_(self, valores):
        return (self.nombre, frozenset(valores))

    def __eq__(self, otro):
        return ("join", self.nombre, getattr(otro, "nombre", otro))

    def asc(self):
        return ("asc", self.nombre)


class ConsultaSintetica:
    def __init__(self, asignaciones):
        self.asignaciones = asignaciones
        self.filtros = []

    def join(self, *_args):
        return self

    def filter(self, condicion):
        self.filtros.append(condicion)
        return self

    def all(self):
        asignaciones = self.asignaciones
        for campo, permitidos in self.filtros:
            if campo == "inventario_id":
                asignaciones = [row for row in asignaciones if row[0] in permitidos]
            elif campo == "sucursal_id":
                asignaciones = [row for row in asignaciones if row[1] in permitidos]
        return [(inventario_id, nombre) for inventario_id, _, nombre in asignaciones]


@pytest.fixture
def sucursales_falsas(monkeypatch):
    asignaciones = [
        (27, 1, "Villas del rey"),
        (27, 2, "Independencia"),
        (27, 1, "Villas del rey"),
        (36, 3, "Villa verde mexicali"),
    ]
    consulta = ConsultaSintetica(asignaciones)
    session = Mock()
    session.query.return_value = consulta
    monkeypatch.setattr(routes, "db", SimpleNamespace(session=session))
    monkeypatch.setattr(
        routes, "InventarioSucursal",
        SimpleNamespace(
            inventario_id=ColumnaSintetica("inventario_id"),
            sucursal_id=ColumnaSintetica("sucursal_id"),
        ),
    )
    monkeypatch.setattr(
        routes, "Sucursal",
        SimpleNamespace(
            sucursal_id=ColumnaSintetica("sucursal_id_ref"),
            sucursal=ColumnaSintetica("nombre_sucursal"),
        ),
    )
    return consulta, session


def test_catalogo_global_agrega_sucursales_reales_sin_duplicar(sucursales_falsas):
    consulta, session = sucursales_falsas
    resultado = routes._sucursales_visibles_por_inventario([27, 36, 999, 27])
    assert resultado == {
        27: "Independencia, Villas del rey",
        36: "Villa verde mexicali",
    }
    assert len(consulta.filtros) == 1
    session.query.assert_called_once()


def test_rol_acotado_no_obtiene_sucursales_ajenas(sucursales_falsas):
    consulta, session = sucursales_falsas
    resultado = routes._sucursales_visibles_por_inventario([27, 36], [1])
    assert resultado == {27: "Villas del rey"}
    assert consulta.filtros[1] == ("sucursal_id", frozenset({1}))
    session.query.assert_called_once()


def test_sin_articulos_o_sin_permiso_no_consulta_base(sucursales_falsas):
    _, session = sucursales_falsas
    assert routes._sucursales_visibles_por_inventario([]) == {}
    assert routes._sucursales_visibles_por_inventario([27], []) == {}
    session.query.assert_not_called()


@pytest.mark.parametrize("scope,esperado", [(None, None), ([1], [1])])
def test_endpoint_solicita_solo_sucursales_del_scope(scope, esperado, monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="qa09-maestro-synthetic")
    JWTManager(app)
    app.register_blueprint(routes.inventario_bp)

    inv = SimpleNamespace(
        id=27, tipo="dispositivo", nombre="Mouse", descripcion="Mouse",
        marca="", proveedor="", categoria="Equipo", subcategoria="",
        unidad_medida="Unidad", unidad_compra=None, factor_compra=1,
        codigo_interno="VDR-033-RECMOU", no_equipo="", gasto_sem=None,
        gasto_mes=None, pedido_mes=None, semana_pedido=None,
        fecha_inventario=None, grupo_muscular="N/A",
        categoria_inventario_id=None,
    )

    nombre_col = ColumnaSintetica("nombre")
    maestro_query = Mock()
    maestro_query.order_by.return_value.all.return_value = [inv]
    maestro_model = SimpleNamespace(
        id=ColumnaSintetica("id"),
        nombre=nombre_col,
        query=maestro_query,
    )
    inventario_sucursal = SimpleNamespace(
        inventario_id=ColumnaSintetica("inventario_id"),
        sucursal_id=ColumnaSintetica("sucursal_id"),
        stock=ColumnaSintetica("stock"),
    )

    consulta_join = Mock()
    consulta_join.join.return_value = consulta_join
    consulta_join.filter.return_value = consulta_join
    consulta_join.order_by.return_value.all.return_value = [(inv, 1)]

    session = Mock()
    session.query.return_value = consulta_join

    def leer_sucursales(ids, permitido=None):
        assert set(ids) == {27}
        assert permitido == esperado
        return {27: "Villas del rey"}

    with patch.object(routes, "_resolve_inventory_read_sucursal_ids", return_value=(scope, None)), \
         patch.object(routes, "InventarioGeneral", maestro_model), \
         patch.object(routes, "InventarioSucursal", inventario_sucursal), \
         patch.object(routes, "db", SimpleNamespace(session=session)), \
         patch.object(routes, "_sucursales_visibles_por_inventario", side_effect=leer_sucursales):
        with app.app_context():
            token = create_access_token(identity="91")
        respuesta = app.test_client().get(
            "/api/inventario/",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert respuesta.status_code == 200
    assert respuesta.get_json()[0]["sucursales"] == "Villas del rey"
    if scope is None:
        session.query.assert_not_called()
    else:
        session.query.assert_called_once()
