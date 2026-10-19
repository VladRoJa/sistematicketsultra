"""Configuration guard regression tests; never connect to a real server."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from campaign_v2_visual_audit import validate_target, open_tool


class VisualAuditTargetTests(unittest.TestCase):
    def config(self, **kwargs):
        defaults = {
            "SUITE_QA_USERNAME": "TEST_ONLY",
            "SUITE_QA_PASSWORD": "not-a-real-password",
            "SUITE_QA_ALLOWED_HOST": "localhost",
        }
        defaults.update(kwargs)
        return patch.dict(os.environ, defaults, clear=True)

    def test_tools_menu_uses_declared_accessible_name(self):
        # Angular aria-label overrides the visible text "Herramientas".
        import re
        from unittest.mock import MagicMock, call

        html_path = Path(__file__).resolve().parents[2] / (
            "frontend/src/app/marketing-campaign-v2/marketing-campaign-v2-page.component.html"
        )
        markup = html_path.read_text(encoding="utf-8")
        trigger = re.search(
            r'\\[matMenuTriggerFor\\]="campaignToolsMenu"\\s+aria-label="([^"]+)"',
            markup,
        )
        self.assertIsNotNone(trigger, "Herramientas trigger missing an accessible label")
        page = MagicMock()
        open_tool(page, "Preparar prueba interna · 1 contacto")
        self.assertEqual(page.get_by_role.call_args_list, [
            call("button", name=trigger.group(1), exact=True),
            call("menuitem", name="Preparar prueba interna · 1 contacto", exact=True),
        ])

    def test_real_local_explicitly_authorized(self):
        with self.config(SUITE_QA_REAL_LOCAL_READONLY_CONFIRMED="YES"):
            self.assertIsNone(validate_target("authenticated", "http://localhost:4200"))

    def test_real_local_remote_host_is_rejected(self):
        with self.config(
            SUITE_QA_REAL_LOCAL_READONLY_CONFIRMED="YES",
            SUITE_QA_ALLOWED_HOST="qa.example.test",
        ):
            with self.assertRaisesRegex(ValueError, "only on localhost"):
                validate_target("authenticated", "https://qa.example.test")

    def test_real_local_other_loopback_is_supported(self):
        with self.config(
            SUITE_QA_REAL_LOCAL_READONLY_CONFIRMED="YES",
            SUITE_QA_ALLOWED_HOST="127.0.0.1",
        ):
            self.assertIsNone(validate_target("authenticated", "http://127.0.0.1:4200"))

    def test_no_explicit_data_mode_is_rejected(self):
        with self.config():
            with self.assertRaisesRegex(ValueError, "exactly one data mode"):
                validate_target("authenticated", "http://localhost:4200")

    def test_mixed_real_and_synthetic_is_rejected(self):
        with self.config(
            SUITE_QA_REAL_LOCAL_READONLY_CONFIRMED="YES",
            SUITE_QA_SYNTHETIC_DATA_CONFIRMED="YES",
        ):
            with self.assertRaisesRegex(ValueError, "exactly one data mode"):
                validate_target("authenticated", "http://localhost:4200")

    def test_synthetic_remote_qa_still_allowed(self):
        with self.config(
            SUITE_QA_SYNTHETIC_DATA_CONFIRMED="YES",
            SUITE_QA_ALLOWED_HOST="qa.example.test",
        ):
            self.assertIsNone(validate_target("authenticated", "https://qa.example.test"))

    def test_host_mismatch_is_rejected(self):
        with self.config(SUITE_QA_REAL_LOCAL_READONLY_CONFIRMED="YES"):
            with self.assertRaisesRegex(ValueError, "exact audit hostname"):
                validate_target("authenticated", "http://127.0.0.1:4200")

    def test_missing_credentials_is_rejected(self):
        with self.config(
            SUITE_QA_REAL_LOCAL_READONLY_CONFIRMED="YES",
            SUITE_QA_PASSWORD="",
        ):
            with self.assertRaisesRegex(ValueError, "credentials missing"):
                validate_target("authenticated", "http://localhost:4200")


if __name__ == "__main__":
    unittest.main()
