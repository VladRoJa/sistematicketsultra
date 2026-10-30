"""E4 Bloque 1: compatibilidad v0.1/v0.2, evidencia histórica y no mutación V1."""
import csv
from hashlib import sha256
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
from zipfile import ZipFile
import re

from app.extensions import db
from app.routes.inventario_levantamientos_routes import inventario_levantamientos_bp
from app.services.inventario_levantamiento_excel_parser import (
    parse_historical_csv, parse_xlsx_v01,
)

BASE = Path(__file__).resolve().parents[2]
MIGRATION = BASE / "migrations/versions/v2e4b1102826_inventario_levantamiento_recepcion.py"
MIGRATION_B2 = BASE / "migrations/versions/v2e4b2103026_levantamiento_conciliacion.py"
MIGRATION_B3 = BASE / "migrations/versions/v2e4b3103026_revisiones_automaticas.py"


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
             initial=False, found=True, version="v0.1 · formato"):
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
        (10, "Versión de entrega", version),
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
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == ["v2e4b3103026"]
    assert script.get_revision("n26c10202626").down_revision == "v2e4b1102826"
    assert script.get_revision("v2e4b2103026").down_revision == "n26c10202626"
    assert script.get_revision("v2e4b3103026").down_revision == "v2e4b2103026"


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


def test_v02_real_distribuida_vacia_se_mantiene_pendiente_y_versiones_desconocidas_invalidas():
    # v0.2 es la etiqueta real del XLSX distribuido el 28/10/2026;
    # el fixture no contiene datos reales ni archivos de gerentes.
    expected, _ = parse_historical_csv(original_csv(), 7)
    received = parse_xlsx_v01(
        workbook(first="", second="", found=False,
                 version="v0.2 · base CSV 2026-10-28"),
        7, expected, "VERIFICACION",
    )
    assert received["resultado"] == "INCOMPLETE"
    assert received["control"]["version_formato"] == "v0.2 · base CSV 2026-10-28"
    assert received["resumen"]["referencias_esperadas"] == 2
    assert received["resumen"]["si"] == 0
    assert received["resumen"]["no"] == 0
    assert received["resumen"]["sin_revisar"] == 2
    assert not received["diagnosticos"]

    unsupported = parse_xlsx_v01(
        workbook(first="", second="", found=False,
                 version="v0.3 · formato no certificado"),
        7, expected, "VERIFICACION",
    )
    assert unsupported["resultado"] == "INVALID"
    assert any(d["codigo"] == "VERSION_FORMATO_NO_RECONOCIDA"
               for d in unsupported["diagnosticos"])


def test_xlsx_sin_dimensiones_como_el_distribuido_real():
    """Los libros distribuidos de E4 carecen de XML <dimension>: max_row=None."""
    original = workbook(
        first="", second="", found=False, version="v0.2 · base CSV 2026-10-28"
    )
    output = BytesIO()
    hojas = 0
    with ZipFile(BytesIO(original)) as z_in, ZipFile(output, "w") as z_out:
        for info in z_in.infolist():
            content = z_in.read(info.filename)
            if re.fullmatch(r"xl/worksheets/sheet[0-9]+\.xml", info.filename):
                content, n = re.subn(rb"<dimension\b[^>]*/>", b"", content, count=1)
                assert n == 1
                hojas += 1
            z_out.writestr(info, content)
    assert hojas == 3
    raw = output.getvalue()
    book = load_workbook(BytesIO(raw), read_only=True, data_only=False)
    try:
        assert all(book[sheet].max_row is None for sheet in ("CONTROL", "APARATOS", "HALLAZGOS"))
    finally:
        book.close()
    expected, _ = parse_historical_csv(original_csv(), 7)
    report = parse_xlsx_v01(raw, 7, expected, "VERIFICACION")
    assert report["resultado"] == "INCOMPLETE"
    assert report["resumen"]["sin_revisar"] == 2
    assert report["resumen"]["si"] == 0
    assert report["resumen"]["no"] == 0
    assert not report["diagnosticos"]


def test_plantilla_rechaza_codigo_diferente_duplicados_y_sucursal_falsa():
    expected, _ = parse_historical_csv(original_csv(), 7)
    report = parse_xlsx_v01(workbook(branch=8, code="OTRO", duplicate=True), 7, expected, "VERIFICACION")
    assert report["resultado"] == "INVALID"
    codes = {x["codigo"] for x in report["diagnosticos"]}
    assert {"SUCURSAL_NO_COINCIDE", "CODIGO_DIFIERE_DEL_CORTE", "ID_DUPLICADO_EN_EXCEL"}.issubset(codes)
    assert report["resumen"]["sin_revisar"] == 2


def test_hallazgo_no_puede_reciclar_codigo_de_aparato_oficial():
    refs, _ = parse_historical_csv(original_csv(), 7)
    book = load_workbook(BytesIO(workbook(second="SI", found=True)))
    book["HALLAZGOS"]["A8"] = "07CA01"
    raw = BytesIO()
    book.save(raw)
    resultado = parse_xlsx_v01(raw.getvalue(), 7, refs, "VERIFICACION")
    assert resultado["resultado"] == "INVALID"
    assert resultado["resumen"]["errores"] == 1
    assert any(d["codigo"] == "CODIGO_HALLAZGO_EN_CORTE"
               and d["inventario_ids_existentes"] == [501]
               for d in resultado["diagnosticos"])


def test_dos_hallazgos_no_pueden_compartir_codigo_fisico():
    refs, _ = parse_historical_csv(original_csv(), 7)
    libro = load_workbook(BytesIO(workbook(second="SI", found=True)))
    hallazgos = libro["HALLAZGOS"]
    hallazgos["A8"] = "07AD99"
    hallazgos.append(["07AD99", "Otro banco", "Peso libre",
                      "Sin marca", "Zona funcional", "Otra referencia física"])
    buf = BytesIO()
    libro.save(buf)
    reporte = parse_xlsx_v01(buf.getvalue(), 7, refs, "VERIFICACION")
    assert reporte["resultado"] == "INVALID"
    assert any(d["codigo"] == "ETIQUETA_NUEVA_DUPLICADA"
               for d in reporte["diagnosticos"])


def test_prefijo_sucursal_ajeno_es_aviso_no_mutacion_de_codigo():
    historical = original_csv().replace(b"07EL01", b"05EL01")
    refs, _ = parse_historical_csv(historical, 7)
    book = load_workbook(BytesIO(workbook(second="SI", found=False)))
    book["APARATOS"]["B9"] = "05EL01"
    raw = BytesIO()
    book.save(raw)
    resultado = parse_xlsx_v01(raw.getvalue(), 7, refs, "VERIFICACION")
    assert resultado["resultado"] == "VALIDATED"
    assert resultado["resumen"]["avisos"] == 1
    assert any(d["codigo"] == "PREFIJO_SUCURSAL_INCONSISTENTE"
               and d["inventario_id"] == 502 and d["prefijo_esperado"] == "07"
               for d in resultado["diagnosticos"])
    assert resultado["resumen"]["si"] == 2


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
    using_real_binary = bool(os.getenv("E4_REAL_XLSX_PATH") or os.getenv("E4_REAL_BASELINE_CSV_PATH") or os.getenv("E4_REAL_SAN_LUIS_XLSX_PATH"))
    if not url:
        if using_real_binary:
            pytest.fail("Gate real requiere INVENTARIO_E2_TEST_POSTGRES_URL aislado")
        pytest.skip("PostgreSQL efímero requerido para la API E4")
    if using_real_binary:
        parsed_url = sa.engine.make_url(url)
        if (parsed_url.host not in {"127.0.0.1", "localhost", "::1"}
                or not re.fullmatch(r"inventario_e4_(?:ci|qa)(?:_[a-z0-9_]+)?", parsed_url.database or "")):
            pytest.fail("Gate real SOLO permite PostgreSQL local y BD inventario_e4_qa/ci")
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
                con.exec_driver_sql("CREATE TABLE sucursales (sucursal_id INTEGER PRIMARY KEY, is_demo BOOLEAN NOT NULL DEFAULT FALSE)")
                con.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY, rol VARCHAR(50))")
                con.exec_driver_sql("CREATE TABLE inventario_general (id INTEGER PRIMARY KEY, codigo_interno VARCHAR(100), tipo VARCHAR(20), nombre VARCHAR(255), marca VARCHAR(100), categoria VARCHAR(100))")
                con.exec_driver_sql("CREATE TABLE inventario_sucursal (inventario_id INTEGER, sucursal_id INTEGER, stock INTEGER, PRIMARY KEY(inventario_id,sucursal_id))")
                con.exec_driver_sql("""
                    CREATE TABLE movimientos_inventario (
                      id INTEGER PRIMARY KEY, tipo_movimiento VARCHAR(16),
                      sucursal_id INTEGER, anulado BOOLEAN DEFAULT FALSE
                    )
                """)
                con.exec_driver_sql("""
                    CREATE TABLE detalle_movimiento (
                      id INTEGER PRIMARY KEY, movimiento_id INTEGER,
                      inventario_id INTEGER, cantidad INTEGER
                    )
                """)
                con.exec_driver_sql("""
                    CREATE TABLE inventario_correccion_solicitudes (
                      id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, tipo VARCHAR(40), estado VARCHAR(24),
                      sucursal_id INTEGER, inventario_id INTEGER, campo VARCHAR(64),
                      valor_original JSONB, valor_propuesto JSONB,
                      hallazgo_provisional JSONB, baseline_canonico JSONB,
                      fecha_observacion_local DATE, motivo TEXT,
                      evidencia_descriptiva TEXT, creado_por_usuario_id INTEGER,
                      creado_en_utc TIMESTAMPTZ, idempotency_key UUID,
                      request_fingerprint VARCHAR(64)
                    )
                """)
                monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(con)))
                migration.upgrade()
                spec_b2 = importlib.util.spec_from_file_location("inv_e4_b2_migration", MIGRATION_B2)
                migration_b2 = importlib.util.module_from_spec(spec_b2)
                assert spec_b2 and spec_b2.loader
                spec_b2.loader.exec_module(migration_b2)
                monkeypatch.setattr(migration_b2, "op", Operations(MigrationContext.configure(con)))
                migration_b2.upgrade()
                spec_b3 = importlib.util.spec_from_file_location("inv_e4_b3_migration", MIGRATION_B3)
                migration_b3 = importlib.util.module_from_spec(spec_b3)
                assert spec_b3 and spec_b3.loader
                spec_b3.loader.exec_module(migration_b3)
                monkeypatch.setattr(migration_b3, "op", Operations(MigrationContext.configure(con)))
                migration_b3.upgrade()
                # Los ID 7 y 8 son DEMO solo dentro del esquema PostgreSQL efímero.
                # No reflejan la semántica de esas sucursales reales en producción.
                con.exec_driver_sql("INSERT INTO sucursales(sucursal_id,is_demo) VALUES (6,false),(7,true),(8,true)")
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
    # Bandeja corporativa: acceso, paginación estricta y filtros.
    assert client.get(url).status_code == 401
    assert client.get(url, headers=tokens[2]).status_code == 403
    assert client.get(url, headers=tokens[3]).status_code == 403
    assert client.get(url + "?per_page=101", headers=tokens[1]).status_code == 400
    assert client.get(url + "?page=0", headers=tokens[1]).status_code == 400
    assert client.get(url + "?sucursal_id=abc", headers=tokens[1]).status_code == 400
    empty = client.get(url, headers=tokens[1])
    assert empty.status_code == 200 and empty.get_json()["total"] == 0
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
    listing = client.get(url + "?sucursal_id=7", headers=tokens[1])
    assert listing.status_code == 200, listing.get_json()
    assert listing.get_json()["total"] == 1
    assert listing.get_json()["items"][0]["id"] == lev
    assert listing.get_json()["items"][0]["importacion_actual"] is None
    assert client.get(url + "?sucursal_id=8", headers=tokens[1]).get_json()["total"] == 0
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
    summary_list = client.get(url, headers=tokens[1]).get_json()["items"][0]
    assert summary_list["importacion_actual"]["resultado"] == "VALIDATED"
    assert (summary_list["importacion_actual"]["si"], summary_list["importacion_actual"]["no"],
            summary_list["importacion_actual"]["sin_revisar"]) == (1, 1, 0)
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


def test_recepcion_unica_resuelve_sucursal_y_corte_sin_ids_ni_csv_por_carga(api):
    client, tokens, app = api
    root = "/api/inventario/levantamientos"
    endpoint = root + "/recepciones"
    raw = workbook(first="SI", second="NO", found=False)
    assert client.post(endpoint, data={
        "idempotency_key": str(uuid4()),
        "file": (BytesIO(raw), "entrega.xlsx"),
    }).status_code == 401
    assert client.post(endpoint, headers=tokens[2], data={
        "idempotency_key": str(uuid4()),
        "file": (BytesIO(raw), "entrega.xlsx"),
    }).status_code == 403
    sin_corte = client.post(endpoint, headers=tokens[1], data={
        "idempotency_key": str(uuid4()),
        "file": (BytesIO(raw), "entrega.xlsx"),
    })
    assert sin_corte.status_code == 409
    assert sin_corte.get_json()["error"] == "CORTE_NO_REGISTRADO"

    created = client.post(root, headers=tokens[1], data={
        "sucursal_id": "7", "origen_corte": "CSV_HISTORICO",
        "cycle_key": str(uuid4()),
        "baseline_csv": (BytesIO(original_csv()), "distribucion.csv"),
    })
    assert created.status_code == 201, created.get_json()
    lev = created.get_json()["levantamiento"]["id"]
    before = _snapshot(app)
    first = client.post(endpoint, headers=tokens[1], data={
        "idempotency_key": str(uuid4()),
        "file": (BytesIO(raw), "devuelto.xlsx"),
    })
    assert first.status_code == 201, first.get_json()
    assert first.get_json()["levantamiento_id"] == lev
    assert first.get_json()["importacion"]["resumen"]["no"] == 1
    second = client.post(endpoint, headers=tokens[1], data={
        "idempotency_key": str(uuid4()),
        "file": (BytesIO(raw), "devuelto_otro_nombre.xlsx"),
    })
    assert second.status_code == 200 and second.get_json()["replayed"] is True
    assert second.get_json()["importacion"]["id"] == first.get_json()["importacion"]["id"]
    assert _snapshot(app) == before

    otro_ciclo = client.post(root, headers=tokens[1], data={
        "sucursal_id": "7", "origen_corte": "CSV_HISTORICO",
        "cycle_key": str(uuid4()),
        "baseline_csv": (BytesIO(original_csv()), "corte2.csv"),
    })
    assert otro_ciclo.status_code == 201
    ambiguo = client.post(endpoint, headers=tokens[1], data={
        "idempotency_key": str(uuid4()), "file": (BytesIO(workbook(first="NO")), "ambiguo.xlsx"),
    })
    assert ambiguo.status_code == 409
    assert ambiguo.get_json()["error"] == "CORTE_AMBIGUO"


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


def test_api_real_xlsx_http_aislado_con_historico_sin_mutaciones(api):
    """Gate opt-in: bytes EXACTOS del archivo distribuido, API real y PostgreSQL efímero.

    Requiere E4_REAL_XLSX_PATH y E4_REAL_BASELINE_CSV_PATH. Los originales
    permanecen fuera del repo, no se envían a CI, y solo se leen.
    """
    path_xlsx = os.getenv("E4_REAL_XLSX_PATH")
    path_csv = os.getenv("E4_REAL_BASELINE_CSV_PATH")
    if not path_xlsx and not path_csv:
        pytest.skip("Gate real no configurado: requiere rutas locales XLSX y CSV")
    assert path_xlsx and path_csv, "Se requieren ambos archivos históricos locales"
    xlsx = Path(path_xlsx).read_bytes()
    baseline = Path(path_csv).read_bytes()
    expected_sha = os.getenv(
        "E4_REAL_XLSX_SHA256",
        "c3f86c1f2a1aa6ede646451c81d5b35306757fec417dad7e45d89e17c4896dd3",
    )
    assert sha256(xlsx).hexdigest() == expected_sha, (
        "El XLSX no coincide con el original de Pabellón Rosarito 2026-10-28"
    )
    references, excluded = parse_historical_csv(baseline, 7)
    assert len(references) == 150, "El CSV no coincide con el corte distribuido de esta sucursal"
    assert len({r["inventario_id_original"] for r in references}) == len(references)

    client, tokens, app = api
    # La BD efímera conserva los 3 aparatos de ejemplo de CI, pero agregamos
    # el universo REAL únicamente como datos temporales de QA: no hay servidor productivo.
    with app.app_context():
        with db.engine.begin() as con:
            for ref in references:
                inv_id = ref["inventario_id_original"]
                codigo = ref["codigo_interno_original"]
                stock = ref["stock_original"]
                assert con.execute(
                    sa.text("SELECT 1 FROM inventario_general WHERE id=:id"), {"id": inv_id}
                ).scalar() is None, f"Colisión con aparato sintético: {inv_id}"
                con.execute(sa.text(
                    "INSERT INTO inventario_general (id,codigo_interno,tipo,nombre) "
                    "VALUES (:id,:codigo,'APARATOS','Referencia histórica E4 QA')"
                ), {"id": inv_id, "codigo": codigo})
                con.execute(sa.text(
                    "INSERT INTO inventario_sucursal (inventario_id,sucursal_id,stock) "
                    "VALUES (:id,7,:stock)"
                ), {"id": inv_id, "stock": stock})
        db.session.remove()
    before = _snapshot(app)
    root = "/api/inventario/levantamientos"
    created = client.post(root, headers=tokens[1], data={
        "sucursal_id": "7", "origen_corte": "CSV_HISTORICO",
        "cycle_key": str(uuid4()), "fecha_corte_local": "2026-10-28",
        "responsable": "QA E4 binario privado",
        "baseline_csv": (BytesIO(baseline), "inventarios_corte_distribucion.csv"),
    })
    assert created.status_code == 201, created.get_json()
    lev = created.get_json()["levantamiento"]
    assert lev["baseline_resumen"]["referencias_esperadas"] == 150
    assert lev["origen_corte"] == "CSV_HISTORICO"
    assert lev["estado"] == "IN_PROGRESS"
    endpoint = f"{root}/{lev['id']}/importaciones"
    first = client.post(endpoint, headers=tokens[1], data={
        "idempotency_key": str(uuid4()),
        "file": (BytesIO(xlsx), Path(path_xlsx).name),
    })
    assert first.status_code == 201, first.get_json()
    imp = first.get_json()["importacion"]
    summary = imp["resumen"]
    assert imp["resultado"] == "INCOMPLETE", imp
    assert imp["file_sha256"] == expected_sha
    assert summary["referencias_esperadas"] == 150
    assert (summary["si"], summary["no"], summary["sin_revisar"]) == (0, 0, 150)
    assert summary["hallazgos"] == 0
    assert summary["errores"] == 0, imp["diagnosticos"]
    assert summary["avisos"] == 0, imp["diagnosticos"]
    assert len(summary["pendientes"]) == 150
    assert {p["inventario_id"] for p in summary["pendientes"]} == {
        r["inventario_id_original"] for r in references
    }
    detail = client.get(
        f"{endpoint}/{imp['id']}", headers=tokens[1]
    )
    assert detail.status_code == 200, detail.get_json()
    filas = detail.get_json()["filas"]
    assert len(filas) == 150
    assert all(r["hoja"] == "APARATOS" and r["respuesta"] == "SIN_REVISAR" for r in filas)

    downloaded = client.get(
        f"{endpoint}/{imp['id']}/archivo", headers=tokens[1]
    )
    assert downloaded.status_code == 200
    assert downloaded.data == xlsx, "El original privado no coincide byte a byte"
    replay = client.post(endpoint, headers=tokens[1], data={
        "idempotency_key": str(uuid4()),
        "file": (BytesIO(xlsx), "segunda_entrega_igual.xlsx"),
    })
    assert replay.status_code == 200
    assert replay.get_json()["replayed"] is True
    assert replay.get_json()["importacion"]["id"] == imp["id"]
    listed = client.get(f"{root}/{lev['id']}", headers=tokens[1])
    assert listed.status_code == 200
    assert len(listed.get_json()["versiones"]) == 1
    assert _snapshot(app) == before, "La evidencia NO debe cambiar inventario V1/E2"


def test_e3_aprobada_con_efecto_real_habilita_cierre_sin_movimiento_e4(api, monkeypatch):
    monkeypatch.setenv("INVENTARIO_E4_AUTO_REVIEW_DEMO_ENABLED", "true")
    """E4 nunca escribe stock; solo valida la decisión E3 ya aplicada."""
    client, tokens, app = api
    root = "/api/inventario/levantamientos"
    created = client.post(root, headers=tokens[1], data={
        "sucursal_id": "7", "origen_corte": "CSV_HISTORICO",
        "cycle_key": str(uuid4()), "baseline_csv": (BytesIO(original_csv()), "corte.csv"),
    })
    assert created.status_code == 201, created.get_json()
    lev = created.get_json()["levantamiento"]["id"]
    book = load_workbook(BytesIO(workbook(first="SI", second="NO", found=False)))
    book["APARATOS"]["G9"] = "Verificado físicamente, no localizado tras segunda inspección"
    buf = BytesIO()
    book.save(buf)
    loaded = client.post(f"{root}/recepciones", headers=tokens[1], data={
        "idempotency_key": str(uuid4()), "file": (BytesIO(buf.getvalue()), "recibido.xlsx"),
    })
    assert loaded.status_code == 201, loaded.get_json()
    board = client.get(f"{root}/{lev}/conciliacion", headers=tokens[1]).get_json()
    assert board["puede_cerrar"] is False
    assert board["bloqueos"] == ["REVISIONES_SIN_AUTORIZACION"]
    assert client.post(f"{root}/{lev}/cerrar", headers=tokens[1], json={
        "motivo": "Intento sin autorización E3 suficiente",
        "idempotency_key": str(uuid4()),
    }).status_code == 409
    items = client.get(f"{root}/{lev}/revisiones", headers=tokens[1]).get_json()["items"]
    assert len(items) == 1 and items[0]["solicitud_e2_id"]
    solicitud_id = items[0]["solicitud_e2_id"]
    # La aceptación E3 real se prueba en test_inventario_e3_decisiones_pg.py.
    # Aquí se simula su efecto ya aplicado y se comprueba que E4 NO reescribe V1.
    with app.app_context():
        with db.engine.begin() as con:
            con.execute(sa.text(
                "UPDATE inventario_correccion_solicitudes SET estado='APPROVED' WHERE id=:id"
            ), {"id": solicitud_id})
            con.exec_driver_sql("UPDATE inventario_sucursal SET stock=0 WHERE inventario_id=502")
        db.session.remove()
    before = _snapshot(app)
    board = client.get(f"{root}/{lev}/conciliacion", headers=tokens[1]).get_json()
    assert board["puede_cerrar"] and board["casos"][0]["resuelto"]
    key = str(uuid4())
    closed = client.post(f"{root}/{lev}/cerrar", headers=tokens[1], json={
        "motivo": "Aprobación E3 y ausencia física conciliadas con evidencia",
        "idempotency_key": key,
    })
    assert closed.status_code == 201, closed.get_json()
    assert client.post(f"{root}/{lev}/cerrar", headers=tokens[1], json={
        "motivo": "Aprobación E3 y ausencia física conciliadas con evidencia",
        "idempotency_key": key,
    }).status_code == 200
    assert _snapshot(app) == before
    assert client.post(f"{root}/recepciones", headers=tokens[1], data={
        "idempotency_key": str(uuid4()), "file": (BytesIO(buf.getvalue()), "nueva.xlsx"),
    }).status_code == 409


def test_rechazo_e3_y_baja_v1_no_burlan_revisiones_automaticas(api, monkeypatch):
    monkeypatch.setenv("INVENTARIO_E4_AUTO_REVIEW_DEMO_ENABLED", "true")
    client, tokens, app = api
    root = "/api/inventario/levantamientos"
    created = client.post(root, headers=tokens[1], data={
        "sucursal_id": "7", "origen_corte": "CSV_HISTORICO",
        "cycle_key": str(uuid4()), "baseline_csv": (BytesIO(original_csv()), "corte.csv"),
    })
    lev = created.get_json()["levantamiento"]["id"]
    b = load_workbook(BytesIO(workbook(first="SI", second="NO", found=False)))
    b["APARATOS"]["G9"] = "Gerente confirmó ausencia de equipo y solicitó revisión física"
    raw = BytesIO()
    b.save(raw)
    loaded = client.post(f"{root}/recepciones", headers=tokens[1], data={
        "idempotency_key": str(uuid4()), "file": (BytesIO(raw.getvalue()), "reporte.xlsx"),
    })
    assert loaded.status_code == 201, loaded.get_json()
    revisions = client.get(f"{root}/{lev}/revisiones", headers=tokens[1]).get_json()
    sid = revisions["items"][0]["solicitud_e2_id"]
    assert sid
    with app.app_context():
        with db.engine.begin() as con:
            con.execute(sa.text(
                "UPDATE inventario_correccion_solicitudes SET estado='REJECTED' WHERE id=:id"
            ), {"id": sid})
        db.session.remove()
    board = client.get(f"{root}/{lev}/conciliacion", headers=tokens[1]).get_json()
    assert board["puede_cerrar"] is False
    assert "REVISIONES_SIN_AUTORIZACION" in board["bloqueos"]


def test_inicial_hallazgo_sin_identidad_bloquea_y_no_da_alta(api, monkeypatch):
    monkeypatch.setenv("INVENTARIO_E4_AUTO_REVIEW_DEMO_ENABLED", "true")
    client, tokens, app = api
    root = "/api/inventario/levantamientos"
    created = client.post(root, headers=tokens[1], data={
        "sucursal_id": "8", "origen_corte": "INICIAL", "cycle_key": str(uuid4()),
    })
    lev = created.get_json()["levantamiento"]["id"]
    before = _snapshot(app)
    loaded = client.post(f"{root}/recepciones", headers=tokens[1], data={
        "idempotency_key": str(uuid4()),
        "file": (BytesIO(workbook(branch=8, initial=True, found=False)), "inicial.xlsx"),
    })
    assert loaded.status_code == 201, loaded.get_json()
    lista = client.get(f"{root}/{lev}/revisiones", headers=tokens[1]).get_json()
    assert lista["total"] == 1
    assert lista["items"][0]["estado"] == "BLOCKED"
    assert lista["items"][0]["solicitud_e2_id"] is None
    assert client.get(f"{root}/{lev}/conciliacion", headers=tokens[1]).get_json()["puede_cerrar"] is False
    assert _snapshot(app) == before


def test_api_san_luis_real_http_recepcion_y_bloqueo_por_codigo_duplicado(api):
    """Opt-in local: XLSX devuelto + CSV real del corte; sin compartir privados con CI.

    El archivo del gerente tiene un código 06PLJW54 reutilizado como hallazgo.
    Es evidencia, no autorización para crear un segundo equipo con esa etiqueta.
    """
    xlsx_path = os.getenv("E4_REAL_SAN_LUIS_XLSX_PATH")
    baseline_path = os.getenv("E4_REAL_BASELINE_CSV_PATH")
    if not xlsx_path:
        pytest.skip("Archivo real de San Luis no configurado (opt-in)")
    assert baseline_path, "Se requiere el CSV histórico real junto con San Luis"
    raw_xlsx = Path(xlsx_path).read_bytes()
    baseline = Path(baseline_path).read_bytes()
    refs, _ = parse_historical_csv(baseline, 6)
    assert len(refs) == 139, "El corte histórico no corresponde a las 139 referencias de San Luis"

    client, tokens, app = api
    with app.app_context():
        with db.engine.begin() as connection:
            for ref in refs:
                identity = ref["inventario_id_original"]
                assert connection.execute(sa.text(
                    "SELECT 1 FROM inventario_general WHERE id=:identidad"
                ), {"identidad": identity}).scalar() is None
                connection.execute(sa.text(
                    "INSERT INTO inventario_general (id,codigo_interno,tipo,nombre) "
                    "VALUES (:id,:codigo,'APARATOS','Histórico temporal de San Luis')"
                ), {"id": identity, "codigo": ref["codigo_interno_original"]})
                connection.execute(sa.text(
                    "INSERT INTO inventario_sucursal (inventario_id,sucursal_id,stock) "
                    "VALUES (:id,6,:stock)"
                ), {"id": identity, "stock": ref["stock_original"]})
        db.session.remove()
    before = _snapshot(app)
    root = "/api/inventario/levantamientos"
    created = client.post(root, headers=tokens[1], data={
        "sucursal_id": "6", "origen_corte": "CSV_HISTORICO",
        "cycle_key": str(uuid4()), "fecha_corte_local": "2026-10-28",
        "responsable": "QA privado San Luis",
        "baseline_csv": (BytesIO(baseline), "corte_original.csv"),
    })
    assert created.status_code == 201, created.get_json()
    lev = created.get_json()["levantamiento"]["id"]
    assert created.get_json()["levantamiento"]["baseline_resumen"]["referencias_esperadas"] == 139
    endpoint = f"{root}/{lev}/importaciones"
    received = client.post(endpoint, headers=tokens[1], data={
        "idempotency_key": str(uuid4()),
        "file": (BytesIO(raw_xlsx), Path(xlsx_path).name),
    })
    assert received.status_code == 201, received.get_json()
    imported = received.get_json()["importacion"]
    summary = imported["resumen"]
    assert summary["referencias_esperadas"] == 139
    assert (summary["si"], summary["no"], summary["sin_revisar"]) == (137, 2, 0)
    assert summary["hallazgos"] == 7
    assert imported["resultado"] == "INVALID"
    codes = [d["codigo"] for d in imported["diagnosticos"]]
    assert codes.count("PREFIJO_SUCURSAL_INCONSISTENTE") == 4
    assert "CODIGO_HALLAZGO_EN_CORTE" in codes
    duplicated = [d for d in imported["diagnosticos"]
                  if d["codigo"] == "CODIGO_HALLAZGO_EN_CORTE"]
    assert any(d["codigo_declarado"].strip().upper() == "06PLJW54"
               and 2587 in d["inventario_ids_existentes"] for d in duplicated)

    recovered = client.get(
        f"{endpoint}/{imported['id']}/archivo", headers=tokens[1]
    )
    assert recovered.status_code == 200
    assert recovered.data == raw_xlsx
    repeat = client.post(endpoint, headers=tokens[1], data={
        "idempotency_key": str(uuid4()),
        "file": (BytesIO(raw_xlsx), "misma_entrega.xlsx"),
    })
    assert repeat.status_code == 200 and repeat.get_json()["replayed"]
    board = client.get(f"{root}/{lev}/conciliacion", headers=tokens[1])
    assert board.status_code == 200
    assert board.get_json()["puede_cerrar"] is False
    assert client.post(f"{root}/{lev}/cerrar", headers=tokens[1], json={
        "idempotency_key": str(uuid4()),
        "motivo": "Intento prohibido de cerrar archivo con identidad ambigua",
    }).status_code == 409
    assert _snapshot(app) == before


def test_auto_revisiones_e2_unica_por_ciclo_y_nueva_evidencia(api, monkeypatch):
    monkeypatch.setenv("INVENTARIO_E4_AUTO_REVIEW_DEMO_ENABLED", "true")
    """Una diferencia física con evidencia E2 completa abre una sola solicitud."""
    client, tokens, app = api
    root = "/api/inventario/levantamientos"
    created = client.post(root, headers=tokens[1], data={
        "sucursal_id": "7", "origen_corte": "CSV_HISTORICO",
        "cycle_key": str(uuid4()), "baseline_csv": (BytesIO(original_csv()), "corte.csv"),
    })
    assert created.status_code == 201, created.get_json()
    lev = created.get_json()["levantamiento"]["id"]
    book = load_workbook(BytesIO(workbook(first="SI", second="NO", found=False)))
    book["APARATOS"]["G9"] = "No fue localizado tras inspeccionar todo el club"
    payload = BytesIO()
    book.save(payload)
    before = _snapshot(app)
    received = client.post(f"{root}/recepciones", headers=tokens[1], data={
        "idempotency_key": str(uuid4()), "file": (BytesIO(payload.getvalue()), "devuelto.xlsx"),
    })
    assert received.status_code == 201, received.get_json()
    summary = received.get_json()["importacion"]["resumen"]["revisiones_auto"]
    assert summary == {"nuevas": 1, "reutilizadas": 0, "bloqueadas": 0, "e2_creadas": 1}
    state = client.get(f"{root}/{lev}/revisiones", headers=tokens[1])
    assert state.status_code == 200, state.get_json()
    items = state.get_json()["items"]
    assert len(items) == 1 and items[0]["tipo"] == "NOT_LOCATED"
    assert items[0]["estado"] == "AWAITING_E3"
    first_e2 = items[0]["solicitud_e2_id"]
    assert first_e2
    assert _snapshot(app)["stock"] == before["stock"]
    assert _snapshot(app)["master"] == before["master"]
    assert _snapshot(app)["mov"] == before["mov"]
    assert _snapshot(app)["e2"] == before["e2"] + 1

    # El mismo binario no crea otra versión/caso/solicitud.
    retry = client.post(f"{root}/recepciones", headers=tokens[1], data={
        "idempotency_key": str(uuid4()), "file": (BytesIO(payload.getvalue()), "retry.xlsx"),
    })
    assert retry.status_code == 200 and retry.get_json()["replayed"]
    assert _snapshot(app)["e2"] == before["e2"] + 1
    # Nueva versión, misma identidad: evidencia nueva, la E2 original se conserva.
    book["APARATOS"]["G9"] = "No fue localizado tras una segunda revisión completa"
    payload2 = BytesIO()
    book.save(payload2)
    second = client.post(f"{root}/recepciones", headers=tokens[1], data={
        "idempotency_key": str(uuid4()), "file": (BytesIO(payload2.getvalue()), "v2.xlsx"),
    })
    assert second.status_code == 201, second.get_json()
    assert second.get_json()["importacion"]["resumen"]["revisiones_auto"] == {
        "nuevas": 0, "reutilizadas": 1, "bloqueadas": 0, "e2_creadas": 0,
    }
    after = client.get(f"{root}/{lev}/revisiones", headers=tokens[1]).get_json()
    assert after["total"] == 1 and after["items"][0]["solicitud_e2_id"] == first_e2
    assert _snapshot(app)["e2"] == before["e2"] + 1
    with app.app_context():
        ids = db.session.execute(sa.text(
            "SELECT importacion_id FROM inventario_levantamiento_revision_evidencias"
            " ORDER BY importacion_id"
        )).scalars().all()
        assert len(ids) == 2 and len(set(ids)) == 2


def test_auto_revisiones_sin_evidencia_se_bloquean_sin_e2(api, monkeypatch):
    monkeypatch.setenv("INVENTARIO_E4_AUTO_REVIEW_DEMO_ENABLED", "true")
    client, tokens, app = api
    root = "/api/inventario/levantamientos"
    created = client.post(root, headers=tokens[1], data={
        "sucursal_id": "7", "origen_corte": "CSV_HISTORICO",
        "cycle_key": str(uuid4()), "baseline_csv": (BytesIO(original_csv()), "corte.csv"),
    })
    lev = created.get_json()["levantamiento"]["id"]
    before = _snapshot(app)
    uploaded = client.post(f"{root}/recepciones", headers=tokens[1], data={
        "idempotency_key": str(uuid4()),
        "file": (BytesIO(workbook(first="SI", second="NO", found=False)), "devuelto.xlsx"),
    })
    assert uploaded.status_code == 201, uploaded.get_json()
    revisiones = client.get(f"{root}/{lev}/revisiones", headers=tokens[1]).get_json()
    assert revisiones["total"] == 1
    assert revisiones["items"][0]["estado"] == "BLOCKED"
    assert revisiones["items"][0]["motivo_bloqueo"] == "EVIDENCIA_O_PROPUESTA_INCOMPLETA"
    assert revisiones["items"][0]["solicitud_e2_id"] is None
    assert _snapshot(app) == before


def test_auto_e2_jamas_se_activa_fuera_is_demo_ni_sin_flag(api, monkeypatch):
    """Aunque el flag esté ON, una sucursal operativa real nunca crea E2."""
    client, tokens, app = api
    root = "/api/inventario/levantamientos"
    monkeypatch.setenv("INVENTARIO_E4_AUTO_REVIEW_DEMO_ENABLED", "true")
    # En este esquema QA la sucursal 6 es NO demo.
    created = client.post(root, headers=tokens[1], data={
        "sucursal_id": "6", "origen_corte": "INICIAL",
        "cycle_key": str(uuid4()),
    })
    assert created.status_code == 201, created.get_json()
    lev = created.get_json()["levantamiento"]["id"]
    before = _snapshot(app)
    received = client.post(root + "/recepciones", headers=tokens[1], data={
        "idempotency_key": str(uuid4()),
        "file": (BytesIO(workbook(branch=6, initial=True)), "no_demo.xlsx"),
    })
    assert received.status_code == 201, received.get_json()
    assert received.get_json()["importacion"]["resumen"]["revisiones_auto"]["auto_revisiones_habilitadas"] is False
    lista = client.get(f"{root}/{lev}/revisiones", headers=tokens[1]).get_json()
    assert lista["total"] == 0
    assert _snapshot(app) == before
    cierre = client.post(f"{root}/{lev}/cerrar", headers=tokens[1], json={
        "idempotency_key": str(uuid4()),
        "motivo": "Intento de cierre de sucursal que no es demo",
    })
    assert cierre.status_code == 409
    assert cierre.get_json()["error"] == "PILOTO_DEMO_NO_HABILITADO"

    # Y sin el flag ni siquiera la sucursal demo puede generar revisiones.
    monkeypatch.delenv("INVENTARIO_E4_AUTO_REVIEW_DEMO_ENABLED", raising=False)
    created_demo = client.post(root, headers=tokens[1], data={
        "sucursal_id": "7", "origen_corte": "CSV_HISTORICO",
        "cycle_key": str(uuid4()),
        "baseline_csv": (BytesIO(original_csv()), "corte.csv"),
    })
    assert created_demo.status_code == 201, created_demo.get_json()
    demo_id = created_demo.get_json()["levantamiento"]["id"]
    raw = workbook(first="SI", second="NO", found=False)
    no_flag = client.post(root + "/recepciones", headers=tokens[1], data={
        "idempotency_key": str(uuid4()), "file": (BytesIO(raw), "sin_flag.xlsx"),
    })
    assert no_flag.status_code == 201, no_flag.get_json()
    assert no_flag.get_json()["importacion"]["resumen"]["revisiones_auto"]["auto_revisiones_habilitadas"] is False
    assert client.get(f"{root}/{demo_id}/revisiones", headers=tokens[1]).get_json()["total"] == 0
    assert _snapshot(app) == before


def test_piloto_cinco_aparatos_cinco_escenarios_en_mismo_xlsx(api, monkeypatch):
    """5 casos independientes: SI, NO válido, NO sin evidencia, código diferente, blanco."""
    monkeypatch.setenv("INVENTARIO_E4_AUTO_REVIEW_DEMO_ENABLED", "true")
    client, tokens, app = api
    root = "/api/inventario/levantamientos"
    # En este esquema efímero, sucursal 7 es DEMO; los IDs no se reutilizan
    # ni se deducen para el sistema productivo.
    with app.app_context():
        with db.engine.begin() as con:
            con.exec_driver_sql("UPDATE inventario_sucursal SET stock=1 WHERE inventario_id=503")
            con.exec_driver_sql("""
                INSERT INTO inventario_general (id,codigo_interno,tipo,nombre,marca)
                VALUES (504,'07BI01','APARATOS','Bicicleta','Star Trac'),
                       (505,'07ES01','APARATOS','Escaladora','Precor')
            """)
            con.exec_driver_sql(
                "INSERT INTO inventario_sucursal VALUES (504,7,1),(505,7,1)")
        db.session.remove()
    corte = original_csv().replace(
        b"503,07RE00,Cardio,Remo,Concept2,0",
        b"503,07RE00,Cardio,Remo,Concept2,1",
    )
    corte += (
        b"7,Pabellon rosarito,504,07BI01,Cardio,Bicicleta,Star Trac,1\n"
        b"7,Pabellon rosarito,505,07ES01,Cardio,Escaladora,Precor,1\n"
    )
    created = client.post(root, headers=tokens[1], data={
        "sucursal_id": "7", "origen_corte": "CSV_HISTORICO",
        "cycle_key": str(uuid4()), "baseline_csv": (BytesIO(corte), "cinco.csv"),
    })
    assert created.status_code == 201, created.get_json()
    lev = created.get_json()["levantamiento"]["id"]
    wb = load_workbook(BytesIO(workbook(first="SI", second="NO", found=False)))
    aparatos = wb["APARATOS"]
    aparatos["G9"] = "Inspeccionado completo: el aparato no se encontró en el club"
    aparatos.append([503, "07RE00", "Cardio", "Remo", "Concept2", "NO", ""])
    aparatos.append([504, "07BI99", "Cardio", "Bicicleta", "Star Trac", "SI",
                      "La etiqueta física difiere del código distribuido"])
    aparatos.append([505, "07ES01", "Cardio", "Escaladora", "Precor", "", ""])
    archivo = BytesIO()
    wb.save(archivo)
    antes = _snapshot(app)
    received = client.post(root + "/recepciones", headers=tokens[1], data={
        "idempotency_key": str(uuid4()), "file": (BytesIO(archivo.getvalue()), "cinco.xlsx"),
    })
    assert received.status_code == 201, received.get_json()
    res = received.get_json()["importacion"]
    assert res["resultado"] == "INCOMPLETE"
    assert res["resumen"]["referencias_esperadas"] == 5
    assert (res["resumen"]["si"], res["resumen"]["no"],
            res["resumen"]["sin_revisar"]) == (1, 2, 2)
    assert res["resumen"]["revisiones_auto"] == {
        "nuevas": 3, "reutilizadas": 0, "bloqueadas": 2, "e2_creadas": 1,
    }
    review = client.get(f"{root}/{lev}/revisiones", headers=tokens[1]).get_json()
    assert review["total"] == 3
    por_id = {i["inventario_id"]: i for i in review["items"]}
    assert por_id[502]["estado"] == "AWAITING_E3"
    assert por_id[502]["solicitud_e2_id"]
    assert por_id[503]["estado"] == "BLOCKED"
    assert por_id[503]["solicitud_e2_id"] is None
    assert por_id[504]["tipo"] == "IDENTITY_MISMATCH"
    assert por_id[504]["estado"] == "BLOCKED"
    assert 501 not in por_id and 505 not in por_id
    assert _snapshot(app)["stock"] == antes["stock"]
    assert _snapshot(app)["master"] == antes["master"]
    assert _snapshot(app)["mov"] == antes["mov"]
    assert _snapshot(app)["e2"] == antes["e2"] + 1
    board = client.get(f"{root}/{lev}/conciliacion", headers=tokens[1]).get_json()
    assert board["puede_cerrar"] is False
    assert "SIN_REVISAR" in board["bloqueos"]
