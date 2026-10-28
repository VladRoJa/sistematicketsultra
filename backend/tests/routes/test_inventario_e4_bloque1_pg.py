"""E4 Bloque 1: compatibilidad v0.1, evidencia histórica y no mutación V1."""
import csv
from io import BytesIO, StringIO
from uuid import uuid4
import importlib.util
import os
import secrets
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token
from openpyxl import Workbook, load_workbook

from app.extensions import db
from app.routes.inventario_levantamientos_routes import inventario_levantamientos_bp
from app.services.inventario_levantamiento_excel_parser import (
    parse_historical_csv, parse_xlsx_v01,
)

BASE = Path(__file__).resolve().parents[2]
MIGRATION = BASE / "migrations/versions/v2e4b1102826_inventario_levantamiento_recepcion.py"


def original_csv():
    """Encabezados del CSV histórico real de distribución (28/10/2026)."""
    return (
        "sucursal_id,sucursal,inventario_id,codigo_interno,categoria,aparato,marca,stock_sistema_qa\n"
        "7,Pabellon rosarito,501,07CA01,Cardio,Caminadora,Star Trac,3\n"
        "7,Pabellon rosarito,502,07EL01,Cardio,Eliptica,Precor,1\n"
        "7,Pabellon rosarito,503,07RE00,Cardio,Remo,Concept2,0\n"
        "8,Mision ensenada,601,08CA01,Cardio,Caminadora,Star Trac,1\n"
    ).encode()


def workbook(branch=7, second="", first="SI", code="07EL01", duplicate=False,
             initial=False, found=True):
    """Reconstruye las posiciones A5/C6, encabezado fila 7 de la plantilla oficial v0.1."""
    wb = Workbook()
    ctl = wb.active
    ctl.title = "CONTROL"
    for r, name, val in (
        (5, "Sucursal", "Pabellon rosarito"),
        (6, "ID sucursal", branch),
        (7, "Gerente responsable", "Responsable QA"),
        (8, "Fecha del recorrido", "2026-10-28"),
        (9, "Folio / corte E4", "PENDIENTE - GENERADOR E4"),
        (10, "Versión de entrega", "v0.1 · formato"),
    ):
        ctl.cell(r, 1, name)
        ctl.cell(r, 3, val)
    a = wb.create_sheet("APARATOS")
    a.append(["APARATOS · VERIFICACIÓN FÍSICA POR CÓDIGO"])
    for r in range(2, 7):
        a.cell(r, 1, "Instrucciones" if r == 2 else None)
    a.append(["ID oficial", "CÓDIGO INTERNO", "CATEGORÍA", "APARATO",
              "MARCA", "¿ESTÁ? SI / NO", "OBSERVACIONES / UBICACIÓN"])
    if not initial:
        a.append([501, "07CA01", "Cardio", "Caminadora", "Star Trac", first, "Zona cardio"])
        a.append([502, code, "Cardio", "Eliptica", "Precor", second, ""])
        if duplicate:
            a.append([501, "07CA01", "Cardio", "Caminadora", "Star Trac", "NO", ""])
    else:
        a.append([None, "SIN CÓDIGO", "Cardio", "Caminadora", "Star Trac", "SI", "Alta inicial sin ID"])
    h = wb.create_sheet("HALLAZGOS")
    for r in range(1, 7):
        h.cell(r, 1, "HALLAZGOS · APARATOS NO INCLUIDOS" if r == 1 else None)
    h.append(["CÓDIGO EN ETIQUETA", "NOMBRE / APARATO", "CATEGORÍA",
              "MARCA", "UBICACIÓN / ZONA", "DESCRIPCIÓN DEL HALLAZGO"])
    if found:
        h.append(["SIN CÓDIGO", "Banco no registrado", "Peso Libre",
                  "Desconocida", "Zona pesas", "Encontrado sin referencia oficial"])
    target = BytesIO()
    wb.save(target)
    return target.getvalue()


def test_e4_cadena_alembic_no_abre_rama_paralela():
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(BASE / "migrations"))
    assert ScriptDirectory.from_config(cfg).get_heads() == ["v2e4b1102826"]


def test_plantilla_v01_parser_y_sin_revisar_por_id():
    rows, excluded = parse_historical_csv(original_csv(), 7)
    assert len(rows) == 2 and len(excluded) == 1
    report = parse_xlsx_v01(workbook(), 7, rows, "VERIFICACION")
    assert report["resultado"] == "INCOMPLETE"
    assert report["resumen"]["si"] == 1
    assert report["resumen"]["no"] == 0
    assert report["resumen"]["sin_revisar"] == 1
    assert report["resumen"]["pendientes"][0]["inventario_id"] == 502
    assert report["resumen"]["pendientes"][0]["fila_excel"] == 9
    assert report["resumen"]["hallazgos"] == 1
    assert report["control"]["sucursal_id"] == "7"


def test_plantilla_rechaza_codigo_diferente_duplicados_y_sucursal_falsa():
    expected, _ = parse_historical_csv(original_csv(), 7)
    report = parse_xlsx_v01(workbook(branch=8, code="OTRO", duplicate=True), 7, expected, "VERIFICACION")
    assert report["resultado"] == "INVALID"
    codes = {x["codigo"] for x in report["diagnosticos"]}
    assert {"SUCURSAL_NO_COINCIDE", "CODIGO_DIFIERE_DEL_CORTE", "ID_DUPLICADO_EN_EXCEL"}.issubset(codes)
    assert report["resumen"]["sin_revisar"] == 2


def test_inicial_no_equivale_a_conciliado_sin_referencias():
    report = parse_xlsx_v01(workbook(branch=8, initial=True), 8, [], "INICIAL")
    assert report["resultado"] == "INCOMPLETE"
    assert report["resumen"]["requiere_revision_inicial"] is True
    assert report["resumen"]["hallazgos"] == 1
    assert report["resumen"]["provisionales_aparatos"] == 1
    assert report["filas"][0]["inventario_id_declarado"] is None


@pytest.fixture()
def api(monkeypatch, tmp_path):
    url = os.getenv("INVENTARIO_E2_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("PostgreSQL efímero requerido para la API E4")
    schema = "inv_e4_" + secrets.token_hex(5)
    admin = sa.create_engine(url, future=True)
    with admin.begin() as con:
        con.exec_driver_sql(f"CREATE SCHEMA {schema}")
    monkeypatch.setenv("E4_UPLOAD_DIR", str(tmp_path / "e4-private"))
    app = Flask(__name__)
    app.config.update(
        TESTING=True, JWT_SECRET_KEY="e4-qa-isolated-only",
        SQLALCHEMY_DATABASE_URI=url,
        SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"options": f"-csearch_path={schema}"}},
    )
    db.init_app(app)
    JWTManager(app)
    app.register_blueprint(inventario_levantamientos_bp, url_prefix="/api/inventario/levantamientos")
    spec = importlib.util.spec_from_file_location("inv_e4_migration", MIGRATION)
    migration = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(migration)
    try:
        with app.app_context():
            with db.engine.begin() as con:
                con.exec_driver_sql("CREATE TABLE sucursales (sucursal_id INTEGER PRIMARY KEY)")
                con.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY, rol VARCHAR(50))")
                con.exec_driver_sql("CREATE TABLE inventario_general (id INTEGER PRIMARY KEY, codigo_interno VARCHAR(100), tipo VARCHAR(20), nombre VARCHAR(255), marca VARCHAR(100), categoria VARCHAR(100))")
                con.exec_driver_sql("CREATE TABLE inventario_sucursal (inventario_id INTEGER, sucursal_id INTEGER, stock INTEGER, PRIMARY KEY(inventario_id,sucursal_id))")
                con.exec_driver_sql("CREATE TABLE movimientos_inventario (id INTEGER PRIMARY KEY)")
                con.exec_driver_sql("CREATE TABLE inventario_correccion_solicitudes (id INTEGER PRIMARY KEY)")
                monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(con)))
                migration.upgrade()
                con.exec_driver_sql("INSERT INTO sucursales VALUES (7),(8)")
                con.exec_driver_sql("INSERT INTO users VALUES (1,'ADMINISTRADOR'),(2,'GERENTE'),(3,'GERENTE_REGIONAL')")
                con.exec_driver_sql("INSERT INTO inventario_general (id,codigo_interno,tipo,nombre,marca) VALUES (501,'07CA01','APARATOS','Caminadora','Star Trac'),(502,'07EL01','APARATOS','Eliptica','Precor'),(503,'07RE00','APARATOS','Remo','Concept2')")
                con.exec_driver_sql("INSERT INTO inventario_sucursal VALUES (501,7,3),(502,7,1),(503,7,0)")
            token = {uid: {"Authorization": "Bearer " + create_access_token(identity=str(uid))}
                     for uid in (1,2,3)}
            yield app.test_client(), token, app
            db.session.remove()
            db.engine.dispose()
    finally:
        with admin.begin() as con:
            con.exec_driver_sql(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        admin.dispose()


def _snapshot(app):
    with app.app_context():
        return {
            "stock": db.session.execute(sa.text("SELECT inventario_id,stock FROM inventario_sucursal ORDER BY inventario_id")).all(),
            "master": db.session.execute(sa.text("SELECT id,codigo_interno FROM inventario_general ORDER BY id")).all(),
            "mov": db.session.execute(sa.text("SELECT count(*) FROM movimientos_inventario")).scalar(),
            "e2": db.session.execute(sa.text("SELECT count(*) FROM inventario_correccion_solicitudes")).scalar(),
        }


def test_api_historico_versionado_idempotente_sin_cambios_oficiales(api):
    client, tokens, app = api
    url = "/api/inventario/levantamientos"
    assert client.post(url, headers=tokens[2], data={"sucursal_id":"7"}).status_code == 403
    assert client.post(url, headers=tokens[3], data={"sucursal_id":"7"}).status_code == 403
    assert client.post(url, data={"sucursal_id":"7"}).status_code == 401
    original = _snapshot(app)
    basekey = str(uuid4())
    created = client.post(url, headers=tokens[1], data={
        "sucursal_id": "7", "origen_corte": "CSV_HISTORICO", "cycle_key": basekey,
        "fecha_corte_local": "2026-10-28", "responsable": "Gerencia sucursal",
        "baseline_csv": (BytesIO(original_csv()), "Inventarios para revisar.csv"),
    })
    assert created.status_code == 201, created.get_json()
    lev = created.get_json()["levantamiento"]["id"]
    assert created.get_json()["levantamiento"]["baseline_resumen"]["excluidas_stock_cero"] == 1
    first_bytes = workbook()
    endpoint = f"{url}/{lev}/importaciones"
    key = str(uuid4())
    first = client.post(endpoint, headers=tokens[1], data={
        "idempotency_key": key, "file": (BytesIO(first_bytes), "pabellon.xlsx"),
    })
    assert first.status_code == 201, first.get_json()
    first_data = first.get_json()["importacion"]
    assert first_data["resultado"] == "INCOMPLETE"
    assert first_data["resumen"]["pendientes"][0]["inventario_id"] == 502
    replay = client.post(endpoint, headers=tokens[1], data={
        "idempotency_key": str(uuid4()), "file": (BytesIO(first_bytes), "retry.xlsx"),
    })
    assert replay.status_code == 200
    assert replay.get_json()["replayed"] is True
    assert replay.get_json()["importacion"]["id"] == first_data["id"]
    badkey = client.post(endpoint, headers=tokens[1], data={
        "idempotency_key": key, "file": (BytesIO(workbook(second="NO")), "modified.xlsx"),
    })
    assert badkey.status_code == 409
    second = client.post(endpoint, headers=tokens[1], data={
        "idempotency_key": str(uuid4()), "file": (BytesIO(workbook(second="NO")), "final.xlsx"),
    })
    assert second.status_code == 201, second.get_json()
    assert second.get_json()["importacion"]["version"] == 2
    assert second.get_json()["importacion"]["resultado"] == "VALIDATED"
    # Archivo estructuralmente incompatible: archivar, diagnosticar y NO promover.
    malformed = load_workbook(BytesIO(workbook(second="NO")))
    del malformed["HALLAZGOS"]
    damaged = BytesIO()
    malformed.save(damaged)
    third = client.post(endpoint, headers=tokens[1], data={
        "idempotency_key": str(uuid4()), "file": (BytesIO(damaged.getvalue()), "faltan_hojas.xlsx"),
    })
    assert third.status_code == 201, third.get_json()
    assert third.get_json()["importacion"]["resultado"] == "INVALID"
    assert third.get_json()["importacion"]["diagnosticos"][0]["codigo"] == "ESTRUCTURA_EXCEL"
    listed = client.get(f"{url}/{lev}", headers=tokens[1])
    assert listed.status_code == 200
    assert len(listed.get_json()["versiones"]) == 3
    assert listed.get_json()["levantamiento"]["ultima_importacion_id"] == second.get_json()["importacion"]["id"]
    assert _snapshot(app) == original
    assert client.get(f"{url}/{lev}", headers=tokens[2]).status_code == 403


def test_inicial_restringido_y_evidencia_persistente(api):
    client, tokens, app = api
    root = "/api/inventario/levantamientos"
    created = client.post(root, headers=tokens[1], data={
        "sucursal_id":"8","origen_corte":"INICIAL","cycle_key":str(uuid4())})
    assert created.status_code == 201, created.get_json()
    lev = created.get_json()["levantamiento"]["id"]
    result = client.post(f"{root}/{lev}/importaciones", headers=tokens[1], data={
        "idempotency_key":str(uuid4()),"file":(BytesIO(workbook(branch=8,initial=True)),"sin_catalogo.xlsx")})
    assert result.status_code == 201, result.get_json()
    assert result.get_json()["importacion"]["resultado"] == "INCOMPLETE"
    assert result.get_json()["importacion"]["resumen"]["requiere_revision_inicial"]
    assert _snapshot(app)["mov"] == 0
