from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlsplit
from uuid import uuid4

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.routine_control.providers.runtime import (
    BrowserPhase,
    BrowserRuntime,
    ProviderBrowserError,
    ProviderConfigurationError,
    ProviderRuntimeConfig,
)

from .config import (
    TrainingymProviderConfig,
    TrainingymWorkoutConfigurationError,
)
from .workout_discovery import (
    TrainingymWorkoutDiscoveryError,
    WorkoutDiscoveryObservation,
    WorkoutExportControl,
    WorkoutFilterControl,
    WorkoutFrameSummary,
    discover_workout,
)


_EMAIL = re.compile(r"\b[^@\s]+@[^@\s]+\.[^@\s]+\b", re.IGNORECASE)
_SENSITIVE = re.compile(
    r"\b(?:bearer|token|password|contraseña|secret|cookie|authorization)\b",
    re.IGNORECASE,
)
_LONG_IDENTIFIER = re.compile(r"\b\d{5,}\b")
_SPACE = re.compile(r"\s+")
_AUTH_PATH = "/auth"
_EXPECTED_TITLE = "Trainingym Manager"
_USER_SELECTOR = 'input[placeholder="Usuario*"]'
_PASSWORD_SELECTOR = 'input[placeholder="Contraseña*"]'
_COOKIE_SELECTOR = "#hs-eu-confirmation-button"
_LOGIN_SELECTOR = "#tg-login-accept"
_CENTER_INPUT_SELECTOR = (
    "nz-select-top-control input.ant-select-selection-search-input"
)
_CENTER_OPTIONS_SELECTOR = (
    "nz-option-item,[role='option'],.ant-select-item-option"
)
_POST_LOGIN_CONTROL_SCRIPT = """
() => {
  const excluded = "table,tbody,[role='grid'],[role='rowgrid'],.grid,[class*='grid']";
  const groups = [
    "nav button,nav a,nav input[placeholder],nav select,nav label,nav [role='menuitem']",
    "aside button,aside a,aside input[placeholder],aside select,aside label,aside [role='menuitem']",
    "header button,header a,header input[placeholder],header select,header label,header [role='menuitem']",
    "menu button,menu a,menu input[placeholder],menu select,menu label,menu [role='menuitem']",
    "button,a,input[placeholder],select,label,[role='menuitem']"
  ];
  const seen = new Set();
  const result = [];
  const visible = (element) => {
    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.visibility !== "hidden" && style.display !== "none"
      && rect.width > 0 && rect.height > 0;
  };
  const textFor = (element) => {
    if (element.matches("input[placeholder]")) {
      return element.getAttribute("placeholder") || "";
    }
    if (element.matches("select")) {
      const labels = Array.from(element.labels || [])
        .map((label) => label.innerText || label.textContent || "")
        .join(" ");
      return labels || element.getAttribute("aria-label") || "";
    }
    return element.innerText || element.textContent
      || element.getAttribute("aria-label") || "";
  };
  for (const selector of groups) {
    for (const element of document.querySelectorAll(selector)) {
      if (seen.has(element) || element.closest(excluded) || !visible(element)) {
        continue;
      }
      seen.add(element);
      const text = textFor(element).replace(/\\s+/g, " ").trim();
      if (text) {
        result.push(text);
      }
      if (result.length >= 80) {
        return result;
      }
    }
  }
  return result;
}
"""
_CREDENTIAL_PRESENT_SCRIPT = "(element) => Boolean(element.value)"
_LOGIN_ENABLED_SCRIPT = """
() => {
  const button = document.querySelector("#tg-login-accept");
  return Boolean(
    button
    && !button.disabled
    && button.getAttribute("aria-disabled") !== "true"
  );
}
"""
_LEFT_AUTH_SCRIPT = "() => window.location.pathname !== '/auth'"
_AUTH_OUTCOME_SCRIPT = f"""
() => (
  window.location.pathname !== "/auth"
  || Boolean(document.querySelector("{_CENTER_INPUT_SELECTOR}"))
)
"""
_CENTER_OPTIONS_VISIBLE_SCRIPT = f"""
() => Array.from(document.querySelectorAll("{_CENTER_OPTIONS_SELECTOR}"))
  .some((element) => {{
    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.visibility !== "hidden"
      && style.display !== "none"
      && rect.width > 0
      && rect.height > 0;
  }})
"""
_CENTER_SELECTION_VISIBLE_SCRIPT = """
(expected) => {
  const container = document.querySelector("nz-select-top-control");
  if (!container) {
    return false;
  }
  const normalize = (value) => String(value || "")
    .trim()
    .replace(/\\s+/g, " ")
    .toLocaleLowerCase();
  return normalize(container.innerText || container.textContent).includes(expected);
}
"""
_DOCUMENT_STABLE_SCRIPT = """
() => (
  document.readyState === "interactive"
  || document.readyState === "complete"
) && Boolean(document.body)
"""
_SCREENSHOT_EXCLUSION_SELECTOR = (
    "table,tbody,[role='grid'],[role='rowgrid'],.grid,[class*='grid']"
)
_LOGIN_CONTROL_SELECTORS = (
    _USER_SELECTOR,
    _PASSWORD_SELECTOR,
    _LOGIN_SELECTOR,
)
LOGGER = logging.getLogger(__name__)


class TrainingymDiscoveryError(RuntimeError):
    def __init__(
        self,
        error_code: str,
        error_message: str,
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(error_message)
        self.error_code = error_code
        self.provider_retryable = retryable
        self.provider_preserve_on_exhaustion = retryable
        self.attempts = 1


@dataclass(frozen=True, slots=True)
class DiscoveryObservation:
    post_login_url: str
    visible_texts: tuple[str, ...]
    diagnostic_artifact: str | None
    workout: WorkoutDiscoveryObservation | None = None


@dataclass(frozen=True, slots=True)
class TrainingymDiscoveryResult:
    succeeded: bool
    post_login_path: str | None
    visible_controls: tuple[str, ...]
    diagnostic_artifact: str | None
    attempts: int
    elapsed_seconds: float
    workout_path: str | None = None
    workout_reached: bool = False
    report_mode: str | None = None
    frame_summaries: tuple[WorkoutFrameSummary, ...] = ()
    filter_controls: tuple[WorkoutFilterControl, ...] = ()
    export_controls: tuple[WorkoutExportControl, ...] = ()
    export_contract_verified: bool = False
    workout_error_code: str | None = None
    error_code: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "attempts": self.attempts,
            "diagnostic_artifact": self.diagnostic_artifact,
            "elapsed_seconds": self.elapsed_seconds,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "export_contract_verified": self.export_contract_verified,
            "export_controls": [
                control.to_dict() for control in self.export_controls
            ],
            "filter_controls": [
                control.to_dict() for control in self.filter_controls
            ],
            "frame_summaries": [
                frame.to_dict() for frame in self.frame_summaries
            ],
            "post_login_path": self.post_login_path,
            "report_mode": self.report_mode,
            "succeeded": self.succeeded,
            "visible_controls": list(self.visible_controls),
            "workout_error_code": self.workout_error_code,
            "workout_path": self.workout_path,
            "workout_reached": self.workout_reached,
        }


def sanitize_discovery_texts(
    values: Iterable[object],
    *,
    limit: int = 50,
) -> tuple[str, ...]:
    sanitized: list[str] = []
    for raw in values:
        value = _SPACE.sub(" ", str(raw or "")).strip()
        if (
            not value
            or len(value) > 120
            or _EMAIL.search(value)
            or _SENSITIVE.search(value)
            or _LONG_IDENTIFIER.search(value)
        ):
            continue
        if value not in sanitized:
            sanitized.append(value)
        if len(sanitized) >= limit:
            break
    return tuple(sanitized)


def sanitized_url_path(value: str) -> str:
    parsed = urlsplit(value)
    path = parsed.path or "/"
    return path[:300]


def _normalize_center_name(value: object) -> str:
    return _SPACE.sub(" ", str(value or "")).strip().casefold()


def _is_execution_context_destroyed(exc: BaseException) -> bool:
    return "execution context was destroyed" in str(exc).casefold()


def _sanitized_title(page) -> str:
    try:
        values = sanitize_discovery_texts((page.title(),), limit=1)
        return values[0] if values else "unavailable"
    except Exception:
        return "unavailable"


def _selector_match_counts(page) -> tuple[int, int, int]:
    counts: list[int] = []
    for selector in _LOGIN_CONTROL_SELECTORS:
        try:
            counts.append(int(page.locator(selector).count()))
        except Exception:
            counts.append(0)
    return counts[0], counts[1], counts[2]


def _wait_for_login_controls(page):
    started = time.monotonic()
    locators = tuple(page.locator(selector) for selector in _LOGIN_CONTROL_SELECTORS)
    try:
        for locator in locators:
            locator.wait_for(state="visible")
    except PlaywrightTimeoutError as exc:
        user_count, password_count, login_count = _selector_match_counts(page)
        LOGGER.warning(
            "Trainingym login controls timeout: title=%s path=%s "
            "user_matches=%s password_matches=%s login_matches=%s "
            "elapsed=%.3f phase=LOGIN",
            _sanitized_title(page),
            sanitized_url_path(page.url),
            user_count,
            password_count,
            login_count,
            time.monotonic() - started,
        )
        raise TrainingymDiscoveryError(
            "TRAININGYM_LOGIN_CONTRACT_FAILED",
            "Los controles de login no aparecieron dentro del timeout configurado.",
            retryable=True,
        ) from exc
    return locators


def _dismiss_cookie_banner(page) -> bool:
    cookies = page.locator(_COOKIE_SELECTOR)
    if cookies.count() <= 0 or not cookies.is_visible():
        return False
    cookies.click()
    cookies.wait_for(state="hidden")
    return True


def _wait_for_first_auth_outcome(page) -> str:
    try:
        page.wait_for_function(_AUTH_OUTCOME_SCRIPT)
    except PlaywrightTimeoutError as exc:
        raise TrainingymDiscoveryError(
            "TRAININGYM_LOGIN_FAILED",
            "Trainingym no confirmó credenciales ni selección de centro.",
        ) from exc
    except Exception as exc:
        if not _is_execution_context_destroyed(exc):
            raise TrainingymDiscoveryError(
                "TRAININGYM_LOGIN_FAILED",
                "Trainingym no confirmó el estado posterior al login.",
            ) from exc
    if sanitized_url_path(page.url) != _AUTH_PATH:
        return "AUTHENTICATED"
    center_input = page.locator(_CENTER_INPUT_SELECTOR)
    try:
        center_input.wait_for(state="visible")
    except PlaywrightTimeoutError as exc:
        raise TrainingymDiscoveryError(
            "TRAININGYM_CENTER_CONTRACT_FAILED",
            "Trainingym permaneció en /auth sin mostrar el selector de centro.",
        ) from exc
    return "CENTER_SELECTION"


def _resolve_center_option(option_locators, center_name: str):
    target = _normalize_center_name(center_name)
    visible_options: list[tuple[str, object]] = []
    for option in option_locators:
        if not option.is_visible():
            continue
        normalized = _normalize_center_name(option.inner_text())
        if normalized:
            visible_options.append((normalized, option))

    exact = [option for normalized, option in visible_options if normalized == target]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise TrainingymDiscoveryError(
            "TRAININGYM_CENTER_AMBIGUOUS",
            "Más de una opción coincide con el centro configurado.",
        )

    partial = [
        option
        for normalized, option in visible_options
        if target in normalized or normalized in target
    ]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        raise TrainingymDiscoveryError(
            "TRAININGYM_CENTER_AMBIGUOUS",
            "Más de una opción coincide parcialmente con el centro configurado.",
        )
    raise TrainingymDiscoveryError(
        "TRAININGYM_CENTER_NOT_FOUND",
        "No existe una opción para el centro configurado.",
    )


def _select_configured_center(page, center_name: str) -> None:
    center_input = page.locator(_CENTER_INPUT_SELECTOR)
    try:
        center_input.wait_for(state="visible")
    except PlaywrightTimeoutError as exc:
        raise TrainingymDiscoveryError(
            "TRAININGYM_CENTER_CONTRACT_FAILED",
            "No apareció el selector de centro comprobado.",
        ) from exc
    center_input.click()
    center_input.fill(center_name)
    try:
        page.wait_for_function(_CENTER_OPTIONS_VISIBLE_SCRIPT)
    except PlaywrightTimeoutError as exc:
        raise TrainingymDiscoveryError(
            "TRAININGYM_CENTER_NOT_FOUND",
            "Trainingym no mostró opciones para el centro configurado.",
        ) from exc
    try:
        selected_option = _resolve_center_option(
            page.locator(_CENTER_OPTIONS_SELECTOR).all(),
            center_name,
        )
        selected_option_name = _normalize_center_name(
            selected_option.inner_text()
        )
        selected_option.click()
        page.wait_for_function(
            _CENTER_SELECTION_VISIBLE_SCRIPT,
            arg=selected_option_name,
        )
    except TrainingymDiscoveryError:
        raise
    except PlaywrightTimeoutError as exc:
        raise TrainingymDiscoveryError(
            "TRAININGYM_CENTER_SELECTION_FAILED",
            "Trainingym no confirmó visualmente el centro seleccionado.",
        ) from exc
    except Exception as exc:
        raise TrainingymDiscoveryError(
            "TRAININGYM_CENTER_SELECTION_FAILED",
            "No fue posible completar la selección del centro configurado.",
        ) from exc

    submit = page.locator(_LOGIN_SELECTOR)
    try:
        submit.wait_for(state="visible")
        page.wait_for_function(_LOGIN_ENABLED_SCRIPT)
        submit.click()
    except PlaywrightTimeoutError as exc:
        raise TrainingymDiscoveryError(
            "TRAININGYM_CENTER_SELECTION_FAILED",
            "El acceso no quedó habilitado después de seleccionar el centro.",
        ) from exc


def _wait_until_outside_auth(page) -> None:
    try:
        page.wait_for_function(_LEFT_AUTH_SCRIPT)
    except PlaywrightTimeoutError as exc:
        if sanitized_url_path(page.url) == _AUTH_PATH:
            raise TrainingymDiscoveryError(
                "TRAININGYM_LOGIN_FAILED",
                "Trainingym no confirmó una transición fuera de /auth.",
            ) from exc
    except Exception as exc:
        if not _is_execution_context_destroyed(exc):
            raise TrainingymDiscoveryError(
                "TRAININGYM_NAVIGATION_FAILED",
                "Falló la navegación posterior al login.",
            ) from exc


def _stabilize_post_login(page) -> tuple[str, str]:
    last_error: BaseException | None = None
    for attempt in range(2):
        try:
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_function(_DOCUMENT_STABLE_SCRIPT)
            page.locator("body").wait_for(state="visible")
            path = sanitized_url_path(page.url)
            if path == _AUTH_PATH:
                raise TrainingymDiscoveryError(
                    "TRAININGYM_LOGIN_FAILED",
                    "Trainingym permaneció en /auth después del acceso.",
                )
            title = _SPACE.sub(" ", page.title()).strip()
            return path, title
        except TrainingymDiscoveryError:
            raise
        except Exception as exc:
            last_error = exc
            if _is_execution_context_destroyed(exc) and attempt == 0:
                continue
            break
    raise TrainingymDiscoveryError(
        "TRAININGYM_DISCOVERY_FAILED",
        "El documento post-login no se estabilizó dentro del timeout.",
    ) from last_error


def _read_stable_post_login(page) -> tuple[str, str, tuple[str, ...]]:
    path, title = _stabilize_post_login(page)
    try:
        controls = tuple(page.evaluate(_POST_LOGIN_CONTROL_SCRIPT) or ())
        return path, title, controls
    except Exception as exc:
        if not _is_execution_context_destroyed(exc):
            raise TrainingymDiscoveryError(
                "TRAININGYM_DISCOVERY_FAILED",
                "No fue posible inspeccionar controles post-login.",
            ) from exc
    path, title = _stabilize_post_login(page)
    try:
        controls = tuple(page.evaluate(_POST_LOGIN_CONTROL_SCRIPT) or ())
    except Exception as exc:
        raise TrainingymDiscoveryError(
            "TRAININGYM_DISCOVERY_FAILED",
            "No fue posible inspeccionar controles post-login.",
        ) from exc
    return path, title, controls


def _resolve_diagnostic_dir(
    artifact_root: Path,
    diagnostic_dir: str | Path | None,
) -> Path:
    root = artifact_root.resolve()
    resolved = (
        Path(diagnostic_dir).resolve()
        if diagnostic_dir is not None
        else (root / "diagnostics").resolve()
    )
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ProviderConfigurationError(
            "diagnostic_dir debe estar dentro de ROUTINE_CONTROL_ARTIFACT_DIR."
        ) from exc
    return resolved


class TrainingymDiscoveryService:
    def __init__(
        self,
        *,
        runtime_factory: Callable[[ProviderRuntimeConfig], BrowserRuntime] = BrowserRuntime,
        discovery_operation: Callable[
            [object, object, int, TrainingymProviderConfig, Path], DiscoveryObservation
        ]
        | None = None,
    ) -> None:
        self._runtime_factory = runtime_factory
        self._discovery_operation = discovery_operation or self._browser_discovery

    @staticmethod
    def _browser_discovery(
        page,
        tracker,
        _attempt: int,
        config: TrainingymProviderConfig,
        diagnostic_dir: Path,
    ) -> DiscoveryObservation:
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

        tracker.set(BrowserPhase.DISCOVERY)
        try:
            post_login_path, title, controls = _read_stable_post_login(page)
            post_login_url = page.url
            visible_texts = (f"title: {title}", f"path: {post_login_path}", *controls)

            screenshot_name = None
            if page.locator(_SCREENSHOT_EXCLUSION_SELECTOR).count() == 0:
                diagnostic_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                screenshot_name = f"trainingym-discovery-{uuid4().hex}.png"
                screenshot_path = diagnostic_dir / screenshot_name
                page.screenshot(path=str(screenshot_path), full_page=False)
                try:
                    screenshot_path.chmod(0o600)
                except OSError:
                    pass
        except TrainingymDiscoveryError:
            raise
        except Exception as exc:
            raise TrainingymDiscoveryError(
                "TRAININGYM_DISCOVERY_FAILED",
                "No fue posible inspeccionar controles post-login.",
            ) from exc
        if not config.workout_url:
            raise TrainingymWorkoutDiscoveryError(
                "TRAININGYM_WORKOUT_CONFIG_FAILED",
                "Falta la variable de entorno: TRAININGYM_WORKOUT_URL",
            )
        try:
            workout = discover_workout(page, config.workout_url)
        except TrainingymWorkoutDiscoveryError as exc:
            exc.post_login_path = post_login_path
            raise
        return DiscoveryObservation(
            post_login_url=post_login_url,
            visible_texts=visible_texts,
            diagnostic_artifact=screenshot_name,
            workout=workout,
        )

    def run(
        self,
        *,
        headless: bool | None,
        diagnostic_dir: str | Path | None,
    ) -> TrainingymDiscoveryResult:
        started = time.monotonic()
        try:
            provider_config = TrainingymProviderConfig.from_env(
                require_center=True,
                require_workout=True,
            )
            runtime_config = ProviderRuntimeConfig.from_env(headless=headless)
            diagnostics = _resolve_diagnostic_dir(
                runtime_config.artifact_root,
                diagnostic_dir,
            )
        except TrainingymWorkoutConfigurationError as exc:
            return TrainingymDiscoveryResult(
                succeeded=False,
                post_login_path=None,
                visible_controls=(),
                diagnostic_artifact=None,
                attempts=0,
                elapsed_seconds=round(time.monotonic() - started, 3),
                workout_error_code="TRAININGYM_WORKOUT_CONFIG_FAILED",
                error_code="TRAININGYM_WORKOUT_CONFIG_FAILED",
                error_message=str(exc),
            )
        except ProviderConfigurationError as exc:
            return TrainingymDiscoveryResult(
                succeeded=False,
                post_login_path=None,
                visible_controls=(),
                diagnostic_artifact=None,
                attempts=0,
                elapsed_seconds=round(time.monotonic() - started, 3),
                error_code="TRAININGYM_CONFIG_FAILED",
                error_message=str(exc),
            )

        def operation(page, tracker, attempt):
            return self._discovery_operation(
                page,
                tracker,
                attempt,
                provider_config,
                diagnostics,
            )

        try:
            execution = self._runtime_factory(runtime_config).run(operation)
            observation = execution.value
            workout = observation.workout
            return TrainingymDiscoveryResult(
                succeeded=True,
                post_login_path=sanitized_url_path(observation.post_login_url),
                visible_controls=sanitize_discovery_texts(
                    observation.visible_texts
                ),
                diagnostic_artifact=(
                    Path(observation.diagnostic_artifact).name
                    if observation.diagnostic_artifact
                    else None
                ),
                attempts=execution.attempts,
                elapsed_seconds=execution.elapsed_seconds,
                workout_path=workout.workout_path if workout else None,
                workout_reached=bool(workout and workout.workout_reached),
                report_mode=workout.report_mode if workout else None,
                frame_summaries=(
                    workout.frame_summaries if workout else ()
                ),
                filter_controls=(
                    workout.filter_controls if workout else ()
                ),
                export_controls=(
                    workout.export_controls if workout else ()
                ),
                export_contract_verified=bool(
                    workout and workout.export_contract_verified
                ),
                workout_error_code=(
                    workout.workout_error_code if workout else None
                ),
            )
        except TrainingymWorkoutDiscoveryError as exc:
            return TrainingymDiscoveryResult(
                succeeded=False,
                post_login_path=getattr(exc, "post_login_path", None),
                visible_controls=(),
                diagnostic_artifact=None,
                attempts=int(getattr(exc, "attempts", 1)),
                elapsed_seconds=round(time.monotonic() - started, 3),
                workout_error_code=exc.error_code,
                error_code=exc.error_code,
                error_message=str(exc),
            )
        except TrainingymDiscoveryError as exc:
            return TrainingymDiscoveryResult(
                succeeded=False,
                post_login_path=None,
                visible_controls=(),
                diagnostic_artifact=None,
                attempts=int(getattr(exc, "attempts", 1)),
                elapsed_seconds=round(time.monotonic() - started, 3),
                error_code=exc.error_code,
                error_message=str(exc),
            )
        except ProviderBrowserError as exc:
            error_codes = {
                BrowserPhase.BROWSER: "TRAININGYM_BROWSER_FAILED",
                BrowserPhase.NAVIGATION: "TRAININGYM_NAVIGATION_FAILED",
                BrowserPhase.LOGIN: "TRAININGYM_LOGIN_FAILED",
                BrowserPhase.DISCOVERY: "TRAININGYM_DISCOVERY_FAILED",
            }
            return TrainingymDiscoveryResult(
                succeeded=False,
                post_login_path=None,
                visible_controls=(),
                diagnostic_artifact=None,
                attempts=exc.attempts,
                elapsed_seconds=round(time.monotonic() - started, 3),
                error_code=error_codes.get(
                    exc.phase,
                    "TRAININGYM_DISCOVERY_FAILED",
                ),
                error_message=str(exc),
            )
