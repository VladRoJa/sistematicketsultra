#  backend\app\warehouse\services\gasca_single_report_runner_impl.py


from __future__ import annotations

import os
import shutil
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator

import pandas as pd
import pytz
from calendar import monthrange
from flask import current_app
from playwright.sync_api import sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


CORTE_CAJA_REPORT_TYPE_KEY = "corte_caja"
CARGOS_RECURRENTES_REPORT_TYPE_KEY = "cargos_recurrentes"
VENTA_TOTAL_REPORT_TYPE_KEY = "venta_total"
SOCIOS_VENCIDOS_REPORT_TYPE_KEY = "socios_vencidos"
SUPPORTED_REPORT_TYPES = frozenset(
    {
        CORTE_CAJA_REPORT_TYPE_KEY,
        CARGOS_RECURRENTES_REPORT_TYPE_KEY,
        VENTA_TOTAL_REPORT_TYPE_KEY,
        SOCIOS_VENCIDOS_REPORT_TYPE_KEY,
    }
)
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DATATABLES_EXPORT_MENU_SELECTOR = "div.dropdown-menu[role='menu']:visible"
DATATABLES_EXCEL_OPTION_SELECTOR = "a:has-text('Excel'):visible"



class GascaSingleReportRunnerError(RuntimeError):
    """Error base del single report runner interno de Gasca."""


@dataclass(slots=True)
class GascaRuntimeConfig:
    user: str
    password: str
    login_url: str
    reportes_url: str
    show_browser: bool
    timezone_name: str = "America/Tijuana"


def register_gasca_single_report_runner_impl(app) -> None:
    """
    Registra esta implementación como single report runner concreto.

    Deja resuelto:
        app.config["WAREHOUSE_GASCA_SINGLE_REPORT_RUNNER"] = run_gasca_single_report
    """
    app.config["WAREHOUSE_GASCA_SINGLE_REPORT_RUNNER"] = run_gasca_single_report


def run_gasca_single_report(
    *,
    report_type_key: str,
    run_mode: str,
    snapshot_kind: str,
    requested_by: str | None = None,
    trigger_source: str | None = None,
    requested_at: datetime | None = None,
    target_business_date: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    """
    Ejecuta un solo reporte Gasca y publica el artifact contractual en Warehouse.

    En esta primera versión solo soporta:
    - corte_caja
    """
    _validate_inputs(
        report_type_key=report_type_key,
        run_mode=run_mode,
        snapshot_kind=snapshot_kind,
    )

    runtime = _resolve_runtime_config()
    current_app.logger.info(
        "Gasca single report runner starting: report_type_key=%s run_mode=%s snapshot_kind=%s requested_by=%s trigger_source=%s",
        report_type_key,
        run_mode,
        snapshot_kind,
        requested_by,
        trigger_source,
    )

    with _authenticated_page(runtime) as page:
        if report_type_key == CORTE_CAJA_REPORT_TYPE_KEY:
            artifact_path, extra_metadata = _run_corte_caja_report(
                page=page,
                runtime=runtime,
            )
        elif report_type_key == CARGOS_RECURRENTES_REPORT_TYPE_KEY:
            artifact_path, extra_metadata = _run_cargos_recurrentes_report(
                page=page,
                runtime=runtime,
            )
        elif report_type_key == VENTA_TOTAL_REPORT_TYPE_KEY:
            artifact_path, extra_metadata = _run_venta_total_report(
                page=page,
                runtime=runtime,
                target_business_date=target_business_date,
            )
        elif report_type_key == SOCIOS_VENCIDOS_REPORT_TYPE_KEY:
            artifact_path, extra_metadata = _run_socios_vencidos_report(
                page=page,
                runtime=runtime,
                date_from=date_from,
                date_to=date_to,
            )
        else:
            raise GascaSingleReportRunnerError(
                f"No hay implementación interna para report_type_key={report_type_key!r}"
            )

    captured_at = datetime.now(tz=pytz.timezone(runtime.timezone_name))

    result = {
        "report_type_key": report_type_key,
        "original_filename": artifact_path.name,
        "content_type": XLSX_CONTENT_TYPE,
        "file_path": str(artifact_path),
        "captured_at": captured_at.isoformat(),
        "metadata": {
            "bridge_source": "single_report_runner",
            "runner_mode": "internalized_suite_runner",
            "output_dir": str(artifact_path.parent),
            "filename_prefix": report_type_key,
            **extra_metadata,
        },
    }

    current_app.logger.info(
        "Gasca single report runner finished: report_type_key=%s file_path=%s",
        report_type_key,
        artifact_path,
    )
    return result


def _validate_inputs(
    *,
    report_type_key: str,
    run_mode: str,
    snapshot_kind: str,
) -> None:
    if report_type_key not in SUPPORTED_REPORT_TYPES:
        raise ValueError(
            "El 'report_type_key' no es válido para el single report runner interno. "
            f"Permitidos: {sorted(SUPPORTED_REPORT_TYPES)}"
        )

    if not run_mode:
        raise ValueError("El 'run_mode' es obligatorio.")

    if not snapshot_kind:
        raise ValueError("El 'snapshot_kind' es obligatorio.")


def _resolve_runtime_config() -> GascaRuntimeConfig:
    user = _get_config_value("DIRECCION_USER")
    password = _get_config_value("DIRECCION_PASS")
    login_url = _get_config_value("DIRECCION_LOGIN_URL")
    reportes_url = _get_config_value("REPORTES_URL")
    show_browser = _get_bool_config_value("SHOW_BROWSER", default=False)

    missing: list[str] = []
    if not user:
        missing.append("DIRECCION_USER")
    if not password:
        missing.append("DIRECCION_PASS")
    if not login_url:
        missing.append("DIRECCION_LOGIN_URL")
    if not reportes_url:
        missing.append("REPORTES_URL")

    if missing:
        raise GascaSingleReportRunnerError(
            "Faltan configuraciones para el single report runner interno de Gasca: "
            + ", ".join(missing)
        )

    return GascaRuntimeConfig(
        user=user,
        password=password,
        login_url=login_url,
        reportes_url=reportes_url,
        show_browser=show_browser,
    )


def _get_config_value(key: str) -> str:
    value = current_app.config.get(key)
    if value is None:
        value = os.getenv(key)
    return str(value).strip() if value is not None else ""


def _get_bool_config_value(key: str, *, default: bool) -> bool:
    value = current_app.config.get(key)
    if value is None:
        value = os.getenv(key)

    if value is None:
        return default

    if isinstance(value, bool):
        return value

    normalized = str(value).strip().lower()
    return normalized in {"1", "true", "yes", "on"}


@contextmanager
def _authenticated_page(runtime: GascaRuntimeConfig) -> Iterator[Any]:
    browser = None
    context = None
    pw = None

    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=not runtime.show_browser)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        page.set_default_timeout(120_000)
        page.set_default_navigation_timeout(120_000)

        _hacer_login(page=page, runtime=runtime)
        yield page
    finally:
        if context is not None:
            context.close()
        if browser is not None:
            browser.close()
        if pw is not None:
            pw.stop()


def _hacer_login(*, page: Any, runtime: GascaRuntimeConfig) -> None:
    current_app.logger.info("Gasca single report runner: iniciando login.")
    page.goto(runtime.login_url, timeout=60_000)

    page.get_by_label("Usuario").fill(runtime.user)
    page.get_by_label("Contraseña").fill(runtime.password)
    page.get_by_role("button", name="INICIAR SESIÓN").click()
    page.wait_for_load_state("networkidle")

    try:
        ir_a_inicio = page.get_by_text("Ir a Inicio")
        if ir_a_inicio.count() > 0:
            current_app.logger.info("Gasca single report runner: detectado 404, clic en 'Ir a Inicio'.")
            ir_a_inicio.first.click()
            page.wait_for_load_state("networkidle")
    except Exception:
        pass


def _run_corte_caja_report(
    *,
    page: Any,
    runtime: GascaRuntimeConfig,
) -> tuple[Path, dict[str, Any]]:
    current_app.logger.info("Gasca single report runner: ejecutando corte_caja.")

    page.goto(runtime.reportes_url, timeout=120_000)
    page.wait_for_load_state("networkidle")

    _seleccionar_tipo_reporte(page, "Reporte Corte De Caja")

    hoy_local = datetime.now(pytz.timezone(runtime.timezone_name)).date()
    inicio_mes = hoy_local.replace(day=1)

    _rellenar_fechas_corte_caja(
        page=page,
        fecha_inicio=inicio_mes,
        fecha_fin=hoy_local,
    )

    _click_boton_generar(page)

    current_app.logger.info("Gasca single report runner: esperando carga de Corte de Caja.")
    time.sleep(5)
    page.wait_for_selector("button:has-text('Exportar')", timeout=120_000)

    _click_tab_membresia(page)

    artifact_path = _resolve_contractual_output_path(report_type_key=CORTE_CAJA_REPORT_TYPE_KEY)
    _descargar_excel_desde_tabla(
        page=page,
        nombre_reporte="Reporte Corte De Caja (Membresia)",
        destination_path=artifact_path,
    )

    _limpiar_excel_inplace(artifact_path)

    metadata = {
        "date_from": inicio_mes.isoformat(),
        "date_to": hoy_local.isoformat(),
        "snapshot_kind_hint": "daily",
    }
    return artifact_path, metadata

def _run_venta_total_report(
    *,
    page: Any,
    runtime: GascaRuntimeConfig,
    target_business_date: date | None = None,
) -> tuple[Path, dict[str, Any]]:
    current_app.logger.info("Gasca single report runner: ejecutando venta_total.")

    page.goto(runtime.reportes_url, timeout=120_000)
    page.wait_for_load_state("networkidle")

    _seleccionar_tipo_reporte(page, "Reporte Venta Total")

    hoy_local = datetime.now(pytz.timezone(runtime.timezone_name)).date()

    if target_business_date is None:
        fecha_fin = hoy_local
    elif isinstance(target_business_date, datetime):
        fecha_fin = target_business_date.date()
    elif isinstance(target_business_date, date):
        fecha_fin = target_business_date
    else:
        raise GascaSingleReportRunnerError(
            "Venta Total: target_business_date debe ser date, datetime o None."
        )

    if fecha_fin > hoy_local:
        raise GascaSingleReportRunnerError(
            "Venta Total: target_business_date no puede ser una fecha futura. "
            f"Recibida={fecha_fin.isoformat()} hoy={hoy_local.isoformat()}."
        )

    inicio_mes = fecha_fin.replace(day=1)

    _rellenar_fechas_rango_simple(
        page=page,
        fecha_inicio=inicio_mes,
        fecha_fin=fecha_fin,
    )

    _click_boton_generar(page)

    _esperar_fin_carga_venta_total(
        page=page,
        timeout_seconds=120,
    )

    page.wait_for_selector("button:has-text('Exportar')", timeout=120_000)

    artifact_path = _resolve_contractual_output_path(
        report_type_key=VENTA_TOTAL_REPORT_TYPE_KEY
    )

    _descargar_excel_desde_tabla(
        page=page,
        nombre_reporte="Reporte Venta Total",
        destination_path=artifact_path,
    )

    _limpiar_excel_inplace(artifact_path)

    metadata = {
        "date_from": inicio_mes.isoformat(),
        "date_to": fecha_fin.isoformat(),
        "snapshot_kind_hint": "daily",
    }
    return artifact_path, metadata


def _normalize_socios_vencidos_date(
    value: date | None,
    *,
    field_name: str,
) -> date:
    if value is None:
        raise GascaSingleReportRunnerError(
            f"Socios Vencidos: {field_name} es requerido."
        )

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    raise GascaSingleReportRunnerError(
        f"Socios Vencidos: {field_name} debe ser date o datetime."
    )


def _validate_socios_vencidos_date_range(
    *,
    runtime: GascaRuntimeConfig,
    date_from: date | None,
    date_to: date | None,
) -> tuple[date, date]:
    normalized_date_from = _normalize_socios_vencidos_date(
        date_from,
        field_name="date_from",
    )
    normalized_date_to = _normalize_socios_vencidos_date(
        date_to,
        field_name="date_to",
    )

    if normalized_date_from > normalized_date_to:
        raise GascaSingleReportRunnerError(
            "Socios Vencidos: date_from no puede ser posterior a date_to."
        )

    today_local = datetime.now(
        pytz.timezone(runtime.timezone_name)
    ).date()
    if normalized_date_to > today_local:
        raise GascaSingleReportRunnerError(
            "Socios Vencidos: date_to no puede ser una fecha futura. "
            f"Recibida={normalized_date_to.isoformat()} "
            f"hoy={today_local.isoformat()}."
        )

    return normalized_date_from, normalized_date_to


def _esperar_tabla_socios_vencidos(
    *,
    page: Any,
    timeout_seconds: int = 120,
) -> int:
    current_app.logger.info(
        "Gasca single report runner: esperando tabla de Socios Vencidos."
    )

    loading = page.get_by_text("Cargando", exact=False).first
    try:
        loading.wait_for(state="visible", timeout=10_000)
        loading.wait_for(
            state="hidden",
            timeout=timeout_seconds * 1000,
        )
    except PlaywrightTimeoutError:
        # La tabla puede responder tan rápido que el loader no llegue a observarse.
        pass

    try:
        page.wait_for_selector(
            "table tbody tr:visible",
            state="visible",
            timeout=timeout_seconds * 1000,
        )
        page.wait_for_selector(
            "button:has-text('Exportar')",
            state="visible",
            timeout=timeout_seconds * 1000,
        )
    except PlaywrightTimeoutError as exc:
        raise GascaSingleReportRunnerError(
            "Socios Vencidos: no apareció una tabla exportable dentro del timeout."
        ) from exc

    approximate_row_count = page.locator(
        "table tbody tr:visible"
    ).count()
    if approximate_row_count <= 0:
        raise GascaSingleReportRunnerError(
            "Socios Vencidos: la tabla visible no contiene filas exportables."
        )

    return approximate_row_count


def _validate_downloaded_xlsx(artifact_path: Path) -> None:
    if not artifact_path.is_file():
        raise GascaSingleReportRunnerError(
            "Socios Vencidos: la descarga no produjo el archivo esperado."
        )

    if artifact_path.stat().st_size <= 0:
        raise GascaSingleReportRunnerError(
            "Socios Vencidos: el archivo descargado está vacío."
        )


def _run_socios_vencidos_report(
    *,
    page: Any,
    runtime: GascaRuntimeConfig,
    date_from: date | None,
    date_to: date | None,
) -> tuple[Path, dict[str, Any]]:
    normalized_date_from, normalized_date_to = (
        _validate_socios_vencidos_date_range(
            runtime=runtime,
            date_from=date_from,
            date_to=date_to,
        )
    )
    started_at = time.monotonic()

    current_app.logger.info(
        "Gasca single report runner: ejecutando socios_vencidos "
        "date_from=%s date_to=%s branch_scope=unfiltered.",
        normalized_date_from.isoformat(),
        normalized_date_to.isoformat(),
    )

    try:
        page.goto(runtime.reportes_url, timeout=120_000)
        page.wait_for_load_state("networkidle")

        _seleccionar_tipo_reporte(page, "Reporte Socios Vencidos")
        _rellenar_fechas_rango_simple(
            page=page,
            fecha_inicio=normalized_date_from,
            fecha_fin=normalized_date_to,
        )
        _click_boton_generar(page)

        approximate_row_count = _esperar_tabla_socios_vencidos(
            page=page,
            timeout_seconds=120,
        )

        artifact_path = _resolve_contractual_output_path(
            report_type_key=SOCIOS_VENCIDOS_REPORT_TYPE_KEY
        )
        _descargar_excel_desde_tabla(
            page=page,
            nombre_reporte="Reporte Socios Vencidos",
            destination_path=artifact_path,
        )
        _validate_downloaded_xlsx(artifact_path)
    except Exception:
        duration_seconds = round(time.monotonic() - started_at, 3)
        current_app.logger.warning(
            "Gasca single report runner: socios_vencidos terminado "
            "date_from=%s date_to=%s duration_seconds=%s status=failed.",
            normalized_date_from.isoformat(),
            normalized_date_to.isoformat(),
            duration_seconds,
        )
        raise

    duration_seconds = round(time.monotonic() - started_at, 3)
    current_app.logger.info(
        "Gasca single report runner: socios_vencidos terminado "
        "date_from=%s date_to=%s approximate_rows=%s "
        "duration_seconds=%s status=downloaded.",
        normalized_date_from.isoformat(),
        normalized_date_to.isoformat(),
        approximate_row_count,
        duration_seconds,
    )

    metadata = {
        "date_from": normalized_date_from.isoformat(),
        "date_to": normalized_date_to.isoformat(),
        "snapshot_kind_hint": "range",
        "branch_scope": "unfiltered",
        "approximate_row_count": approximate_row_count,
        "duration_seconds": duration_seconds,
        "raw_file_preserved": True,
    }
    return artifact_path, metadata

def _resolve_contractual_output_path(*, report_type_key: str) -> Path:
    backend_dir = Path(__file__).resolve().parents[3]
    output_dir = backend_dir / "data" / report_type_key
    output_dir.mkdir(parents=True, exist_ok=True)

    filename_map = {
        CORTE_CAJA_REPORT_TYPE_KEY: "corte_caja.xlsx",
        CARGOS_RECURRENTES_REPORT_TYPE_KEY: "cargos_recurrentes.xlsx",
        VENTA_TOTAL_REPORT_TYPE_KEY: "venta_total.xlsx",
        SOCIOS_VENCIDOS_REPORT_TYPE_KEY: "socios_vencidos.xlsx",
    }
    filename = filename_map.get(report_type_key)
    if not filename:
        raise GascaSingleReportRunnerError(
            f"No hay nombre contractual configurado para report_type_key={report_type_key!r}"
        )

    return output_dir / filename

def _esperar_fin_carga_venta_total(*, page: Any, timeout_seconds: int = 120) -> None:
    current_app.logger.info(
        "Gasca single report runner: esperando fin de carga de Venta Total."
    )

    try:
        page.wait_for_selector("text=Cargando...", timeout=10_000)
        current_app.logger.info(
            "Gasca single report runner: 'Cargando...' detectado en Venta Total."
        )
    except Exception:
        current_app.logger.info(
            "Gasca single report runner: no se detectó 'Cargando...' en Venta Total; se asume carga rápida."
        )
        return

    try:
        page.wait_for_selector(
            "text=Cargando...",
            state="detached",
            timeout=timeout_seconds * 1000,
        )
    except Exception as exc:
        raise GascaSingleReportRunnerError(
            "Venta Total: 'Cargando...' no desapareció dentro del timeout."
        ) from exc


def _seleccionar_tipo_reporte(page: Any, texto_opcion: str) -> None:
    current_app.logger.info("Gasca single report runner: seleccionando tipo de reporte %s.", texto_opcion)

    page.wait_for_selector("select", timeout=15_000)

    timeout_s = 20
    start = time.time()
    ultimo_result = None

    while time.time() - start < timeout_s:
        result = page.evaluate(
            """
            (labelBuscado) => {
                const selects = Array.from(document.querySelectorAll('select'));
                if (!selects.length) return 'no-selects';

                const sel = selects[0];
                const options = Array.from(sel.options);

                const opt = options.find(o =>
                    o.textContent.trim().toLowerCase() === labelBuscado.trim().toLowerCase()
                );

                if (!opt) return 'no-option';

                sel.value = opt.value;
                sel.dispatchEvent(new Event('change', { bubbles: true }));
                return 'ok';
            }
            """,
            texto_opcion,
        )

        ultimo_result = result
        if result == "ok":
            time.sleep(1)
            return

        time.sleep(1)

    raise GascaSingleReportRunnerError(
        f"No se pudo seleccionar tipo de reporte {texto_opcion!r}. Último resultado: {ultimo_result}"
    )


def _rellenar_fechas_corte_caja(
    *,
    page: Any,
    fecha_inicio: date,
    fecha_fin: date,
) -> None:
    fecha_inicio_str = fecha_inicio.strftime("%m/%d/%Y")
    fecha_fin_str = fecha_fin.strftime("%m/%d/%Y")

    inputs = page.locator("input[type='text']")
    total = inputs.count()
    if total < 2:
        raise GascaSingleReportRunnerError(
            f"Corte de Caja: esperaba al menos 2 inputs de texto para fechas, pero encontré {total}"
        )

    campo_inicio = inputs.nth(0)
    campo_fin = inputs.nth(1)

    for campo, valor in [
        (campo_inicio, fecha_inicio_str),
        (campo_fin, fecha_fin_str),
    ]:
        campo.click()
        campo.fill("")
        campo.type(valor, delay=50)
        time.sleep(0.3)


def _click_boton_generar(page: Any) -> None:
    try:
        page.get_by_role("button", name="Generar").click()
        return
    except Exception:
        pass

    try:
        page.locator("button:has-text('Generar')").first.click()
        return
    except Exception:
        pass

    try:
        page.get_by_text("Generar", exact=False).first.click()
        return
    except Exception as exc:
        raise GascaSingleReportRunnerError("No se pudo hacer clic en el botón 'Generar'.") from exc


def _click_tab_membresia(page: Any) -> None:
    textos_posibles = ["Membresía", "Membresia"]

    for texto in textos_posibles:
        try:
            page.get_by_role("button", name=texto, exact=False).click()
            return
        except Exception:
            pass

        try:
            page.locator(f"a:has-text('{texto}')").first.click()
            return
        except Exception:
            pass

        try:
            page.get_by_text(texto, exact=False).first.click()
            return
        except Exception:
            pass

    raise GascaSingleReportRunnerError("No se encontró un tab clickeable 'Membresía/Membresia'.")


def _resolver_opcion_excel_datatables(
    *,
    page: Any,
    nombre_reporte: str,
) -> Any:
    try:
        page.wait_for_selector(
            DATATABLES_EXPORT_MENU_SELECTOR,
            state="visible",
            timeout=10_000,
        )
    except PlaywrightTimeoutError as exc:
        raise GascaSingleReportRunnerError(
            f"{nombre_reporte}: se encontraron 0 candidatos Excel interactivos "
            "visibles porque no apareció el menú DataTables Exportar."
        ) from exc

    menus = page.locator(DATATABLES_EXPORT_MENU_SELECTOR)
    menu_count = menus.count()
    if menu_count != 1:
        raise GascaSingleReportRunnerError(
            f"{nombre_reporte}: se esperaba exactamente 1 menú DataTables "
            f"Exportar visible y se encontraron {menu_count}."
        )

    candidates = menus.locator(DATATABLES_EXCEL_OPTION_SELECTOR)
    candidate_count = candidates.count()
    if candidate_count != 1:
        raise GascaSingleReportRunnerError(
            f"{nombre_reporte}: {candidate_count} candidatos Excel interactivos "
            "visibles; se esperaba exactamente 1."
        )

    return candidates


def _descargar_excel_desde_tabla(
    *,
    page: Any,
    nombre_reporte: str,
    destination_path: Path,
) -> Path:
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        export_btn = page.get_by_role("button", name="Exportar")
    except Exception:
        export_btn = None

    if not export_btn:
        try:
            export_btn = page.locator("button:has-text('Exportar')").first
        except Exception as exc:
            raise GascaSingleReportRunnerError(
                f"No se encontró botón 'Exportar' para {nombre_reporte}."
            ) from exc

    export_btn.scroll_into_view_if_needed()
    export_btn.click()

    excel_option = _resolver_opcion_excel_datatables(
        page=page,
        nombre_reporte=nombre_reporte,
    )

    try:
        with page.expect_download(timeout=60_000) as dl_info:
            excel_option.click()

        download = dl_info.value
    except PlaywrightTimeoutError as exc:
        raise GascaSingleReportRunnerError(
            f"{nombre_reporte}: no se pudo iniciar/terminar la descarga de Excel en 60s."
        ) from exc

    if destination_path.exists():
        destination_path.unlink()

    download.save_as(str(destination_path))
    return destination_path


def _limpiar_excel_inplace(ruta: Path | str) -> Path:
    ruta = Path(ruta)
    current_app.logger.info("Gasca single report runner: limpiando Excel %s.", ruta)

    df = None
    last_error = None

    for intento in range(1, 4):
        try:
            df = pd.read_excel(ruta)
            break
        except Exception as exc:
            last_error = exc
            current_app.logger.warning(
                "No se pudo leer %s en intento %s/3 para limpieza: %s",
                ruta,
                intento,
                exc,
            )
            time.sleep(10)

    if df is None:
        raise GascaSingleReportRunnerError(
            f"No se pudo limpiar el Excel {ruta.name} después de 3 intentos."
        ) from last_error

    tmp_path = ruta.with_suffix(".tmp.xlsx")
    df.to_excel(tmp_path, index=False)

    try:
        ruta.unlink()
    except Exception:
        pass

    tmp_path.rename(ruta)
    return ruta

def _rellenar_fechas_rango_simple(
    *,
    page: Any,
    fecha_inicio: date,
    fecha_fin: date,
) -> None:
    fecha_inicio_str = fecha_inicio.strftime("%m/%d/%Y")
    fecha_fin_str = fecha_fin.strftime("%m/%d/%Y")

    inputs = page.locator("input[type='text']")
    total = inputs.count()
    if total < 2:
        raise GascaSingleReportRunnerError(
            f"Esperaba al menos 2 inputs de texto para fechas, pero encontré {total}"
        )

    campo_inicio = inputs.nth(0)
    campo_fin = inputs.nth(1)

    for campo, valor in [
        (campo_inicio, fecha_inicio_str),
        (campo_fin, fecha_fin_str),
    ]:
        campo.click()
        campo.fill("")
        campo.type(valor, delay=50)
        time.sleep(0.3)
        
def _run_cargos_recurrentes_report(
    *,
    page: Any,
    runtime: GascaRuntimeConfig,
) -> tuple[Path, dict[str, Any]]:
    current_app.logger.info("Gasca single report runner: ejecutando cargos_recurrentes.")

    page.goto(runtime.reportes_url, timeout=120_000)
    page.wait_for_load_state("networkidle")

    _seleccionar_tipo_reporte(page, "Reporte Cargos Recurrentes")

    hoy_local = datetime.now(pytz.timezone(runtime.timezone_name)).date()
    inicio_mes = hoy_local.replace(day=1)

    _rellenar_fechas_rango_simple(
        page=page,
        fecha_inicio=inicio_mes,
        fecha_fin=hoy_local,
    )

    _click_boton_generar(page)

    current_app.logger.info("Gasca single report runner: esperando carga de Cargos Recurrentes.")
    time.sleep(5)

    try:
        page.wait_for_selector("table tbody tr", timeout=20_000)
    except Exception:
        current_app.logger.warning(
            "Gasca single report runner: no se detectaron filas visibles en tabla de Cargos Recurrentes antes de exportar."
        )

    artifact_path = _resolve_contractual_output_path(
        report_type_key=CARGOS_RECURRENTES_REPORT_TYPE_KEY
    )

    _descargar_excel_desde_tabla(
        page=page,
        nombre_reporte="Reporte Cargos Recurrentes",
        destination_path=artifact_path,
    )

    _limpiar_excel_inplace(artifact_path)

    metadata = {
        "date_from": inicio_mes.isoformat(),
        "date_to": hoy_local.isoformat(),
        "snapshot_kind_hint": "daily",
    }
    return artifact_path, metadata
