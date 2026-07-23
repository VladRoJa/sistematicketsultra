from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.routine_control.providers.runtime import BrowserExecutionResult
from app.routine_control.providers.trainingym.discovery import (
    DiscoveryObservation,
    TrainingymDiscoveryService,
    sanitize_discovery_texts,
    sanitized_url_path,
)


class _NoBrowserRuntime:
    def __init__(self, _config) -> None:
        raise AssertionError("No debe abrirse el browser sin configuración.")


class _LocalRuntime:
    def __init__(self, _config) -> None:
        pass

    def run(self, operation):
        value = operation(object(), object(), 1)
        return BrowserExecutionResult(value=value, attempts=1, elapsed_seconds=0.01)


class TrainingymDiscoveryTestCase(unittest.TestCase):
    def test_missing_configuration_is_detected_before_browser(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            result = TrainingymDiscoveryService(
                runtime_factory=_NoBrowserRuntime,
            ).run(headless=True, diagnostic_dir=None)
        self.assertFalse(result.succeeded)
        self.assertEqual(result.error_code, "CONFIG_INVALID")
        self.assertIn("TRAININGYM_LOGIN_URL", result.error_message)
        self.assertIn("TRAININGYM_PASS", result.error_message)

    def test_discovery_output_removes_pii_tokens_queries_and_absolute_paths(self) -> None:
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

        environment = {
            "TRAININGYM_LOGIN_URL": "https://example.invalid/auth",
            "TRAININGYM_USER": "trainingym-user-secret",
            "TRAININGYM_PASS": "trainingym-password-secret",
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            environment,
            clear=True,
        ):
            result = TrainingymDiscoveryService(
                runtime_factory=_LocalRuntime,
                discovery_operation=discover,
            ).run(headless=True, diagnostic_dir=Path(temp_dir))
        payload = json.dumps(result.to_dict(), ensure_ascii=False)
        self.assertTrue(result.succeeded)
        self.assertEqual(result.post_login_path, "/dashboard")
        self.assertEqual(result.visible_controls, ("Workout", "Centro Norte"))
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
        self.assertEqual(len(sanitize_discovery_texts(values)), 30)
        self.assertEqual(
            sanitized_url_path("https://example.invalid/a/b?secret=1#fragment"),
            "/a/b",
        )


if __name__ == "__main__":
    unittest.main()
