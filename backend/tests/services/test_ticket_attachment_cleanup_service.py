import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.services.ticket_attachment_cleanup_service as cleanup_service


class TicketAttachmentCleanupServiceTest(unittest.TestCase):
    def setUp(self):
        self.session = MagicMock()

        self.db_patch = patch.object(
            cleanup_service,
            "db",
            SimpleNamespace(session=self.session),
        )
        self.db_patch.start()

        self.delete_patch = patch.object(
            cleanup_service,
            "delete_ticket_attachment",
        )
        self.mock_delete = self.delete_patch.start()

        self.now = datetime(
            2026,
            9,
            16,
            14,
            30,
            tzinfo=timezone.utc,
        )

    def tearDown(self):
        self.delete_patch.stop()
        self.db_patch.stop()

    def _attachment(
        self,
        attachment_id,
        storage_key,
    ):
        return SimpleNamespace(
            id=attachment_id,
            storage_key=storage_key,
            deleted_at=None,
        )

    def test_existing_file_is_deleted_and_marked(self):
        attachment = self._attachment(
            1,
            "tickets/137/"
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg",
        )

        self.session.scalars.return_value.all.return_value = [
            attachment
        ]
        self.mock_delete.return_value = True

        result = (
            cleanup_service.cleanup_expired_ticket_attachments(
                now=self.now,
            )
        )

        self.mock_delete.assert_called_once_with(
            attachment.storage_key
        )

        self.assertEqual(
            attachment.deleted_at,
            self.now,
        )
        self.assertEqual(result["examined"], 1)
        self.assertEqual(result["marked_deleted"], 1)
        self.assertEqual(result["files_deleted"], 1)
        self.assertEqual(
            result["files_already_missing"],
            0,
        )
        self.assertEqual(result["failed"], [])

        self.session.commit.assert_called_once_with()
        self.session.rollback.assert_not_called()

    def test_missing_file_is_still_marked_deleted(self):
        attachment = self._attachment(
            2,
            "tickets/137/"
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.png",
        )

        self.session.scalars.return_value.all.return_value = [
            attachment
        ]
        self.mock_delete.return_value = False

        result = (
            cleanup_service.cleanup_expired_ticket_attachments(
                now=self.now,
            )
        )

        self.assertEqual(
            attachment.deleted_at,
            self.now,
        )
        self.assertEqual(result["marked_deleted"], 1)
        self.assertEqual(result["files_deleted"], 0)
        self.assertEqual(
            result["files_already_missing"],
            1,
        )

        self.session.commit.assert_called_once_with()

    def test_one_bad_file_does_not_block_other_attachment(self):
        bad = self._attachment(
            3,
            "tickets/137/"
            "cccccccccccccccccccccccccccccccc.webp",
        )
        good = self._attachment(
            4,
            "tickets/138/"
            "dddddddddddddddddddddddddddddddd.jpg",
        )

        self.session.scalars.return_value.all.return_value = [
            bad,
            good,
        ]

        self.mock_delete.side_effect = [
            OSError("permiso denegado"),
            True,
        ]

        result = (
            cleanup_service.cleanup_expired_ticket_attachments(
                now=self.now,
            )
        )

        self.assertIsNone(bad.deleted_at)
        self.assertEqual(
            good.deleted_at,
            self.now,
        )

        self.assertEqual(result["examined"], 2)
        self.assertEqual(result["marked_deleted"], 1)
        self.assertEqual(result["files_deleted"], 1)
        self.assertEqual(len(result["failed"]), 1)
        self.assertEqual(
            result["failed"][0]["attachment_id"],
            3,
        )

        self.session.commit.assert_called_once_with()

    def test_empty_batch_does_not_commit(self):
        self.session.scalars.return_value.all.return_value = []

        result = (
            cleanup_service.cleanup_expired_ticket_attachments(
                now=self.now,
            )
        )

        self.assertEqual(result["examined"], 0)
        self.assertEqual(result["marked_deleted"], 0)

        self.mock_delete.assert_not_called()
        self.session.commit.assert_not_called()
        self.session.rollback.assert_not_called()

    def test_commit_failure_rolls_back_and_propagates(self):
        attachment = self._attachment(
            5,
            "tickets/139/"
            "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee.jpg",
        )

        self.session.scalars.return_value.all.return_value = [
            attachment
        ]
        self.mock_delete.return_value = True
        self.session.commit.side_effect = RuntimeError(
            "db unavailable"
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "db unavailable",
        ):
            cleanup_service.cleanup_expired_ticket_attachments(
                now=self.now,
            )

        self.session.rollback.assert_called_once_with()

    def test_invalid_limit_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "limit inválido",
        ):
            cleanup_service.cleanup_expired_ticket_attachments(
                now=self.now,
                limit=0,
            )

        self.session.scalars.assert_not_called()
        self.mock_delete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
