import os
import tempfile
import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PIL import Image

import app.services.ticket_attachment_service as service
from app.services.ticket_attachment_storage_service import (
    resolve_ticket_attachment_path,
)


_STORAGE_KEY = (
    "tickets/123/"
    "0123456789abcdef0123456789abcdef.png"
)


def _make_png_bytes() -> bytes:
    image = Image.new(
        "RGB",
        (320, 180),
        (40, 80, 120),
    )

    buffer = BytesIO()
    image.save(buffer, format="PNG")

    return buffer.getvalue()


class TicketAttachmentServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

        self.env_patch = patch.dict(
            os.environ,
            {
                "TICKET_ATTACHMENT_DIR": self.temp_dir.name,
            },
        )
        self.env_patch.start()

        self.session = MagicMock()
        self.db_patch = patch.object(
            service,
            "db",
            SimpleNamespace(session=self.session),
        )
        self.db_patch.start()

        self.duplicate_patch = patch.object(
            service,
            "_ticket_already_has_attachment",
            return_value=False,
        )
        self.mock_duplicate = self.duplicate_patch.start()

        self.key_patch = patch.object(
            service,
            "build_ticket_attachment_storage_key",
            return_value=_STORAGE_KEY,
        )
        self.key_patch.start()

        self.content = _make_png_bytes()

    def tearDown(self):
        self.key_patch.stop()
        self.duplicate_patch.stop()
        self.db_patch.stop()
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_valid_image_is_persisted_with_metadata(self):
        attachment = service.create_ticket_image_attachment(
            ticket_id=123,
            content=self.content,
            original_filename="arte-final.png",
            declared_mime_type="image/png",
        )

        self.assertEqual(attachment.ticket_id, 123)
        self.assertEqual(
            attachment.original_filename,
            "arte-final.png",
        )
        self.assertEqual(
            attachment.storage_key,
            _STORAGE_KEY,
        )
        self.assertEqual(
            attachment.mime_type,
            "image/png",
        )
        self.assertEqual(
            attachment.size_bytes,
            len(self.content),
        )
        self.assertEqual(attachment.width, 320)
        self.assertEqual(attachment.height, 180)
        self.assertEqual(
            attachment.optimization_mode,
            "original",
        )

        path = resolve_ticket_attachment_path(
            _STORAGE_KEY
        )

        self.assertTrue(path.is_file())
        self.assertEqual(
            path.read_bytes(),
            self.content,
        )

        self.session.add.assert_called_once_with(
            attachment
        )
        self.session.flush.assert_called_once_with()
        self.session.commit.assert_called_once_with()
        self.session.rollback.assert_not_called()

    def test_existing_attachment_is_rejected_before_write(self):
        self.mock_duplicate.return_value = True

        with self.assertRaisesRegex(
            ValueError,
            "ya tiene un archivo adjunto",
        ):
            service.create_ticket_image_attachment(
                ticket_id=123,
                content=self.content,
                original_filename="segundo.png",
                declared_mime_type="image/png",
            )

        path = resolve_ticket_attachment_path(
            _STORAGE_KEY
        )

        self.assertFalse(path.exists())
        self.session.add.assert_not_called()
        self.session.flush.assert_not_called()
        self.session.commit.assert_not_called()

    def test_database_flush_failure_does_not_write_file(self):
        self.session.flush.side_effect = RuntimeError(
            "simulated flush failure"
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "simulated flush failure",
        ):
            service.create_ticket_image_attachment(
                ticket_id=123,
                content=self.content,
                original_filename="arte.png",
                declared_mime_type="image/png",
            )

        path = resolve_ticket_attachment_path(
            _STORAGE_KEY
        )

        self.assertFalse(path.exists())
        self.session.rollback.assert_called_once_with()
        self.session.commit.assert_not_called()

    def test_commit_failure_removes_written_file(self):
        self.session.commit.side_effect = RuntimeError(
            "simulated commit failure"
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "simulated commit failure",
        ):
            service.create_ticket_image_attachment(
                ticket_id=123,
                content=self.content,
                original_filename="arte.png",
                declared_mime_type="image/png",
            )

        path = resolve_ticket_attachment_path(
            _STORAGE_KEY
        )

        self.assertFalse(path.exists())
        self.session.flush.assert_called_once_with()
        self.session.rollback.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
