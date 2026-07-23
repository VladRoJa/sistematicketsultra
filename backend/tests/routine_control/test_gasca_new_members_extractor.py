from __future__ import annotations

import shutil
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.routine_control.providers.gasca.new_members_extractor import (
    GASCA_CONTRACT_ERROR,
    GascaNewMembersExtractor,
)
from app.routine_control.providers.runtime import BrowserExecutionResult


FIXTURE = Path(__file__).parent / "fixtures" / "gasca_socios_nuevos_detallado.xlsx"
OBSERVED_AT = datetime(2026, 7, 23, 18, 0, tzinfo=timezone.utc)


class _NoBrowserRuntime:
    def __init__(self, _config) -> None:
        raise AssertionError("Playwright no debe abrirse con configuración incompleta.")


class _LocalRuntime:
    def __init__(self, _config) -> None:
        pass

    def run(self, operation):
        value = operation(object(), object_with_set(), 1)
        return BrowserExecutionResult(value=value, attempts=1, elapsed_seconds=0.01)


class object_with_set:
    def set(self, _phase) -> None:
        pass


class GascaNewMembersExtractorTestCase(unittest.TestCase):
    def _env(self, artifact_root: str) -> dict[str, str]:
        return {
            "DIRECCION_LOGIN_URL": "https://example.invalid/login",
            "DIRECCION_REPORTE_URL": "https://example.invalid/report",
            "DIRECCION_USER": "gasca-user-secret",
            "DIRECCION_PASS": "gasca-password-secret",
            "ROUTINE_CONTROL_ARTIFACT_DIR": artifact_root,
        }

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

    def test_unverified_detailed_report_contract_does_not_open_browser(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._env(temp_dir),
            clear=True,
        ):
            result = GascaNewMembersExtractor(
                runtime_factory=_NoBrowserRuntime,
            ).extract(
                date_from=date(2026, 7, 1),
                date_to=date(2026, 7, 23),
                observed_at_utc=OBSERVED_AT,
            )
        self.assertFalse(result.succeeded)
        self.assertEqual(result.error_code, GASCA_CONTRACT_ERROR)

    def test_verified_injected_download_creates_valid_private_artifact(self) -> None:
        def download(_page, _tracker, _config, _date_from, _date_to, partial):
            shutil.copyfile(FIXTURE, partial)
            return "socios-nuevos-detallado.xlsx"

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._env(temp_dir),
            clear=True,
        ):
            result = GascaNewMembersExtractor(
                download_operation=download,
                runtime_factory=_LocalRuntime,
            ).extract(
                date_from=date(2026, 7, 1),
                date_to=date(2026, 7, 23),
                observed_at_utc=OBSERVED_AT,
            )
            self.assertTrue(result.succeeded)
            self.assertIsNotNone(result.artifact)
            self.assertTrue(result.artifact.local_path.is_file())
            self.assertEqual(
                result.artifact.source_filename,
                "socios-nuevos-detallado.xlsx",
            )

    def test_failed_download_never_falls_back_to_previous_artifact(self) -> None:
        calls = 0

        def download(_page, _tracker, _config, _date_from, _date_to, partial):
            nonlocal calls
            calls += 1
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
                runtime_factory=_LocalRuntime,
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
            self.assertIsNone(second.artifact)
            self.assertTrue(first.artifact.local_path.exists())


if __name__ == "__main__":
    unittest.main()
