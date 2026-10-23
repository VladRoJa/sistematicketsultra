"""QA-24: endpoint agregado del dashboard con SQLite sintético.

Se usan tablas mínimas y datos de prueba; nunca conecta a la BD real.
"""
from datetime import date
from types import SimpleNamespace

import pytest
from flask import Flask, jsonify
from flask_jwt_extended import JWTManager, create_access_token, get_jwt_identity
from sqlalchemy import text

from app.extensions import db
from app.routes import inventarios as routes


HOY = date(2026, 10, 22)


@pytest.fixture
def client_qa24(monkeypatch):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="dashboard-inventory-qa24-synthetic",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    JWTManager(app)
    app.register_blueprint(routes.inventario_bp)

    # La autorización real se verifica antes de consultar los agregados.
    # Aquí simulamos su contrato: administrador global y usuario limitado a sede 2.
    def alcance(sucursal_solicitada):
        if get_jwt_identity() == "admin":
            return ([sucursal_solicitada] if sucursal_solicitada else None), None
        if sucursal_solicitada is not None and sucursal_solicitada != 2:
            return None, (jsonify({"error": "Forbidden"}), 403)
        return [2], None

    monkeypatch.setattr(routes, "_resolve_inventory_read_sucursal_ids", alcance)
    from app.services import inventario_dashboard_service as service
    monkeypatch.setattr(service, "datetime", SimpleNamespace(
        now=lambda _tz: SimpleNamespace(date=lambda: HOY),
        combine=__import__("datetime").datetime.combine,
    ))

    with app.app_context():
        # Las consultas usan únicamente estas columnas. No creamos modelos ni
        # migramos el esquema completo de Suite Ultra durante la prueba.
        for ddl in [
            "CREATE TABLE sucursales (sucursal_id INTEGER PRIMARY KEY, sucursal TEXT, is_demo BOOLEAN)",
            "CREATE TABLE inventario_sucursal (id INTEGER PRIMARY KEY, inventario_id INTEGER, sucursal_id INTEGER, stock INTEGER)",
            "CREATE TABLE inventario_general (id INTEGER PRIMARY KEY, categoria TEXT, categoria_inventario_id INTEGER)",
            "CREATE TABLE catalogo_categoria_inventario (id INTEGER PRIMARY KEY, nombre TEXT)",
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT)",
            """CREATE TABLE movimientos_inventario (
                id INTEGER PRIMARY KEY, fecha DATETIME, tipo_movimiento TEXT,
                anulado BOOLEAN, anulado_en_utc DATETIME,
                usuario_id INTEGER, sucursal_id INTEGER
            )""",
        ]:
            db.session.execute(text(ddl))

        for sql in [
            """INSERT INTO sucursales VALUES
                (1, 'Santa Fe', 0), (2, 'Metepec', 0),
                (3, 'ULTRA DEMO', 1), (4, 'Sucursal sin inventario', 0)""",
            """INSERT INTO catalogo_categoria_inventario VALUES
                (7, 'Cardio'), (8, 'Peso Libre')""",
            """INSERT INTO inventario_general VALUES
                (101, 'Cardio antiguo', 7),
                (102, 'Peso Libre', 8),
                (103, 'Peso Libre', 8),
                (104, NULL, NULL),
                (999, 'Solo demo', NULL)""",
            """INSERT INTO inventario_sucursal VALUES
                (1,101,1,1),(2,102,1,0),(3,103,1,3),
                (4,101,2,2),(5,104,2,-1),(6,999,3,1)""",
            "INSERT INTO users VALUES (47,'ADMICORP')",
            """INSERT INTO movimientos_inventario VALUES
                (1,'2026-10-21 13:00:00','entrada',0,NULL,47,1),
                (2,'2026-10-20 13:00:00','salida',0,NULL,47,2),
                (3,'2026-09-12 13:00:00','entrada',1,'2026-10-22 22:00:00',47,3),
                (4,'2026-09-12 13:00:00','entrada',1,'2026-10-22 22:00:00',47,1),
                (5,'2026-09-01 13:00:00','entrada',0,NULL,47,1),
                (6,'2026-10-21 15:00:00','salida',1,'2026-10-22 22:00:00',47,1)""",
        ]:
            db.session.execute(text(sql))
        db.session.commit()
        admin_token = create_access_token(identity="admin")
        scoped_token = create_access_token(identity="scoped")

    def get(path="/api/inventario/reportes/resumen", scope="admin"):
        headers = {
            "Authorization": f"Bearer {admin_token if scope == 'admin' else scoped_token}"
        }
        return app.test_client().get(path, headers=headers)

    yield SimpleNamespace(app=app, get=get)
    with app.app_context():
        db.session.remove()


def test_global_descarta_demo_y_cuenta_referencias_no_unidades(client_qa24):
    response = client_qa24.get()
    assert response.status_code == 200
    data = response.get_json()

    assert data["alcance"] == {"sucursal_id": None, "excluye_demo": True}
    assert data["periodo"] == {
        "dias": 30,
        "desde": "2026-09-23",
        "hasta": "2026-10-22",
        "zona_horaria": "America/Tijuana",
    }
    assert data["indicadores"] == {
        "referencias_con_stock": 3,
        "referencias_sin_stock": 2,
        "entradas_vigentes_periodo": 1,
        "salidas_vigentes_periodo": 1,
        "anulaciones_periodo": 2,
    }
    assert data["por_sucursal"] == [
        {"sucursal_id": 2, "sucursal": "Metepec", "referencias_con_stock": 1, "referencias_sin_stock": 1},
        {"sucursal_id": 1, "sucursal": "Santa Fe", "referencias_con_stock": 2, "referencias_sin_stock": 1},
        {"sucursal_id": 4, "sucursal": "Sucursal sin inventario", "referencias_con_stock": 0, "referencias_sin_stock": 0},
    ]
    assert data["por_categoria"] == [
        {"categoria": "Cardio", "referencias_con_stock": 2},
        {"categoria": "Peso Libre", "referencias_con_stock": 1},
    ]
    assert [r["movimiento_id"] for r in data["movimientos_recientes"]] == [6, 1, 2]
    assert data["movimientos_recientes"][0]["estado"] == "anulado"
    assert all(r["sucursal"] != "ULTRA DEMO" for r in data["movimientos_recientes"])


def test_demo_solo_si_sucursal_explicita(client_qa24):
    result = client_qa24.get(
        "/api/inventario/reportes/resumen?sucursal_id=3"
    )
    assert result.status_code == 200
    data = result.get_json()
    assert data["alcance"] == {"sucursal_id": 3, "excluye_demo": False}
    assert data["indicadores"]["referencias_con_stock"] == 1
    assert data["indicadores"]["anulaciones_periodo"] == 1
    assert data["indicadores"]["entradas_vigentes_periodo"] == 0
    assert len(data["por_sucursal"]) == 1
    assert data["por_categoria"][0]["categoria"] == "Solo demo"


def test_scope_lector_solo_sucursal_asignada(client_qa24):
    data = client_qa24.get(scope="scoped").get_json()
    assert [r["sucursal_id"] for r in data["por_sucursal"]] == [2]
    assert data["indicadores"]["referencias_con_stock"] == 1
    assert data["indicadores"]["referencias_sin_stock"] == 1
    assert data["indicadores"]["entradas_vigentes_periodo"] == 0
    assert data["indicadores"]["salidas_vigentes_periodo"] == 1
    assert data["indicadores"]["anulaciones_periodo"] == 0
    assert all(r["sucursal_id"] == 2 for r in data["movimientos_recientes"])
    assert client_qa24.get(
        "/api/inventario/reportes/resumen?sucursal_id=1", "scoped"
    ).status_code == 403
    assert client_qa24.get(
        "/api/inventario/reportes/resumen?sucursal_id=3", "scoped"
    ).status_code == 403


@pytest.mark.parametrize("valor", ["abc", "-1", "0", "1.5", ""])
def test_id_invalido_no_acepta_acceso_global_implicito(client_qa24, valor):
    assert client_qa24.get(
        "/api/inventario/reportes/resumen?sucursal_id=" + valor
    ).status_code == 400


@pytest.mark.parametrize("valor", ["0", "8", "365", "-30", "abc", ""])
def test_periodo_no_valido_rechazado(client_qa24, valor):
    assert client_qa24.get(
        "/api/inventario/reportes/resumen?periodo_dias=" + valor
    ).status_code == 400


def test_periodo_siete_dias_no_mueve_stock_y_separa_anulaciones(client_qa24):
    data = client_qa24.get(
        "/api/inventario/reportes/resumen?periodo_dias=7"
    ).get_json()
    assert data["periodo"]["desde"] == "2026-10-16"
    assert data["indicadores"]["referencias_con_stock"] == 3
    assert data["indicadores"]["entradas_vigentes_periodo"] == 1
    assert data["indicadores"]["salidas_vigentes_periodo"] == 1
    # Movimientos creados en septiembre pero anulados en octubre sí cuentan.
    assert data["indicadores"]["anulaciones_periodo"] == 2


def test_sucursal_inexistente_y_sin_jwt(client_qa24):
    assert client_qa24.get(
        "/api/inventario/reportes/resumen?sucursal_id=9999"
    ).status_code == 404
    assert client_qa24.app.test_client().get(
        "/api/inventario/reportes/resumen"
    ).status_code == 401
