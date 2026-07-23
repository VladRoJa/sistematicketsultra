from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlsplit
from uuid import uuid4

from app.routine_control.providers.runtime import (
    BrowserPhase,
    BrowserRuntime,
    ProviderBrowserError,
    ProviderConfigurationError,
    ProviderRuntimeConfig,
)

from .config import TrainingymProviderConfig


_EMAIL = re.compile(r"\b[^@\s]+@[^@\s]+\.[^@\s]+\b", re.IGNORECASE)
_SENSITIVE = re.compile(
    r"\b(?:bearer|token|password|contraseña|secret|cookie|authorization)\b",
    re.IGNORECASE,
)
_LONG_IDENTIFIER = re.compile(r"\b\d{5,}\b")
_SPACE = re.compile(r"\s+")
_LOGIN_BUTTON = re.compile(
    r"^(?:acceder|iniciar sesi[oó]n|login|sign in)$",
    re.IGNORECASE,
)


class TrainingymDiscoveryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DiscoveryObservation:
    post_login_url: str
    visible_texts: tuple[str, ...]
    diagnostic_artifact: str | None


@dataclass(frozen=True, slots=True)
class TrainingymDiscoveryResult:
    succeeded: bool
    post_login_path: str | None
    visible_controls: tuple[str, ...]
    diagnostic_artifact: str | None
    attempts: int
    elapsed_seconds: float
    error_code: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "attempts": self.attempts,
            "diagnostic_artifact": self.diagnostic_artifact,
            "elapsed_seconds": self.elapsed_seconds,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "post_login_path": self.post_login_path,
            "succeeded": self.succeeded,
            "visible_controls": list(self.visible_controls),
        }


def sanitize_discovery_texts(
    values: Iterable[object],
    *,
    limit: int = 30,
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


def _single_visible(locator, *, description: str):
    visible = [
        locator.nth(index)
        for index in range(locator.count())
        if locator.nth(index).is_visible()
    ]
    if len(visible) != 1:
        raise TrainingymDiscoveryError(
            f"No se detectó un único control de {description}."
        )
    return visible[0]


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
        tracker.set(BrowserPhase.LOGIN)
        page.goto(config.login_url)
        user_field = _single_visible(
            page.locator(
                'input[type="email"], input[autocomplete="username"], '
                'input[name*="user" i]'
            ),
            description="usuario",
        )
        password_field = _single_visible(
            page.locator('input[type="password"]'),
            description="password",
        )
        submit = _single_visible(
            page.get_by_role("button", name=_LOGIN_BUTTON),
            description="envío de login",
        )
        user_field.fill(config.user)
        password_field.fill(config.password)
        submit.click()
        page.wait_for_timeout(1_000)

        tracker.set(BrowserPhase.NAVIGATION)
        visible_texts = tuple(
            page.locator("h1,h2,h3,button,a,label").all_inner_texts()[:60]
        )

        # Nunca conservar credenciales en una captura del formulario.
        for field in (user_field, password_field):
            try:
                if field.is_visible():
                    field.fill("")
            except Exception:
                pass

        diagnostic_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        screenshot_name = f"trainingym-discovery-{uuid4().hex}.png"
        screenshot_path = diagnostic_dir / screenshot_name
        page.screenshot(path=str(screenshot_path), full_page=False)
        try:
            screenshot_path.chmod(0o600)
        except OSError:
            pass
        return DiscoveryObservation(
            post_login_url=page.url,
            visible_texts=visible_texts,
            diagnostic_artifact=screenshot_name,
        )

    def run(
        self,
        *,
        headless: bool | None,
        diagnostic_dir: str | Path | None,
    ) -> TrainingymDiscoveryResult:
        started = time.monotonic()
        try:
            provider_config = TrainingymProviderConfig.from_env()
            runtime_config = ProviderRuntimeConfig.from_env(headless=headless)
        except ProviderConfigurationError as exc:
            return TrainingymDiscoveryResult(
                succeeded=False,
                post_login_path=None,
                visible_controls=(),
                diagnostic_artifact=None,
                attempts=0,
                elapsed_seconds=round(time.monotonic() - started, 3),
                error_code="CONFIG_INVALID",
                error_message=str(exc),
            )
        diagnostics = Path(
            diagnostic_dir
            if diagnostic_dir is not None
            else runtime_config.artifact_root / "diagnostics"
        ).resolve()

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
            )
        except ProviderBrowserError as exc:
            return TrainingymDiscoveryResult(
                succeeded=False,
                post_login_path=None,
                visible_controls=(),
                diagnostic_artifact=None,
                attempts=exc.attempts,
                elapsed_seconds=round(time.monotonic() - started, 3),
                error_code=f"TRAININGYM_{exc.phase.value}_FAILED",
                error_message=str(exc),
            )

