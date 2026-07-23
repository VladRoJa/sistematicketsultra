from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Callable

from playwright.sync_api import sync_playwright

from .contracts import ProviderRuntimeConfig


class BrowserPhase(StrEnum):
    CONFIG = "CONFIG"
    BROWSER = "BROWSER"
    LOGIN = "LOGIN"
    NAVIGATION = "NAVIGATION"
    DISCOVERY = "DISCOVERY"
    EXPORT = "EXPORT"
    DOWNLOAD = "DOWNLOAD"
    VALIDATION = "VALIDATION"


class ProviderBrowserError(RuntimeError):
    def __init__(self, *, phase: BrowserPhase, attempts: int) -> None:
        super().__init__(
            f"El provider falló en fase {phase.value} después de {attempts} intento(s)."
        )
        self.phase = phase
        self.attempts = attempts


@dataclass(frozen=True, slots=True)
class BrowserExecutionResult:
    value: Any
    attempts: int
    elapsed_seconds: float


class BrowserPhaseTracker:
    def __init__(self) -> None:
        self.phase = BrowserPhase.BROWSER

    def set(self, phase: BrowserPhase) -> None:
        self.phase = phase


class BrowserRuntime:
    def __init__(
        self,
        config: ProviderRuntimeConfig,
        *,
        playwright_factory: Callable[[], Any] = sync_playwright,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._config = config
        self._playwright_factory = playwright_factory
        self._sleeper = sleeper

    @staticmethod
    def _close(resource: Any) -> None:
        if resource is None:
            return
        try:
            resource.close()
        except Exception:
            pass

    def run(
        self,
        operation: Callable[[Any, BrowserPhaseTracker, int], Any],
    ) -> BrowserExecutionResult:
        started = time.monotonic()
        last_phase = BrowserPhase.CONFIG
        for attempt in range(1, self._config.max_attempts + 1):
            manager = browser = context = page = None
            tracker = BrowserPhaseTracker()
            try:
                manager = self._playwright_factory()
                playwright = manager.start()
                browser = playwright.chromium.launch(headless=self._config.headless)
                context = browser.new_context(accept_downloads=True)
                page = context.new_page()
                page.set_default_timeout(self._config.timeout_ms)
                page.set_default_navigation_timeout(self._config.timeout_ms)
                value = operation(page, tracker, attempt)
                return BrowserExecutionResult(
                    value=value,
                    attempts=attempt,
                    elapsed_seconds=round(time.monotonic() - started, 3),
                )
            except Exception as exc:
                last_phase = tracker.phase
                if getattr(exc, "provider_retryable", True) is False:
                    try:
                        exc.attempts = attempt
                    except Exception:
                        pass
                    raise
                if attempt >= self._config.max_attempts:
                    if getattr(
                        exc,
                        "provider_preserve_on_exhaustion",
                        False,
                    ):
                        try:
                            exc.attempts = attempt
                        except Exception:
                            pass
                        raise
                    raise ProviderBrowserError(
                        phase=last_phase,
                        attempts=attempt,
                    ) from None
            finally:
                self._close(page)
                self._close(context)
                self._close(browser)
                if manager is not None:
                    try:
                        manager.stop()
                    except Exception:
                        pass
            self._sleeper(min(0.25 * attempt, 1.0))
        raise ProviderBrowserError(
            phase=last_phase,
            attempts=self._config.max_attempts,
        )
