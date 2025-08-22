# backend/scripts/extract/gasca/asistencia_clases_export.py
# ---------------------------------------------------------
# OBJETIVO
#   - Iniciar sesión en Gasca
#   - Navegar a Reportes > "Reporte de Asistencia de Clases"
#   - NO aplicar filtros (descargar TODO)
#   - Exportar en CSV
#   - Renombrar a un nombre determinista: asistencia_clases__full__YYYYMMDD_HHMMSS.csv
#
# CÓMO CORRER
#   - Requiere:
#       pip install playwright python-dotenv
#       playwright install
#   - Variables en .env (ver bloque "Carga de .env"):
#       GASCA_BASE_URL=https://ultragimnasios.com
#       GASCA_USER=...
#       GASCA_PASS=...
#   - Ejemplo:
#       $env:APP_ENV="local"
#       python backend/scripts/extract/gasca/asistencia_clases_export.py --outdir "./data/gasca/asistencias" --headful
#
# PUNTOS DE AJUSTE FRECUENTES (BUSCA "🔧 AJUSTE"):
#   1) Resolución del .env si mueves archivos de entorno
#   2) Selectores de login (labels "Usuario"/"Contraseña" o botón "INICIAR SESIÓN")
#   3) Selector del enlace "Reportes" (href fijo de módulo)
#   4) Selector del "Tipo de Reporte" y opción "Reporte de Asistencia de Clases"
#   5) Esperas antes de exportar (filas visibles / spinner)
#   6) Dropdown de "Exportar" y click en "CSV" (menú visible vs hidden)
#   7) Nombre del archivo destino (convención y extensión)
# ---------------------------------------------------------

import argparse
import os
import re
import hashlib
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from sqlalchemy import create_engine, text
import csv
import json


def start_ingest_run(engine, source_system: str, dataset: str) -> int:
    """
    Inserta un run 'running' y regresa el id.
    Tabla: ext.ingest_runs
    """
    with engine.begin() as conn:
        run_id = conn.execute(
            text("""
                INSERT INTO ext.ingest_runs (source_system, dataset, status)
                VALUES (:source_system, :dataset, 'running')
                RETURNING id
            """),
            {"source_system": source_system, "dataset": dataset}
        ).scalar_one()
    return run_id

def finish_ingest_run(engine, run_id: int, status: str,
                      file_name: str | None = None,
                      file_checksum: str | None = None,
                      rows_ingested: int | None = None,
                      error_message: str | None = None) -> None:
    """
    Actualiza el run con estado final, hora de fin y metadatos del archivo.
    - status: 'success' | 'failed'
    - rows_ingested: lo dejaremos None por ahora (se llenará en el paso de staging)
    """
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE ext.ingest_runs
                   SET status = :status,
                       run_ended_at = now(),
                       file_name = COALESCE(:file_name, file_name),
                       file_checksum = COALESCE(:file_checksum, file_checksum),
                       rows_ingested = COALESCE(:rows_ingested, rows_ingested),
                       error_message = COALESCE(:error_message, error_message)
                 WHERE id = :run_id
            """),
            {
                "status": status,
                "file_name": file_name,
                "file_checksum": file_checksum,
                "rows_ingested": rows_ingested,
                "error_message": error_message,
                "run_id": run_id
            }
        )

def sha256_file(path: Path) -> str:
    """Calcula SHA256 del archivo descargado. Útil para idempotencia/consistencia."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def load_csv_to_staging(engine, run_id: int, csv_path: Path, batch_size: int = 1000) -> int:
    """
    Carga el CSV a ext.gasca_asistencia_clases_stg como JSONB (payload) + raw_line (aprox).
    - Lee encabezados del CSV y mantiene los nombres tal cual (sin transformar).
    - Inserta en lotes para mejor rendimiento.
    - Retorna: total de filas insertadas.

    🔧 AJUSTES:
      - Si el CSV usa otro delimitador: agrega `delimiter=';'` al DictReader.
      - Si necesitas normalizar encabezados (trim/mayúsculas), hazlo antes de armar `payload`.
      - Si requieres guardar la línea cruda exacta, aquí hacemos una aproximación
        serializando la fila a JSON para `raw_line`. Si quieres la línea textual,
        tendríamos que leer el archivo 2 veces o usar otro approach.
    """
    total = 0
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        # Opcional: limpiar espacios en encabezados
        headers = [h.strip() if isinstance(h, str) else h for h in headers]

        batch = []
        with engine.begin() as conn:
            for row in reader:
                # Limpia espacios en valores (string); deja otros tipos tal cual
                payload = {}
                for k in headers:
                    v = row.get(k)
                    if isinstance(v, str):
                        v = v.strip()
                    payload[k] = v
                # Guardamos una "línea cruda" aproximada como JSON texto para auditoría
                raw_line = json.dumps(row, ensure_ascii=False)

                batch.append({
                    "ingest_run_id": run_id,
                    "payload": json.dumps(payload, ensure_ascii=False),
                    "raw_line": raw_line
                })

                if len(batch) >= batch_size:
                    conn.execute(
                        text("""
                            INSERT INTO ext.gasca_asistencia_clases_stg (ingest_run_id, payload, raw_line)
                            VALUES (:ingest_run_id, CAST(:payload AS JSONB), :raw_line)
                        """),
                        batch
                    )
                    total += len(batch)
                    batch.clear()

            # flush final
            if batch:
                conn.execute(
                        text("""
                            INSERT INTO ext.gasca_asistencia_clases_stg (ingest_run_id, payload, raw_line)
                            VALUES (:ingest_run_id, CAST(:payload AS JSONB), :raw_line)
                        """),
                    batch
                )
                total += len(batch)

    return total


def slugify(text: str) -> str:
    """Convierte texto a slug (por si algún día decides incluir sucursal/instructor en el nombre).
    Actualmente NO se usa, pero lo dejamos utilitario por si expandes la convención."""
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9\-_\s]", "", text)
    text = re.sub(r"\s+", "-", text)
    return text or "na"

def resolve_base_url(cli_base_url: str | None) -> str:
    """
    Determina la URL de login:
    - Prioriza --base-url si viene por CLI.
    - Si no, usa GASCA_BASE_URL de .env.
    - Si te dan raíz sin /Login, la normaliza a /Login.
    🔧 AJUSTE: Si Gasca cambia la ruta de login, modifica aquí.
    """
    env_url = os.getenv("GASCA_BASE_URL")
    base = (cli_base_url or env_url or "").rstrip("/")
    if not base:
        raise SystemExit("Falta base URL (pasa --base-url o define GASCA_BASE_URL en .env)")
    if "Login" not in base:
        return base + "/Login"
    return base

def main():
    # -----------------------------------------------------
    # CARGA DE .env (prioriza backend/.env.local)
    # -----------------------------------------------------
    script_path = Path(__file__).resolve()

    # Estructura esperada:
    #   .../Sistema tickets/backend/scripts/extract/gasca/asistencia_clases_export.py
    # parents[3] = .../backend
    # parents[4] = .../Sistema tickets (raíz)
    backend_dir = script_path.parents[3]
    repo_root   = script_path.parents[4]

    app_env = os.getenv("APP_ENV", "local").lower()

    def env_name_for(env: str) -> str:
        if env == "prod":
            return ".env.prod"
        if env == "docker":
            return ".env.docker"
        return ".env.local"  # default local

    preferred = env_name_for(app_env)

    # 🔧 AJUSTE (orden de búsqueda):
    #   - Si cambias de lugar tus .env, ajusta esta lista.
    candidates = [
        backend_dir / preferred,   # backend/.env.local (o prod/docker)
        backend_dir / ".env",      # backend/.env
        repo_root / preferred,     # raiz/.env.local (o prod/docker)
        repo_root / ".env",        # raiz/.env
    ]

    loaded_from = None
    for env_path in candidates:
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=False)  # override=False para no pisar variables del proceso
            loaded_from = env_path
            break

    if not loaded_from:
        print("⚠️  No se encontró .env.{local|prod|docker} ni .env en backend/ o raíz.")
    else:
        print(f"ℹ️  .env cargado desde: {loaded_from}")

    # -----------------------------------------------------
    # ARGUMENTOS CLI (solo outdir/headful aquí; URL viene del .env)
    # -----------------------------------------------------
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", help="URL base o de login (ej. https://ultragimnasios.com/ o .../Login)")
    parser.add_argument("--outdir", default="./data/gasca/asistencias", help="Carpeta destino de descargas")
    parser.add_argument("--headful", action="store_true", help="Abrir navegador visible para depurar")
    args = parser.parse_args()

    # -----------------------------------------------------
    # CREDENCIALES
    # -----------------------------------------------------
    USER = os.getenv("GASCA_USER")
    PASS = os.getenv("GASCA_PASS")
    if not USER or not PASS:
        # 🔧 AJUSTE: si ves este error, confirma que el .env correcto se imprimió arriba
        # y que contiene las claves exactas GASCA_USER/GASCA_PASS.
        raise SystemExit("Faltan credenciales GASCA_USER / GASCA_PASS en .env")
    
        # 🔧 AJUSTE: usamos la URI que ya usas en tu app Flask
    DB_URI = os.getenv("SQLALCHEMY_DATABASE_URI")
    if not DB_URI:
        raise SystemExit("Falta SQLALCHEMY_DATABASE_URI en .env (para registrar ingest_runs).")

    engine = create_engine(DB_URI, future=True)

    login_url = resolve_base_url(args.base_url)

    # -----------------------------------------------------
    # PREPARAR CARPETA DE SALIDA
    # -----------------------------------------------------
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    
    # -----------------------------------------------------
    # INICIO de ingest_run
    # -----------------------------------------------------

    run_id = start_ingest_run(engine, source_system="gasca", dataset="asistencia_clases")

    # -----------------------------------------------------
    # PLAYWRIGHT
    # -----------------------------------------------------
    
    try:
    
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not args.headful)
            # accept_downloads=True es clave para poder capturar el archivo
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()

            # -------------------------------------------------
            # 1) LOGIN
            # -------------------------------------------------
            page.goto(login_url, wait_until="domcontentloaded")

            # 🔧 AJUSTE (selectores de login):
            #   - Si cambian labels/placeholder, ajusta los get_by_label / get_by_role.
            page.get_by_label("Usuario").fill(USER)
            page.get_by_label(re.compile(r"Contraseña|Contrasena", re.I)).fill(PASS)
            page.get_by_role("button", name=re.compile(r"INICIAR SESIÓN|Iniciar sesión|Iniciar Sesión", re.I)).click()
            page.wait_for_load_state("networkidle")  # espera a que se estabilicen las peticiones

            # -------------------------------------------------
            # 2) NAVEGAR A REPORTES
            # -------------------------------------------------
            # Preferimos un selector determinista por href (evita duplicados "Reportes" en breadcrumb y mosaico).
            # 🔧 AJUSTE: si cambia la ruta, actualiza el href aquí.
            try:
                page.locator('a[href="/Modulo/Reporte/Index"]').first.click()
            except Exception:
                page.locator('a[href*="/Modulo/Reporte/Index"]').first.click()

            # Espera explícita a la URL del módulo de reportes (evita clicks prematuros).
            page.wait_for_url(re.compile(r"/Modulo/Reporte/Index$", re.I))

            # -------------------------------------------------
            # 3) SELECCIONAR "Reporte de Asistencia de Clases"
            # -------------------------------------------------
            # 🔧 AJUSTE:
            #   - Si el <select> cambia de label o se vuelve un componente, usa el fallback por role.
            tipo_label = page.get_by_label(re.compile(r"Tipo de Reporte", re.I))
            try:
                tipo_label.select_option(label="Reporte de Asistencia de Clases")
            except PWTimeout:
                page.get_by_role("combobox").select_option(label="Reporte de Asistencia de Clases")

            # -------------------------------------------------
            # 4) NO APLICAMOS FILTROS
            # -------------------------------------------------
            # Descargamos todo. Si algún día quieres filtrar por semana/sucursal:
            # 🔧 AJUSTE (ejemplos):
            #   page.get_by_label("Sucursal").select_option(label="PASEO LA PAZ")
            #   page.get_by_label("Semana").fill("2025-08-18")
            #   page.get_by_label("Instructor").select_option(label="Todos")

            # -------------------------------------------------
            # 5) GENERAR (por si requiere refrescar)
            # -------------------------------------------------
            # Algunas páginas requieren "Generar" antes de exportar; otras ya listan todo.
            try:
                page.get_by_role("button", name=re.compile(r"Generar", re.I)).click()
                page.wait_for_load_state("networkidle")
            except Exception:
                pass

            # -------------------------------------------------
            # 6) EXPORTAR → CSV (robusto con fallback)
            # -------------------------------------------------
            # Recomendación: si existe un spinner (ej. .dataTables_processing:visible),
            # espera a que desaparezca ANTES de exportar:
            # 🔧 AJUSTE opcional (descomenta si detectas spinner):
            # try:
            #     page.locator(".dataTables_processing:visible").first.wait_for(state="hidden", timeout=60000)
            # except Exception:
            #     pass

            # A) Clic en "Exportar"
            export_btn = page.get_by_role("button", name=re.compile(r"Exportar", re.I))
            export_btn.click()

            # B) Intento 1: menú visible + clic normal
            #   Muchas UIs usan .dropdown-menu (Bootstrap). A veces está "hidden" según PW.
            menu = page.locator(".dropdown-menu").first
            csv_in_menu = menu.locator('text=/^CSV$/').first
            try:
                # Esperamos visibilidad real del dropdown
                menu.wait_for(state="visible", timeout=8000)
                with page.expect_download() as download_info:
                    csv_in_menu.click()
                download = download_info.value
            except Exception:
                # C) Fallback: el menú existe pero queda hidden; clic forzado al item CSV
                any_csv = page.locator('.dropdown-menu >> text=/^CSV$/').first
                any_csv.wait_for(timeout=8000)  # espera a que exista el nodo
                with page.expect_download() as download_info:
                    any_csv.click(force=True)    # ⬅️ clave para bypass de hidden
                download = download_info.value

            # -------------------------------------------------
            # 7) RENOMBRAR ARCHIVO
            # -------------------------------------------------
            # Convención clara y estable. Cambia "full" si un día looping por sucursal/instructor.
            # 🔧 AJUSTE nombre (ejemplos):
            #   fname = f"asistencia_clases__sucursal-{slugify('PASEO LA PAZ')}__{ts}.csv"
            #   fname = f"asistencia_clases__semana-{fecha_semana}__{ts}.csv"
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = f"asistencia_clases__full__{ts}.csv"
            dest = outdir / fname
            download.save_as(dest)
            
            # -------------------------------------------------
            # 8) CARGAR A STAGING
            # -------------------------------------------------           
           
            rows = load_csv_to_staging(engine, run_id, dest)
           
           
           
            # -------------------------------------------------
            # 9) FIN de ingest_run (SUCCESS) — guardamos file_name y checksum
            # -------------------------------------------------
            
            checksum = sha256_file(dest)
            finish_ingest_run(
                engine, run_id,
                status="success",
                file_name=dest.name,
                file_checksum=checksum,
                rows_ingested=rows,
                error_message=None
            )

            print(f"run_id: {run_id}")
            print(f"checksum: {checksum}")
            print(f"rows_ingested: {rows}")
            print(f"✅ CSV descargado: {dest}")

            # Cierre de contexto/navegador
            context.close()
            browser.close()
            
    except Exception as e:
        # En cualquier error, marcamos el run como FAILED con el mensaje
        finish_ingest_run(
            engine, run_id,
            status="failed",
            error_message=str(e)[:500]  # recorta por si el error es muy largo
        )
        # Propagamos para que el script salga con código != 0 si lo usas en cron
        raise       

if __name__ == "__main__":
    main()
