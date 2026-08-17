import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.ticket_attachment_storage_service import (
    build_ticket_attachment_storage_key,
    delete_ticket_attachment,
    resolve_ticket_attachment_path,
    ticket_attachment_exists,
    validate_ticket_attachment_storage_key,
    write_ticket_attachment_bytes,
)


class TicketAttachmentStorageServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

        self.env_patch = patch.dict(
            os.environ,
            {
                "TICKET_ATTACHMENT_DIR": self.temp_dir.name,
            },
        )
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_write_and_delete_are_private_and_idempotent(self):
        storage_key = build_ticket_attachment_storage_key(
            ticket_id=123,
            extension=".png",
        )

        self.assertRegex(
            storage_key,
            r"^tickets/123/[a-f0-9]{32}\.png$",
        )

        content = b"fake-image-content"

        stored_path = write_ticket_attachment_bytes(
            storage_key,
            content,
        )

        root = Path(self.temp_dir.name).resolve()

        self.assertTrue(stored_path.is_file())
        self.assertIn(root, stored_path.parents)
        self.assertEqual(stored_path.read_bytes(), content)
        self.assertTrue(ticket_attachment_exists(storage_key))

        deleted = delete_ticket_attachment(storage_key)

        self.assertTrue(deleted)
        self.assertFalse(ticket_attachment_exists(storage_key))

        deleted_again = delete_ticket_attachment(storage_key)

        self.assertFalse(deleted_again)

    def test_storage_key_rejects_path_traversal(self):
        invalid_keys = [
            "../secret.png",
            "tickets/123/../../secret.png",
            "/tickets/123/file.png",
            "tickets/abc/file.png",
            "tickets/123/file with spaces.png",
            "tickets/123/not-a-uuid.png",
        ]

        for storage_key in invalid_keys:
            with self.subTest(storage_key=storage_key):
                with self.assertRaises(ValueError):
                    validate_ticket_attachment_storage_key(
                        storage_key
                    )

    def test_empty_content_is_rejected(self):
        storage_key = build_ticket_attachment_storage_key(
            ticket_id=1,
            extension="webp",
        )

        with self.assertRaises(ValueError):
            write_ticket_attachment_bytes(
                storage_key,
                b"",
            )

        target = resolve_ticket_attachment_path(storage_key)

        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
