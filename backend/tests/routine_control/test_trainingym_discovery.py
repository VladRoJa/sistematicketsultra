from __future__ import annotations

import json
import inspect
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.routine_control.providers.runtime import (
    BrowserExecutionResult,
    BrowserPhase,
    BrowserRuntime,
    ProviderBrowserError,
)
from app.routine_control.providers.trainingym.discovery import (
    DiscoveryObservation,
    TrainingymDiscoveryService,
    sanitize_discovery_texts,
    sanitized_url_path,
)


USER_SELECTOR = 'input[placeholder="Usuario*"]'
PASSWORD_SELECTOR = 'input[placeholder="Contraseña*"]'
COOKIE_SELECTOR = "#hs-eu-confirmation-button"
LOGIN_SELECTOR = "#tg-login-accept"
CENTER_INPUT_SELECTOR = (
    "nz-select-top-control input.ant-select-selection-search-input"
)
CENTER_OPTIONS_SELECTOR = (
    "nz-option-item,[role='option'],.ant-select-item-option"
)


class _Tracker:
    def __init__(self) -> None:
        self.phase = BrowserPhase.BROWSER

    def set(self, phase: BrowserPhase) -> None:
        self.phase = phase


class _FakeLocator:
    def __init__(self, page: "_FakePage", selector: str) -> None:
        self.page = page
        self.selector = selector

    def count(self) -> int:
        if self.selector == COOKIE_SELECTOR:
            return 1 if self.page.cookie_is_visible() else 0
        if self.selector in self.page.missing_selectors:
            return 0
        if self.selector == CENTER_INPUT_SELECTOR:
            return 1 if self.page.center_input_visible else 0
        if self.selector == CENTER_OPTIONS_SELECTOR:
            return len(self.page.center_options) if self.page.center_opened else 0
        if self.selector.startswith("table,tbody"):
            return 1 if self.page.grid_present else 0
        if self.selector in (USER_SELECTOR, PASSWORD_SELECTOR, LOGIN_SELECTOR):
            return 1 if self.page.controls_rendered else 0
        return 1

    def is_visible(self) -> bool:
        if self.selector == COOKIE_SELECTOR:
            return self.page.cookie_is_visible()
        return self.count() > 0

    def click(self) -> None:
        self.page.clicks.append(self.selector)
        if self.selector == COOKIE_SELECTOR:
            self.page.cookie_dismissed = True
        elif self.selector == CENTER_INPUT_SELECTOR:
            self.page.center_opened = True
        elif self.selector == LOGIN_SELECTOR:
            self.page.submit_count += 1

    def fill(self, value: str) -> None:
        self.page.fills[self.selector] = value
        self.page.fill_calls.append((self.selector, value))

    def evaluate(self, script: str):
        self.page.locator_evaluations.append((self.selector, script))
        return bool(self.page.fills.get(self.selector))

    def wait_for(self, *, state: str) -> None:
        self.page.locator_waits.append((self.selector, state))
        if self.selector == COOKIE_SELECTOR:
            if state == "hidden" and not self.page.cookie_is_visible():
                return
            raise PlaywrightTimeoutError("cookie timeout")
        if state != "visible":
            return
        if self.selector == "body":
            self.page.events.append("body-visible")
            return
        if self.selector == CENTER_INPUT_SELECTOR:
            if (
                self.page.center_input_visible
                and self.selector not in self.page.missing_selectors
            ):
                return
            raise PlaywrightTimeoutError("center selector timeout")
        if self.selector in self.page.missing_selectors:
            raise PlaywrightTimeoutError("selector timeout")
        if not self.page.controls_rendered:
            if self.page.render_controls_on_wait:
                self.page.controls_rendered = True
            else:
                raise PlaywrightTimeoutError("render timeout")
        if self.selector == LOGIN_SELECTOR:
            self.page.login_controls_waited = True

    def all(self):
        if self.selector != CENTER_OPTIONS_SELECTOR or not self.page.center_opened:
            return []
        return [
            _FakeOption(self.page, option_text)
            for option_text in self.page.center_options
        ]


class _FakeOption:
    def __init__(self, page: "_FakePage", text: str) -> None:
        self.page = page
        self.text = text

    def is_visible(self) -> bool:
        return True

    def inner_text(self) -> str:
        return self.text

    def click(self) -> None:
        self.page.option_clicks.append(self.text)
        self.page.selected_center = self.text


class _FakePage:
    def __init__(
        self,
        *,
        cookies_present: bool = True,
        transition: bool = True,
        missing_selectors: set[str] | None = None,
        controls: tuple[str, ...] = ("Workout", "Centros"),
        grid_present: bool = False,
        login_enabled: bool = True,
        discovery_error: bool = False,
        controls_rendered: bool = True,
        render_controls_on_wait: bool = True,
        cookie_after_controls: bool = False,
        auth_mode: str | None = None,
        center_selector_delayed: bool = False,
        center_options: tuple[str, ...] = (
            "UltraGym & Fitness - Azahares",
        ),
        center_selection_confirmed: bool = True,
        context_destroyed_after_center_submit: bool = False,
        context_destroyed_on_title_once: bool = False,
        context_destroyed_on_controls_once: bool = False,
    ) -> None:
        self.cookies_present = cookies_present
        self.cookie_after_controls = cookie_after_controls
        self.cookie_dismissed = False
        self.login_controls_waited = False
        self.auth_mode = auth_mode or ("direct" if transition else "rejected")
        self.missing_selectors = missing_selectors or set()
        self.controls = controls
        self.grid_present = grid_present
        self.login_enabled = login_enabled
        self.discovery_error = discovery_error
        self.controls_rendered = controls_rendered
        self.render_controls_on_wait = render_controls_on_wait
        self.center_selector_delayed = center_selector_delayed
        self.center_options = center_options
        self.center_selection_confirmed = center_selection_confirmed
        self.context_destroyed_after_center_submit = (
            context_destroyed_after_center_submit
        )
        self.context_destroyed_on_title_once = context_destroyed_on_title_once
        self.context_destroyed_on_controls_once = context_destroyed_on_controls_once
        self.center_input_visible = False
        self.center_opened = False
        self.selected_center: str | None = None
        self.submit_count = 0
        self._destroyed_after_center_submit = False
        self._destroyed_on_title = False
        self._destroyed_on_controls = False
        self.url = "https://portal.example.invalid/auth"
        self.goto_calls: list[tuple[str, str | None]] = []
        self.load_states: list[str] = []
        self.locator_calls: list[str] = []
        self.clicks: list[str] = []
        self.fills: dict[str, str] = {}
        self.fill_calls: list[tuple[str, str]] = []
        self.option_clicks: list[str] = []
        self.locator_evaluations: list[tuple[str, str]] = []
        self.locator_waits: list[tuple[str, str]] = []
        self.wait_function_scripts: list[str] = []
        self.wait_timeouts: list[int] = []
        self.evaluate_scripts: list[str] = []
        self.screenshots: list[Path] = []
        self.events: list[str] = []
        self.title_calls = 0
        self.closed = False

    def cookie_is_visible(self) -> bool:
        if not self.cookies_present or self.cookie_dismissed:
            return False
        return not self.cookie_after_controls or self.login_controls_waited

    def goto(self, url: str, *, wait_until: str | None = None) -> None:
        self.goto_calls.append((url, wait_until))
        self.url = url

    def wait_for_load_state(self, state: str) -> None:
        self.load_states.append(state)

    def title(self) -> str:
        self.title_calls += 1
        if (
            "/auth" not in self.url
            and self.context_destroyed_on_title_once
            and not self._destroyed_on_title
        ):
            self._destroyed_on_title = True
            raise RuntimeError("Execution context was destroyed during navigation")
        return "Trainingym Manager" if "/auth" in self.url else "Trainingym Dashboard"

    def locator(self, selector: str) -> _FakeLocator:
        self.locator_calls.append(selector)
        return _FakeLocator(self, selector)

    def wait_for_function(self, script: str, *, arg=None) -> None:
        self.wait_function_scripts.append(script)
        if "#tg-login-accept" in script:
            if not self.login_enabled:
                raise PlaywrightTimeoutError("button timeout")
            return
        if "document.querySelectorAll" in script and CENTER_OPTIONS_SELECTOR in script:
            if not self.center_opened or not self.center_options:
                raise PlaywrightTimeoutError("center options timeout")
            return
        if "nz-select-top-control" in script and "expected" in script:
            normalized = " ".join((self.selected_center or "").split()).casefold()
            if (
                not self.center_selection_confirmed
                or not arg
                or arg not in normalized
            ):
                raise PlaywrightTimeoutError("center selection timeout")
            return
        if CENTER_INPUT_SELECTOR in script and "window.location.pathname" in script:
            if self.auth_mode == "rejected":
                raise PlaywrightTimeoutError("authentication outcome timeout")
            if self.auth_mode == "direct":
                self.url = "https://portal.example.invalid/?token=private#section"
                return
            if self.auth_mode == "center":
                self.center_input_visible = True
                if self.center_selector_delayed:
                    self.events.append("center-selector-delayed")
                return
            raise AssertionError(f"Unsupported auth mode: {self.auth_mode}")
        if "window.location.pathname" in script:
            if self.auth_mode == "direct" and "/auth" not in self.url:
                return
            if self.auth_mode == "center" and self.submit_count >= 2:
                self.url = "https://portal.example.invalid/?token=private#section"
                if (
                    self.context_destroyed_after_center_submit
                    and not self._destroyed_after_center_submit
                ):
                    self._destroyed_after_center_submit = True
                    raise RuntimeError(
                        "Execution context was destroyed during navigation"
                    )
                return
            raise PlaywrightTimeoutError("navigation timeout")
        if "document.readyState" in script:
            self.events.append("document-stable")
            return

    def wait_for_timeout(self, milliseconds: int) -> None:
        self.wait_timeouts.append(milliseconds)

    def evaluate(self, script: str):
        self.evaluate_scripts.append(script)
        self.events.append("controls-read")
        if (
            self.context_destroyed_on_controls_once
            and not self._destroyed_on_controls
        ):
            self._destroyed_on_controls = True
            raise RuntimeError("Execution context was destroyed during navigation")
        if self.discovery_error:
            raise RuntimeError("private discovery detail")
        return list(self.controls)

    def screenshot(self, *, path: str, full_page: bool) -> None:
        del full_page
        screenshot = Path(path)
        screenshot.write_bytes(b"private-png")
        self.screenshots.append(screenshot)

    def set_default_timeout(self, _value: int) -> None:
        pass

    def set_default_navigation_timeout(self, _value: int) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class _PageRuntime:
    def __init__(self, _config, page: _FakePage) -> None:
        self.page = page
        self.calls = 0

    def run(self, operation):
        self.calls += 1
        value = operation(self.page, _Tracker(), 1)
        return BrowserExecutionResult(value=value, attempts=1, elapsed_seconds=0.01)


class _NoBrowserRuntime:
    def __init__(self, _config) -> None:
        raise AssertionError("No debe abrirse el browser sin configuración.")


class _BrowserFailureRuntime:
    def __init__(self, _config) -> None:
        pass

    def run(self, _operation):
        raise ProviderBrowserError(phase=BrowserPhase.BROWSER, attempts=2)


class _HarnessContext:
    def __init__(self, page: _FakePage, events: list[str]) -> None:
        self.page = page
        self.events = events

    def new_page(self):
        return self.page

    def close(self) -> None:
        self.events.append("context")


class _HarnessBrowser:
    def __init__(self, page: _FakePage, events: list[str]) -> None:
        self.context = _HarnessContext(page, events)
        self.events = events

    def new_context(self, **_kwargs):
        return self.context

    def close(self) -> None:
        self.events.append("browser")


class _HarnessChromium:
    def __init__(self, page: _FakePage, events: list[str]) -> None:
        self.page = page
        self.events = events

    def launch(self, **_kwargs):
        self.events.append("launch")
        return _HarnessBrowser(self.page, self.events)


class _HarnessPlaywright:
    def __init__(self, page: _FakePage, events: list[str]) -> None:
        self.chromium = _HarnessChromium(page, events)


class _HarnessManager:
    def __init__(self, page: _FakePage, events: list[str]) -> None:
        self.page = page
        self.events = events

    def start(self):
        return _HarnessPlaywright(self.page, self.events)

    def stop(self) -> None:
        self.events.append("manager")


class TrainingymDiscoveryTestCase(unittest.TestCase):
    def _environment(self, artifact_root: str) -> dict[str, str]:
        return {
            "TRAININGYM_LOGIN_URL": "https://portal.example.invalid/auth",
            "TRAININGYM_USER": "trainingym-user-secret",
            "TRAININGYM_PASS": "trainingym-password-secret",
            "TRAININGYM_CENTER_NAME": "UltraGym & Fitness - Azahares",
            "ROUTINE_CONTROL_ARTIFACT_DIR": artifact_root,
        }

    def _run_page(
        self,
        page: _FakePage,
        artifact_root: str,
    ):
        runtime_holder: list[_PageRuntime] = []

        def runtime_factory(config):
            runtime = _PageRuntime(config, page)
            runtime_holder.append(runtime)
            return runtime

        result = TrainingymDiscoveryService(
            runtime_factory=runtime_factory,
        ).run(
            headless=True,
            diagnostic_dir=Path(artifact_root) / "diagnostics",
        )
        return result, runtime_holder[0]

    def test_missing_configuration_is_detected_before_browser(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            result = TrainingymDiscoveryService(
                runtime_factory=_NoBrowserRuntime,
            ).run(headless=True, diagnostic_dir=None)
        self.assertFalse(result.succeeded)
        self.assertEqual(result.error_code, "TRAININGYM_CONFIG_FAILED")
        self.assertIn("TRAININGYM_LOGIN_URL", result.error_message)
        self.assertIn("TRAININGYM_PASS", result.error_message)
        self.assertIn("TRAININGYM_CENTER_NAME", result.error_message)

    def test_missing_center_name_is_config_failure_before_browser(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            environment = self._environment(temp_dir)
            environment.pop("TRAININGYM_CENTER_NAME")
            with patch.dict("os.environ", environment, clear=True):
                result = TrainingymDiscoveryService(
                    runtime_factory=_NoBrowserRuntime,
                ).run(headless=True, diagnostic_dir=None)
        self.assertEqual(result.error_code, "TRAININGYM_CONFIG_FAILED")
        self.assertIn("TRAININGYM_CENTER_NAME", result.error_message)
        self.assertNotIn("trainingym-user-secret", result.error_message)

    def test_la_viga_center_is_rejected_without_echoing_configured_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            environment = self._environment(temp_dir)
            environment["TRAININGYM_CENTER_NAME"] = "  UltraGym - La   Viga "
            with patch.dict("os.environ", environment, clear=True):
                result = TrainingymDiscoveryService(
                    runtime_factory=_NoBrowserRuntime,
                ).run(headless=True, diagnostic_dir=None)
        self.assertEqual(result.error_code, "TRAININGYM_CONFIG_FAILED")
        self.assertIn("TRAININGYM_CENTER_NAME", result.error_message)
        self.assertNotIn("UltraGym", result.error_message)
        self.assertNotIn("La   Viga", result.error_message)

    def test_real_contract_accepts_cookies_and_uses_exact_selectors(self) -> None:
        page = _FakePage(cookies_present=True)
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result, runtime = self._run_page(page, temp_dir)
        self.assertTrue(result.succeeded)
        self.assertEqual(runtime.calls, 1)
        self.assertEqual(
            page.goto_calls,
            [("https://portal.example.invalid/auth", "domcontentloaded")],
        )
        self.assertEqual(
            page.load_states,
            ["domcontentloaded", "domcontentloaded"],
        )
        for selector in (
            COOKIE_SELECTOR,
            USER_SELECTOR,
            PASSWORD_SELECTOR,
            LOGIN_SELECTOR,
        ):
            self.assertIn(selector, page.locator_calls)
        self.assertEqual(
            page.fills,
            {
                USER_SELECTOR: "trainingym-user-secret",
                PASSWORD_SELECTOR: "trainingym-password-secret",
            },
        )
        self.assertEqual(
            page.clicks,
            [COOKIE_SELECTOR, LOGIN_SELECTOR],
        )
        self.assertNotIn("1", page.locator_calls)
        self.assertTrue(
            any("#tg-login-accept" in script for script in page.wait_function_scripts)
        )
        self.assertEqual(
            [
                (USER_SELECTOR, "visible"),
                (PASSWORD_SELECTOR, "visible"),
                (LOGIN_SELECTOR, "visible"),
            ],
            [
                wait
                for wait in page.locator_waits
                if wait[0] in (USER_SELECTOR, PASSWORD_SELECTOR, LOGIN_SELECTOR)
            ],
        )
        self.assertEqual(result.post_login_path, "/")

    def test_direct_authentication_skips_center_selection(self) -> None:
        page = _FakePage(cookies_present=False, auth_mode="direct")
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result, _runtime = self._run_page(page, temp_dir)
        self.assertTrue(result.succeeded)
        self.assertEqual(result.post_login_path, "/")
        self.assertNotIn(CENTER_INPUT_SELECTOR, page.fills)
        self.assertEqual(page.option_clicks, [])
        self.assertEqual(page.clicks.count(LOGIN_SELECTOR), 1)

    def test_center_selection_state_is_supported_while_path_remains_auth(self) -> None:
        page = _FakePage(cookies_present=False, auth_mode="center")
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result, _runtime = self._run_page(page, temp_dir)
        self.assertTrue(result.succeeded)
        self.assertIn(CENTER_INPUT_SELECTOR, page.locator_calls)
        self.assertEqual(
            page.fills[CENTER_INPUT_SELECTOR],
            "UltraGym & Fitness - Azahares",
        )
        self.assertEqual(result.post_login_path, "/")

    def test_delayed_center_selector_is_awaited_deterministically(self) -> None:
        page = _FakePage(
            cookies_present=False,
            auth_mode="center",
            center_selector_delayed=True,
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result, _runtime = self._run_page(page, temp_dir)
        self.assertTrue(result.succeeded)
        self.assertIn("center-selector-delayed", page.events)
        self.assertIn((CENTER_INPUT_SELECTOR, "visible"), page.locator_waits)

    def test_exact_center_option_is_preferred(self) -> None:
        page = _FakePage(
            cookies_present=False,
            auth_mode="center",
            center_options=(
                "Azahares",
                "  UltraGym   & Fitness - AZAHARES ",
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result, _runtime = self._run_page(page, temp_dir)
        self.assertTrue(result.succeeded)
        self.assertEqual(
            page.option_clicks,
            ["  UltraGym   & Fitness - AZAHARES "],
        )

    def test_unique_partial_center_option_is_accepted(self) -> None:
        page = _FakePage(
            cookies_present=False,
            auth_mode="center",
            center_options=(
                "UltraGym & Fitness - Centro",
                "UltraGym & Fitness - Azahares Norte",
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            environment = self._environment(temp_dir)
            environment["TRAININGYM_CENTER_NAME"] = "Azahares"
            with patch.dict("os.environ", environment, clear=True):
                result, _runtime = self._run_page(page, temp_dir)
        self.assertTrue(result.succeeded)
        self.assertEqual(
            page.option_clicks,
            ["UltraGym & Fitness - Azahares Norte"],
        )

    def test_shorter_unique_partial_center_option_is_accepted(self) -> None:
        page = _FakePage(
            cookies_present=False,
            auth_mode="center",
            center_options=("Azahares",),
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result, _runtime = self._run_page(page, temp_dir)
        self.assertTrue(result.succeeded)
        self.assertEqual(page.option_clicks, ["Azahares"])

    def test_missing_center_option_has_semantic_error(self) -> None:
        page = _FakePage(
            cookies_present=False,
            auth_mode="center",
            center_options=("UltraGym & Fitness - Centro",),
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result, _runtime = self._run_page(page, temp_dir)
        self.assertEqual(result.error_code, "TRAININGYM_CENTER_NOT_FOUND")
        self.assertEqual(page.clicks.count(LOGIN_SELECTOR), 1)

    def test_empty_center_options_has_not_found_error(self) -> None:
        page = _FakePage(
            cookies_present=False,
            auth_mode="center",
            center_options=(),
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result, _runtime = self._run_page(page, temp_dir)
        self.assertEqual(result.error_code, "TRAININGYM_CENTER_NOT_FOUND")

    def test_ambiguous_partial_center_option_is_rejected(self) -> None:
        page = _FakePage(
            cookies_present=False,
            auth_mode="center",
            center_options=(
                "UltraGym Azahares Norte",
                "UltraGym Azahares Sur",
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            environment = self._environment(temp_dir)
            environment["TRAININGYM_CENTER_NAME"] = "Azahares"
            with patch.dict("os.environ", environment, clear=True):
                result, _runtime = self._run_page(page, temp_dir)
        self.assertEqual(result.error_code, "TRAININGYM_CENTER_AMBIGUOUS")
        self.assertEqual(page.option_clicks, [])

    def test_center_is_not_selected_by_first_option_index(self) -> None:
        page = _FakePage(
            cookies_present=False,
            auth_mode="center",
            center_options=(
                "UltraGym & Fitness - Centro",
                "UltraGym & Fitness - Azahares",
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result, _runtime = self._run_page(page, temp_dir)
        self.assertTrue(result.succeeded)
        self.assertEqual(
            page.option_clicks,
            ["UltraGym & Fitness - Azahares"],
        )

    def test_center_flow_submits_twice_without_refilling_credentials(self) -> None:
        page = _FakePage(cookies_present=False, auth_mode="center")
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result, _runtime = self._run_page(page, temp_dir)
        self.assertTrue(result.succeeded)
        self.assertEqual(page.clicks.count(LOGIN_SELECTOR), 2)
        self.assertEqual(
            sum(selector == USER_SELECTOR for selector, _value in page.fill_calls),
            1,
        )
        self.assertEqual(
            sum(selector == PASSWORD_SELECTOR for selector, _value in page.fill_calls),
            1,
        )

    def test_center_selection_must_be_visually_confirmed(self) -> None:
        page = _FakePage(
            cookies_present=False,
            auth_mode="center",
            center_selection_confirmed=False,
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result, _runtime = self._run_page(page, temp_dir)
        self.assertEqual(
            result.error_code,
            "TRAININGYM_CENTER_SELECTION_FAILED",
        )
        self.assertEqual(page.clicks.count(LOGIN_SELECTOR), 1)

    def test_disappearing_center_selector_has_contract_error(self) -> None:
        page = _FakePage(
            cookies_present=False,
            auth_mode="center",
            missing_selectors={CENTER_INPUT_SELECTOR},
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result, _runtime = self._run_page(page, temp_dir)
        self.assertEqual(
            result.error_code,
            "TRAININGYM_CENTER_CONTRACT_FAILED",
        )

    def test_center_error_does_not_expose_configuration_or_credentials(self) -> None:
        page = _FakePage(
            cookies_present=False,
            auth_mode="center",
            center_options=(),
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result, _runtime = self._run_page(page, temp_dir)
        payload = json.dumps(result.to_dict(), ensure_ascii=False)
        self.assertEqual(result.error_code, "TRAININGYM_CENTER_NOT_FOUND")
        for sensitive in (
            "UltraGym & Fitness - Azahares",
            "trainingym-user-secret",
            "trainingym-password-secret",
        ):
            self.assertNotIn(sensitive, payload)

    def test_all_browser_resources_close_on_center_error(self) -> None:
        page = _FakePage(
            cookies_present=False,
            auth_mode="center",
            center_options=(),
        )
        events: list[str] = []

        def runtime_factory(config):
            return BrowserRuntime(
                config,
                playwright_factory=lambda: _HarnessManager(page, events),
                sleeper=lambda _seconds: None,
            )

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result = TrainingymDiscoveryService(
                runtime_factory=runtime_factory,
            ).run(
                headless=True,
                diagnostic_dir=Path(temp_dir) / "diagnostics",
            )
        self.assertEqual(result.error_code, "TRAININGYM_CENTER_NOT_FOUND")
        self.assertTrue(page.closed)
        self.assertEqual(events[-3:], ["context", "browser", "manager"])

    def test_context_destruction_after_second_submit_is_tolerated(self) -> None:
        page = _FakePage(
            cookies_present=False,
            auth_mode="center",
            context_destroyed_after_center_submit=True,
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result, _runtime = self._run_page(page, temp_dir)
        self.assertTrue(result.succeeded)
        self.assertEqual(result.post_login_path, "/")
        self.assertEqual(page.clicks.count(LOGIN_SELECTOR), 2)

    def test_context_destruction_during_title_read_rechecks_document(self) -> None:
        page = _FakePage(
            cookies_present=False,
            context_destroyed_on_title_once=True,
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result, _runtime = self._run_page(page, temp_dir)
        self.assertTrue(result.succeeded)
        self.assertEqual(page.events.count("document-stable"), 2)
        self.assertGreaterEqual(page.title_calls, 3)

    def test_context_destruction_during_control_read_restabilizes(self) -> None:
        page = _FakePage(
            cookies_present=False,
            context_destroyed_on_controls_once=True,
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result, _runtime = self._run_page(page, temp_dir)
        self.assertTrue(result.succeeded)
        self.assertEqual(page.events.count("document-stable"), 2)
        self.assertEqual(page.events.count("controls-read"), 2)

    def test_post_login_document_is_stable_before_controls_are_read(self) -> None:
        page = _FakePage(cookies_present=False)
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result, _runtime = self._run_page(page, temp_dir)
        self.assertTrue(result.succeeded)
        self.assertLess(
            page.events.index("document-stable"),
            page.events.index("controls-read"),
        )

    def test_center_contract_uses_only_confirmed_exact_selectors(self) -> None:
        page = _FakePage(cookies_present=False, auth_mode="center")
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result, _runtime = self._run_page(page, temp_dir)
        self.assertTrue(result.succeeded)
        self.assertIn(CENTER_INPUT_SELECTOR, page.locator_calls)
        self.assertIn(CENTER_OPTIONS_SELECTOR, page.locator_calls)
        self.assertNotIn("nz-select", page.locator_calls)

    def test_login_controls_inserted_after_simulated_render_delay(self) -> None:
        page = _FakePage(
            cookies_present=False,
            controls_rendered=False,
            render_controls_on_wait=True,
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result, _runtime = self._run_page(page, temp_dir)
        self.assertTrue(result.succeeded)
        self.assertTrue(page.controls_rendered)
        self.assertIn((USER_SELECTOR, "visible"), page.locator_waits)
        self.assertEqual(page.clicks, [LOGIN_SELECTOR])

    def test_cookie_banner_before_delayed_controls_is_dismissed_first(self) -> None:
        page = _FakePage(
            cookies_present=True,
            controls_rendered=False,
            render_controls_on_wait=True,
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result, _runtime = self._run_page(page, temp_dir)
        self.assertTrue(result.succeeded)
        self.assertEqual(page.clicks, [COOKIE_SELECTOR, LOGIN_SELECTOR])
        self.assertIn((COOKIE_SELECTOR, "hidden"), page.locator_waits)

    def test_cookie_banner_after_controls_is_dismissed_and_controls_reconfirmed(self) -> None:
        page = _FakePage(
            cookies_present=True,
            cookie_after_controls=True,
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result, _runtime = self._run_page(page, temp_dir)
        self.assertTrue(result.succeeded)
        self.assertEqual(page.clicks, [COOKIE_SELECTOR, LOGIN_SELECTOR])
        control_waits = [
            wait
            for wait in page.locator_waits
            if wait[0] in (USER_SELECTOR, PASSWORD_SELECTOR, LOGIN_SELECTOR)
        ]
        self.assertEqual(len(control_waits), 6)

    def test_missing_cookie_banner_does_not_fail(self) -> None:
        page = _FakePage(cookies_present=False)
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result, _runtime = self._run_page(page, temp_dir)
        self.assertTrue(result.succeeded)
        self.assertNotIn(COOKIE_SELECTOR, page.clicks)
        self.assertIn(LOGIN_SELECTOR, page.clicks)

    def test_controls_never_render_fail_after_timeout_with_sanitized_diagnostic(self) -> None:
        page = _FakePage(
            cookies_present=False,
            controls_rendered=False,
            render_controls_on_wait=False,
        )
        events: list[str] = []

        def runtime_factory(config):
            return BrowserRuntime(
                config,
                playwright_factory=lambda: _HarnessManager(page, events),
                sleeper=lambda _seconds: None,
            )

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            {
                **self._environment(temp_dir),
                "ROUTINE_CONTROL_PROVIDER_MAX_ATTEMPTS": "2",
            },
            clear=True,
        ), self.assertLogs(
            "app.routine_control.providers.trainingym.discovery",
            level="WARNING",
        ) as captured:
            result = TrainingymDiscoveryService(
                runtime_factory=runtime_factory,
            ).run(
                headless=True,
                diagnostic_dir=Path(temp_dir) / "diagnostics",
            )
        logs = "\n".join(captured.output)
        self.assertEqual(result.error_code, "TRAININGYM_LOGIN_CONTRACT_FAILED")
        self.assertEqual(result.attempts, 2)
        self.assertEqual(events.count("launch"), 2)
        self.assertIn("title=Trainingym Manager", logs)
        self.assertIn("path=/auth", logs)
        self.assertIn("user_matches=0", logs)
        self.assertIn("elapsed=", logs)
        self.assertIn("phase=LOGIN", logs)
        self.assertNotIn("trainingym-user-secret", logs)
        self.assertNotIn("trainingym-password-secret", logs)
        self.assertEqual(page.fills, {})

    def test_login_render_wait_does_not_use_fixed_sleep(self) -> None:
        source = inspect.getsource(TrainingymDiscoveryService._browser_discovery)
        self.assertNotIn("time.sleep", source)
        self.assertNotIn("wait_for_timeout", source)
        self.assertIn("_wait_for_login_controls", source)

    def test_credentials_are_checked_as_booleans_and_not_returned(self) -> None:
        page = _FakePage()
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result, _runtime = self._run_page(page, temp_dir)
        payload = json.dumps(result.to_dict(), ensure_ascii=False)
        self.assertEqual(
            {selector for selector, _script in page.locator_evaluations},
            {USER_SELECTOR, PASSWORD_SELECTOR},
        )
        for _selector, script in page.locator_evaluations:
            self.assertIn("Boolean(element.value)", script)
        self.assertNotIn("trainingym-user-secret", payload)
        self.assertNotIn("trainingym-password-secret", payload)

    def test_remaining_on_auth_is_login_failed_without_screenshot_or_retry(self) -> None:
        page = _FakePage(transition=False)
        events: list[str] = []

        def runtime_factory(config):
            return BrowserRuntime(
                config,
                playwright_factory=lambda: _HarnessManager(page, events),
                sleeper=lambda _seconds: None,
            )

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            {
                **self._environment(temp_dir),
                "ROUTINE_CONTROL_PROVIDER_MAX_ATTEMPTS": "3",
            },
            clear=True,
        ):
            result = TrainingymDiscoveryService(
                runtime_factory=runtime_factory,
            ).run(
                headless=True,
                diagnostic_dir=Path(temp_dir) / "diagnostics",
            )
        self.assertFalse(result.succeeded)
        self.assertEqual(result.error_code, "TRAININGYM_LOGIN_FAILED")
        self.assertEqual(result.attempts, 1)
        self.assertEqual(events.count("launch"), 1)
        self.assertEqual(page.clicks.count(LOGIN_SELECTOR), 1)
        self.assertEqual(page.screenshots, [])
        self.assertTrue(page.closed)
        self.assertEqual(events[-3:], ["context", "browser", "manager"])

    def test_missing_login_selector_is_contract_failure_after_wait(self) -> None:
        page = _FakePage(missing_selectors={PASSWORD_SELECTOR})
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result, runtime = self._run_page(page, temp_dir)
        self.assertFalse(result.succeeded)
        self.assertEqual(result.error_code, "TRAININGYM_LOGIN_CONTRACT_FAILED")
        self.assertEqual(result.attempts, 1)
        self.assertEqual(runtime.calls, 1)
        self.assertEqual(page.screenshots, [])

    def test_browser_failure_is_not_classified_as_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result = TrainingymDiscoveryService(
                runtime_factory=_BrowserFailureRuntime,
            ).run(
                headless=True,
                diagnostic_dir=Path(temp_dir) / "diagnostics",
            )
        self.assertFalse(result.succeeded)
        self.assertEqual(result.error_code, "TRAININGYM_BROWSER_FAILED")
        self.assertEqual(result.attempts, 2)

    def test_disabled_login_button_is_login_failed_without_click(self) -> None:
        page = _FakePage(login_enabled=False)
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result, _runtime = self._run_page(page, temp_dir)
        self.assertEqual(result.error_code, "TRAININGYM_LOGIN_FAILED")
        self.assertNotIn(LOGIN_SELECTOR, page.clicks)
        self.assertEqual(page.screenshots, [])

    def test_post_login_controls_are_sanitized_bounded_and_skip_grid_screenshot(self) -> None:
        controls = (
            "Workout",
            "Socio socio@example.com",
            "ID 123456789",
            "X" * 121,
            *(f"Button {index}" for index in range(100)),
        )
        page = _FakePage(controls=controls, grid_present=True)
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result, _runtime = self._run_page(page, temp_dir)
        payload = json.dumps(result.to_dict(), ensure_ascii=False)
        self.assertTrue(result.succeeded)
        self.assertLessEqual(len(result.visible_controls), 50)
        self.assertTrue(all(len(value) <= 120 for value in result.visible_controls))
        self.assertNotIn("socio@example.com", payload)
        self.assertNotIn("123456789", payload)
        self.assertEqual(page.screenshots, [])
        self.assertTrue(
            any(
                "element.closest(excluded)" in script
                and "table,tbody" in script
                for script in page.evaluate_scripts
            )
        )

    def test_screenshot_is_post_login_private_and_inside_artifact_root(self) -> None:
        page = _FakePage(grid_present=False)
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result, _runtime = self._run_page(page, temp_dir)
            self.assertTrue(result.succeeded)
            self.assertEqual(len(page.screenshots), 1)
            page.screenshots[0].resolve().relative_to(Path(temp_dir).resolve())
            self.assertEqual(
                result.diagnostic_artifact,
                page.screenshots[0].name,
            )
        self.assertNotIn("/auth", result.post_login_path)

    def test_diagnostic_dir_outside_artifact_root_is_config_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as outside, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result = TrainingymDiscoveryService(
                runtime_factory=_NoBrowserRuntime,
            ).run(headless=True, diagnostic_dir=outside)
        self.assertEqual(result.error_code, "TRAININGYM_CONFIG_FAILED")

    def test_post_login_inspection_error_is_discovery_failed(self) -> None:
        page = _FakePage(discovery_error=True)
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result, _runtime = self._run_page(page, temp_dir)
        self.assertEqual(result.error_code, "TRAININGYM_DISCOVERY_FAILED")
        self.assertNotIn("private discovery detail", result.error_message)

    def test_injected_observation_keeps_path_only_and_removes_pii(self) -> None:
        def discover(_page, _tracker, _attempt, _config, _diagnostic_dir):
            return DiscoveryObservation(
                post_login_url=(
                    "https://portal.example.invalid/dashboard?"
                    "token=trainingym-token-secret"
                ),
                visible_texts=(
                    "Workout",
                    "Socio socio@example.com",
                    "Authorization Bearer abc",
                    "Centro Norte",
                    "ID 123456789",
                    "Workout",
                ),
                diagnostic_artifact="C:/private/diagnostic.png",
            )

        class LocalRuntime:
            def __init__(self, _config) -> None:
                pass

            def run(self, operation):
                value = operation(object(), object(), 1)
                return BrowserExecutionResult(
                    value=value,
                    attempts=1,
                    elapsed_seconds=0.01,
                )

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result = TrainingymDiscoveryService(
                runtime_factory=LocalRuntime,
                discovery_operation=discover,
            ).run(
                headless=True,
                diagnostic_dir=Path(temp_dir) / "diagnostics",
            )
        payload = json.dumps(result.to_dict(), ensure_ascii=False)
        self.assertTrue(result.succeeded)
        self.assertEqual(result.post_login_path, "/dashboard")
        self.assertIn("Workout", result.visible_controls)
        self.assertIn("Centro Norte", result.visible_controls)
        self.assertEqual(result.diagnostic_artifact, "diagnostic.png")
        for secret in (
            "trainingym-token-secret",
            "trainingym-user-secret",
            "trainingym-password-secret",
            "socio@example.com",
            "123456789",
            "C:/private",
        ):
            self.assertNotIn(secret, payload)

    def test_sanitizers_are_bounded(self) -> None:
        values = [f"Button {index}" for index in range(100)]
        self.assertEqual(len(sanitize_discovery_texts(values)), 50)
        self.assertEqual(
            sanitized_url_path("https://example.invalid/a/b?secret=1#fragment"),
            "/a/b",
        )


if __name__ == "__main__":
    unittest.main()
