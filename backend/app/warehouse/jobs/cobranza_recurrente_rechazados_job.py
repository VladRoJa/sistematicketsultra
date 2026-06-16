# backend/app/warehouse/jobs/cobranza_recurrente_rechazados_job.py

from __future__ import annotations

import logging
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import Page, sync_playwright

from app.warehouse.jobs._cobranza_recurrente_rechazados_xlsx import procesar_archivo
from app.warehouse.jobs.cobranza_recurrente_rechazados_publisher import (
    publish_cobranza_recurrente_rechazados_outputs,
)

logger = logging.getLogger(__name__)

JOB_KEY = "cobranza_recurrente_rechazados"
REPORT_TYPE_KEY = "cobranza_recurrente_rechazados"


@dataclass(frozen=True)
class CobranzaJobConfig:
    gasca_user: str
    gasca_pass: str
    gasca_login_url: str
    gasca_reportes_url: str
    show_browser: bool
    timezone_name: str
    report_type_match: str
    max_retries: int
    login_field_timeout_ms: int
    table_ready_timeout_sec: int
    table_min_real_rows: int
    report_page_retries: int
    output_base_dir: Path


USER_SELECTORS = [
    "input[aria-label='Usuario']",
    "input[name='Usuario']",
    "input[id*='Usuario']",
    "input[type='text']",
]

PASSWORD_SELECTORS = [
    "input[aria-label='Contraseña']",
    "input[name='Contrasena']",
    "input[name='Password']",
    "input[id*='Contras']",
    "input[type='password']",
]

LOGIN_BUTTONS = [
    ("role_button", "INICIAR SESIÓN"),
    ("role_button", "INICIAR SESION"),
    ("text", "INICIAR SESIÓN"),
    ("text", "INICIAR SESION"),
    ("css", "button[type='submit']"),
    ("css", "input[type='submit']"),
]


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)

    if raw is None or not raw.strip():
        return default

    try:
        return int(raw)
    except ValueError:
        logger.warning("Variable %s inválida=%r. Usando default=%s", name, raw, default)
        return default


def _default_output_base_dir() -> Path:
    configured = os.getenv("COBRANZA_RECURRENTE_OUTPUT_DIR", "").strip()

    if configured:
        return Path(configured)

    uploads_dir = Path("/uploads")

    if uploads_dir.exists():
        return uploads_dir / "warehouse" / "automations" / JOB_KEY

    backend_root = Path(__file__).resolve().parents[3]

    return backend_root / "storage" / "warehouse" / "automations" / JOB_KEY


def load_config() -> CobranzaJobConfig:
    return CobranzaJobConfig(
        gasca_user=os.getenv("GASCA_USER", "").strip(),
        gasca_pass=os.getenv("GASCA_PASS", "").strip(),
        gasca_login_url=os.getenv("GASCA_LOGIN_URL", "https://ultragimnasios.com/").strip(),
        gasca_reportes_url=os.getenv(
            "GASCA_REPORTES_URL",
            "https://ultragimnasios.com/Modulo/Reporte/Index",
        ).strip(),
        show_browser=_env_bool("SHOW_BROWSER", False),
        timezone_name=(
            os.getenv("COBRANZA_RECURRENTE_TZ")
            or os.getenv("REPORTS_SCHEDULER_TZ")
            or os.getenv("TIMEZONE")
            or "America/Tijuana"
        ).strip(),
        report_type_match=os.getenv(
            "REPORT_TYPE_MATCH",
            "reporte de cobranza de cargos recurrentes",
        ).strip(),
        max_retries=_env_int("COBRANZA_RECURRENTE_MAX_RETRIES", _env_int("MAX_RETRIES", 3)),
        login_field_timeout_ms=_env_int("LOGIN_FIELD_TIMEOUT_MS", 2500),
        table_ready_timeout_sec=_env_int("TABLE_READY_TIMEOUT_SEC", 120),
        table_min_real_rows=_env_int("TABLE_MIN_REAL_ROWS", 1),
        report_page_retries=_env_int("REPORT_PAGE_RETRIES", 3),
        output_base_dir=_default_output_base_dir(),
    )


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = value.lower()

    return re.sub(r"\s+", " ", value).strip()


def resolve_timezone(config: CobranzaJobConfig) -> ZoneInfo:
    candidates = [config.timezone_name]
    normalized = config.timezone_name.lower()

    if normalized in {"america/tijuana", "tijuana", "baja", "baja_california"}:
        candidates.extend(["America/Los_Angeles", "UTC"])
    else:
        candidates.append("UTC")

    last_error = None

    for tz_name in candidates:
        try:
            if tz_name != config.timezone_name:
                logger.warning(
                    "TIMEZONE %r no disponible. Usando fallback %r.",
                    config.timezone_name,
                    tz_name,
                )
            return ZoneInfo(tz_name)
        except ZoneInfoNotFoundError as exc:
            last_error = exc

    raise RuntimeError(
        "No se pudo resolver la zona horaria. "
        "Instala tzdata o usa REPORTS_SCHEDULER_TZ=America/Los_Angeles."
    ) from last_error


def now_local(config: CobranzaJobConfig) -> datetime:
    return datetime.now(resolve_timezone(config))


def validate_config(config: CobranzaJobConfig) -> None:
    missing: list[str] = []

    if not config.gasca_user:
        missing.append("GASCA_USER")

    if not config.gasca_pass:
        missing.append("GASCA_PASS")

    if not config.gasca_login_url:
        missing.append("GASCA_LOGIN_URL")

    if not config.gasca_reportes_url:
        missing.append("GASCA_REPORTES_URL")

    if missing:
        raise RuntimeError(f"Faltan variables de entorno: {', '.join(missing)}")


def get_day_folders(
    config: CobranzaJobConfig,
    business_date: date | None = None,
) -> tuple[str, Path, Path]:
    if business_date is None:
        business_date = now_local(config).date()

    today_str = business_date.strftime("%Y-%m-%d")
    run_dir = config.output_base_dir / today_str
    raw_dir = run_dir / "raw"
    clubs_dir = run_dir / "sucursales"

    raw_dir.mkdir(parents=True, exist_ok=True)
    clubs_dir.mkdir(parents=True, exist_ok=True)

    return today_str, raw_dir, clubs_dir


def first_working_locator(page: Page, selectors: list[str], timeout_ms: int = 2000):
    last_error = None

    for selector in selectors:
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=timeout_ms)
            return locator
        except Exception as exc:  # noqa: BLE001
            last_error = exc

    raise RuntimeError(f"No encontré el elemento esperado. Último error: {last_error}")


def fast_fill(
    page: Page,
    selectors: list[str],
    value: str,
    field_name: str,
    config: CobranzaJobConfig,
) -> None:
    locator = first_working_locator(
        page,
        selectors,
        timeout_ms=config.login_field_timeout_ms,
    )

    try:
        locator.fill(value, timeout=config.login_field_timeout_ms)
        locator.dispatch_event("input")
        locator.dispatch_event("change")
    except Exception:
        locator.click(timeout=config.login_field_timeout_ms)
        locator.press("Control+A")
        locator.type(value, delay=0, timeout=config.login_field_timeout_ms)

    logger.info("Campo capturado: %s", field_name)


def click_first(
    page: Page,
    candidates: list[tuple[str, str]],
    timeout_ms: int = 3000,
) -> bool:
    last_error = None

    for kind, value in candidates:
        try:
            if kind == "role_button":
                page.get_by_role("button", name=value, exact=False).first.click(timeout=timeout_ms)
            elif kind == "text":
                page.get_by_text(value, exact=False).first.click(timeout=timeout_ms)
            elif kind == "css":
                page.locator(value).first.click(timeout=timeout_ms)
            else:
                raise RuntimeError(f"Tipo de selector no soportado: {kind}")

            return True
        except Exception as exc:  # noqa: BLE001
            last_error = exc

    logger.warning("No se pudo hacer clic con los selectores dados: %s", last_error)

    return False


def session_state(page: Page) -> dict:
    password_visible = False
    select_visible = False
    ir_inicio_visible = False

    try:
        password_visible = page.locator("input[type='password']").count() > 0
    except Exception:
        pass

    try:
        select_visible = page.locator("select").count() > 0
    except Exception:
        pass

    try:
        ir_inicio_visible = page.get_by_text("Ir a Inicio", exact=False).count() > 0
    except Exception:
        pass

    url = ""

    try:
        url = page.url or ""
    except Exception:
        pass

    url_norm = url.lower()
    on_login = password_visible or ("login" in url_norm) or ("signin" in url_norm)
    on_reports = ("/modulo/reporte/index" in url_norm) or select_visible
    authenticated = on_reports or ir_inicio_visible or (not password_visible and not on_login)

    return {
        "url": url,
        "on_login": on_login,
        "on_reports": on_reports,
        "authenticated": authenticated,
        "password_visible": password_visible,
        "ir_inicio_visible": ir_inicio_visible,
    }


def wait_for_authenticated_state(page: Page, timeout_sec: int = 12) -> bool:
    deadline = time.time() + timeout_sec

    while time.time() < deadline:
        state = session_state(page)

        if state["authenticated"]:
            return True

        time.sleep(0.25)

    return session_state(page)["authenticated"]


def hacer_login(page: Page, config: CobranzaJobConfig) -> None:
    logger.info("Abriendo login...")
    page.goto(config.gasca_login_url, wait_until="domcontentloaded", timeout=60_000)

    initial = session_state(page)

    if initial["authenticated"] and not initial["on_login"]:
        logger.info("Sesión activa detectada.")
        return

    logger.info("Capturando credenciales...")

    fast_fill(page, USER_SELECTORS, config.gasca_user, "Usuario", config)

    password_locator = first_working_locator(
        page,
        PASSWORD_SELECTORS,
        timeout_ms=config.login_field_timeout_ms,
    )

    try:
        password_locator.fill(config.gasca_pass, timeout=config.login_field_timeout_ms)
        password_locator.dispatch_event("input")
        password_locator.dispatch_event("change")
    except Exception:
        password_locator.click(timeout=config.login_field_timeout_ms)
        password_locator.press("Control+A")
        password_locator.type(config.gasca_pass, delay=0, timeout=config.login_field_timeout_ms)

    if wait_for_authenticated_state(page, timeout_sec=2):
        logger.info("Login completado por autoenvío.")
        return

    try:
        password_locator.press("Enter", timeout=1200)

        if wait_for_authenticated_state(page, timeout_sec=6):
            logger.info("Login completado.")
            return
    except Exception:
        pass

    try:
        submitted = page.evaluate(
            """
            () => {
                const pwd = document.querySelector("input[type='password']");
                const form = pwd?.closest('form') || document.querySelector('form');
                if (!form) return false;
                if (typeof form.requestSubmit === 'function') {
                    form.requestSubmit();
                } else {
                    form.submit();
                }
                return true;
            }
            """
        )

        if submitted and wait_for_authenticated_state(page, timeout_sec=6):
            logger.info("Login completado.")
            return
    except Exception:
        pass

    if click_first(page, LOGIN_BUTTONS, timeout_ms=1500):
        if wait_for_authenticated_state(page, timeout_sec=6):
            logger.info("Login completado.")
            return
    elif wait_for_authenticated_state(page, timeout_sec=3):
        logger.info("Login completado.")
        return

    state = session_state(page)

    raise RuntimeError(
        "El login no terminó de consolidarse. "
        f"url='{state['url']}', on_login={state['on_login']}, authenticated={state['authenticated']}"
    )


def abrir_reportes(page: Page, config: CobranzaJobConfig) -> None:
    logger.info("Abriendo módulo de reportes...")
    last_error = None

    for attempt in range(1, config.report_page_retries + 1):
        try:
            page.goto(config.gasca_reportes_url, wait_until="domcontentloaded", timeout=60_000)

            try:
                ir_inicio = page.get_by_text("Ir a Inicio", exact=False)

                if ir_inicio.count() > 0:
                    logger.info("Pantalla intermedia detectada. Resolviendo...")
                    ir_inicio.first.click(timeout=2500)
                    page.goto(config.gasca_reportes_url, wait_until="domcontentloaded", timeout=60_000)
            except Exception:
                pass

            page.wait_for_selector("select", timeout=15_000)
            return
        except Exception as exc:
            last_error = exc
            state = session_state(page)

            if state["on_login"]:
                raise RuntimeError("La sesión no quedó activa: Reportes regresó al login.") from exc

            if attempt < config.report_page_retries:
                logger.warning("Reintento Reportes %s/%s", attempt, config.report_page_retries)
                time.sleep(2)

    raise RuntimeError("No cargó la pantalla de reportes después del login.") from last_error


def seleccionar_tipo_reporte(page: Page, config: CobranzaJobConfig) -> str:
    logger.info("Seleccionando tipo de reporte...")

    page.wait_for_selector("select", timeout=20_000)

    objetivo = normalize_text(config.report_type_match)

    matched = page.evaluate(
        r"""
        (objetivo) => {
            const normalizar = (texto) =>
                (texto || "")
                    .normalize("NFD")
                    .replace(/[\u0300-\u036f]/g, "")
                    .toLowerCase()
                    .replace(/\s+/g, " ")
                    .trim();

            const select = document.querySelector("select");
            if (!select) return null;

            const options = Array.from(select.options);
            const candidatos = [objetivo, "reporte de cobranza de cargos recurrentes"]
                .map(v => normalizar(v))
                .filter(Boolean);

            const normalizadas = options.map(opt => ({
                opt,
                text: normalizar(opt.textContent)
            }));

            let target = null;

            for (const candidato of candidatos) {
                target = normalizadas.find(x => x.text === candidato)?.opt;
                if (target) break;
            }

            if (!target) {
                for (const candidato of candidatos) {
                    target = normalizadas.find(x => x.text.includes(candidato))?.opt;
                    if (target) break;
                }
            }

            if (!target) {
                return {
                    matched: null,
                    options: options.map(o => o.textContent.trim()).filter(Boolean)
                };
            }

            select.value = target.value;
            select.dispatchEvent(new Event("change", { bubbles: true }));

            return { matched: target.textContent.trim(), options: [] };
        }
        """,
        objetivo,
    )

    matched_text = None
    options = []

    if isinstance(matched, dict):
        matched_text = matched.get("matched")
        options = matched.get("options") or []
    else:
        matched_text = matched

    if not matched_text:
        suffix = f" Opciones detectadas: {options}" if options else ""
        raise RuntimeError(
            "No encontré la opción del reporte. Ajusta REPORT_TYPE_MATCH." + suffix
        )

    logger.info("Reporte seleccionado: %s", matched_text)

    time.sleep(0.4)

    return str(matched_text)


def rellenar_fechas(
    page: Page,
    config: CobranzaJobConfig,
    business_date: date | None = None,
) -> str:
    if business_date is None:
        business_date = now_local(config).date()

    report_date = business_date.strftime("%m/%d/%Y")

    logger.info("Fecha Inicio/Fin = %s", report_date)

    inputs = page.locator("input[type='text']")
    total = inputs.count()

    if total < 2:
        raise RuntimeError(
            f"Esperaba al menos 2 inputs de texto para fechas, pero encontré {total}."
        )

    for idx, nombre in [(0, "Fecha Inicio"), (1, "Fecha Fin")]:
        campo = inputs.nth(idx)
        campo.fill(report_date)
        campo.dispatch_event("input")
        campo.dispatch_event("change")
        campo.press("Tab")

        logger.info("%s = %s", nombre, report_date)

        time.sleep(0.1)

    return report_date


def _table_status(page: Page) -> dict:
    return page.evaluate(
        r"""
        () => {
            const textNorm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
            const isVisible = (el) => !!(el && el.offsetParent !== null);

            const loadingTexts = Array.from(document.querySelectorAll('body *'))
                .filter(isVisible)
                .map(el => textNorm(el.textContent))
                .filter(Boolean);

            const loading = loadingTexts.some(t => t === 'cargando...' || t.includes('cargando'));

            const rows = Array.from(document.querySelectorAll('table tbody tr')).filter(isVisible);
            const rowTexts = rows.map(r => textNorm(r.innerText));

            const realRows = rowTexts.filter(t => {
                if (!t) return false;
                if (t.startsWith('del ') && t.includes(' a ')) return false;
                if (t === '#') return false;
                if (t.includes('no hay registros')) return false;
                return true;
            });

            return {
                total_rows: rows.length,
                real_rows: realRows.length,
                export_visible: Array.from(document.querySelectorAll('button, a, span, div'))
                    .filter(isVisible)
                    .some(el => textNorm(el.textContent).includes('exportar')),
                loading,
            };
        }
        """
    )


def esperar_tabla_generada(
    page: Page,
    config: CobranzaJobConfig,
    baseline_real_rows: int,
    baseline_total_rows: int,
) -> None:
    logger.info("Esperando a que la tabla termine de generarse...")

    started = time.time()
    saw_loading_once = False
    stable_positive_checks = 0

    while time.time() - started < config.table_ready_timeout_sec:
        status = _table_status(page)
        total_rows = int(status.get("total_rows", 0))
        real_rows = int(status.get("real_rows", 0))
        loading = bool(status.get("loading", False))
        export_visible = bool(status.get("export_visible", False))

        if loading:
            saw_loading_once = True
            stable_positive_checks = 0
        elif real_rows >= config.table_min_real_rows:
            stable_positive_checks += 1
        else:
            stable_positive_checks = 0

        logger.info(
            "filas detectadas=%s | filas reales=%s | loading=%s",
            total_rows,
            real_rows,
            loading,
        )

        dataset_changed = (real_rows > baseline_real_rows) or (total_rows > baseline_total_rows)

        if export_visible and not loading and real_rows >= config.table_min_real_rows:
            if saw_loading_once or dataset_changed or stable_positive_checks >= 2:
                logger.info("Tabla lista para exportar.")
                return

        time.sleep(1)

    raise RuntimeError("La tabla no terminó de generarse a tiempo o sigue sin filas reales.")


def generar_reporte(page: Page, config: CobranzaJobConfig) -> None:
    logger.info("Generando reporte...")

    before = _table_status(page)

    triggered = click_first(
        page,
        [
            ("role_button", "Generar"),
            ("css", "button:has-text('Generar')"),
            ("text", "Generar"),
        ],
        timeout_ms=4000,
    )

    if not triggered:
        triggered = bool(
            page.evaluate(
                """
                () => {
                    const btn = Array.from(
                        document.querySelectorAll('button, input[type="button"], input[type="submit"], a')
                    ).find(el => ((el.textContent || el.value || '').toLowerCase().includes('generar')));
                    if (!btn) return false;
                    btn.click();
                    return true;
                }
                """
            )
        )

    if not triggered:
        raise RuntimeError("No se pudo disparar el botón Generar.")

    time.sleep(0.4)

    esperar_tabla_generada(
        page,
        config,
        baseline_real_rows=int(before.get("real_rows", 0)),
        baseline_total_rows=int(before.get("total_rows", 0)),
    )

    logger.info("Reporte cargado.")


def descargar_excel(page: Page, raw_dir: Path, today_str: str) -> Path:
    destino = raw_dir / f"cobranza_cargos_recurrentes_{today_str}.xlsx"

    if destino.exists():
        destino.unlink()

    logger.info("Descargando Excel...")

    if not click_first(
        page,
        [
            ("role_button", "Exportar"),
            ("css", "button:has-text('Exportar')"),
            ("text", "Exportar"),
        ],
        timeout_ms=4000,
    ):
        raise RuntimeError("No se pudo abrir el menú Exportar.")

    time.sleep(0.8)

    try:
        with page.expect_download(timeout=120_000) as dl_info:
            if not click_first(
                page,
                [
                    ("text", "Excel"),
                    ("css", "text=Excel"),
                ],
                timeout_ms=4000,
            ):
                raise RuntimeError("No se encontró la opción Excel.")

        download = dl_info.value
    except PlaywrightTimeoutError as exc:
        raise RuntimeError(f"Timeout esperando la descarga de Excel: {exc}") from exc

    download.save_as(str(destino))

    logger.info("Archivo descargado en: %s", destino)

    return destino


def run_once(business_date: date | None = None) -> dict:
    config = load_config()
    validate_config(config)

    today_str, raw_dir, clubs_dir = get_day_folders(config, business_date)

    logger.info("==== Inicio %s ====", JOB_KEY)
    logger.info("Carpeta del día: %s", raw_dir.parent)

    inicio = time.time()

    raw_file: Path | None = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not config.show_browser)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        page.set_default_timeout(60_000)
        page.set_default_navigation_timeout(60_000)

        try:
            hacer_login(page, config)
            abrir_reportes(page, config)
            seleccionar_tipo_reporte(page, config)
            rellenar_fechas(page, config, business_date)
            generar_reporte(page, config)

            raw_file = descargar_excel(page, raw_dir, today_str)

            logger.info("Procesando archivo descargado...")
            processing_result = procesar_archivo(raw_file, clubs_dir)
            logger.info("Archivo procesado y separado por sucursal.")

            logger.info("Publicando archivos en Warehouse/Nube...")
            publication_result = publish_cobranza_recurrente_rechazados_outputs(
                business_date=today_str,
                raw_file=raw_file,
                artifacts=processing_result["artifacts"],
            )
            logger.info(
                "Publicación Warehouse/Nube OK. uploads=%s internal_documents=%s",
                publication_result["total_uploads"],
                publication_result.get("total_internal_documents", 0),
            )
        finally:
            browser.close()

    duration_seconds = time.time() - inicio

    result = {
        "job_key": JOB_KEY,
        "report_type_key": REPORT_TYPE_KEY,
        "business_date": today_str,
        "raw_file": str(raw_file) if raw_file else None,
        "output_dir": str(raw_dir.parent),
        "total_rows": processing_result["total_rows"],
        "total_files": processing_result["total_files"],
        "artifacts": processing_result["artifacts"],
        "warehouse_publication": publication_result,
        "duration_seconds": round(duration_seconds, 2),
    }

    logger.info(
        "OK | day=%s | file=%s | rows=%s | files=%s | sec=%.1f",
        today_str,
        raw_file.name if raw_file else None,
        result["total_rows"],
        result["total_files"],
        duration_seconds,
    )

    return result


def run_job(business_date: date | None = None) -> dict:
    config = load_config()

    last_error: Exception | None = None

    for intento in range(1, config.max_retries + 1):
        try:
            logger.info("Intento %s/%s", intento, config.max_retries)
            return run_once(business_date)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.exception("Fallo en intento %s/%s", intento, config.max_retries)

            if intento < config.max_retries:
                logger.info("Reintentando en 10 segundos...")
                time.sleep(10)

    raise RuntimeError(
        f"El proceso falló después de {config.max_retries} intentos: {last_error}"
    ) from last_error


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    )

    from app import create_app
    from app.extensions import db

    app = create_app()

    with app.app_context():
        try:
            result = run_job()

            print("Proceso terminado correctamente.")
            print(f"Fecha negocio: {result['business_date']}")
            print(f"Archivo raw: {result['raw_file']}")
            print(f"Carpeta salida: {result['output_dir']}")
            print(f"Filas exportadas: {result['total_rows']}")
            print(f"Archivos generados: {result['total_files']}")
            print(f"Duración: {result['duration_seconds']}s")

            publication = result.get("warehouse_publication") or {}
            if publication:
                print(f"Documentos Nube: {publication.get('total_internal_documents', 0)}")

            return 0
        finally:
            db.session.remove()

if __name__ == "__main__":
    raise SystemExit(main())