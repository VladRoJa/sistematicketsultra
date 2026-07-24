from __future__ import annotations

import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.routine_control.providers.runtime import (
    ArtifactStore,
    ArtifactStoreError,
    BrowserPhase,
    BrowserRuntime,
    ProviderArtifact,
    ProviderBrowserError,
    ProviderConfigurationError,
    ProviderExtractionResult,
    ProviderRuntimeConfig,
    provider_lock,
)
from app.routine_control.providers.trainingym_evidence_normalizer import (
    TrainingymNormalizationError,
    load_trainingym_evidence_commands_from_xlsx,
)

from .config import TrainingymProviderConfig
from .discovery import (
    TrainingymDiscoveryError,
    _AUTH_PATH,
    _CREDENTIAL_PRESENT_SCRIPT,
    _EXPECTED_TITLE,
    _LOGIN_ENABLED_SCRIPT,
    _dismiss_cookie_banner,
    _select_configured_center,
    _stabilize_post_login,
    _wait_for_first_auth_outcome,
    _wait_for_login_controls,
    _wait_until_outside_auth,
    sanitized_url_path,
)


TRAININGYM_PROVIDER_KEY = "trainingym"
TRAININGYM_WORKOUT_DATASET_KEY = "workout"
TRAININGYM_WORKOUT_FILENAME = "trainingym-workout.xlsx"
TRAININGYM_WORKOUT_HEADERS = frozenset(
    {
        "id",
        "Idsocioexterno",
        "Email",
        "Técnico",
        "NºRutinas",
        "NºPesajes",
        "Fecha",
        "Centro Origen",
    }
)
_REPORT_PATH = "/reports/workout"
_HOME_PATH = "/trainingym/home"
_ROUTE_STABLE_MS = 1_500
_ROUTE_SETTLE_TIMEOUT_MS = 15_000
_REPORT_RENDER_TIMEOUT_MS = 60_000
_REPORT_SLICER_TIMEOUT_MS = 180_000
_REPORT_SLICER_POLL_MS = 500
_REPORT_HEADER_PATTERNS = (
    re.compile(r"^Email$", re.IGNORECASE),
    re.compile(r"^Técnico$", re.IGNORECASE),
    re.compile(r"^N[º°]Rutinas$", re.IGNORECASE),
    re.compile(r"^N[º°]Pesajes$", re.IGNORECASE),
    re.compile(r"^Valoración$", re.IGNORECASE),
    re.compile(r"^Fecha$", re.IGNORECASE),
    re.compile(r"^Centro Origen$", re.IGNORECASE),
)
_TABLE_READY_HEADER_PATTERNS = (
    re.compile(r"NombreApellidos", re.IGNORECASE),
    re.compile(r"^Email$", re.IGNORECASE),
    re.compile(r"^Técnico$", re.IGNORECASE),
    re.compile(r"^N[º°]Rutinas$", re.IGNORECASE),
    re.compile(r"^N[º°]Pesajes$", re.IGNORECASE),
    re.compile(r"Total Rutinas-Pesaje", re.IGNORECASE),
    re.compile(r"^Valoración$", re.IGNORECASE),
)

_TABLE_READY_MIN_HEADERS = 4
_TABLE_RENDER_TIMEOUT_MS = 240_000
_TABLE_RENDER_POLL_MS = 500
_MENU_RENDER_TIMEOUT_MS = 20_000
_MORE_OPTIONS = re.compile(
    r"^(?:Más opciones|More options)$",
    re.IGNORECASE,
)
_EXPORT_DATA = re.compile(
    r"^(?:Exportar datos|Export data)$",
    re.IGNORECASE,
)
_EXPORT_DIALOG = re.compile(
    r"^¿Qué datos quiere exportar\?$",
    re.IGNORECASE,
)
_CURRENT_LAYOUT = re.compile(
    r"^Datos con diseño actual$",
    re.IGNORECASE,
)
_EXPORT_BUTTON = re.compile(r"^Exportar$", re.IGNORECASE)
_CENTER = re.compile(r"centro", re.IGNORECASE)
_ALL_CENTERS = re.compile(r"^Todas$", re.IGNORECASE)
_ALL_CENTERS_VISIBLE = re.compile(r"\bTodas\b", re.IGNORECASE)
_SET_DATES_SCRIPT = """
({startValue, endValue}) => {
  const inputs = Array.from(
    document.querySelectorAll("input.date-slicer-input")
  );
  if (inputs.length !== 2) {
    return {ok: false, count: inputs.length};
  }
  const setValue = (element, value) => {
    element.focus();
    element.value = value;
    element.dispatchEvent(new Event("input", {bubbles: true}));
    element.dispatchEvent(new Event("change", {bubbles: true}));
    element.dispatchEvent(new Event("blur", {bubbles: true}));
  };
  setValue(inputs[1], endValue);
  setValue(inputs[0], startValue);
  return {
    ok: true,
    startValue: inputs[0].value,
    endValue: inputs[1].value
  };
}
"""
_CENTER_VALUE_SCRIPT = """
(element) => [
  element.innerText,
  element.textContent,
  element.getAttribute("aria-label"),
  element.getAttribute("aria-valuetext"),
  element.value
].join(" ").replace(/\\s+/g, " ").trim()
"""
_DATE_INPUT_SELECTOR = "input.date-slicer-input"
_VISUAL_BY_ID_ANCESTOR = (
    "xpath=ancestor-or-self::*[@data-visual-id][1]"
)
_VISUAL_CONTAINER_ANCESTOR = (
    "xpath=ancestor-or-self::div[contains(@class,'visualContainer')][1]"
)
_EXPORT_TEST_ID_SELECTOR = "button[data-testid='export-btn']"
_EXPORT_ARIA_SELECTOR = "button[aria-label='Exportar']"


class TrainingymWorkoutExtractionError(RuntimeError):
    provider_retryable = False

    def __init__(self, error_code: str, error_message: str) -> None:
        super().__init__(error_message)
        self.error_code = error_code
        self.attempts = 1


DownloadOperation = Callable[
    [
        object,
        object,
        TrainingymProviderConfig,
        date,
        date,
        Path,
    ],
    str,
]
Normalizer = Callable[..., object]


def _unique_visible(locator):
    visible = [candidate for candidate in locator.all() if candidate.is_visible()]
    return visible[0] if len(visible) == 1 else None


def _first_visible(locator):
    for candidate in locator.all():
        if candidate.is_visible():
            return candidate
    return None


def _authenticate_trainingym(
    page,
    tracker,
    config: TrainingymProviderConfig,
) -> None:
    tracker.set(BrowserPhase.NAVIGATION)
    page.goto(config.login_url, wait_until="domcontentloaded")
    page.wait_for_load_state("domcontentloaded")
    if (
        sanitized_url_path(page.url) != _AUTH_PATH
        or page.title().strip() != _EXPECTED_TITLE
    ):
        raise TrainingymDiscoveryError(
            "TRAININGYM_NAVIGATION_FAILED",
            "La página inicial no coincide con el contrato Trainingym comprobado.",
            retryable=True,
        )

    tracker.set(BrowserPhase.LOGIN)
    _dismiss_cookie_banner(page)
    user_field, password_field, submit = _wait_for_login_controls(page)
    if _dismiss_cookie_banner(page):
        user_field, password_field, submit = _wait_for_login_controls(page)
    user_field.fill(config.user)
    password_field.fill(config.password)
    if not bool(user_field.evaluate(_CREDENTIAL_PRESENT_SCRIPT)) or not bool(
        password_field.evaluate(_CREDENTIAL_PRESENT_SCRIPT)
    ):
        raise TrainingymDiscoveryError(
            "TRAININGYM_LOGIN_FAILED",
            "Los controles de login no conservaron las credenciales requeridas.",
        )
    try:
        page.wait_for_function(_LOGIN_ENABLED_SCRIPT)
    except PlaywrightTimeoutError as exc:
        raise TrainingymDiscoveryError(
            "TRAININGYM_LOGIN_FAILED",
            "El botón de acceso no quedó habilitado.",
        ) from exc
    submit.click()

    auth_outcome = _wait_for_first_auth_outcome(page)
    if auth_outcome == "CENTER_SELECTION":
        if not config.center_name:
            raise TrainingymDiscoveryError(
                "TRAININGYM_CONFIG_FAILED",
                "Falta la variable de entorno: TRAININGYM_CENTER_NAME",
            )
        _select_configured_center(page, config.center_name)
    _wait_until_outside_auth(page)
    _stabilize_post_login(page)

def _wait_for_stable_path(
    page,
    expected_path: str,
    *,
    timeout_ms: int = _ROUTE_SETTLE_TIMEOUT_MS,
    stable_ms: int = _ROUTE_STABLE_MS,
) -> bool:
    deadline = time.monotonic() + (timeout_ms / 1000)
    stable_since: float | None = None

    while time.monotonic() < deadline:
        current_path = sanitized_url_path(page.url)

        if current_path == expected_path:
            if stable_since is None:
                stable_since = time.monotonic()

            stable_elapsed_ms = (
                time.monotonic() - stable_since
            ) * 1000

            if stable_elapsed_ms >= stable_ms:
                try:
                    page.locator("body").wait_for(
                        state="visible",
                        timeout=1_000,
                    )
                except Exception:
                    pass

                return True
        else:
            stable_since = None

        page.wait_for_timeout(100)

    return False

def _navigate_to_workout(
    page,
    config: TrainingymProviderConfig,
):
    if not config.workout_url:
        raise TrainingymWorkoutExtractionError(
            "TRAININGYM_WORKOUT_CONFIG_FAILED",
            "Falta la variable de entorno: TRAININGYM_WORKOUT_URL",
        )

    # El login de Trainingym puede dejar pendiente un redirect tardío
    # hacia /trainingym/home. Esperamos a que Home se estabilice antes
    # de intentar abrir Workout.
    current_path = sanitized_url_path(page.url)

    if current_path == _HOME_PATH:
        if not _wait_for_stable_path(page, _HOME_PATH):
            raise TrainingymWorkoutExtractionError(
                "TRAININGYM_WORKOUT_NAVIGATION_FAILED",
                "Trainingym no estabilizó la navegación posterior al login.",
            )

    # Si el primer intento es sobrescrito por el redirect tardío,
    # esperamos nuevamente Home y repetimos sólo la navegación.
    # Nunca repetimos credenciales ni selección de centro.
    for navigation_attempt in range(1, 3):
        try:
            page.goto(
                config.workout_url,
                wait_until="domcontentloaded",
            )
        except Exception:
            # Puede ocurrir ERR_ABORTED o destrucción temporal del contexto
            # mientras la SPA sustituye el documento. Evaluamos el path real.
            pass

        if _wait_for_stable_path(
            page,
            _REPORT_PATH,
            timeout_ms=_ROUTE_SETTLE_TIMEOUT_MS,
        ):
            return

        current_path = sanitized_url_path(page.url)

        if (
            navigation_attempt == 1
            and current_path == _HOME_PATH
        ):
            if not _wait_for_stable_path(page, _HOME_PATH):
                break

            continue

        break

    raise TrainingymWorkoutExtractionError(
        "TRAININGYM_WORKOUT_NAVIGATION_FAILED",
        "Trainingym regresó a Home antes de estabilizar Workout.",
    )


def _is_powerbi_report_frame(frame) -> bool:
    parsed = urlsplit(str(frame.url or ""))
    return (
        (parsed.hostname or "").casefold() == "app.powerbi.com"
        and "reportembed" in parsed.path.casefold()
    )


def _find_report_frame(page):
    deadline = time.monotonic() + (_REPORT_RENDER_TIMEOUT_MS / 1000)

    while time.monotonic() < deadline:
        # Camino principal: Playwright ya registró el frame navegado.
        for frame in page.frames:
            if _is_powerbi_report_frame(frame):
                return frame

        # Fallback: resolver el ElementHandle del iframe y luego su Frame.
        for iframe_locator in page.locator("iframe").all():
            handle = None

            try:
                handle = iframe_locator.element_handle()

                if handle is None:
                    continue

                content_frame = handle.content_frame()

                if (
                    content_frame is not None
                    and _is_powerbi_report_frame(content_frame)
                ):
                    return content_frame

            except Exception:
                # El iframe puede estar reemplazándose mientras Power BI carga.
                continue

            finally:
                if handle is not None:
                    try:
                        handle.dispose()
                    except Exception:
                        pass

        page.wait_for_timeout(250)

    raise TrainingymWorkoutExtractionError(
        "TRAININGYM_WORKOUT_VISUAL_NOT_FOUND",
        "No apareció el frame reportEmbed de Power BI.",
    )

def _wait_for_date_controls(
    frame,
    *,
    timeout_ms: int = _REPORT_SLICER_TIMEOUT_MS,
):
    deadline = time.monotonic() + (timeout_ms / 1000)
    last_visible_count = 0

    while time.monotonic() < deadline:
        try:
            controls = [
                control
                for control in frame.locator(
                    _DATE_INPUT_SELECTOR
                ).all()
                if control.is_visible()
            ]
        except Exception:
            # Power BI puede reemplazar su DOM durante el render inicial.
            controls = []

        last_visible_count = len(controls)

        if last_visible_count == 2:
            return controls[0], controls[1]

        frame.page.wait_for_timeout(
            _REPORT_SLICER_POLL_MS
        )

    raise TrainingymWorkoutExtractionError(
        "TRAININGYM_WORKOUT_FILTER_CONTRACT_FAILED",
        (
            "Workout no presentó dos date-slicer-input visibles "
            "después de esperar la carga del reporte "
            f"(detectados: {last_visible_count})."
        ),
    )

def _date_controls(frame):
    controls = [
        control
        for control in frame.locator(_DATE_INPUT_SELECTOR).all()
        if control.is_visible()
    ]
    if len(controls) != 2:
        raise TrainingymWorkoutExtractionError(
            "TRAININGYM_WORKOUT_FILTER_CONTRACT_FAILED",
            "Workout no presentó exactamente dos date-slicer-input visibles.",
        )
    return controls[0], controls[1]


def _set_date_controls(frame, date_from: date, date_to: date) -> None:
    _wait_for_date_controls(frame)
    start_value = date_from.strftime("%d/%m/%Y")
    end_value = date_to.strftime("%d/%m/%Y")
    result = dict(
        frame.evaluate(
            _SET_DATES_SCRIPT,
            {
                "startValue": start_value,
                "endValue": end_value,
            },
        )
        or {}
    )
    if (
        not result.get("ok")
        or result.get("startValue") != start_value
        or result.get("endValue") != end_value
    ):
        raise TrainingymWorkoutExtractionError(
            "TRAININGYM_WORKOUT_FILTER_CONTRACT_FAILED",
            "Los filtros de fecha no conservaron los valores DD/MM/YYYY.",
        )


def _center_filter(frame):
    by_role = _unique_visible(
        frame.get_by_role("combobox", name=_CENTER)
    )
    if by_role is not None:
        return by_role
    by_label = _unique_visible(frame.get_by_label(_CENTER))
    if by_label is not None:
        return by_label
    candidates = _unique_visible(
        frame.locator(
            "[aria-label*='centro' i],[title*='centro' i]"
        )
    )
    if candidates is not None:
        return candidates
    raise TrainingymWorkoutExtractionError(
        "TRAININGYM_WORKOUT_FILTER_CONTRACT_FAILED",
        "No se identificó inequívocamente el filtro Centro.",
    )


def _select_all_centers(frame, control) -> None:
    try:
        current = str(control.evaluate(_CENTER_VALUE_SCRIPT) or "")
    except Exception:
        current = ""
    if _ALL_CENTERS_VISIBLE.search(current):
        return

    control.click()
    option = _unique_visible(
        frame.get_by_role("option", name=_ALL_CENTERS)
    )
    if option is None:
        option = _unique_visible(
            frame.get_by_role("menuitem", name=_ALL_CENTERS)
        )
    if option is None:
        option = _unique_visible(frame.get_by_text(_ALL_CENTERS, exact=True))
    if option is None:
        raise TrainingymWorkoutExtractionError(
            "TRAININGYM_WORKOUT_FILTER_CONTRACT_FAILED",
            "No apareció la opción Todas del filtro Centro.",
        )
    option.click()
    try:
        selected = str(control.evaluate(_CENTER_VALUE_SCRIPT) or "")
    except Exception as exc:
        raise TrainingymWorkoutExtractionError(
            "TRAININGYM_WORKOUT_FILTER_CONTRACT_FAILED",
            "No se pudo confirmar visualmente el filtro Centro.",
        ) from exc
    if not _ALL_CENTERS_VISIBLE.search(selected):
        visible_value = _unique_visible(
            frame.get_by_text(_ALL_CENTERS, exact=True)
        )
        if visible_value is None:
            raise TrainingymWorkoutExtractionError(
                "TRAININGYM_WORKOUT_FILTER_CONTRACT_FAILED",
                "El filtro Centro no quedó en Todas.",
            )


def _configure_filters(
    frame,
    date_from: date,
    date_to: date,
) -> None:
    _set_date_controls(frame, date_from, date_to)
    _select_all_centers(frame, _center_filter(frame))
    _wait_for_table_headers(frame)


def _wait_for_table_headers(
    frame,
    *,
    timeout_ms: int = _TABLE_RENDER_TIMEOUT_MS,
):
    print("⏳ [TG] Esperando render de la tabla Workout...")

    deadline = time.monotonic() + (timeout_ms / 1000)
    last_detected = 0

    while time.monotonic() < deadline:
        detected = []

        for pattern in _TABLE_READY_HEADER_PATTERNS:
            try:
                header = _first_visible(
                    frame.get_by_text(
                        pattern,
                        exact=False,
                    )
                )
            except Exception:
                # Power BI puede reemplazar nodos durante el refresh.
                header = None

            if header is not None:
                detected.append(header)

        last_detected = len(detected)

        if last_detected >= _TABLE_READY_MIN_HEADERS:
            print(
                "✅ [TG] Tabla lista: "
                f"{last_detected} encabezados detectados."
            )
            return detected

        frame.page.wait_for_timeout(
            _TABLE_RENDER_POLL_MS
        )

    raise TrainingymWorkoutExtractionError(
        "TRAININGYM_WORKOUT_VISUAL_NOT_FOUND",
        (
            "La tabla Workout no terminó de renderizar "
            f"(encabezados detectados: {last_detected})."
        ),
    )

def _find_tabular_visual(frame):
    headers = _wait_for_table_headers(frame)

    for anchor in headers:
        try:
            visual = _first_visible(
                anchor.locator(
                    _VISUAL_BY_ID_ANCESTOR
                )
            )

            if visual is not None:
                print(
                    "✅ [TG] Visual tabular resuelto "
                    "mediante data-visual-id."
                )
                return visual
        except Exception:
            pass

    for anchor in headers:
        try:
            visual = _first_visible(
                anchor.locator(
                    _VISUAL_CONTAINER_ANCESTOR
                )
            )

            if visual is not None:
                print(
                    "✅ [TG] Visual tabular resuelto "
                    "mediante visualContainer."
                )
                return visual
        except Exception:
            pass

    raise TrainingymWorkoutExtractionError(
        "TRAININGYM_WORKOUT_VISUAL_NOT_FOUND",
        "No se resolvió el contenedor del visual tabular.",
    )


def _semantic_locator(scope, *, role: str, name: re.Pattern[str]):
    by_role = _unique_visible(scope.get_by_role(role, name=name))
    if by_role is not None:
        return by_role
    if role == "button":
        by_title = _unique_visible(scope.get_by_title(name))
        if by_title is not None:
            return by_title
    return None


def _open_export_dialog(frame, visual) -> None:
    print(
        "➡ [TG] Activando controles del visual tabular..."
    )

    try:
        visual.scroll_into_view_if_needed()
    except Exception:
        pass

    try:
        visual.hover()
    except Exception as exc:
        raise TrainingymWorkoutExtractionError(
            "TRAININGYM_WORKOUT_MENU_NOT_FOUND",
            "No fue posible activar el visual tabular.",
        ) from exc

    deadline = time.monotonic() + (
        _MENU_RENDER_TIMEOUT_MS / 1000
    )
    menu = None

    while time.monotonic() < deadline:
        menu = _semantic_locator(
            visual,
            role="button",
            name=_MORE_OPTIONS,
        )

        if menu is None:
            menu = _semantic_locator(
                frame,
                role="button",
                name=_MORE_OPTIONS,
            )

        if menu is not None:
            break

        # El toolbar puede desaparecer si Power BI refresca.
        try:
            visual.hover()
        except Exception:
            pass

        frame.page.wait_for_timeout(250)

    if menu is None:
        raise TrainingymWorkoutExtractionError(
            "TRAININGYM_WORKOUT_MENU_NOT_FOUND",
            "No apareció el botón Más opciones del visual.",
        )

    print("➡ [TG] Abriendo Más opciones...")
    menu.click()

    deadline = time.monotonic() + (
        _MENU_RENDER_TIMEOUT_MS / 1000
    )
    export_data = None

    while time.monotonic() < deadline:
        export_data = _semantic_locator(
            frame,
            role="menuitem",
            name=_EXPORT_DATA,
        )

        if export_data is None:
            export_data = _first_visible(
                frame.get_by_text(
                    _EXPORT_DATA,
                    exact=False,
                )
            )

        if export_data is not None:
            break

        frame.page.wait_for_timeout(200)

    if export_data is None:
        raise TrainingymWorkoutExtractionError(
            "TRAININGYM_WORKOUT_MENU_NOT_FOUND",
            "No apareció la acción Exportar datos.",
        )

    print("➡ [TG] Seleccionando Exportar datos...")
    export_data.click()


def _export_button(scope):
    by_test_id = _unique_visible(scope.locator(_EXPORT_TEST_ID_SELECTOR))
    if by_test_id is not None:
        return by_test_id
    by_aria = _unique_visible(scope.locator(_EXPORT_ARIA_SELECTOR))
    if by_aria is not None:
        return by_aria
    by_role = _semantic_locator(
        scope,
        role="button",
        name=_EXPORT_BUTTON,
    )
    if by_role is not None:
        return by_role
    return _unique_visible(scope.get_by_text(_EXPORT_BUTTON, exact=True))


def _find_export_dialog(page):
    deadline = time.monotonic() + (_REPORT_RENDER_TIMEOUT_MS / 1000)
    while time.monotonic() < deadline:
        for frame in page.frames:
            heading = _first_visible(
                frame.get_by_text(_EXPORT_DIALOG, exact=True)
            )
            dialog = _unique_visible(
                frame.get_by_role("dialog").filter(has_text=_EXPORT_DIALOG)
            )
            frame_button = _export_button(frame)
            if heading is not None or dialog is not None or frame_button is not None:
                scope = dialog or frame
                button = _export_button(scope)
                if button is None:
                    button = frame_button
                if button is not None:
                    return scope, button
        page.wait_for_timeout(250)
    raise TrainingymWorkoutExtractionError(
        "TRAININGYM_WORKOUT_EXPORT_DIALOG_FAILED",
        "No apareció el diálogo de exportación comprobado.",
    )


def _dialog_controls(page):
    scope, export_button = _find_export_dialog(page)
    current_layout = _semantic_locator(
        scope,
        role="radio",
        name=_CURRENT_LAYOUT,
    )
    if current_layout is not None:
        current_layout.check()
    else:
        current_layout_text = _unique_visible(
            scope.get_by_text(_CURRENT_LAYOUT, exact=True)
        )
        if current_layout_text is None:
            raise TrainingymWorkoutExtractionError(
                "TRAININGYM_WORKOUT_EXPORT_DIALOG_FAILED",
                "No apareció la opción Datos con diseño actual.",
            )
        current_layout_text.click()

    return export_button


def _safe_source_filename(value: object) -> str:
    del value
    return TRAININGYM_WORKOUT_FILENAME


def _download_workout(
    page,
    frame,
    partial_path: Path,
) -> str:
    visual = _find_tabular_visual(frame)
    _open_export_dialog(frame, visual)
    export_button = _dialog_controls(page)
    try:
        with page.expect_download() as download_info:
            export_button.click()
        download = download_info.value
        download.save_as(str(partial_path))
    except Exception as exc:
        raise TrainingymWorkoutExtractionError(
            "TRAININGYM_WORKOUT_DOWNLOAD_FAILED",
            "No fue posible completar la descarga XLSX.",
        ) from exc
    if not partial_path.is_file() or partial_path.stat().st_size <= 0:
        raise TrainingymWorkoutExtractionError(
            "TRAININGYM_WORKOUT_DOWNLOAD_FAILED",
            "La descarga XLSX no produjo un archivo utilizable.",
        )
    return _safe_source_filename(download.suggested_filename)


def _browser_export(
    page,
    tracker,
    config: TrainingymProviderConfig,
    date_from: date,
    date_to: date,
    partial_path: Path,
) -> str:
    _authenticate_trainingym(page, tracker, config)

    tracker.set(BrowserPhase.NAVIGATION)
    _navigate_to_workout(page, config)

    frame = _find_report_frame(page)

    tracker.set(BrowserPhase.EXPORT)
    _configure_filters(frame, date_from, date_to)

    tracker.set(BrowserPhase.DOWNLOAD)

    return _download_workout(
        page,
        frame,
        partial_path,
    )

class TrainingymWorkoutExtractor:
    def __init__(
        self,
        *,
        download_operation: DownloadOperation = _browser_export,
        runtime_factory: Callable[[ProviderRuntimeConfig], BrowserRuntime] = BrowserRuntime,
        normalizer: Normalizer = load_trainingym_evidence_commands_from_xlsx,
        store_factory: Callable[[Path], ArtifactStore] = ArtifactStore,
    ) -> None:
        self._download_operation = download_operation
        self._runtime_factory = runtime_factory
        self._normalizer = normalizer
        self._store_factory = store_factory

    @staticmethod
    def _failed(
        *,
        started: float,
        error_code: str,
        error_message: str,
        attempts: int = 0,
    ) -> ProviderExtractionResult:
        return ProviderExtractionResult(
            succeeded=False,
            artifact=None,
            attempts=attempts,
            elapsed_seconds=round(time.monotonic() - started, 3),
            error_code=error_code,
            error_message=error_message,
        )

    def extract(
        self,
        *,
        date_from: date,
        date_to: date,
        observed_at_utc: datetime,
        headless: bool | None = None,
    ) -> ProviderExtractionResult:
        started = time.monotonic()
        if date_from > date_to:
            return self._failed(
                started=started,
                error_code="INVALID_DATE_RANGE",
                error_message="date_from no puede ser posterior a date_to.",
            )
        if (
            observed_at_utc.tzinfo is None
            or observed_at_utc.utcoffset() is None
        ):
            return self._failed(
                started=started,
                error_code="INVALID_OBSERVED_AT",
                error_message="observed_at_utc debe incluir timezone.",
            )
        try:
            provider_config = TrainingymProviderConfig.from_env(
                require_center=True,
                require_workout=True,
            )
            runtime_config = ProviderRuntimeConfig.from_env(headless=headless)
        except ProviderConfigurationError as exc:
            return self._failed(
                started=started,
                error_code="TRAININGYM_WORKOUT_CONFIG_FAILED",
                error_message=str(exc),
            )

        try:
            store = self._store_factory(runtime_config.artifact_root)
            run_directory = store.create_run_directory(
                provider_key=TRAININGYM_PROVIDER_KEY,
                dataset_key=TRAININGYM_WORKOUT_DATASET_KEY,
            )
            partial_path, final_path = store.prepare_download(
                run_directory=run_directory,
                source_filename=TRAININGYM_WORKOUT_FILENAME,
            )
        except (ArtifactStoreError, OSError):
            return self._failed(
                started=started,
                error_code="TRAININGYM_WORKOUT_VALIDATION_FAILED",
                error_message="No fue posible preparar el artifact Workout.",
            )
        execution = None

        def operation(page, tracker, _attempt):
            return self._download_operation(
                page,
                tracker,
                provider_config,
                date_from,
                date_to,
                partial_path,
            )

        try:
            with provider_lock(
                runtime_config.artifact_root,
                provider_key=TRAININGYM_PROVIDER_KEY,
                dataset_key=TRAININGYM_WORKOUT_DATASET_KEY,
            ):
                execution = self._runtime_factory(runtime_config).run(operation)
                try:
                    self._normalizer(
                        partial_path,
                        observed_at_utc=observed_at_utc,
                        provider_run_id=None,
                    )
                except TrainingymNormalizationError as exc:
                    raise TrainingymWorkoutExtractionError(
                        "TRAININGYM_WORKOUT_VALIDATION_FAILED",
                        "El XLSX descargado no cumple el contrato Trainingym.",
                    ) from exc
                artifact = store.finalize_download(
                    partial_path=partial_path,
                    final_path=final_path,
                    provider_key=TRAININGYM_PROVIDER_KEY,
                    dataset_key=TRAININGYM_WORKOUT_DATASET_KEY,
                    required_headers=TRAININGYM_WORKOUT_HEADERS,
                    extracted_at_utc=observed_at_utc.astimezone(timezone.utc),
                    business_date_from=date_from,
                    business_date_to=date_to,
                    source_filename=_safe_source_filename(execution.value),
                    diagnostic_metadata={
                        "export_contract": "powerbi_current_layout",
                    },
                )
            return ProviderExtractionResult(
                succeeded=True,
                artifact=artifact,
                attempts=execution.attempts,
                elapsed_seconds=execution.elapsed_seconds,
            )
        except TrainingymWorkoutExtractionError as exc:
            store.discard_incomplete(partial_path)
            return self._failed(
                started=started,
                error_code=exc.error_code,
                error_message=str(exc),
                attempts=int(
                    getattr(
                        exc,
                        "attempts",
                        execution.attempts if execution else 1,
                    )
                ),
            )
        except TrainingymDiscoveryError as exc:
            store.discard_incomplete(partial_path)
            return self._failed(
                started=started,
                error_code=exc.error_code,
                error_message=str(exc),
                attempts=int(getattr(exc, "attempts", 1)),
            )
        except ProviderBrowserError as exc:
            store.discard_incomplete(partial_path)
            return self._failed(
                started=started,
                error_code=f"TRAININGYM_{exc.phase.value}_FAILED",
                error_message=str(exc),
                attempts=exc.attempts,
            )
        except (ArtifactStoreError, TrainingymNormalizationError):
            store.discard_incomplete(partial_path)
            return self._failed(
                started=started,
                error_code="TRAININGYM_WORKOUT_VALIDATION_FAILED",
                error_message="El XLSX descargado no es válido.",
                attempts=execution.attempts if execution else 1,
            )
        except Exception:
            store.discard_incomplete(partial_path)
            return self._failed(
                started=started,
                error_code="TRAININGYM_WORKOUT_VALIDATION_FAILED",
                error_message="No fue posible finalizar el artifact Workout.",
                attempts=execution.attempts if execution else 1,
            )
