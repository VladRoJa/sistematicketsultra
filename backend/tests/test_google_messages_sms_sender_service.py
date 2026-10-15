"""Safe editor-read regressions; never opens a browser or sends SMS."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "rpa"
    / "services"
    / "google_messages_sms_sender_service.py"
)
SPEC = importlib.util.spec_from_file_location("gasca_sms_sender_under_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
sender = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sender
SPEC.loader.exec_module(sender)


class GoogleMessagesEditorReadTest(unittest.TestCase):
    def test_textarea_reads_input_value(self) -> None:
        locator = Mock()
        locator.get_attribute.return_value = None
        locator.input_value.return_value = "ULTRA GYM: codigo 12345"

        result = sender._read_locator_value(locator)

        self.assertEqual(result, "ULTRA GYM: codigo 12345")
        locator.input_value.assert_called_once()
        locator.inner_text.assert_not_called()

    def test_contenteditable_reads_inner_text(self) -> None:
        locator = Mock()
        locator.get_attribute.return_value = "true"
        locator.inner_text.return_value = "ULTRA GYM: codigo 12345"

        result = sender._read_locator_value(locator)

        self.assertEqual(result, "ULTRA GYM: codigo 12345")
        locator.inner_text.assert_called_once()
        locator.input_value.assert_not_called()

    def test_contenteditable_empty_is_readable_empty_string(self) -> None:
        locator = Mock()
        locator.get_attribute.return_value = ""
        locator.inner_text.return_value = ""

        self.assertEqual(sender._read_locator_value(locator), "")

    def test_unreadable_contenteditable_fails_closed(self) -> None:
        locator = Mock()
        locator.get_attribute.return_value = "true"
        locator.inner_text.side_effect = RuntimeError("DOM detached")

        with self.assertRaises(sender.GoogleMessagesSmsSenderError):
            sender._read_locator_value(locator)

    def test_unreadable_textarea_fails_closed(self) -> None:
        locator = Mock()
        locator.get_attribute.return_value = None
        locator.input_value.side_effect = RuntimeError("DOM detached")

        with self.assertRaises(sender.GoogleMessagesSmsSenderError):
            sender._read_locator_value(locator)

    def test_unreadable_editor_attribute_fails_closed(self) -> None:
        locator = Mock()
        locator.get_attribute.side_effect = RuntimeError("Browser closed")

        with self.assertRaises(sender.GoogleMessagesSmsSenderError):
            sender._read_locator_value(locator)

    def test_invalid_editor_value_is_not_an_empty_confirmation(self) -> None:
        locator = Mock()
        locator.get_attribute.return_value = "true"
        locator.inner_text.return_value = None

        with self.assertRaises(sender.GoogleMessagesSmsSenderError):
            sender._read_locator_value(locator)

    def test_wait_for_written_text_supports_contenteditable(self) -> None:
        locator = Mock()
        locator.get_attribute.return_value = "true"
        locator.inner_text.return_value = "ULTRA GYM: codigo 12345"

        sender._wait_until_locator_value_contains(
            locator, "codigo 12345", timeout_ms=50
        )

    def test_wait_for_empty_supports_contenteditable(self) -> None:
        locator = Mock()
        locator.get_attribute.return_value = "true"
        locator.inner_text.return_value = ""

        sender._wait_until_locator_empty(locator, timeout_ms=50)

    def test_unreadable_editor_cannot_confirm_empty_after_send(self) -> None:
        locator = Mock()
        locator.get_attribute.return_value = "true"
        locator.inner_text.side_effect = RuntimeError("DOM detached")

        with self.assertRaises(sender.GoogleMessagesSmsSenderError):
            sender._wait_until_locator_empty(locator, timeout_ms=50)

    def test_no_send_click_when_editor_cannot_be_verified(self) -> None:
        locator = Mock()
        locator.get_attribute.side_effect = RuntimeError("Browser closed")
        page = Mock()
        page.locator.return_value.last = locator
        config = sender.GoogleMessagesSmsConfig(profile_dir=Path("/unused"))

        with (
            patch.object(sender, "_body_message_occurrence_count", return_value=0),
            patch.object(sender, "_send_failure_marker_count", return_value=0),
            patch.object(sender, "_click_send_button_if_available") as click_send,
        ):
            with self.assertRaises(sender.GoogleMessagesSmsSenderError):
                sender._send_by_enter(page, "div[contenteditable='true']", "SMS", config)

            click_send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
