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
                con.exec_driver_sql("CREATE TABLE sucursales (sucursal_id INTEGER PRIMARY KEY)")
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
                con.exec_driver_sql("INSERT INTO sucursales VALUES (6),(7),(8)")
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


def test_api_conciliacion_cierre_no_modifica_inventario_y_exige_e3(api):
    """Un NO y un hallazgo deben tener resolución autorizada antes del cierre."""
    client, tokens, app = api
    root = "/api/inventario/levantamientos"
    created = client.post(root, headers=tokens[1], data={
        "sucursal_id": "7", "origen_corte": "CSV_HISTORICO",
        "cycle_key": str(uuid4()), "baseline_csv": (BytesIO(original_csv()), "corte.csv"),
    })
    assert created.status_code == 201, created.get_json()
    lev = created.get_json()["levantamiento"]["id"]
    book = load_workbook(BytesIO(workbook(first="SI", second="NO", found=True)))
    book["HALLAZGOS"]["A8"] = "07AD99"
    original = BytesIO()
    book.save(original)
    imp_resp = client.post(f"{root}/{lev}/importaciones", headers=tokens[1], data={
        "idempotency_key": str(uuid4()), "file": (BytesIO(original.getvalue()), "devuelto.xlsx"),
    })
    assert imp_resp.status_code == 201, imp_resp.get_json()
    imp = imp_resp.get_json()["importacion"]
    assert imp["resultado"] == "VALIDATED"
    endpoint = f"{root}/{lev}/conciliacion"
    assert client.get(endpoint, headers=tokens[2]).status_code == 403
    board = client.get(endpoint, headers=tokens[1])
    assert board.status_code == 200, board.get_json()
    casos = {x["caso"] for x in board.get_json()["casos"]}
    assert casos == {"NO:502", "HALLAZGO:8"}
    assert board.get_json()["puede_cerrar"] is False
    assert client.post(f"{root}/{lev}/cerrar", headers=tokens[1], json={
        "idempotency_key": str(uuid4()), "motivo": "Cierre antes de autorizar hallazgos",
    }).status_code == 409

    # Simular únicamente la decisión E3 ya aplicada, no a través de la ruta E4.
    with app.app_context():
        with db.engine.begin() as con:
            con.exec_driver_sql("""
                INSERT INTO inventario_correccion_solicitudes
                    (id,tipo,estado,sucursal_id,inventario_id,creado_por_usuario_id)
                VALUES (900,'NOT_LOCATED','APPROVED',7,502,2)
            """)
            con.exec_driver_sql("UPDATE inventario_sucursal SET stock=0 WHERE inventario_id=502")
            con.exec_driver_sql("""
                INSERT INTO inventario_general (id,codigo_interno,tipo,nombre)
                VALUES (504,'07AD99','APARATOS','Banco hallado')
            """)
            con.exec_driver_sql("INSERT INTO inventario_sucursal VALUES (504,7,1)")
        db.session.remove()
    snapshot = _snapshot(app)
    reason = "Conciliado con evidencia y autorización corporativa verificada"
    no_key = str(uuid4())
    no = client.post(f"{root}/{lev}/resoluciones", headers=tokens[1], json={
        "caso": "NO:502", "accion": "E2_APROBADA",
        "solicitud_id": 900, "motivo": reason, "idempotency_key": no_key,
    })
    assert no.status_code == 201, no.get_json()
    replay = client.post(f"{root}/{lev}/resoluciones", headers=tokens[1], json={
        "caso": "NO:502", "accion": "E2_APROBADA",
        "solicitud_id": 900, "motivo": reason, "idempotency_key": no_key,
    })
    assert replay.status_code == 200 and replay.get_json()["replayed"]
    assert client.post(f"{root}/{lev}/cerrar", headers=tokens[1], json={
        "idempotency_key": str(uuid4()), "motivo": reason,
    }).status_code == 409
    found = client.post(f"{root}/{lev}/resoluciones", headers=tokens[1], json={
        "caso": "HALLAZGO:8", "accion": "REGISTRADO_OFICIAL",
        "inventario_id_resultante": 504, "motivo": reason,
        "idempotency_key": str(uuid4()),
    })
    assert found.status_code == 201, found.get_json()
    board = client.get(endpoint, headers=tokens[1]).get_json()
    assert board["puede_cerrar"] is True and not board["bloqueos"]
    close_key = str(uuid4())
    cierre = client.post(f"{root}/{lev}/cerrar", headers=tokens[1], json={
        "idempotency_key": close_key, "motivo": reason,
    })
    assert cierre.status_code == 201, cierre.get_json()
    assert cierre.get_json()["cierre"]["estado"] == "CLOSED"
    close_replay = client.post(f"{root}/{lev}/cerrar", headers=tokens[1], json={
        "idempotency_key": close_key, "motivo": reason,
    })
    assert close_replay.status_code == 200
    assert close_replay.get_json()["replayed"]
    assert client.post(f"{root}/{lev}/importaciones", headers=tokens[1], data={
        "idempotency_key": str(uuid4()),
        "file": (BytesIO(original.getvalue()), "intento_post_cierre.xlsx"),
    }).status_code == 409
    assert _snapshot(app) == snapshot, "E4 solo resuelve/cierra: no muta V1 ni E2"


def test_baja_previa_exige_movimiento_salida_valido_sin_duplicarlo(api):
    client, tokens, app = api
    root = "/api/inventario/levantamientos"
    response = client.post(root, headers=tokens[1], data={
        "sucursal_id": "7", "origen_corte": "CSV_HISTORICO",
        "cycle_key": str(uuid4()), "baseline_csv": (BytesIO(original_csv()), "corte.csv"),
    })
    assert response.status_code == 201, response.get_json()
    lev = response.get_json()["levantamiento"]["id"]
    upload = client.post(f"{root}/{lev}/importaciones", headers=tokens[1], data={
        "idempotency_key": str(uuid4()),
        "file": (BytesIO(workbook(first="SI", second="NO", found=False)), "entrega.xlsx"),
    })
    assert upload.status_code == 201, upload.get_json()
    assert upload.get_json()["importacion"]["resultado"] == "VALIDATED"
    base = {
        "caso": "NO:502", "accion": "BAJA_PREVIA", "movimiento_id": 77,
        "motivo": "Baja con salida oficial autorizada anteriormente",
        "idempotency_key": str(uuid4()),
    }
    assert client.post(f"{root}/{lev}/resoluciones", headers=tokens[1],
                       json=base).status_code == 409
    with app.app_context():
        with db.engine.begin() as con:
            con.exec_driver_sql("UPDATE inventario_sucursal SET stock=0 WHERE inventario_id=502")
            con.exec_driver_sql(
                "INSERT INTO movimientos_inventario VALUES (77,'salida',7,true)")
            con.exec_driver_sql(
                "INSERT INTO detalle_movimiento VALUES (88,77,502,1)")
        db.session.remove()
    assert client.post(f"{root}/{lev}/resoluciones", headers=tokens[1],
                       json=base).status_code == 409
    with app.app_context():
        with db.engine.begin() as con:
            con.exec_driver_sql("UPDATE movimientos_inventario SET anulado=false WHERE id=77")
        db.session.remove()
    before = _snapshot(app)
    r = client.post(f"{root}/{lev}/resoluciones", headers=tokens[1], json=base)
    assert r.status_code == 201, r.get_json()
    board = client.get(f"{root}/{lev}/conciliacion", headers=tokens[1]).get_json()
    assert board["puede_cerrar"] and len(board["casos"]) == 1
    closed = client.post(f"{root}/{lev}/cerrar", headers=tokens[1], json={
        "motivo": "Inventario conciliado con registro de baja V1 confirmado",
        "idempotency_key": str(uuid4()),
    })
    assert closed.status_code == 201, closed.get_json()
    assert _snapshot(app) == before


def test_prefijo_exige_correccion_e2_aprobada_y_no_reescribe_el_corte(api):
    client, tokens, app = api
    root = "/api/inventario/levantamientos"
    historico = original_csv().replace(b"07EL01", b"05EL01")
    created = client.post(root, headers=tokens[1], data={
        "sucursal_id": "7", "origen_corte": "CSV_HISTORICO",
        "cycle_key": str(uuid4()), "baseline_csv": (BytesIO(historico), "historico.csv"),
    })
    assert created.status_code == 201, created.get_json()
    lev = created.get_json()["levantamiento"]["id"]
    report = client.post(f"{root}/{lev}/importaciones", headers=tokens[1], data={
        "idempotency_key": str(uuid4()),
        "file": (BytesIO(workbook(first="SI",second="SI",code="05EL01",found=False)), "devuelto.xlsx"),
    })
    assert report.status_code == 201, report.get_json()
    assert report.get_json()["importacion"]["resultado"] == "VALIDATED"
    panel = client.get(f"{root}/{lev}/conciliacion", headers=tokens[1]).get_json()
    assert {c["caso"] for c in panel["casos"]} == {"PREFIJO:502"}
    assert not panel["puede_cerrar"]
    motivo = "Reetiquetado y corrección de prefijo aprobados por corporativo"
    resolver = {
        "caso": "PREFIJO:502", "accion": "E2_APROBADA", "solicitud_id": 901,
        "motivo": motivo, "idempotency_key": str(uuid4()),
    }
    assert client.post(f"{root}/{lev}/resoluciones", headers=tokens[1], json=resolver).status_code == 409
    with app.app_context():
        with db.engine.begin() as con:
            con.exec_driver_sql("""
                INSERT INTO inventario_correccion_solicitudes
                   (id,tipo,estado,sucursal_id,inventario_id,campo,valor_propuesto)
                VALUES (901,'MASTER_FIELD','APPROVED',7,502,'codigo_interno','"07EL01"'::jsonb)
            """)
        db.session.remove()
    before = _snapshot(app)
    assert client.post(f"{root}/{lev}/resoluciones", headers=tokens[1], json=resolver).status_code == 201
    assert client.get(f"{root}/{lev}/conciliacion", headers=tokens[1]).get_json()["puede_cerrar"]
    close = client.post(f"{root}/{lev}/cerrar", headers=tokens[1], json={
        "motivo": "Todas las etiquetas fueron validadas y corregidas",
        "idempotency_key": str(uuid4()),
    })
    assert close.status_code == 201, close.get_json()
    assert _snapshot(app) == before


def test_levantamiento_inicial_requiere_alta_identificada_antes_de_cierre(api):
    client, tokens, app = api
    root = "/api/inventario/levantamientos"
    created = client.post(root, headers=tokens[1], data={
        "sucursal_id": "8", "origen_corte": "INICIAL", "cycle_key": str(uuid4()),
    })
    assert created.status_code == 201
    lev = created.get_json()["levantamiento"]["id"]
    libro = load_workbook(BytesIO(workbook(branch=8, initial=True, found=False)))
    libro["APARATOS"]["B8"] = "08CA0001"
    buf = BytesIO()
    libro.save(buf)
    uploaded = client.post(f"{root}/{lev}/importaciones", headers=tokens[1], data={
        "idempotency_key": str(uuid4()),
        "file": (BytesIO(buf.getvalue()), "inventario_inicial.xlsx"),
    })
    assert uploaded.status_code == 201, uploaded.get_json()
    assert uploaded.get_json()["importacion"]["resultado"] == "INCOMPLETE"
    board = client.get(f"{root}/{lev}/conciliacion", headers=tokens[1]).get_json()
    assert {row["caso"] for row in board["casos"]} == {"INICIAL:8"}
    assert not board["puede_cerrar"]
    motivo = "Alta oficial comprobada contra equipo y etiqueta física"
    input_res = {
        "caso": "INICIAL:8", "accion": "REGISTRADO_OFICIAL",
        "inventario_id_resultante": 505, "motivo": motivo,
        "idempotency_key": str(uuid4()),
    }
    assert client.post(f"{root}/{lev}/resoluciones", headers=tokens[1], json=input_res).status_code == 409
    with app.app_context():
        with db.engine.begin() as con:
            con.exec_driver_sql("""
                INSERT INTO inventario_general (id,codigo_interno,tipo,nombre)
                VALUES (505,'08CA0001','APARATOS','Caminadora')
            """)
            con.exec_driver_sql("INSERT INTO inventario_sucursal VALUES (505,8,1)")
        db.session.remove()
    before = _snapshot(app)
    assert client.post(f"{root}/{lev}/resoluciones", headers=tokens[1], json=input_res).status_code == 201
    assert client.get(f"{root}/{lev}/conciliacion", headers=tokens[1]).get_json()["puede_cerrar"]
    assert client.post(f"{root}/{lev}/cerrar", headers=tokens[2], json={
        "motivo": motivo, "idempotency_key": str(uuid4()),
    }).status_code == 403
    assert client.post(f"{root}/{lev}/cerrar", headers=tokens[1], json={
        "motivo": motivo, "idempotency_key": str(uuid4()),
    }).status_code == 201
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
