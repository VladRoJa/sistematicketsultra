from __future__ import annotations

import inspect
import json
import shutil
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from openpyxl import Workbook

from app.routine_control.providers.runtime import (
    BrowserExecutionResult,
    BrowserPhase,
    BrowserRuntime,
)
from app.routine_control.providers.trainingym.config import TrainingymProviderConfig
from app.routine_control.providers.trainingym import workout_extractor as extractor
from app.routine_control.providers.trainingym.workout_extractor import (
    TRAININGYM_WORKOUT_FILENAME,
    TrainingymWorkoutExtractionError,
    TrainingymWorkoutExtractor,
)


FIXTURE = Path(__file__).parent / "fixtures" / "trainingym_workout.xlsx"
OBSERVED_AT = datetime(2026, 7, 23, 18, 0, tzinfo=timezone.utc)
DATE_FROM = date(2026, 7, 1)
DATE_TO = date(2026, 7, 23)
HEADERS = (
    "Email Técnico NºRutinas NºPesajes Valoración Fecha Centro Origen"
)


class _Tracker:
    def __init__(self) -> None:
        self.phases: list[BrowserPhase] = []

    def set(self, phase: BrowserPhase) -> None:
        self.phases.append(phase)


class _LocalRuntime:
    def __init__(self, _config) -> None:
        pass

    def run(self, operation):
        value = operation(object(), _Tracker(), 1)
        return BrowserExecutionResult(
            value=value,
            attempts=1,
            elapsed_seconds=0.01,
        )


class _NoBrowserRuntime:
    def __init__(self, _config) -> None:
        raise AssertionError("No debe abrirse Playwright con configuración inválida.")


class _Collection:
    def __init__(self, values=()) -> None:
        self.values = list(values)

    def all(self):
        return list(self.values)

    def filter(self, **_kwargs):
        return self


class _Element:
    def __init__(
        self,
        name: str,
        events: list[str],
        *,
        text: str = "",
        on_click=None,
        page=None,
    ) -> None:
        self.name = name
        self.events = events
        self.text = text or name
        self.on_click = on_click
        self.page = page
        self.checked = False

    def is_visible(self) -> bool:
        return True

    def inner_text(self) -> str:
        return self.text

    def hover(self) -> None:
        self.events.append(f"hover:{self.name}")

    def click(self) -> None:
        if self.name == "Exportar":
            self.events.append(
                f"click:Exportar:inside_expect={bool(self.page.download_active)}"
            )
        else:
            self.events.append(f"click:{self.name}")
        if self.on_click:
            self.on_click()

    def check(self) -> None:
        self.checked = True
        self.events.append(f"check:{self.name}")

    def wait_for(self, **_kwargs) -> None:
        pass


class _DateControl(_Element):
    def __init__(self, name: str, events: list[str]) -> None:
        super().__init__(name, events)
        self.value = ""


class _CenterControl(_Element):
    def __init__(self, events: list[str]) -> None:
        super().__init__("Centro", events)
        self.value = "Azahares"

    def evaluate(self, _script: str):
        return self.value


class _Visual(_Element):
    def __init__(
        self,
        events: list[str],
        *,
        page,
        menu_by_title: bool = False,
        include_headers: bool = True,
    ) -> None:
        super().__init__(
            "visual-tabular",
            events,
            text=HEADERS if include_headers else "Otro visual",
        )
        self.page = page
        self.menu_by_title = menu_by_title
        self.menu = _Element("Más opciones", events)

    def get_by_role(self, role: str, *, name):
        if (
            role == "button"
            and name.search("Más opciones")
            and not self.menu_by_title
        ):
            self.events.append("lookup:visual:Más opciones")
            return _Collection((self.menu,))
        return _Collection()

    def get_by_title(self, title):
        if title.search("Más opciones") and self.menu_by_title:
            self.events.append("lookup:visual-title:Más opciones")
            return _Collection((self.menu,))
        return _Collection()


class _Header(_Element):
    def __init__(
        self,
        name: str,
        events: list[str],
        visual,
        *,
        use_visual_container: bool = False,
    ) -> None:
        super().__init__(name, events)
        self.visual = visual
        self.use_visual_container = use_visual_container

    def locator(self, selector: str):
        if selector == extractor._VISUAL_BY_ID_ANCESTOR:
            return _Collection(
                () if self.use_visual_container else (self.visual,)
            )
        if selector == extractor._VISUAL_CONTAINER_ANCESTOR:
            return _Collection(
                (self.visual,) if self.use_visual_container else ()
            )
        raise AssertionError(f"Unexpected header selector: {selector}")


class _Dialog(_Element):
    def __init__(
        self,
        events: list[str],
        *,
        page,
        current_layout_by_text: bool = False,
    ) -> None:
        super().__init__("dialog", events)
        self.current_layout_by_text = current_layout_by_text
        self.current_layout = _Element("Datos con diseño actual", events)
        self.export_button = _Element(
            "Exportar",
            events,
            page=page,
        )

    def get_by_role(self, role: str, *, name):
        if (
            role == "radio"
            and name.search("Datos con diseño actual")
            and not self.current_layout_by_text
        ):
            return _Collection((self.current_layout,))
        if role == "button" and name.search("Exportar"):
            return _Collection((self.export_button,))
        return _Collection()

    def get_by_title(self, _title):
        return _Collection()

    def locator(self, selector: str):
        if selector in (
            extractor._EXPORT_TEST_ID_SELECTOR,
            extractor._EXPORT_ARIA_SELECTOR,
        ):
            return _Collection((self.export_button,))
        raise AssertionError(f"Unexpected dialog selector: {selector}")

    def get_by_text(self, text, *, exact: bool):
        del exact
        if text.search("Datos con diseño actual"):
            return _Collection((self.current_layout,))
        if text.search("Exportar"):
            return _Collection((self.export_button,))
        return _Collection()


class _Frame:
    def __init__(
        self,
        page,
        *,
        menu_by_title: bool = False,
        include_menu: bool = True,
        include_dialog: bool = True,
        include_visual: bool = True,
        include_dates: bool = True,
        current_layout_by_text: bool = False,
        use_visual_container: bool = False,
        url: str = "https://app.powerbi.com/reportEmbed?reportId=secret",
    ) -> None:
        self.page = page
        self.url = url
        self.events = page.events
        self.start = _DateControl("fecha-inicial", self.events)
        self.end = _DateControl("fecha-final", self.events)
        self.center = _CenterControl(self.events)
        self.all_centers = _Element(
            "Todas",
            self.events,
            on_click=lambda: setattr(self.center, "value", "Todas"),
        )
        self.visual = _Visual(
            self.events,
            page=page,
            menu_by_title=menu_by_title,
        )
        self.other_visual = _Visual(
            self.events,
            page=page,
            include_headers=False,
        )
        self.export_data = _Element("Exportar datos", self.events)
        self.heading = _Element(
            "¿Qué datos quiere exportar?",
            self.events,
        )
        self.dialog = _Dialog(
            self.events,
            page=page,
            current_layout_by_text=current_layout_by_text,
        )
        self.include_menu = include_menu
        self.include_dialog = include_dialog
        self.include_visual = include_visual
        self.include_dates = include_dates
        self.wait_scripts: list[str] = []
        self.headers = {
            text: _Header(
                text,
                self.events,
                self.visual,
                use_visual_container=use_visual_container,
            )
            for text in (
                "Email",
                "Técnico",
                "NºRutinas",
                "NºPesajes",
                "Valoración",
                "Fecha",
                "Centro Origen",
            )
        }

    def evaluate(self, script: str, values=None):
        if "input.date-slicer-input" in script:
            if not self.include_dates:
                return {"ok": False, "count": 0}
            self.end.value = values["endValue"]
            for event_name in ("input", "change", "blur"):
                self.events.append(f"date:fecha-final:{event_name}")
            self.start.value = values["startValue"]
            for event_name in ("input", "change", "blur"):
                self.events.append(f"date:fecha-inicial:{event_name}")
            return {
                "ok": True,
                "startValue": self.start.value,
                "endValue": self.end.value,
            }
        raise AssertionError("Unexpected frame evaluate")

    def wait_for_function(self, script: str) -> None:
        self.wait_scripts.append(script)

    def locator(self, selector: str):
        if selector == extractor._DATE_INPUT_SELECTOR:
            return _Collection(
                (self.start, self.end) if self.include_dates else ()
            )
        if "aria-label*='centro'" in selector:
            return _Collection()
        if selector in (
            extractor._EXPORT_TEST_ID_SELECTOR,
            extractor._EXPORT_ARIA_SELECTOR,
        ):
            return _Collection(
                (self.dialog.export_button,)
                if self.include_dialog
                else ()
            )
        raise AssertionError(f"Unexpected selector: {selector}")

    def get_by_role(self, role: str, *, name=None):
        if role == "combobox" and name.search("Centro"):
            return _Collection((self.center,))
        if role == "option" and name.search("Todas"):
            return _Collection((self.all_centers,))
        if role == "menuitem" and name.search("Exportar datos"):
            return _Collection(
                (self.export_data,) if self.include_menu else ()
            )
        if role == "button" and name is not None and name.search("Exportar"):
            return _Collection(
                (self.dialog.export_button,)
                if self.include_dialog
                else ()
            )
        if role == "dialog":
            return _Collection(
                (self.dialog,) if self.include_dialog else ()
            )
        return _Collection()

    def get_by_label(self, _name):
        return _Collection()

    def get_by_title(self, _name):
        return _Collection()

    def get_by_text(self, text, *, exact: bool):
        del exact
        pattern = getattr(text, "pattern", str(text))
        if hasattr(text, "search") and text.search("Todas"):
            return _Collection((self.all_centers,))
        if hasattr(text, "search") and text.search("Exportar datos"):
            return _Collection(
                (self.export_data,) if self.include_menu else ()
            )
        if "Qué datos quiere exportar" in pattern:
            return _Collection(
                (self.heading,) if self.include_dialog else ()
            )
        if hasattr(text, "search") and text.search("Exportar"):
            return _Collection(
                (self.dialog.export_button,)
                if self.include_dialog
                else ()
            )
        for header_text, header in self.headers.items():
            if hasattr(text, "fullmatch") and text.fullmatch(header_text):
                return _Collection(
                    (header,) if self.include_visual else ()
                )
        return _Collection()

class _IframeHandle:
    def __init__(self, frame) -> None:
        self.frame = frame
        self.disposed = False

    def content_frame(self):
        return self.frame

    def dispose(self) -> None:
        self.disposed = True

class _Iframe(_Element):
    def __init__(self, events: list[str], frame, src: str) -> None:
        super().__init__("iframe", events)
        self.frame = frame
        self.src = src
        self.handle = _IframeHandle(frame)

    def get_attribute(self, name: str):
        return self.src if name == "src" else None

    def element_handle(self):
        return self.handle


class _Download:
    suggested_filename = "sensitive-token-report.xlsx"

    def __init__(self, source: Path) -> None:
        self.source = source
        self.saved_paths: list[Path] = []

    def save_as(self, path: str) -> None:
        target = Path(path)
        shutil.copyfile(self.source, target)
        self.saved_paths.append(target)


class _DownloadInfo:
    def __init__(self, page: "_Page") -> None:
        self.page = page
        self.value = page.download

    def __enter__(self):
        self.page.download_active = True
        self.page.events.append("expect_download:enter")
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        self.page.events.append("expect_download:exit")
        self.page.download_active = False


class _Page:
    def __init__(
        self,
        download_source: Path = FIXTURE,
        *,
        dialog_in_other_frame: bool = False,
        **frame_kwargs,
    ) -> None:
        self.events: list[str] = []
        self.download_active = False
        self.expect_download_timeout = None
        self.download = _Download(download_source)
        self.url = "https://app.example.invalid/reports/bi_routines_weighings"
        self.frame = _Frame(self, **frame_kwargs)
        self.frames = [self.frame]
        if dialog_in_other_frame:
            self.frame.include_dialog = False
            self.dialog_frame = _Frame(
                self,
                include_dates=False,
                include_visual=False,
                include_menu=False,
                include_dialog=True,
                url="https://app.powerbi.com/reportEmbed/dialog",
            )
            self.frames.append(self.dialog_frame)
        else:
            self.dialog_frame = self.frame
        self.iframes: list[_Iframe] = []

    def expect_download(self, *, timeout=None):
        self.expect_download_timeout = timeout
        return _DownloadInfo(self)

    def locator(self, selector: str):
        if selector == "iframe":
            return _Collection(self.iframes)
        if selector == "body":
            return _Element("body", self.events)
        raise AssertionError(f"Unexpected page selector: {selector}")

    def wait_for_timeout(self, _timeout: int) -> None:
        pass

    def goto(self, url: str, *, wait_until: str) -> None:
        self.events.append(f"goto:{url}:{wait_until}")
        self.url = url

    def wait_for_url(self, value: str) -> None:
        self.events.append(f"wait_for_url:{value}")

    def wait_for_load_state(self, value: str) -> None:
        self.events.append(f"wait_for_load_state:{value}")


class _HarnessPage:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def set_default_timeout(self, _value: int) -> None:
        pass

    def set_default_navigation_timeout(self, _value: int) -> None:
        pass

    def close(self) -> None:
        self.events.append("page")


class _HarnessContext:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def new_page(self):
        return _HarnessPage(self.events)

    def close(self) -> None:
        self.events.append("context")


class _HarnessBrowser:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def new_context(self, **_kwargs):
        return _HarnessContext(self.events)

    def close(self) -> None:
        self.events.append("browser")


class _HarnessChromium:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def launch(self, **_kwargs):
        self.events.append("launch")
        return _HarnessBrowser(self.events)


class _HarnessPlaywright:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.chromium = _HarnessChromium(events)

    def stop(self) -> None:
        self.events.append("playwright")


class _HarnessManager:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def start(self):
        return _HarnessPlaywright(self.events)


class TrainingymWorkoutExtractorTestCase(unittest.TestCase):
    def _environment(self, artifact_root: str) -> dict[str, str]:
        return {
            "TRAININGYM_LOGIN_URL": "https://app.example.invalid/auth",
            "TRAININGYM_USER": "trainingym-user-secret",
            "TRAININGYM_PASS": "trainingym-password-secret",
            "TRAININGYM_CENTER_NAME": "Configured Center",
            "TRAININGYM_WORKOUT_URL": (
                "https://app.example.invalid/reports/bi_routines_weighings"
            ),
            "ROUTINE_CONTROL_ARTIFACT_DIR": artifact_root,
        }

    @staticmethod
    def _copy_fixture_operation(
        _page,
        _tracker,
        _config,
        _date_from,
        _date_to,
        partial_path,
    ) -> str:
        partial_path.write_text(
            (
                "\ufeff"
                '"ID";"ID externo";"Socio";"Email";"Edad";"Sexo";'
                '"Empleados";"Workouts";"Pesajes";"Total";"Valoración";'
                '"Fecha";"Centro"\n'
                '"24639860";"88669";"SOCIO PRUEBA";"test@example.com";'
                '"42";"F";"TECNICO PRUEBA";"1";"0";"1";"";'
                '"2026-07-23";"UltraGym Centro"\n'
            ),
            encoding="utf-8",
            newline="",
        )
        return TRAININGYM_WORKOUT_FILENAME

    def _extract(self, temp_dir: str, **kwargs):
        extractor_kwargs = {
            "download_operation": kwargs.get(
                "download_operation",
                self._copy_fixture_operation,
            ),
            "runtime_factory": kwargs.get("runtime_factory", _LocalRuntime),
        }
        if "normalizer" in kwargs:
            extractor_kwargs["normalizer"] = kwargs["normalizer"]
        return TrainingymWorkoutExtractor(
            **extractor_kwargs,
        ).extract(
            date_from=DATE_FROM,
            date_to=DATE_TO,
            observed_at_utc=OBSERVED_AT,
            headless=True,
        )

    def test_native_csv_is_validated_and_stored_as_provider_artifact(self) -> None:
        def native_csv_operation(
            _page,
            _tracker,
            _config,
            _date_from,
            _date_to,
            partial_path,
        ) -> str:
            partial_path.write_text(
                (
                    "\ufeff"
                    '"ID";"ID externo";"Socio";"Email";"Edad";"Sexo";'
                    '"Empleados";"Workouts";"Pesajes";"Total";"Valoración";'
                    '"Fecha";"Centro"\n'
                    '"24639860";"88669";"SOCIO PRUEBA";"test@example.com";'
                    '"42";"F";"TECNICO PRUEBA";"1";"0";"1";"";'
                    '"2026-07-23";"UltraGym Centro"\n'
                ),
                encoding="utf-8",
                newline="",
            )
            return extractor.TRAININGYM_WORKOUT_CSV_FILENAME

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result = TrainingymWorkoutExtractor(
                download_operation=native_csv_operation,
                runtime_factory=_LocalRuntime,
            ).extract(
                date_from=DATE_FROM,
                date_to=DATE_TO,
                observed_at_utc=OBSERVED_AT,
                headless=True,
            )

        self.assertTrue(result.succeeded)
        self.assertIsNotNone(result.artifact)
        self.assertEqual(
            result.artifact.source_filename,
            "trainingym-workout.csv",
        )
        self.assertEqual(
            result.artifact.provider_key,
            "trainingym",
        )
        self.assertEqual(
            result.artifact.dataset_key,
            "workout",
        )
        self.assertEqual(
            result.artifact.local_path.name,
            "trainingym-workout.csv",
        )
        self.assertEqual(
            result.artifact.diagnostic_metadata["export_contract"],
            "tg_native_routines_weighings_csv",
        )

    def test_complete_success_creates_provider_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result = self._extract(temp_dir)
            self.assertTrue(result.succeeded)
            self.assertIsNotNone(result.artifact)
            self.assertTrue(result.artifact.local_path.is_file())
            self.assertEqual(result.artifact.provider_key, "trainingym")
            self.assertEqual(result.artifact.dataset_key, "workout")
            self.assertEqual(
                result.artifact.source_filename,
                TRAININGYM_WORKOUT_FILENAME,
            )
            self.assertNotIn(
                "sensitive-token",
                json.dumps(dict(result.artifact.diagnostic_metadata)),
            )
            artifact_text = result.artifact.local_path.read_text(
                encoding="utf-8-sig",
            )
            self.assertIn(
                '"ID";"ID externo";"Socio";',
                artifact_text,
            )
            self.assertIn(
                '"Workouts";"Pesajes";',
                artifact_text,
            )

    def test_download_is_validated_by_current_normalizer(self) -> None:
        normalizer = Mock(return_value=[])
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result = self._extract(temp_dir, normalizer=normalizer)
        self.assertTrue(result.succeeded)
        normalizer.assert_called_once()
        self.assertEqual(
            normalizer.call_args.kwargs["observed_at_utc"],
            OBSERVED_AT,
        )

    def test_report_frame_is_found_first_in_page_frames(self) -> None:
        page = _Page()
        page.iframes.append(
            _Iframe(
                page.events,
                _Frame(page),
                "https://app.powerbi.com/reportEmbed/fallback",
            )
        )
        self.assertIs(extractor._find_report_frame(page), page.frame)

    def test_report_frame_falls_back_to_dom_iframe_content_frame(self) -> None:
        page = _Page()
        same_origin = _Frame(
            page,
            url="https://app.example.invalid/trainingym",
        )
        powerbi = _Frame(
            page,
            url="https://app.powerbi.com/reportEmbed/view?token=secret",
        )
        page.frames = [same_origin]
        page.iframes = [
            _Iframe(
                page.events,
                powerbi,
                "about:blank",
            )
        ]
        self.assertIs(extractor._find_report_frame(page), powerbi)

    def test_authentication_waits_for_post_login_route_to_settle(self) -> None:
        class Field:
            def fill(self, _value: str) -> None:
                pass

            def evaluate(self, _script) -> bool:
                return True

        class Submit:
            def __init__(self, page) -> None:
                self.page = page

            def click(self) -> None:
                # El login real devuelve primero a la raíz.
                self.page.url = "https://app.example.invalid/"

        class Body:
            def wait_for(self, **_kwargs) -> None:
                pass

        class Page:
            def __init__(self) -> None:
                self.url = "https://app.example.invalid/auth"
                self.elapsed_ms = 0

            def goto(self, url: str, *, wait_until: str) -> None:
                self.url = url

            def wait_for_load_state(self, _state: str) -> None:
                pass

            def wait_for_function(self, _script) -> None:
                pass

            def title(self) -> str:
                return extractor._EXPECTED_TITLE

            def wait_for_timeout(self, milliseconds: int) -> None:
                self.elapsed_ms += milliseconds

                if self.elapsed_ms >= 1_300:
                    self.url = (
                        "https://app.example.invalid/"
                        "trainingym/home"
                    )
                elif self.elapsed_ms >= 400:
                    self.url = (
                        "https://app.example.invalid/"
                        "trainingym"
                    )

            def locator(self, selector: str):
                if selector != "body":
                    raise AssertionError(
                        f"Unexpected selector: {selector}"
                    )
                return Body()

        page = Page()
        tracker = _Tracker()

        config = TrainingymProviderConfig(
            login_url="https://app.example.invalid/auth",
            user="private-user",
            password="private-password",
            center_name="Configured Center",
            workout_url=(
                "https://app.example.invalid/"
                "reports/bi_routines_weighings"
            ),
        )

        user_field = Field()
        password_field = Field()
        submit = Submit(page)

        with (
            patch.object(
                extractor,
                "_dismiss_cookie_banner",
                return_value=False,
            ),
            patch.object(
                extractor,
                "_wait_for_login_controls",
                return_value=(
                    user_field,
                    password_field,
                    submit,
                ),
            ),
            patch.object(
                extractor,
                "_wait_for_first_auth_outcome",
                return_value="DIRECT_AUTH",
            ),
            patch.object(
                extractor,
                "_wait_until_outside_auth",
            ),
            patch.object(
                extractor,
                "_stabilize_post_login",
                return_value=("/", extractor._EXPECTED_TITLE),
            ),
        ):
            extractor._authenticate_trainingym(
                page,
                tracker,
                config,
            )

        self.assertEqual(
            page.url,
            "https://app.example.invalid/trainingym/home",
        )


    def test_navigation_survives_delayed_post_login_home_redirect(self) -> None:
        class Body:
            def wait_for(self, **_kwargs) -> None:
                pass

        class Page:
            def __init__(self) -> None:
                self.url = "https://app.example.invalid/"
                self.events: list[str] = []
                self.elapsed_ms = 0
                self.pending_login_redirect = True

            def goto(self, url: str, *, wait_until: str) -> None:
                self.events.append(
                    f"goto:{url}:{wait_until}"
                )
                self.url = url

            def wait_for_timeout(self, milliseconds: int) -> None:
                self.elapsed_ms += milliseconds

                if (
                    self.pending_login_redirect
                    and self.elapsed_ms >= 1_800
                ):
                    self.url = (
                        "https://app.example.invalid/"
                        "trainingym/home"
                    )
                    self.pending_login_redirect = False

            def locator(self, selector: str):
                if selector != "body":
                    raise AssertionError(
                        f"Unexpected selector: {selector}"
                    )
                return Body()

        page = Page()

        config = TrainingymProviderConfig(
            login_url="https://app.example.invalid/auth",
            user="private-user",
            password="private-password",
            center_name="Configured Center",
            workout_url=(
                "https://app.example.invalid/"
                "reports/bi_routines_weighings"
            ),
        )

        extractor._navigate_to_workout(
            page,
            config,
        )

        # Simula el pequeño intervalo posterior al return.
        # El redirect pendiente del login no debe poder
        # sustituir el reporte después de que navegación
        # haya sido declarada exitosa.
        page.wait_for_timeout(500)

        self.assertEqual(
            page.url,
            config.workout_url,
        )


    def test_home_is_not_an_error_and_navigation_uses_workout_url(self) -> None:
        page = _Page()
        page.url = "https://app.example.invalid/trainingym/home"
        config = TrainingymProviderConfig(
            login_url="https://app.example.invalid/auth",
            user="private-user",
            password="private-password",
            center_name="Configured Center",
            workout_url="https://app.example.invalid/reports/bi_routines_weighings",
        )
        extractor._navigate_to_workout(page, config)
        self.assertEqual(page.url, config.workout_url)
        self.assertIn(
            f"goto:{config.workout_url}:domcontentloaded",
            page.events,
        )

    def test_native_center_selector_waits_for_options_before_select_all(self) -> None:
        events: list[str] = []

        class Page:
            def __init__(self) -> None:
                self.options_ready = False

            def locator(self, selector: str):
                if selector == extractor._CENTER_SELECT_SELECTOR:
                    return Select(self)

                if selector == extractor._CENTER_TOGGLE_ALL_SELECTOR:
                    return Toggle(self)

                if selector == "nz-option-item":
                    return Options(self)

                raise AssertionError(
                    f"Unexpected selector: {selector}"
                )

        class Select:
            def __init__(self, page) -> None:
                self.page = page

            def wait_for(self, **_kwargs) -> None:
                events.append("center:visible")

            def click(self) -> None:
                events.append("center:click")

        class Options:
            def __init__(self, page) -> None:
                self.page = page

            @property
            def first(self):
                return self

            def wait_for(self, **_kwargs) -> None:
                events.append("options:ready")
                self.page.options_ready = True

        class Toggle:
            def __init__(self, page) -> None:
                self.page = page

            def wait_for(self, **_kwargs) -> None:
                events.append("toggle:visible")

            def inner_text(self) -> str:
                if self.page.options_ready:
                    return getattr(
                        self.page,
                        "toggle_text",
                        "Seleccionar todos",
                    )

                return "Seleccionar todos"

            def click(self) -> None:
                if not self.page.options_ready:
                    events.append(
                        "toggle:premature-click"
                    )
                    return

                events.append("toggle:click")
                self.page.toggle_text = "quitar_todos"

        extractor._ensure_all_centers(
            Page()
        )

        self.assertNotIn(
            "toggle:premature-click",
            events,
        )

        self.assertEqual(
            events[:3],
            [
                "center:visible",
                "center:click",
                "options:ready",
            ],
        )


    def test_native_center_selector_ensures_all_centers(self) -> None:
        events: list[str] = []

        class Toggle:
            def __init__(self) -> None:
                self.text = "Seleccionar todos"

            def wait_for(self, **_kwargs) -> None:
                pass

            def inner_text(self) -> str:
                return self.text

            def click(self) -> None:
                events.append("click:select-all")
                self.text = "quitar_todos"

        class Select:
            @property
            def first(self):
                return self

            def wait_for(self, **_kwargs) -> None:
                pass

            def click(self) -> None:
                events.append("click:center-select")

        toggle = Toggle()
        select = Select()

        class Page:
            def locator(self, selector: str):
                if selector == extractor._CENTER_SELECT_SELECTOR:
                    return select
                if selector == extractor._CENTER_TOGGLE_ALL_SELECTOR:
                    return toggle
                if selector == "nz-option-item":
                    return select
                raise AssertionError(f"Unexpected selector: {selector}")

        extractor._ensure_all_centers(Page())

        self.assertEqual(
            events,
            ["click:center-select", "click:select-all"],
        )
        self.assertEqual(
            extractor._normalize_control_text(toggle.inner_text()),
            "quitar todos",
        )

    def test_native_center_selector_does_not_toggle_when_all_are_selected(self) -> None:
        events: list[str] = []

        class Toggle:
            def wait_for(self, **_kwargs) -> None:
                pass

            def inner_text(self) -> str:
                return "quitar_todos"

            def click(self) -> None:
                events.append("click:select-all")

        class Select:
            @property
            def first(self):
                return self

            def wait_for(self, **_kwargs) -> None:
                pass

            def click(self) -> None:
                events.append("click:center-select")

        toggle = Toggle()
        select = Select()

        class Page:
            def locator(self, selector: str):
                if selector == extractor._CENTER_SELECT_SELECTOR:
                    return select
                if selector == extractor._CENTER_TOGGLE_ALL_SELECTOR:
                    return toggle
                if selector == "nz-option-item":
                    return select
                raise AssertionError(f"Unexpected selector: {selector}")

        extractor._ensure_all_centers(Page())

        self.assertEqual(
            events,
            ["click:center-select"],
        )

    def test_native_date_range_uses_calendar_and_navigates_to_target_month(self) -> None:
        events: list[str] = []

        class Input:
            def __init__(
                self,
                name: str,
                value: str,
            ) -> None:
                self.name = name
                self.value = value

            def wait_for(self, **_kwargs) -> None:
                pass

            def click(self) -> None:
                events.append(
                    f"input:click:{self.name}"
                )

            def fill(self, _value: str) -> None:
                raise AssertionError(
                    "El rango nativo no debe usar fill()."
                )

            def input_value(self) -> str:
                return self.value

        start = Input(
            "fecha-inicial",
            "01/08/2026",
        )
        end = Input(
            "fecha-final",
            "31/08/2026",
        )

        class Page:
            def __init__(self) -> None:
                self.left_year = 2026
                self.left_month = 8

            def shift_month(self, delta: int) -> None:
                absolute = (
                    self.left_year * 12
                    + self.left_month
                    - 1
                    + delta
                )

                self.left_year = absolute // 12
                self.left_month = absolute % 12 + 1

            def visible_months(self):
                current = (
                    self.left_year,
                    self.left_month,
                )

                absolute = (
                    self.left_year * 12
                    + self.left_month
                )

                following = (
                    absolute // 12,
                    absolute % 12 + 1,
                )

                return {
                    current,
                    following,
                }

            def locator(self, selector: str):
                if selector == extractor._DATE_RANGE_SELECTOR:
                    return DateRange(self)

                if selector == (
                    ".ant-picker-dropdown:"
                    "not(.ant-picker-dropdown-hidden)"
                ):
                    return Dropdown(self)

                raise AssertionError(
                    f"Unexpected selector: {selector}"
                )

            def wait_for_timeout(
                self,
                _milliseconds: int,
            ) -> None:
                pass

        class DateRange:
            def __init__(self, page) -> None:
                self.page = page

            def wait_for(self, **_kwargs) -> None:
                pass

            def locator(self, selector: str):
                if selector == extractor._DATE_START_SELECTOR:
                    return start

                if selector == extractor._DATE_END_SELECTOR:
                    return end

                raise AssertionError(
                    f"Unexpected selector: {selector}"
                )

        class FirstInViewCell:
            def __init__(self, page) -> None:
                self.page = page

            def get_attribute(self, name: str):
                if name != "title":
                    return None

                return (
                    f"01/{self.page.left_month:02d}/"
                    f"{self.page.left_year:04d}"
                )

        class FirstInViewCells:
            def __init__(self, page) -> None:
                self.page = page

            @property
            def first(self):
                return FirstInViewCell(
                    self.page
                )

        class Panel:
            def __init__(self, page) -> None:
                self.page = page

            def locator(self, selector: str):
                if selector == (
                    "td.ant-picker-cell-in-view[title]"
                ):
                    return FirstInViewCells(
                        self.page
                    )

                raise AssertionError(
                    f"Unexpected panel selector: {selector}"
                )

        class Panels:
            def __init__(self, page) -> None:
                self.page = page

            @property
            def first(self):
                return Panel(
                    self.page
                )

        class DateCell:
            def __init__(
                self,
                page,
                title: str,
            ) -> None:
                self.page = page
                self.title = title

            def is_visible(self) -> bool:
                return True

            def click(self) -> None:
                events.append(
                    f"calendar:click:{self.title}"
                )

                if self.title == "01/07/2026":
                    start.value = self.title

                elif self.title == "23/07/2026":
                    end.value = self.title

        class DateCells:
            def __init__(
                self,
                page,
                title: str,
            ) -> None:
                self.page = page
                self.title = title

            def count(self) -> int:
                _day, month, year = (
                    int(part)
                    for part in self.title.split("/")
                )

                return int(
                    (year, month)
                    in self.page.visible_months()
                )

            @property
            def first(self):
                return DateCell(
                    self.page,
                    self.title,
                )

        class NavigationButton:
            def __init__(
                self,
                page,
                delta: int,
                name: str,
            ) -> None:
                self.page = page
                self.delta = delta
                self.name = name

            @property
            def first(self):
                return self

            def click(self) -> None:
                events.append(
                    f"calendar:{self.name}"
                )
                self.page.shift_month(
                    self.delta
                )

        class Dropdown:
            def __init__(self, page) -> None:
                self.page = page

            def wait_for(self, **_kwargs) -> None:
                pass

            def locator(self, selector: str):
                if selector == ".ant-picker-panel":
                    return Panels(
                        self.page
                    )

                if selector == (
                    ".ant-picker-header-prev-btn:visible"
                ):
                    return NavigationButton(
                        self.page,
                        -1,
                        "previous-month",
                    )

                if selector == (
                    ".ant-picker-header-next-btn:visible"
                ):
                    return NavigationButton(
                        self.page,
                        1,
                        "next-month",
                    )

                prefix = (
                    'td.ant-picker-cell-in-view'
                    '[title="'
                )

                if (
                    selector.startswith(prefix)
                    and selector.endswith('"]')
                ):
                    title = selector[
                        len(prefix):-2
                    ]

                    return DateCells(
                        self.page,
                        title,
                    )

                raise AssertionError(
                    f"Unexpected dropdown selector: {selector}"
                )

        page = Page()

        extractor._set_native_date_range(
            page,
            DATE_FROM,
            DATE_TO,
        )

        self.assertEqual(
            start.value,
            "01/07/2026",
        )
        self.assertEqual(
            end.value,
            "23/07/2026",
        )

        self.assertEqual(
            events,
            [
                "input:click:fecha-inicial",
                "calendar:previous-month",
                "calendar:click:01/07/2026",
                "calendar:click:23/07/2026",
            ],
        )


    def test_native_date_range_fails_if_trainingym_does_not_keep_values(self) -> None:
        class Input:
            def __init__(
                self,
                value: str,
                *,
                persisted_value: str | None = None,
            ) -> None:
                self.value = value
                self.persisted_value = persisted_value

            def wait_for(self, **_kwargs) -> None:
                pass

            def click(self) -> None:
                pass

            def input_value(self) -> str:
                return (
                    self.persisted_value
                    or self.value
                )

        start_input = Input(
            "01/08/2026",
        )

        end_input = Input(
            "31/08/2026",
            persisted_value="31/07/2026",
        )

        class DateRange:
            def wait_for(self, **_kwargs) -> None:
                pass

            def locator(self, selector: str):
                if selector == extractor._DATE_START_SELECTOR:
                    return start_input

                if selector == extractor._DATE_END_SELECTOR:
                    return end_input

                raise AssertionError(
                    f"Unexpected selector: {selector}"
                )

        class FirstCell:
            def get_attribute(self, name: str):
                if name == "title":
                    return "01/07/2026"

                return None

        class FirstCells:
            @property
            def first(self):
                return FirstCell()

        class Panel:
            def locator(self, selector: str):
                if selector == (
                    "td.ant-picker-cell-in-view[title]"
                ):
                    return FirstCells()

                raise AssertionError(
                    f"Unexpected panel selector: {selector}"
                )

        class Panels:
            @property
            def first(self):
                return Panel()

        class DateCell:
            def __init__(self, title: str) -> None:
                self.title = title

            def is_visible(self) -> bool:
                return True

            def click(self) -> None:
                if self.title == "01/07/2026":
                    start_input.value = self.title

                elif self.title == "23/07/2026":
                    end_input.value = self.title

        class DateCells:
            def __init__(self, title: str) -> None:
                self.title = title

            def count(self) -> int:
                return 1

            @property
            def first(self):
                return DateCell(
                    self.title
                )

        class Dropdown:
            def wait_for(self, **_kwargs) -> None:
                pass

            def locator(self, selector: str):
                if selector == ".ant-picker-panel":
                    return Panels()

                prefix = (
                    'td.ant-picker-cell-in-view'
                    '[title="'
                )

                if (
                    selector.startswith(prefix)
                    and selector.endswith('"]')
                ):
                    title = selector[
                        len(prefix):-2
                    ]

                    return DateCells(
                        title
                    )

                raise AssertionError(
                    f"Unexpected dropdown selector: {selector}"
                )

        class Page:
            def locator(self, selector: str):
                if selector == extractor._DATE_RANGE_SELECTOR:
                    return DateRange()

                if selector == (
                    ".ant-picker-dropdown:"
                    "not(.ant-picker-dropdown-hidden)"
                ):
                    return Dropdown()

                raise AssertionError(
                    f"Unexpected selector: {selector}"
                )

            def wait_for_timeout(
                self,
                _milliseconds: int,
            ) -> None:
                pass

        with self.assertRaises(
            TrainingymWorkoutExtractionError
        ) as raised:
            extractor._set_native_date_range(
                Page(),
                DATE_FROM,
                DATE_TO,
            )

        self.assertEqual(
            raised.exception.error_code,
            "TRAININGYM_WORKOUT_FILTER_CONTRACT_FAILED",
        )



    def test_dates_use_exact_slicers_end_first_and_dispatch_events(self) -> None:
        page = _Page()
        extractor._configure_filters(page.frame, DATE_FROM, DATE_TO)
        self.assertEqual(page.frame.start.value, "01/07/2026")
        self.assertEqual(page.frame.end.value, "23/07/2026")
        self.assertLess(
            page.events.index("date:fecha-final:input"),
            page.events.index("date:fecha-inicial:input"),
        )
        self.assertEqual(
            [
                event
                for event in page.events
                if event.startswith("date:")
            ],
            [
                "date:fecha-final:input",
                "date:fecha-final:change",
                "date:fecha-final:blur",
                "date:fecha-inicial:input",
                "date:fecha-inicial:change",
                "date:fecha-inicial:blur",
            ],
        )
        source = inspect.getsource(extractor._set_date_controls)
        self.assertIn("input.date-slicer-input", extractor._SET_DATES_SCRIPT)
        self.assertIn('new Event("input"', extractor._SET_DATES_SCRIPT)
        self.assertIn('new Event("change"', extractor._SET_DATES_SCRIPT)
        self.assertIn('new Event("blur"', extractor._SET_DATES_SCRIPT)
        self.assertNotIn("fill(", source)

    def test_dates_require_exactly_two_date_slicer_inputs(self) -> None:
        page = _Page()
        extra = _DateControl("fecha-extra", page.events)
        original_locator = page.frame.locator

        def locator(selector: str):
            if selector == extractor._DATE_INPUT_SELECTOR:
                return _Collection((page.frame.start, page.frame.end, extra))
            return original_locator(selector)

        page.frame.locator = locator
        with self.assertRaises(TrainingymWorkoutExtractionError) as raised:
            extractor._date_controls(page.frame)
        self.assertEqual(
            raised.exception.error_code,
            "TRAININGYM_WORKOUT_FILTER_CONTRACT_FAILED",
        )

    def test_center_filter_is_left_in_todas(self) -> None:
        page = _Page()
        extractor._configure_filters(page.frame, DATE_FROM, DATE_TO)
        self.assertEqual(page.frame.center.value, "Todas")
        self.assertIn("click:Centro", page.events)
        self.assertIn("click:Todas", page.events)

    def test_table_waits_for_all_headers_and_resolves_data_visual_id(self) -> None:
        page = _Page()
        visual = extractor._find_tabular_visual(page.frame)
        self.assertIs(visual, page.frame.visual)
        self.assertEqual(len(extractor._REPORT_HEADER_PATTERNS), 7)
        self.assertTrue(
            any(
                pattern.fullmatch("N°Rutinas")
                for pattern in extractor._REPORT_HEADER_PATTERNS
            )
        )
        self.assertTrue(
            any(
                pattern.fullmatch("N°Pesajes")
                for pattern in extractor._REPORT_HEADER_PATTERNS
            )
        )

    def test_visual_container_is_used_only_as_ancestor_fallback(self) -> None:
        page = _Page(use_visual_container=True)
        visual = extractor._find_tabular_visual(page.frame)
        self.assertIs(visual, page.frame.visual)

    def test_browser_export_uses_native_trainingym_flow_without_powerbi(self) -> None:
        page = object()
        tracker = _Tracker()

        config = TrainingymProviderConfig(
            login_url="https://app.example.invalid/auth",
            user="private-user",
            password="private-password",
            center_name="Configured Center",
            workout_url=(
                "https://app.example.invalid/"
                "reports/bi_routines_weighings"
            ),
        )

        events: list[str] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            partial = Path(temp_dir) / "download.partial"

            with (
                patch.object(
                    extractor,
                    "_authenticate_trainingym",
                    side_effect=lambda *_args: events.append("authenticate"),
                ),
                patch.object(
                    extractor,
                    "_navigate_to_workout",
                    side_effect=lambda *_args: events.append("navigate"),
                ),
                patch.object(
                    extractor,
                    "_ensure_all_centers",
                    side_effect=lambda *_args: events.append("centers"),
                ),
                patch.object(
                    extractor,
                    "_set_native_date_range",
                    side_effect=lambda *_args: events.append("dates"),
                ),
                patch.object(
                    extractor,
                    "_download_native_csv",
                    side_effect=lambda *_args: (
                        events.append("download")
                        or extractor.TRAININGYM_WORKOUT_CSV_FILENAME
                    ),
                ),
                patch.object(
                    extractor,
                    "_find_report_frame",
                    side_effect=AssertionError(
                        "Power BI frame must not be used."
                    ),
                ),
                patch.object(
                    extractor,
                    "_configure_filters",
                    side_effect=AssertionError(
                        "Power BI filters must not be used."
                    ),
                ),
                patch.object(
                    extractor,
                    "_download_workout",
                    side_effect=AssertionError(
                        "Power BI XLSX download must not be used."
                    ),
                ),
            ):
                result = extractor._browser_export(
                    page,
                    tracker,
                    config,
                    DATE_FROM,
                    DATE_TO,
                    partial,
                )

        self.assertEqual(
            result,
            extractor.TRAININGYM_WORKOUT_CSV_FILENAME,
        )
        self.assertEqual(
            events,
            [
                "authenticate",
                "navigate",
                "centers",
                "dates",
                "download",
            ],
        )
        self.assertEqual(
            tracker.phases,
            [
                BrowserPhase.NAVIGATION,
                BrowserPhase.EXPORT,
                BrowserPhase.DOWNLOAD,
            ],
        )

    def test_native_csv_export_hovers_and_wraps_click_with_expect_download(self) -> None:
        events: list[str] = []

        class ExportButton:
            def wait_for(self, **_kwargs) -> None:
                pass

            def is_disabled(self) -> bool:
                return False

            def hover(self) -> None:
                events.append("hover:export")

        class ExportCsv:
            def is_visible(self) -> bool:
                return True

            def click(self) -> None:
                events.append(
                    f"click:Exportar CSV:inside_expect={page.download_active}"
                )

        class Download:
            suggested_filename = "rutinas_pesajes.csv"

            def save_as(self, path: str) -> None:
                Path(path).write_bytes(b"csv-data")
                events.append("save:csv")

        class DownloadInfo:
            def __enter__(self):
                page.download_active = True
                events.append("expect_download:enter")
                return self

            def __exit__(self, _exc_type, _exc, _traceback):
                events.append("expect_download:exit")
                page.download_active = False

            @property
            def value(self):
                return Download()

        class Page:
            def __init__(self) -> None:
                self.download_active = False
                self.button = ExportButton()
                self.csv = ExportCsv()

            def locator(self, selector: str):
                if selector == extractor._NATIVE_EXPORT_BUTTON_SELECTOR:
                    return self.button
                raise AssertionError(f"Unexpected selector: {selector}")

            def get_by_text(self, text: str, *, exact: bool):
                if text == extractor._NATIVE_EXPORT_CSV_TEXT and exact:
                    return _Collection((self.csv,))
                return _Collection()

            def expect_download(self, *, timeout=None):
                self.expect_download_timeout = timeout
                return DownloadInfo()

            def wait_for_timeout(self, _timeout: int) -> None:
                pass

        page = Page()

        with tempfile.TemporaryDirectory() as temp_dir:
            partial = Path(temp_dir) / "download.partial"

            source_filename = extractor._download_native_csv(
                page,
                partial,
            )

            self.assertTrue(partial.is_file())

        self.assertEqual(
            source_filename,
            extractor.TRAININGYM_WORKOUT_CSV_FILENAME,
        )
        self.assertEqual(
            page.expect_download_timeout,
            extractor._DOWNLOAD_TIMEOUT_MS,
        )
        self.assertLess(
            events.index("hover:export"),
            events.index("expect_download:enter"),
        )
        self.assertIn(
            "click:Exportar CSV:inside_expect=True",
            events,
        )
        self.assertLess(
            events.index("expect_download:enter"),
            events.index("click:Exportar CSV:inside_expect=True"),
        )
        self.assertLess(
            events.index("click:Exportar CSV:inside_expect=True"),
            events.index("expect_download:exit"),
        )
        self.assertIn("save:csv", events)

    def test_native_csv_export_fails_if_csv_action_is_missing(self) -> None:
        class ExportButton:
            def wait_for(self, **_kwargs) -> None:
                pass

            def is_disabled(self) -> bool:
                return False

            def hover(self) -> None:
                pass

        class Page:
            def locator(self, selector: str):
                if selector == extractor._NATIVE_EXPORT_BUTTON_SELECTOR:
                    return ExportButton()
                raise AssertionError(f"Unexpected selector: {selector}")

            def get_by_text(self, text: str, *, exact: bool):
                self.assertEqual if False else None
                return _Collection()

            def wait_for_timeout(self, _timeout: int) -> None:
                pass

        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            extractor,
            "_MENU_RENDER_TIMEOUT_MS",
            0,
        ):
            partial = Path(temp_dir) / "download.partial"

            with self.assertRaises(
                TrainingymWorkoutExtractionError
            ) as raised:
                extractor._download_native_csv(
                    Page(),
                    partial,
                )

        self.assertEqual(
            raised.exception.error_code,
            "TRAININGYM_WORKOUT_MENU_NOT_FOUND",
        )

    def test_hover_precedes_more_options_and_export_data(self) -> None:
        page = _Page()
        with tempfile.TemporaryDirectory() as temp_dir:
            partial = Path(temp_dir) / "download.partial"
            extractor._download_workout(page, page.frame, partial)
        self.assertLess(
            page.events.index("hover:visual-tabular"),
            page.events.index("click:Más opciones"),
        )
        self.assertLess(
            page.events.index("click:Más opciones"),
            page.events.index("click:Exportar datos"),
        )
        self.assertLess(
            page.events.index("lookup:visual:Más opciones"),
            page.events.index("click:Más opciones"),
        )

    def test_more_options_can_be_found_by_title(self) -> None:
        page = _Page(menu_by_title=True)
        extractor._open_export_dialog(page.frame, page.frame.visual)
        self.assertIn("click:Más opciones", page.events)

    def test_current_layout_is_selected_exclusively(self) -> None:
        page = _Page()
        button = extractor._dialog_controls(page)
        self.assertIs(button, page.frame.dialog.export_button)
        self.assertIn("check:Datos con diseño actual", page.events)
        self.assertNotIn("Datos resumidos", " ".join(page.events))
        self.assertNotIn("Datos subyacentes", " ".join(page.events))

    def test_current_layout_text_fallback_is_clicked_not_checked(self) -> None:
        page = _Page(current_layout_by_text=True)
        extractor._dialog_controls(page)
        self.assertIn("click:Datos con diseño actual", page.events)
        self.assertNotIn("check:Datos con diseño actual", page.events)

    def test_export_dialog_can_be_resolved_in_another_frame(self) -> None:
        page = _Page(dialog_in_other_frame=True)
        button = extractor._dialog_controls(page)
        self.assertIs(button, page.dialog_frame.dialog.export_button)
        self.assertIn("check:Datos con diseño actual", page.events)

    def test_expect_download_wraps_final_export_click(self) -> None:
        page = _Page()

        with tempfile.TemporaryDirectory() as temp_dir:
            partial = Path(temp_dir) / "download.partial"
            extractor._download_workout(
                page,
                page.frame,
                partial,
            )

        self.assertEqual(
            page.expect_download_timeout,
            extractor._DOWNLOAD_TIMEOUT_MS,
        )

        self.assertIn(
            "expect_download:enter",
            page.events,
        )

    def test_each_run_uses_a_unique_artifact_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            first = self._extract(temp_dir)
            second = self._extract(temp_dir)
            self.assertTrue(first.succeeded)
            self.assertTrue(second.succeeded)
            self.assertNotEqual(
                first.artifact.local_path.parent,
                second.artifact.local_path.parent,
            )

    def test_invalid_xlsx_is_validation_failed(self) -> None:
        def invalid(
            _page,
            _tracker,
            _config,
            _date_from,
            _date_to,
            partial_path,
        ):
            partial_path.write_bytes(b"not-an-xlsx")
            return "invalid.xlsx"

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result = self._extract(temp_dir, download_operation=invalid)
        self.assertEqual(
            result.error_code,
            "TRAININGYM_WORKOUT_VALIDATION_FAILED",
        )
        self.assertIsNone(result.artifact)

    def test_missing_headers_is_validation_failed(self) -> None:
        def missing_headers(
            _page,
            _tracker,
            _config,
            _date_from,
            _date_to,
            partial_path,
        ):
            workbook = Workbook()
            worksheet = workbook.active
            worksheet.title = "Export"
            worksheet.append(["Email", "Fecha"])
            workbook.save(partial_path)
            return "missing.xlsx"

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result = self._extract(
                temp_dir,
                download_operation=missing_headers,
            )
        self.assertEqual(
            result.error_code,
            "TRAININGYM_WORKOUT_VALIDATION_FAILED",
        )

    def test_failed_run_never_falls_back_to_previous_artifact(self) -> None:
        calls = 0

        def operation(
            _page,
            _tracker,
            _config,
            _date_from,
            _date_to,
            partial_path,
        ):
            nonlocal calls
            calls += 1
            if calls == 1:
                partial_path.write_text(
                    (
                        "\ufeff"
                        '"ID";"ID externo";"Socio";"Email";"Edad";"Sexo";'
                        '"Empleados";"Workouts";"Pesajes";"Total";"Valoración";'
                        '"Fecha";"Centro"\n'
                        '"24639860";"88669";"SOCIO PRUEBA";"test@example.com";'
                        '"42";"F";"TECNICO PRUEBA";"1";"0";"1";"";'
                        '"2026-07-23";"UltraGym Centro"\n'
                    ),
                    encoding="utf-8",
                    newline="",
                )
            else:
                partial_path.write_bytes(b"invalid")
            return TRAININGYM_WORKOUT_FILENAME

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            provider = TrainingymWorkoutExtractor(
                download_operation=operation,
                runtime_factory=_LocalRuntime,
            )
            first = provider.extract(
                date_from=DATE_FROM,
                date_to=DATE_TO,
                observed_at_utc=OBSERVED_AT,
            )
            second = provider.extract(
                date_from=DATE_FROM,
                date_to=DATE_TO,
                observed_at_utc=OBSERVED_AT,
            )
            self.assertTrue(first.succeeded)
            self.assertFalse(second.succeeded)
            self.assertIsNone(second.artifact)
            self.assertTrue(first.artifact.local_path.exists())

    def test_source_uses_ui_download_without_direct_endpoint_or_coordinates(self) -> None:
        source = inspect.getsource(extractor)
        self.assertIn("expect_download", source)
        self.assertNotIn("page.request", source)
        self.assertNotIn("requests.", source)
        self.assertNotIn("httpx", source)
        self.assertNotIn(".mouse", source)
        self.assertNotIn(".nth(", source)

    def test_source_excludes_prohibited_historical_patterns(self) -> None:
        source = inspect.getsource(extractor)
        for preserved in (
            "TrainingymProviderConfig",
            "BrowserRuntime",
            "ArtifactStore",
            "provider_lock",
            "ProviderArtifact",
            "ProviderExtractionResult",
            "load_trainingym_evidence_commands_from_xlsx",
        ):
            with self.subTest(preserved=preserved):
                self.assertIn(preserved, source)
        prohibited = (
            "load_dotenv",
            "TRAINING_LOGIN_URL",
            "TRAINING_REPORT_WORKOUT_URL",
            "TRAINING_USER",
            "TRAINING_PASS",
            "pytz",
            "SHOW_BROWSER",
            ".tg_profile",
            "launch_persistent_context",
            "channel=\"msedge\"",
            "_stealth",
            "screenshot(",
            "page.content(",
            "time.sleep(",
            "RAW_DIR",
            "OUT_DIR",
            "tg_workout.xlsx",
        )
        for pattern in prohibited:
            with self.subTest(pattern=pattern):
                self.assertNotIn(pattern, source)

    def test_errors_and_results_never_expose_credentials(self) -> None:
        def failure(*_args):
            raise TrainingymWorkoutExtractionError(
                "TRAININGYM_WORKOUT_DOWNLOAD_FAILED",
                "No fue posible completar la descarga XLSX.",
            )

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result = self._extract(
                temp_dir,
                download_operation=failure,
            )
        payload = json.dumps(result.__dict__ if hasattr(result, "__dict__") else {
            "error_code": result.error_code,
            "error_message": result.error_message,
        })
        self.assertNotIn("trainingym-user-secret", payload)
        self.assertNotIn("trainingym-password-secret", payload)

    def test_runtime_closes_page_context_browser_and_playwright_on_success(self) -> None:
        events: list[str] = []

        def runtime_factory(config):
            return BrowserRuntime(
                config,
                playwright_factory=lambda: _HarnessManager(events),
                sleeper=lambda _seconds: None,
            )

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            result = self._extract(
                temp_dir,
                runtime_factory=runtime_factory,
            )
        self.assertTrue(result.succeeded)
        self.assertEqual(
            events,
            ["launch", "page", "context", "browser", "playwright"],
        )

    def test_export_error_is_not_retried_and_resources_close(self) -> None:
        events: list[str] = []
        calls = 0

        def failure(*_args):
            nonlocal calls
            calls += 1
            raise TrainingymWorkoutExtractionError(
                "TRAININGYM_WORKOUT_DOWNLOAD_FAILED",
                "No fue posible completar la descarga XLSX.",
            )

        def runtime_factory(config):
            return BrowserRuntime(
                config,
                playwright_factory=lambda: _HarnessManager(events),
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
            result = self._extract(
                temp_dir,
                runtime_factory=runtime_factory,
                download_operation=failure,
            )
        self.assertEqual(calls, 1)
        self.assertEqual(
            result.error_code,
            "TRAININGYM_WORKOUT_DOWNLOAD_FAILED",
        )
        self.assertEqual(
            events,
            ["launch", "page", "context", "browser", "playwright"],
        )

    def test_configuration_failure_precedes_browser(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            result = TrainingymWorkoutExtractor(
                runtime_factory=_NoBrowserRuntime,
            ).extract(
                date_from=DATE_FROM,
                date_to=DATE_TO,
                observed_at_utc=OBSERVED_AT,
            )
        self.assertEqual(
            result.error_code,
            "TRAININGYM_WORKOUT_CONFIG_FAILED",
        )

    def test_each_extraction_phase_preserves_its_semantic_error_code(self) -> None:
        codes = (
            "TRAININGYM_WORKOUT_FILTER_CONTRACT_FAILED",
            "TRAININGYM_WORKOUT_VISUAL_NOT_FOUND",
            "TRAININGYM_WORKOUT_MENU_NOT_FOUND",
            "TRAININGYM_WORKOUT_EXPORT_DIALOG_FAILED",
            "TRAININGYM_WORKOUT_DOWNLOAD_FAILED",
            "TRAININGYM_WORKOUT_VALIDATION_FAILED",
        )
        for code in codes:
            with self.subTest(code=code), tempfile.TemporaryDirectory() as temp_dir:
                def failure(*_args, selected_code=code):
                    raise TrainingymWorkoutExtractionError(
                        selected_code,
                        "Fallo sanitizado.",
                    )

                with patch.dict(
                    "os.environ",
                    self._environment(temp_dir),
                    clear=True,
                ):
                    result = self._extract(
                        temp_dir,
                        download_operation=failure,
                    )
                self.assertEqual(result.error_code, code)

    def test_waits_until_powerbi_date_slicers_are_rendered(self) -> None:
        page = _Page()
        original_locator = page.frame.locator
        locator_calls = 0

        def delayed_locator(selector: str):
            nonlocal locator_calls

            if selector == extractor._DATE_INPUT_SELECTOR:
                locator_calls += 1

                if locator_calls < 3:
                    return _Collection()

                return _Collection(
                    (
                        page.frame.start,
                        page.frame.end,
                    )
                )

            return original_locator(selector)

        page.frame.locator = delayed_locator

        start, end = extractor._wait_for_date_controls(
            page.frame,
            timeout_ms=1_000,
        )

        self.assertIs(start, page.frame.start)
        self.assertIs(end, page.frame.end)
        self.assertEqual(locator_calls, 3)

    def test_table_ready_does_not_require_offscreen_columns_visible(
        self,
    ) -> None:
        page = _Page()

        page.frame.headers["Fecha"].is_visible = lambda: False
        page.frame.headers["Centro Origen"].is_visible = lambda: False

        headers = extractor._wait_for_table_headers(
            page.frame,
            timeout_ms=1_000,
        )

        self.assertGreaterEqual(
            len(headers),
            extractor._TABLE_READY_MIN_HEADERS,
        )

        visible_header_texts = {
            header.inner_text()
            for header in headers
        }

        self.assertNotIn(
            "Fecha",
            visible_header_texts,
        )
        self.assertNotIn(
            "Centro Origen",
            visible_header_texts,
        )

    def test_browser_export_navigates_from_home_before_native_controls(self) -> None:
        page = _Page()
        tracker = _Tracker()

        config = TrainingymProviderConfig(
            login_url="https://app.example.invalid/auth",
            user="private-user",
            password="private-password",
            center_name="Configured Center",
            workout_url=(
                "https://app.example.invalid/"
                "reports/bi_routines_weighings"
            ),
        )

        events: list[str] = []

        def authenticate(
            current_page,
            _tracker,
            _config,
        ):
            current_page.url = (
                "https://app.example.invalid/trainingym/home"
            )
            events.append("authenticated:/trainingym/home")

        def navigate(
            current_page,
            current_config,
        ):
            self.assertTrue(
                current_page.url.endswith("/trainingym/home")
            )
            current_page.goto(
                current_config.workout_url,
                wait_until="domcontentloaded",
            )
            events.append("workout:navigated")

        def ensure_centers(current_page):
            self.assertEqual(
                current_page.url,
                config.workout_url,
            )
            events.append("native:centers")

        def set_dates(
            current_page,
            date_from,
            date_to,
        ):
            self.assertEqual(
                current_page.url,
                config.workout_url,
            )
            self.assertEqual(date_from, DATE_FROM)
            self.assertEqual(date_to, DATE_TO)
            events.append("native:dates")

        def download_csv(
            current_page,
            _partial_path,
        ):
            self.assertEqual(
                current_page.url,
                config.workout_url,
            )
            events.append("native:download")
            return extractor.TRAININGYM_WORKOUT_CSV_FILENAME

        with tempfile.TemporaryDirectory() as temp_dir:
            partial = Path(temp_dir) / "download.partial"

            with (
                patch.object(
                    extractor,
                    "_authenticate_trainingym",
                    side_effect=authenticate,
                ),
                patch.object(
                    extractor,
                    "_navigate_to_workout",
                    side_effect=navigate,
                ),
                patch.object(
                    extractor,
                    "_ensure_all_centers",
                    side_effect=ensure_centers,
                ),
                patch.object(
                    extractor,
                    "_set_native_date_range",
                    side_effect=set_dates,
                ),
                patch.object(
                    extractor,
                    "_download_native_csv",
                    side_effect=download_csv,
                ),
                patch.object(
                    extractor,
                    "_find_report_frame",
                    side_effect=AssertionError(
                        "El flujo nativo no debe buscar Power BI."
                    ),
                ),
            ):
                source_name = extractor._browser_export(
                    page,
                    tracker,
                    config,
                    DATE_FROM,
                    DATE_TO,
                    partial,
                )

        self.assertEqual(
            source_name,
            extractor.TRAININGYM_WORKOUT_CSV_FILENAME,
        )

        self.assertEqual(
            events,
            [
                "authenticated:/trainingym/home",
                "workout:navigated",
                "native:centers",
                "native:dates",
                "native:download",
            ],
        )

        self.assertEqual(
            tracker.phases,
            [
                BrowserPhase.NAVIGATION,
                BrowserPhase.EXPORT,
                BrowserPhase.DOWNLOAD,
            ],
        )

if __name__ == "__main__":
    unittest.main()
