from __future__ import annotations

import inspect
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.routine_control.providers.runtime import (
    BrowserRuntime,
    ProviderRuntimeConfig,
)
from app.routine_control.providers.trainingym.config import (
    TrainingymProviderConfig,
    TrainingymWorkoutConfigurationError,
)
from app.routine_control.providers.trainingym import workout_discovery as workout
from app.routine_control.providers.trainingym.workout_discovery import (
    TrainingymWorkoutDiscoveryError,
    discover_workout,
)


LOGIN_URL = "https://app.example.invalid/auth"
WORKOUT_URL = (
    "https://app.example.invalid/reports/workout?"
    "accessToken=private-token#not-accepted"
)
VALID_WORKOUT_URL = (
    "https://app.example.invalid/reports/workout?"
    "source=private-token"
)


class _SemanticLocator:
    def __init__(
        self,
        frame: "_Frame",
        *,
        role: str = "",
        name: str = "",
        title: str = "",
    ) -> None:
        self.frame = frame
        self.role = role
        self.name = name
        self.title = title

    def count(self) -> int:
        key = self.name or self.title
        return self.frame.semantic_counts.get(key, 1)

    def is_visible(self) -> bool:
        return True

    def click(self) -> None:
        key = self.name or self.title
        self.frame.clicked_semantic.append((self.role, key))
        self.frame.menu_open = True


class _Frame:
    def __init__(
        self,
        *,
        url: str,
        name: str = "",
        powerbi: bool = False,
        report_controls: bool = False,
        workout_text: bool = False,
        filters: tuple[dict[str, object], ...] = (),
        exports: tuple[dict[str, object], ...] = (),
        menu_items: tuple[str, ...] = (),
    ) -> None:
        self.url = url
        self.name = name
        self.powerbi = powerbi
        self.report_controls = report_controls
        self.workout_text = workout_text
        self.filters = filters
        self.exports = exports
        self.menu_items = menu_items
        self.menu_open = False
        self.clicked_semantic: list[tuple[str, str]] = []
        self.semantic_counts: dict[str, int] = {}
        self.evaluate_scripts: list[str] = []
        self.role_locators: list[tuple[str, str, bool]] = []
        self.title_locators: list[tuple[str, bool]] = []

    def evaluate(self, script: str):
        self.evaluate_scripts.append(script)
        if "contains_powerbi" in script:
            return {
                "contains_powerbi": self.powerbi,
                "contains_report_controls": self.report_controls,
                "contains_workout_text": self.workout_text,
            }
        if "workout_filters" in script:
            return list(self.filters)
        if "workout_export_candidates" in script:
            return list(self.exports)
        if "workout_menu_items" in script:
            return list(self.menu_items) if self.menu_open else []
        raise AssertionError("Unexpected frame script")

    def get_by_role(
        self,
        role: str,
        *,
        name: str,
        exact: bool,
    ) -> _SemanticLocator:
        self.role_locators.append((role, name, exact))
        return _SemanticLocator(self, role=role, name=name)

    def get_by_title(
        self,
        title: str,
        *,
        exact: bool,
    ) -> _SemanticLocator:
        self.title_locators.append((title, exact))
        return _SemanticLocator(self, title=title)


class _BodyLocator:
    def __init__(self, page: "_WorkoutPage") -> None:
        self.page = page

    def wait_for(self, *, state: str) -> None:
        self.page.body_waits.append(state)


class _Keyboard:
    def __init__(self, page: "_WorkoutPage") -> None:
        self.page = page
        self.presses: list[str] = []

    def press(self, key: str) -> None:
        self.presses.append(key)
        if key == "Escape":
            for frame in self.page.frames:
                frame.menu_open = False


class _WorkoutPage:
    def __init__(
        self,
        frames: tuple[_Frame, ...] | None = None,
        *,
        evidence: bool = True,
        path_reached: bool = True,
        context_destroyed_once: bool = False,
    ) -> None:
        main = _Frame(
            url=VALID_WORKOUT_URL,
            report_controls=True,
            workout_text=True,
        )
        self.frames = list(frames or (main,))
        self.main_frame = self.frames[0]
        self.url = "https://app.example.invalid/"
        self.evidence = evidence
        self.path_reached = path_reached
        self.context_destroyed_once = context_destroyed_once
        self._context_destroyed = False
        self.goto_calls: list[tuple[str, str | None]] = []
        self.wait_url_calls: list[str] = []
        self.load_states: list[str] = []
        self.wait_function_scripts: list[str] = []
        self.body_waits: list[str] = []
        self.keyboard = _Keyboard(self)
        self.closed = False

    def goto(self, url: str, *, wait_until: str | None = None) -> None:
        self.goto_calls.append((url, wait_until))
        self.url = (
            url
            if self.path_reached
            else "https://app.example.invalid/unexpected?token=private"
        )
        self.main_frame.url = self.url

    def wait_for_url(self, pattern: str) -> None:
        self.wait_url_calls.append(pattern)
        if not self.path_reached:
            raise PlaywrightTimeoutError("path timeout")

    def wait_for_load_state(self, state: str) -> None:
        self.load_states.append(state)

    def wait_for_function(self, script: str) -> None:
        self.wait_function_scripts.append(script)
        if "document.readyState" in script:
            if self.context_destroyed_once and not self._context_destroyed:
                self._context_destroyed = True
                raise RuntimeError("Execution context was destroyed")
            return
        if "Rutinas y pesajes" in script and not self.evidence:
            raise PlaywrightTimeoutError("evidence timeout")

    def locator(self, selector: str) -> _BodyLocator:
        if selector != "body":
            raise AssertionError("Only body is expected")
        return _BodyLocator(self)

    def set_default_timeout(self, _value: int) -> None:
        pass

    def set_default_navigation_timeout(self, _value: int) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class _HarnessContext:
    def __init__(self, page: _WorkoutPage, events: list[str]) -> None:
        self.page = page
        self.events = events

    def new_page(self) -> _WorkoutPage:
        return self.page

    def close(self) -> None:
        self.events.append("context")


class _HarnessBrowser:
    def __init__(self, page: _WorkoutPage, events: list[str]) -> None:
        self.page = page
        self.events = events

    def new_context(self, **_kwargs) -> _HarnessContext:
        return _HarnessContext(self.page, self.events)

    def close(self) -> None:
        self.events.append("browser")


class _HarnessChromium:
    def __init__(self, page: _WorkoutPage, events: list[str]) -> None:
        self.page = page
        self.events = events

    def launch(self, **_kwargs) -> _HarnessBrowser:
        self.events.append("launch")
        return _HarnessBrowser(self.page, self.events)


class _HarnessPlaywright:
    def __init__(self, page: _WorkoutPage, events: list[str]) -> None:
        self.chromium = _HarnessChromium(page, events)


class _HarnessManager:
    def __init__(self, page: _WorkoutPage, events: list[str]) -> None:
        self.page = page
        self.events = events

    def start(self) -> _HarnessPlaywright:
        return _HarnessPlaywright(self.page, self.events)

    def stop(self) -> None:
        self.events.append("manager")


def _filter(
    *,
    text: str = "",
    placeholder: str = "",
    role: str = "",
    aria_label: str = "",
    input_type: str = "",
    value: str = "",
    kind: str = "label",
) -> dict[str, object]:
    return {
        "aria_label": aria_label,
        "input_type": input_type,
        "kind": kind,
        "placeholder": placeholder,
        "role": role,
        "text": text,
        "value": value,
    }


def _export(
    *,
    text: str = "",
    aria_label: str = "",
    title: str = "",
    role: str = "button",
    visual: str = "",
) -> dict[str, object]:
    return {
        "aria_label": aria_label,
        "role": role,
        "text": text,
        "title": title,
        "visual": visual,
    }


class TrainingymWorkoutDiscoveryTestCase(unittest.TestCase):
    def _environment(self, workout_url: str | None) -> dict[str, str]:
        environment = {
            "TRAININGYM_LOGIN_URL": LOGIN_URL,
            "TRAININGYM_USER": "private-user",
            "TRAININGYM_PASS": "private-password",
            "TRAININGYM_CENTER_NAME": "Configured Center",
        }
        if workout_url is not None:
            environment["TRAININGYM_WORKOUT_URL"] = workout_url
        return environment

    def test_missing_workout_url_is_rejected(self) -> None:
        with patch.dict("os.environ", self._environment(None), clear=True):
            with self.assertRaises(TrainingymWorkoutConfigurationError) as caught:
                TrainingymProviderConfig.from_env(require_workout=True)
        self.assertIn("TRAININGYM_WORKOUT_URL", str(caught.exception))

    def test_workout_url_must_use_https(self) -> None:
        url = "http://app.example.invalid/reports/workout?token=private"
        with patch.dict("os.environ", self._environment(url), clear=True):
            with self.assertRaises(TrainingymWorkoutConfigurationError) as caught:
                TrainingymProviderConfig.from_env(require_workout=True)
        message = str(caught.exception)
        self.assertIn("HTTPS", message)
        self.assertNotIn("private", message)

    def test_workout_url_must_share_login_hostname(self) -> None:
        url = "https://other.example.invalid/reports/workout?token=private"
        with patch.dict("os.environ", self._environment(url), clear=True):
            with self.assertRaises(TrainingymWorkoutConfigurationError) as caught:
                TrainingymProviderConfig.from_env(require_workout=True)
        message = str(caught.exception)
        self.assertIn("hostname", message)
        self.assertNotIn("other.example.invalid", message)
        self.assertNotIn("private", message)

    def test_workout_url_rejects_fragment_without_echoing_it(self) -> None:
        with patch.dict("os.environ", self._environment(WORKOUT_URL), clear=True):
            with self.assertRaises(TrainingymWorkoutConfigurationError) as caught:
                TrainingymProviderConfig.from_env(require_workout=True)
        message = str(caught.exception)
        self.assertIn("fragmentos", message)
        self.assertNotIn("not-accepted", message)
        self.assertNotIn("private-token", message)

    def test_navigation_uses_same_page_and_domcontentloaded(self) -> None:
        page = _WorkoutPage()
        result = discover_workout(page, VALID_WORKOUT_URL)
        self.assertTrue(result.workout_reached)
        self.assertEqual(
            page.goto_calls,
            [(VALID_WORKOUT_URL, "domcontentloaded")],
        )

    def test_navigation_waits_for_workout_path(self) -> None:
        page = _WorkoutPage()
        discover_workout(page, VALID_WORKOUT_URL)
        self.assertEqual(page.wait_url_calls, ["**/reports/workout*"])
        self.assertEqual(page.body_waits, ["visible"])
        self.assertEqual(page.load_states, ["domcontentloaded"])

    def test_spa_context_destruction_is_tolerated(self) -> None:
        page = _WorkoutPage(context_destroyed_once=True)
        result = discover_workout(page, VALID_WORKOUT_URL)
        self.assertTrue(result.workout_reached)
        self.assertEqual(page.load_states, ["domcontentloaded", "domcontentloaded"])

    def test_detects_powerbi_iframe(self) -> None:
        main = _Frame(url=VALID_WORKOUT_URL, workout_text=True)
        embedded = _Frame(
            url="https://app.powerbi.com/reportEmbed?accessToken=secret#page",
            name="report-frame",
        )
        result = discover_workout(
            _WorkoutPage((main, embedded)),
            VALID_WORKOUT_URL,
        )
        self.assertEqual(result.report_mode, "powerbi_iframe")
        self.assertTrue(result.frame_summaries[1].contains_powerbi)

    def test_detects_powerbi_same_dom(self) -> None:
        main = _Frame(
            url=VALID_WORKOUT_URL,
            powerbi=True,
            workout_text=True,
        )
        result = discover_workout(_WorkoutPage((main,)), VALID_WORKOUT_URL)
        self.assertEqual(result.report_mode, "powerbi_same_dom")

    def test_detects_native_dom(self) -> None:
        main = _Frame(
            url=VALID_WORKOUT_URL,
            report_controls=True,
            workout_text=True,
        )
        result = discover_workout(_WorkoutPage((main,)), VALID_WORKOUT_URL)
        self.assertEqual(result.report_mode, "native_dom")

    def test_unknown_mode_is_preserved(self) -> None:
        main = _Frame(url=VALID_WORKOUT_URL)
        result = discover_workout(_WorkoutPage((main,)), VALID_WORKOUT_URL)
        self.assertEqual(result.report_mode, "unknown")
        self.assertTrue(result.workout_reached)

    def test_frame_urls_are_reduced_to_hostname_and_path(self) -> None:
        main = _Frame(url=VALID_WORKOUT_URL, workout_text=True)
        embedded = _Frame(
            url="https://app.powerbi.com/reportEmbed?accessToken=secret#page",
            name="user@example.com",
        )
        result = discover_workout(
            _WorkoutPage((main, embedded)),
            VALID_WORKOUT_URL,
        )
        payload = json.dumps(
            [frame.to_dict() for frame in result.frame_summaries]
        )
        self.assertIn("app.powerbi.com", payload)
        self.assertIn("/reportEmbed", payload)
        self.assertNotIn("accessToken", payload)
        self.assertNotIn("secret", payload)
        self.assertNotIn("user@example.com", payload)

    def test_frame_summaries_are_limited_to_twenty(self) -> None:
        frames = tuple(
            _Frame(url=f"https://frame.example.invalid/{index}")
            for index in range(25)
        )
        result = discover_workout(_WorkoutPage(frames), VALID_WORKOUT_URL)
        self.assertEqual(len(result.frame_summaries), 20)

    def test_identifies_date_filters_and_keeps_only_date_values(self) -> None:
        main = _Frame(
            url=VALID_WORKOUT_URL,
            workout_text=True,
            filters=(
                _filter(
                    aria_label="Fecha inicial",
                    input_type="date",
                    value="2026-07-01",
                    kind="date",
                ),
                _filter(
                    aria_label="Socio",
                    input_type="text",
                    value="private member",
                ),
            ),
        )
        result = discover_workout(_WorkoutPage((main,)), VALID_WORKOUT_URL)
        self.assertEqual(result.filter_controls[0].value, "2026-07-01")
        self.assertEqual(result.filter_controls[1].value, "")

    def test_identifies_center_selector_without_modifying_it(self) -> None:
        main = _Frame(
            url=VALID_WORKOUT_URL,
            workout_text=True,
            filters=(
                _filter(
                    text="Centro Todas",
                    role="combobox",
                    aria_label="Centro",
                    kind="selector",
                ),
            ),
        )
        result = discover_workout(_WorkoutPage((main,)), VALID_WORKOUT_URL)
        control = result.filter_controls[0]
        self.assertEqual(control.aria_label, "Centro")
        self.assertEqual(control.role, "combobox")
        self.assertEqual(main.clicked_semantic, [])

    def test_more_options_is_opened_semantically(self) -> None:
        main = _Frame(
            url=VALID_WORKOUT_URL,
            workout_text=True,
            exports=(
                _export(
                    aria_label="More options",
                    visual="Total Pesajes y Rutinas por Técnico",
                ),
            ),
            menu_items=("Export data", "Show as a table"),
        )
        result = discover_workout(_WorkoutPage((main,)), VALID_WORKOUT_URL)
        self.assertEqual(
            main.role_locators,
            [("button", "More options", True)],
        )
        self.assertEqual(
            main.clicked_semantic,
            [("button", "More options")],
        )
        self.assertEqual(
            result.export_controls[0].selector,
            'role=button[name="More options"]',
        )

    def test_export_data_is_detected_but_never_clicked(self) -> None:
        main = _Frame(
            url=VALID_WORKOUT_URL,
            workout_text=True,
            exports=(
                _export(aria_label="Más opciones"),
                _export(text="Exportar datos"),
                _export(text="Download"),
            ),
            menu_items=("Exportar datos",),
        )
        page = _WorkoutPage((main,))
        result = discover_workout(page, VALID_WORKOUT_URL)
        self.assertTrue(result.export_contract_verified)
        self.assertEqual(
            main.clicked_semantic,
            [("button", "Más opciones")],
        )
        self.assertNotIn(("button", "Exportar datos"), main.clicked_semantic)
        self.assertNotIn(("button", "Download"), main.clicked_semantic)

    def test_options_menu_is_closed_after_inspection(self) -> None:
        main = _Frame(
            url=VALID_WORKOUT_URL,
            workout_text=True,
            exports=(_export(aria_label="More options"),),
            menu_items=("Export data",),
        )
        page = _WorkoutPage((main,))
        discover_workout(page, VALID_WORKOUT_URL)
        self.assertEqual(page.keyboard.presses, ["Escape"])
        self.assertFalse(main.menu_open)

    def test_unverified_export_is_nonfatal(self) -> None:
        result = discover_workout(_WorkoutPage(), VALID_WORKOUT_URL)
        self.assertTrue(result.workout_reached)
        self.assertFalse(result.export_contract_verified)
        self.assertEqual(
            result.workout_error_code,
            "TRAININGYM_WORKOUT_EXPORT_CONTRACT_UNVERIFIED",
        )

    def test_discovery_uses_no_coordinates_indexes_downloads_or_sleeps(self) -> None:
        source = inspect.getsource(workout)
        self.assertNotIn(".mouse", source)
        self.assertNotIn(".nth(", source)
        self.assertNotIn("expect_download", source)
        self.assertNotIn("time.sleep", source)
        self.assertNotIn("networkidle", source)

    def test_dom_scripts_exclude_tables_and_grids(self) -> None:
        self.assertIn("table,tbody", workout._FILTER_CONTROLS_SCRIPT)
        self.assertIn("[role='grid']", workout._FILTER_CONTROLS_SCRIPT)
        self.assertIn("table,tbody", workout._EXPORT_CANDIDATES_SCRIPT)

    def test_workout_discovery_never_takes_screenshots(self) -> None:
        source = inspect.getsource(discover_workout)
        self.assertNotIn("screenshot", source)

    def test_filters_and_exports_are_bounded_to_fifty(self) -> None:
        main = _Frame(
            url=VALID_WORKOUT_URL,
            workout_text=True,
            filters=tuple(
                _filter(aria_label=f"Filter {index}") for index in range(60)
            ),
            exports=tuple(
                _export(aria_label=f"Export {index}") for index in range(60)
            ),
        )
        result = discover_workout(_WorkoutPage((main,)), VALID_WORKOUT_URL)
        self.assertEqual(len(result.filter_controls), 50)
        self.assertEqual(len(result.export_controls), 50)

    def test_navigation_failure_has_workout_error(self) -> None:
        with self.assertRaises(TrainingymWorkoutDiscoveryError) as caught:
            discover_workout(
                _WorkoutPage(path_reached=False),
                VALID_WORKOUT_URL,
            )
        self.assertEqual(
            caught.exception.error_code,
            "TRAININGYM_WORKOUT_NAVIGATION_FAILED",
        )

    def test_missing_report_evidence_has_contract_error(self) -> None:
        with self.assertRaises(TrainingymWorkoutDiscoveryError) as caught:
            discover_workout(
                _WorkoutPage(evidence=False),
                VALID_WORKOUT_URL,
            )
        self.assertEqual(
            caught.exception.error_code,
            "TRAININGYM_WORKOUT_CONTRACT_FAILED",
        )

    def test_workout_error_does_not_repeat_prior_login_and_closes_resources(self) -> None:
        page = _WorkoutPage(evidence=False)
        events: list[str] = []
        login_submissions = 0

        def operation(runtime_page, _tracker, _attempt):
            nonlocal login_submissions
            login_submissions += 1
            return discover_workout(runtime_page, VALID_WORKOUT_URL)

        runtime = BrowserRuntime(
            ProviderRuntimeConfig(
                artifact_root=Path("unused"),
                headless=True,
                timeout_ms=1_000,
                max_attempts=3,
            ),
            playwright_factory=lambda: _HarnessManager(page, events),
            sleeper=lambda _seconds: None,
        )
        with self.assertRaises(TrainingymWorkoutDiscoveryError):
            runtime.run(operation)
        self.assertEqual(login_submissions, 1)
        self.assertTrue(page.closed)
        self.assertEqual(events, ["launch", "context", "browser", "manager"])

    def test_resources_close_on_success(self) -> None:
        page = _WorkoutPage()
        events: list[str] = []
        runtime = BrowserRuntime(
            ProviderRuntimeConfig(
                artifact_root=Path("unused"),
                headless=True,
                timeout_ms=1_000,
                max_attempts=3,
            ),
            playwright_factory=lambda: _HarnessManager(page, events),
            sleeper=lambda _seconds: None,
        )
        result = runtime.run(
            lambda runtime_page, _tracker, _attempt: discover_workout(
                runtime_page,
                VALID_WORKOUT_URL,
            )
        )
        self.assertTrue(result.value.workout_reached)
        self.assertTrue(page.closed)
        self.assertEqual(events, ["launch", "context", "browser", "manager"])


if __name__ == "__main__":
    unittest.main()
