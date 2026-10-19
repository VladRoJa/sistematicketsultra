"""Configuration guard regression tests; never connect to a real server."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from campaign_v2_visual_audit import (AuditNavigationTimeout, classify_tools_trigger,
                                      close_dialog, validate_target, open_tool)
from playwright.sync_api import TimeoutError as PlaywrightTimeout


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
            r'\[matMenuTriggerFor\]="campaignToolsMenu"\s+aria-label="([^"]+)"',
            markup,
        )
        self.assertIsNotNone(trigger, "Herramientas trigger missing an accessible label")
        page = MagicMock()
        open_tool(page, "Preparar prueba interna · 1 contacto")
        self.assertEqual(page.get_by_role.call_args_list, [
            call("button", name=trigger.group(1), exact=True),
            call("menuitem", name="Preparar prueba interna · 1 contacto", exact=True),
        ])

    def test_tools_trigger_timeout_is_classified(self):
        from unittest.mock import MagicMock

        page = MagicMock()
        trigger = page.get_by_role.return_value
        trigger.click.side_effect = PlaywrightTimeout("private page details")
        trigger.count.return_value = 1
        trigger.is_visible.return_value = True
        trigger.is_enabled.return_value = True
        trigger.evaluate.return_value = {
            "dialog_open": False, "active_backdrop": False,
            "in_viewport": True, "center_hits_button": True,
        }
        with self.assertRaisesRegex(AuditNavigationTimeout, "^tools_trigger_click_timeout$"):
            open_tool(page, "Preparar prueba interna · 1 contacto")

    def test_close_dialog_uses_explicit_button_and_restores_accessibility(self):
        from unittest.mock import MagicMock

        page = MagicMock()
        dialog = page.locator.return_value
        dialog.get_by_role.return_value.count.return_value = 1
        close_dialog(page)
        dialog.get_by_role.assert_called_once_with(
            "button", name="Cerrar", exact=True
        )
        dialog.get_by_role.return_value.first.click.assert_called_once_with(
            timeout=6000
        )
        page.keyboard.press.assert_not_called()
        dialog.wait_for.assert_called_once_with(state="detached", timeout=5000)
        page.get_by_role.assert_called_once_with(
            "button", name="Abrir herramientas de campañas", exact=True
        )
        page.get_by_role.return_value.wait_for.assert_called_once_with(
            state="visible", timeout=5000
        )

    def test_close_dialog_falls_back_to_escape_if_no_close_button(self):
        from unittest.mock import MagicMock

        page = MagicMock()
        dialog = page.locator.return_value
        dialog.get_by_role.return_value.count.return_value = 0
        close_dialog(page)
        page.keyboard.press.assert_called_once_with("Escape")
        dialog.get_by_role.return_value.first.click.assert_not_called()
        dialog.wait_for.assert_called_once_with(state="detached", timeout=5000)
        page.get_by_role.return_value.wait_for.assert_called_once_with(
            state="visible", timeout=5000
        )

    def test_tools_trigger_safe_diagnostic_codes(self):
        from unittest.mock import MagicMock

        trigger = MagicMock()
        trigger.count.return_value = 1
        trigger.is_visible.return_value = True
        trigger.is_enabled.return_value = True
        base = {
            "dialog_open": False, "active_backdrop": False,
            "in_viewport": True, "center_hits_button": True,
        }
        for change, expected in (
            ({"dialog_open": True}, "tools_trigger_dialog_still_open"),
            ({"active_backdrop": True}, "tools_trigger_backdrop_active"),
            ({"in_viewport": False}, "tools_trigger_outside_viewport"),
            ({"center_hits_button": False}, "tools_trigger_center_obstructed"),
        ):
            trigger.evaluate.return_value = {**base, **change}
            self.assertEqual(classify_tools_trigger(trigger), expected)
        trigger.count.return_value = 0
        self.assertEqual(classify_tools_trigger(trigger), "tools_trigger_missing")
        trigger.count.return_value = 1
        trigger.is_visible.return_value = False
        self.assertEqual(classify_tools_trigger(trigger), "tools_trigger_hidden")

    def test_tools_menu_option_timeout_is_classified(self):
        from unittest.mock import MagicMock

        page = MagicMock()
        button = MagicMock()
        item = MagicMock()
        item.click.side_effect = PlaywrightTimeout("private page details")
        page.get_by_role.side_effect = [button, item]
        with self.assertRaisesRegex(AuditNavigationTimeout, "^tools_menu_item_click_timeout$"):
            open_tool(page, "Preparar prueba interna · 1 contacto")

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
