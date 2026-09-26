from __future__ import annotations

import os
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from zoneinfo import ZoneInfo

from flask import current_app
from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from .attendance_ingestion_service import (
    ingest_attendance_excel,
)
from .attendance_parser import (
    file_sha256,
    parse_attendance_excel,
)


BUSINESS_TZ = ZoneInfo("America/Tijuana")
REPORT_LABEL = (
    "Reporte De Estadisticas De Asistencias"
)
LOADER_LABEL = (
    "Reporte Estadisticas De Asistencias"
)
DEFAULT_MAX_RETRIES = 3


class AttendanceCaptureError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AttendanceCaptureConfig:
    user: str
    password: str
    login_url: str
    reports_url: str
    show_browser: bool


def capture_and_ingest_attendance(
    *,
    business_date: date,
    max_retries: int = DEFAULT_MAX_RETRIES,
    trigger_source: str = "MANUAL_CAPTURE",
) -> dict:
    _validate_business_date(business_date)
    config = _resolve_config()

    with _captured_report(
        business_date=business_date,
        max_retries=max_retries,
        config=config,
    ) as temp_path:
        run = ingest_attendance_excel(
            temp_path,
            business_date=business_date,
            trigger_source=trigger_source,
        )

        result = {
            "status": run.status,
            "run_id": int(run.id),
            "business_date": (
                run.business_date.isoformat()
            ),
            "source_rows": int(
                run.source_rows
            ),
            "inserted_rows": int(
                run.inserted_rows
            ),
            "updated_rows": int(
                run.updated_rows
            ),
            "rejected_rows": int(
                run.rejected_rows
            ),
            "source_sha256": run.source_sha256,
            "temporary_file_preserved": False,
        }

        current_app.logger.info(
            "Captura de asistencia terminada: "
            "fecha=%s run_id=%s source_rows=%s "
            "inserted=%s updated=%s rejected=%s.",
            business_date.isoformat(),
            run.id,
            run.source_rows,
            run.inserted_rows,
            run.rejected_rows,
        )
        return result


def capture_and_validate_attendance(
    *,
    business_date: date,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> dict:
    """
    Descarga y valida el reporte sin escribir en SQL.

    Está pensado para la primera prueba local del
    capturador. El XLSX vive sólo dentro de un
    TemporaryDirectory y se elimina al terminar.
    """
    _validate_business_date(business_date)
    config = _resolve_config()

    with _captured_report(
        business_date=business_date,
        max_retries=max_retries,
        config=config,
    ) as temp_path:
        parsed = parse_attendance_excel(
            temp_path,
            business_date=business_date,
        )
        status_counts = Counter(
            visit.visit_status
            for visit in parsed.visits
        )

        return {
            "status": "VALIDATED",
            "business_date": (
                business_date.isoformat()
            ),
            "source_rows": int(
                parsed.source_rows
            ),
            "parsed_rows": len(
                parsed.visits
            ),
            "rejected_rows": len(
                parsed.rejections
            ),
            "visit_status_counts": {
                key: int(value)
                for key, value
                in sorted(
                    status_counts.items()
                )
            },
            "source_sha256": file_sha256(
                temp_path
            ),
            "temporary_file_preserved": False,
        }


@contextmanager
def _captured_report(
    *,
    business_date: date,
    max_retries: int,
    config: AttendanceCaptureConfig,
):
    attempts = max(1, int(max_retries))

    with TemporaryDirectory(
        prefix="suite_attendance_"
    ) as temp_dir:
        temp_path = (
            Path(temp_dir)
            / (
                "asistencias_"
                f"{business_date:%Y-%m-%d}.xlsx"
            )
        )

        for attempt in range(
            1,
            attempts + 1,
        ):
            try:
                current_app.logger.info(
                    "Captura de asistencia: "
                    "fecha=%s intento=%s/%s.",
                    business_date.isoformat(),
                    attempt,
                    attempts,
                )
                _download_attendance_report(
                    business_date=business_date,
                    destination_path=temp_path,
                    config=config,
                )
                break
            except Exception as exc:
                current_app.logger.warning(
                    "Captura de asistencia falló: "
                    "fecha=%s intento=%s/%s "
                    "error=%s",
                    business_date.isoformat(),
                    attempt,
                    attempts,
                    exc,
                )
                if attempt >= attempts:
                    raise AttendanceCaptureError(
                        "No se pudo descargar el "
                        "reporte de asistencia de "
                        f"{business_date.isoformat()} "
                        f"después de {attempts} "
                        "intentos."
                    ) from exc
                time.sleep(5)

        if not temp_path.is_file():
            raise AttendanceCaptureError(
                "La descarga no produjo el "
                "XLSX temporal."
            )

        if temp_path.stat().st_size <= 0:
            raise AttendanceCaptureError(
                "El XLSX temporal descargado "
                "está vacío."
            )

        yield temp_path


def _download_attendance_report(
    *,
    business_date: date,
    destination_path: Path,
    config: AttendanceCaptureConfig,
) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=not config.show_browser
        )
        context = browser.new_context(
            accept_downloads=True
        )

        try:
            page = context.new_page()
            page.set_default_timeout(120_000)
            page.set_default_navigation_timeout(
                120_000
            )

            _login(
                page,
                config=config,
            )

            page.goto(
                config.reports_url,
                timeout=120_000,
            )
            page.wait_for_load_state(
                "networkidle"
            )

            _select_report_type(
                page,
                REPORT_LABEL,
            )
            _fill_date_range(
                page,
                business_date=business_date,
            )
            _click_generate(page)
            _wait_for_report(page)
            _download_excel(
                page,
                destination_path=destination_path,
            )
        finally:
            context.close()
            browser.close()


def _resolve_config() -> AttendanceCaptureConfig:
    user = _config_value("DIRECCION_USER")
    password = _config_value(
        "DIRECCION_PASS"
    )
    login_url = _config_value(
        "DIRECCION_LOGIN_URL"
    )
    reports_url = _config_value(
        "REPORTES_URL"
    )

    missing = [
        name
        for name, value in (
            ("DIRECCION_USER", user),
            ("DIRECCION_PASS", password),
            (
                "DIRECCION_LOGIN_URL",
                login_url,
            ),
            ("REPORTES_URL", reports_url),
        )
        if not value
    ]
    if missing:
        raise AttendanceCaptureError(
            "Faltan configuraciones: "
            + ", ".join(missing)
        )

    return AttendanceCaptureConfig(
        user=user,
        password=password,
        login_url=login_url,
        reports_url=reports_url,
        show_browser=_config_bool(
            "SHOW_BROWSER",
            default=False,
        ),
    )


def _config_value(name: str) -> str:
    value = current_app.config.get(name)
    if value is None:
        value = os.getenv(name)
    return (
        str(value).strip()
        if value is not None
        else ""
    )


def _config_bool(
    name: str,
    *,
    default: bool,
) -> bool:
    value = current_app.config.get(name)
    if value is None:
        value = os.getenv(name)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _validate_business_date(
    business_date: date,
) -> None:
    if not isinstance(
        business_date,
        date,
    ):
        raise AttendanceCaptureError(
            "business_date debe ser date."
        )

    today = datetime.now(
        BUSINESS_TZ
    ).date()
    if business_date > today:
        raise AttendanceCaptureError(
            "No se puede solicitar "
            "una fecha futura."
        )


def _login(
    page: Any,
    *,
    config: AttendanceCaptureConfig,
) -> None:
    page.goto(
        config.login_url,
        timeout=60_000,
    )

    page.get_by_label("Usuario").fill(
        config.user
    )
    page.get_by_label(
        "Contraseña"
    ).fill(config.password)
    page.get_by_role(
        "button",
        name="INICIAR SESIÓN",
    ).click()
    page.wait_for_load_state(
        "networkidle"
    )

    try:
        go_home = page.get_by_text(
            "Ir a Inicio"
        )
        if go_home.count() > 0:
            go_home.first.click()
            page.wait_for_load_state(
                "networkidle"
            )
    except Exception:
        pass


def _select_report_type(
    page: Any,
    label: str,
) -> None:
    page.wait_for_selector(
        "select",
        timeout=15_000,
    )

    deadline = time.monotonic() + 20
    last_result = None

    while time.monotonic() < deadline:
        last_result = page.evaluate(
            """
            (labelBuscado) => {
                const selects = Array.from(
                    document.querySelectorAll(
                        'select'
                    )
                );
                if (!selects.length) {
                    return 'no-selects';
                }

                const select = selects[0];
                const option = Array.from(
                    select.options
                ).find(
                    (item) =>
                        item.textContent
                            .trim()
                            .toLowerCase()
                        === labelBuscado
                            .trim()
                            .toLowerCase()
                );

                if (!option) {
                    return 'no-option';
                }

                select.value = option.value;
                select.dispatchEvent(
                    new Event(
                        'change',
                        { bubbles: true }
                    )
                );
                return 'ok';
            }
            """,
            label,
        )
        if last_result == "ok":
            time.sleep(1)
            return
        time.sleep(1)

    raise AttendanceCaptureError(
        "No se pudo seleccionar "
        f"{label!r}. Último resultado: "
        f"{last_result!r}."
    )


def _fill_date_range(
    page: Any,
    *,
    business_date: date,
) -> None:
    date_value = business_date.strftime(
        "%m/%d/%Y"
    )
    inputs = page.locator(
        "input[type='text']"
    )

    if inputs.count() < 2:
        raise AttendanceCaptureError(
            "Se esperaban al menos dos "
            "campos de fecha."
        )

    for index in (0, 1):
        field = inputs.nth(index)
        field.click()
        field.fill("")
        field.type(
            date_value,
            delay=50,
        )
        time.sleep(0.2)


def _click_generate(page: Any) -> None:
    try:
        page.get_by_role(
            "button",
            name="Generar",
        ).click()
        return
    except Exception:
        pass

    try:
        page.locator(
            "button:has-text('Generar')"
        ).first.click()
        return
    except Exception as exc:
        raise AttendanceCaptureError(
            "No se pudo hacer clic "
            "en Generar."
        ) from exc


def _wait_for_report(
    page: Any,
    *,
    timeout_seconds: int = 180,
) -> None:
    try:
        page.wait_for_selector(
            f"text={LOADER_LABEL}",
            timeout=10_000,
        )
        page.wait_for_selector(
            f"text={LOADER_LABEL}",
            state="detached",
            timeout=(
                timeout_seconds * 1000
            ),
        )
    except PlaywrightTimeoutError:
        # Puede cargar tan rápido que
        # el overlay no llegue a observarse.
        pass

    try:
        page.wait_for_function(
            """
            () => (
                document.querySelectorAll(
                    'table tbody tr'
                ).length > 0
            )
            """,
            timeout=(
                timeout_seconds * 1000
            ),
        )
        page.wait_for_selector(
            "button:has-text('Exportar')",
            state="visible",
            timeout=30_000,
        )
    except PlaywrightTimeoutError as exc:
        raise AttendanceCaptureError(
            "El reporte no produjo filas "
            "exportables dentro del timeout."
        ) from exc


def _download_excel(
    page: Any,
    *,
    destination_path: Path,
) -> None:
    export_button = page.get_by_role(
        "button",
        name="Exportar",
    )
    if export_button.count() <= 0:
        export_button = page.locator(
            "button:has-text('Exportar')"
        ).first

    export_button.scroll_into_view_if_needed()
    export_button.click()
    time.sleep(0.5)

    try:
        with page.expect_download(
            timeout=60_000
        ) as download_info:
            page.get_by_text(
                "Excel",
                exact=False,
            ).first.click()

        download = download_info.value
    except PlaywrightTimeoutError as exc:
        raise AttendanceCaptureError(
            "No se pudo descargar el Excel "
            "en 60 segundos."
        ) from exc

    destination_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    if destination_path.exists():
        destination_path.unlink()

    download.save_as(
        str(destination_path)
    )
