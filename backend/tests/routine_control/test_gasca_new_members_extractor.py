from __future__ import annotations

import shutil
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.routine_control.providers.gasca.new_members_extractor import (
    GASCA_NEW_MEMBER_HEADERS,
    GascaNewMembersExtractor,
)
from app.routine_control.providers.runtime import (
    BrowserExecutionResult,
    BrowserPhase,
)


FIXTURE = Path(__file__).parent / "fixtures" / "gasca_socios_nuevos_detallado.xlsx"
OBSERVED_AT = datetime(2026, 7, 23, 18, 0, tzinfo=timezone.utc)
KPI_URL = "https://example.invalid/Modulo/Kpis/Index"


class _NoBrowserRuntime:
    def __init__(self, _config) -> None:
        raise AssertionError("Playwright no debe abrirse para este caso.")


class _Tracker:
    def __init__(self) -> None:
        self.phases: list[BrowserPhase] = []

    def set(self, phase: BrowserPhase) -> None:
        self.phases.append(phase)


class _LocalRuntime:
    def __init__(self, page, tracker: _Tracker) -> None:
        self.page = page
        self.tracker = tracker

    def run(self, operation):
        value = operation(self.page, self.tracker, 1)
        return BrowserExecutionResult(value=value, attempts=1, elapsed_seconds=0.01)


class _FakeLocator:
    def __init__(self, page: "_FakePage", selector: str) -> None:
        self.page = page
        self.selector = selector

    def fill(self, value: str) -> None:
        self.page.events.append(("fill", self.selector, value))
        if self.page.failure == "login" and self.selector == "#NombreUsuario":
            raise RuntimeError("gasca-user-secret gasca-password-secret")
        if (
            self.page.failure == "date"
            and self.selector == "#txtFechaIn input.form-control"
        ):
            raise RuntimeError("date control failed")

    def click(self) -> None:
        self.page.events.append(
            ("click", self.selector, self.page.download_context_active)
        )
        if (
            self.page.failure == "download"
            and self.selector == "#btnGenerarKpiVentasClientesNuevosDetallado"
        ):
            raise RuntimeError("download failed")

    def select_option(self, *, label: str) -> None:
        self.page.events.append(("select_option", self.selector, label))
        if self.page.failure == "option":
            raise RuntimeError("option failed")


class _FakeHomeLink:
    def __init__(self, page: "_FakePage") -> None:
        self.page = page

    def is_visible(self) -> bool:
        self.page.events.append(("home_visible", self.page.home_visible))
        return self.page.home_visible

    def click(self) -> None:
        self.page.events.append(("home_click", "Ir a Inicio"))


class _FakeDownload:
    def __init__(
        self,
        page: "_FakePage",
        source_path: Path,
        suggested_filename: str,
    ) -> None:
        self.page = page
        self.source_path = source_path
        self.suggested_filename = suggested_filename
        self.saved_path: Path | None = None

    def save_as(self, path: str) -> None:
        self.saved_path = Path(path)
        self.page.events.append(("save_as", self.saved_path))
        shutil.copyfile(self.source_path, self.saved_path)


class _FakeDownloadExpectation:
    def __init__(self, page: "_FakePage") -> None:
        self.page = page

    def __enter__(self):
        self.page.download_context_active = True
        self.page.events.append(("expect_download_enter",))
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.page.download_context_active = False
        self.page.events.append(("expect_download_exit",))

    @property
    def value(self) -> _FakeDownload:
        return self.page.download


class _FakePage:
    def __init__(
        self,
        *,
        download_source: Path = FIXTURE,
        suggested_filename: str = "KpiUnoSociosNuevosDetallado20260724115653.xlsx",
        home_visible: bool = False,
        failure: str | None = None,
    ) -> None:
        self.events: list[tuple] = []
        self.home_visible = home_visible
        self.failure = failure
        self.download_context_active = False
        self.download = _FakeDownload(
            self,
            download_source,
            suggested_filename,
        )

    def goto(self, url: str, **kwargs) -> None:
        self.events.append(("goto", url, kwargs))
        if self.failure == "navigation" and url == KPI_URL:
            raise RuntimeError("navigation failed")

    def wait_for_load_state(self, state: str) -> None:
        self.events.append(("wait_for_load_state", state))

    def locator(self, selector: str) -> _FakeLocator:
        self.events.append(("locator", selector))
        return _FakeLocator(self, selector)

    def get_by_role(self, role: str, *, name: str, exact: bool) -> _FakeHomeLink:
        self.events.append(("get_by_role", role, name, exact))
        return _FakeHomeLink(self)

    def expect_download(self, *, timeout: int) -> _FakeDownloadExpectation:
        self.events.append(("expect_download", timeout))
        return _FakeDownloadExpectation(self)


class GascaNewMembersExtractorTestCase(unittest.TestCase):
    def _env(self, artifact_root: str) -> dict[str, str]:
        return {
            "DIRECCION_LOGIN_URL": "https://example.invalid/login",
            "DIRECCION_REPORTE_URL": "https://example.invalid/report",
            "DIRECCION_USER": "gasca-user-secret",
            "DIRECCION_PASS": "gasca-password-secret",
            "KPI_DESEMPENO_URL": KPI_URL,
            "ROUTINE_CONTROL_ARTIFACT_DIR": artifact_root,
        }

    @staticmethod
    def _runtime_factory(page: _FakePage, tracker: _Tracker):
        return lambda _config: _LocalRuntime(page, tracker)

    def test_missing_variables_are_reported_before_browser_without_secrets(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            result = GascaNewMembersExtractor(
                runtime_factory=_NoBrowserRuntime,
            ).extract(
                date_from=date(2026, 7, 1),
                date_to=date(2026, 7, 23),
                observed_at_utc=OBSERVED_AT,
            )
        self.assertFalse(result.succeeded)
        self.assertEqual(result.error_code, "CONFIG_INVALID")
        self.assertIn("DIRECCION_LOGIN_URL", result.error_message)
        self.assertIn("DIRECCION_PASS", result.error_message)
        self.assertNotIn("secret", result.error_message)

    def test_default_operation_uses_confirmed_productive_contract(self) -> None:
        page = _FakePage(
            home_visible=True,
            suggested_filename=(
                "downloads/KpiUnoSociosNuevosDetallado20260724115653.xlsx"
            ),
        )
        tracker = _Tracker()
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._env(temp_dir),
            clear=True,
        ):
            result = GascaNewMembersExtractor(
                runtime_factory=self._runtime_factory(page, tracker),
            ).extract(
                date_from=date(2026, 7, 1),
                date_to=date(2026, 7, 24),
                observed_at_utc=OBSERVED_AT,
            )

            self.assertTrue(result.succeeded, result.error_message)
            self.assertIsNotNone(result.artifact)
            artifact = result.artifact
            self.assertEqual(artifact.provider_key, "gasca")
            self.assertEqual(artifact.dataset_key, "new_members")
            self.assertEqual(artifact.local_path.name, "gasca-new-members.xlsx")
            self.assertTrue(artifact.local_path.is_file())
            self.assertGreater(artifact.size_bytes, 0)
            self.assertEqual(len(artifact.sha256), 64)
            self.assertEqual(artifact.business_date_from, date(2026, 7, 1))
            self.assertEqual(artifact.business_date_to, date(2026, 7, 24))
            self.assertEqual(
                artifact.source_filename,
                "KpiUnoSociosNuevosDetallado20260724115653.xlsx",
            )
            self.assertEqual(
                artifact.diagnostic_metadata,
                {"report_contract": "verified_kpi_new_members_detailed"},
            )

        self.assertIn(
            ("fill", "#NombreUsuario", "gasca-user-secret"),
            page.events,
        )
        self.assertIn(
            ("fill", "#Contrasena", "gasca-password-secret"),
            page.events,
        )
        self.assertIn(
            ("click", 'button[type="submit"]', False),
            page.events,
        )
        self.assertIn(
            ("get_by_role", "link", "Ir a Inicio", True),
            page.events,
        )
        self.assertIn(("home_click", "Ir a Inicio"), page.events)
        self.assertIn(
            ("goto", KPI_URL, {"wait_until": "domcontentloaded"}),
            page.events,
        )
        self.assertIn(
            ("select_option", "select", "Ventas Nuevas Socios"),
            page.events,
        )
        self.assertIn(
            ("fill", "#txtFechaIn input.form-control", "07/24/2026"),
            page.events,
        )
        self.assertIn(("expect_download", 240_000), page.events)
        excel_click = (
            "click",
            "#btnGenerarKpiVentasClientesNuevosDetallado",
            True,
        )
        self.assertIn(excel_click, page.events)
        self.assertLess(
            page.events.index(("expect_download_enter",)),
            page.events.index(excel_click),
        )
        self.assertLess(
            page.events.index(excel_click),
            page.events.index(("expect_download_exit",)),
        )
        self.assertIsNotNone(page.download.saved_path)
        self.assertNotEqual(page.download.saved_path.name, "gasca-new-members.xlsx")
        self.assertEqual(
            tracker.phases,
            [
                BrowserPhase.LOGIN,
                BrowserPhase.NAVIGATION,
                BrowserPhase.DISCOVERY,
                BrowserPhase.EXPORT,
                BrowserPhase.DOWNLOAD,
                BrowserPhase.VALIDATION,
            ],
        )
        self.assertEqual(
            GASCA_NEW_MEMBER_HEADERS,
            frozenset(
                {
                    "IDSocio",
                    "IDFolio",
                    "Sucursal",
                    "Nombre",
                    "ApellidoPaterno",
                    "ApellidoMaterno",
                    "Email",
                    "FechaPago",
                    "FechaCreacion",
                }
            ),
        )

    def test_optional_home_link_is_not_clicked_when_absent(self) -> None:
        page = _FakePage(home_visible=False)
        tracker = _Tracker()
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._env(temp_dir),
            clear=True,
        ):
            result = GascaNewMembersExtractor(
                runtime_factory=self._runtime_factory(page, tracker),
            ).extract(
                date_from=date(2026, 7, 1),
                date_to=date(2026, 7, 24),
                observed_at_utc=OBSERVED_AT,
            )
        self.assertTrue(result.succeeded, result.error_message)
        self.assertNotIn(("home_click", "Ir a Inicio"), page.events)

    def test_partial_month_is_rejected_before_browser(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._env(temp_dir),
            clear=True,
        ):
            result = GascaNewMembersExtractor(
                runtime_factory=_NoBrowserRuntime,
            ).extract(
                date_from=date(2026, 7, 10),
                date_to=date(2026, 7, 24),
                observed_at_utc=OBSERVED_AT,
            )
        self.assertFalse(result.succeeded)
        self.assertEqual(result.error_code, "GASCA_DATE_CONTROL_FAILED")
        self.assertNotIn("gasca-user-secret", result.error_message)
        self.assertNotIn("gasca-password-secret", result.error_message)

    def test_invalid_kpi_url_is_rejected_without_exposing_querystring(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            environment = self._env(temp_dir)
            environment["KPI_DESEMPENO_URL"] = (
                "http://example.invalid/Modulo/Kpis/Index?token=query-secret"
            )
            with patch.dict("os.environ", environment, clear=True):
                result = GascaNewMembersExtractor(
                    runtime_factory=_NoBrowserRuntime,
                ).extract(
                    date_from=date(2026, 7, 1),
                    date_to=date(2026, 7, 24),
                    observed_at_utc=OBSERVED_AT,
                )
        self.assertFalse(result.succeeded)
        self.assertEqual(result.error_code, "CONFIG_INVALID")
        self.assertNotIn("query-secret", result.error_message)
        self.assertNotIn("?token=", result.error_message)

    def test_contract_failures_keep_distinct_sanitized_error_codes(self) -> None:
        cases = (
            ("login", "GASCA_LOGIN_FAILED"),
            ("navigation", "GASCA_REPORT_NAVIGATION_FAILED"),
            ("option", "GASCA_REPORT_OPTION_NOT_FOUND"),
            ("date", "GASCA_DATE_CONTROL_FAILED"),
            ("download", "GASCA_DOWNLOAD_FAILED"),
        )
        for failure, error_code in cases:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp_dir:
                page = _FakePage(failure=failure)
                tracker = _Tracker()
                with patch.dict("os.environ", self._env(temp_dir), clear=True):
                    result = GascaNewMembersExtractor(
                        runtime_factory=self._runtime_factory(page, tracker),
                    ).extract(
                        date_from=date(2026, 7, 1),
                        date_to=date(2026, 7, 24),
                        observed_at_utc=OBSERVED_AT,
                    )
                self.assertFalse(result.succeeded)
                self.assertEqual(result.error_code, error_code)
                self.assertIsNone(result.artifact)
                self.assertNotIn("gasca-user-secret", result.error_message)
                self.assertNotIn("gasca-password-secret", result.error_message)
                self.assertNotIn(str(Path(temp_dir).resolve()), result.error_message)

    def test_invalid_download_uses_validation_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            invalid_xlsx = Path(temp_dir) / "invalid.xlsx"
            invalid_xlsx.write_bytes(b"not an xlsx")
            page = _FakePage(download_source=invalid_xlsx)
            tracker = _Tracker()
            with patch.dict("os.environ", self._env(temp_dir), clear=True):
                result = GascaNewMembersExtractor(
                    runtime_factory=self._runtime_factory(page, tracker),
                ).extract(
                    date_from=date(2026, 7, 1),
                    date_to=date(2026, 7, 24),
                    observed_at_utc=OBSERVED_AT,
                )
        self.assertFalse(result.succeeded)
        self.assertEqual(result.error_code, "GASCA_VALIDATION_FAILED")
        self.assertIsNone(result.artifact)
        self.assertNotIn(str(invalid_xlsx), result.error_message)

    def test_injected_download_operation_still_creates_private_artifact(self) -> None:
        def download(_page, _tracker, _config, _date_from, _date_to, partial):
            shutil.copyfile(FIXTURE, partial)
            return "folder/socios-nuevos-detallado.xlsx"

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._env(temp_dir),
            clear=True,
        ):
            result = GascaNewMembersExtractor(
                download_operation=download,
                runtime_factory=lambda _config: _LocalRuntime(object(), _Tracker()),
            ).extract(
                date_from=date(2026, 7, 1),
                date_to=date(2026, 7, 23),
                observed_at_utc=OBSERVED_AT,
            )
            self.assertTrue(result.succeeded, result.error_message)
            self.assertIsNotNone(result.artifact)
            self.assertTrue(result.artifact.local_path.is_file())
            self.assertEqual(
                result.artifact.source_filename,
                "socios-nuevos-detallado.xlsx",
            )

    def test_failed_download_never_falls_back_to_previous_artifact(self) -> None:
        calls = 0
        partial_paths: list[Path] = []

        def download(_page, _tracker, _config, _date_from, _date_to, partial):
            nonlocal calls
            calls += 1
            partial_paths.append(partial)
            if calls == 1:
                shutil.copyfile(FIXTURE, partial)
                return "first.xlsx"
            partial.write_bytes(b"invalid")
            return "second.xlsx"

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._env(temp_dir),
            clear=True,
        ):
            extractor = GascaNewMembersExtractor(
                download_operation=download,
                runtime_factory=lambda _config: _LocalRuntime(object(), _Tracker()),
            )
            first = extractor.extract(
                date_from=date(2026, 7, 1),
                date_to=date(2026, 7, 23),
                observed_at_utc=OBSERVED_AT,
            )
            second = extractor.extract(
                date_from=date(2026, 7, 1),
                date_to=date(2026, 7, 23),
                observed_at_utc=OBSERVED_AT,
            )
            self.assertTrue(first.succeeded)
            self.assertFalse(second.succeeded)
            self.assertEqual(second.error_code, "GASCA_VALIDATION_FAILED")
            self.assertIsNone(second.artifact)
            self.assertTrue(first.artifact.local_path.exists())
            self.assertNotEqual(
                first.artifact.local_path.parent,
                partial_paths[1].parent,
            )
            self.assertFalse(partial_paths[1].exists())


if __name__ == "__main__":
    unittest.main()
