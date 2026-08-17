import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.services.ticket_attachment_retention_service as retention_service


class TicketAttachmentRetentionServiceTest(unittest.TestCase):
    def setUp(self):
        self.session = MagicMock()

        self.db_patch = patch.object(
            retention_service,
            "db",
            SimpleNamespace(session=self.session),
        )
        self.db_patch.start()

    def tearDown(self):
        self.db_patch.stop()

    def test_schedules_exactly_30_days_without_commit(self):
        attachment_1 = SimpleNamespace(
            id=1,
            delete_after=None,
        )
        attachment_2 = SimpleNamespace(
            id=2,
            delete_after=None,
        )

        self.session.scalars.return_value.all.return_value = [
            attachment_1,
            attachment_2,
        ]

        finalized_at = datetime(
            2026,
            8,
            16,
            23,
            15,
            0,
            tzinfo=timezone.utc,
        )

        count, delete_after = (
            retention_service.schedule_ticket_attachment_retention(
                ticket_id=137,
                finalized_at=finalized_at,
            )
        )

        expected = finalized_at + timedelta(days=30)

        self.assertEqual(count, 2)
        self.assertEqual(delete_after, expected)
        self.assertEqual(
            attachment_1.delete_after,
            expected,
        )
        self.assertEqual(
            attachment_2.delete_after,
            expected,
        )

        self.session.commit.assert_not_called()

    def test_naive_datetime_is_treated_as_utc(self):
        attachment = SimpleNamespace(
            id=1,
            delete_after=None,
        )

        self.session.scalars.return_value.all.return_value = [
            attachment
        ]

        finalized_at = datetime(
            2026,
            8,
            16,
            23,
            15,
            0,
        )

        _, delete_after = (
            retention_service.schedule_ticket_attachment_retention(
                ticket_id=137,
                finalized_at=finalized_at,
            )
        )

        expected = datetime(
            2026,
            9,
            15,
            23,
            15,
            0,
            tzinfo=timezone.utc,
        )

        self.assertEqual(delete_after, expected)
        self.assertEqual(
            attachment.delete_after,
            expected,
        )

    def test_ticket_without_attachment_is_valid(self):
        self.session.scalars.return_value.all.return_value = []

        finalized_at = datetime(
            2026,
            8,
            16,
            23,
            15,
            tzinfo=timezone.utc,
        )

        count, delete_after = (
            retention_service.schedule_ticket_attachment_retention(
                ticket_id=999,
                finalized_at=finalized_at,
            )
        )

        self.assertEqual(count, 0)
        self.assertEqual(
            delete_after,
            finalized_at + timedelta(days=30),
        )

        self.session.commit.assert_not_called()

    def test_invalid_ticket_id_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "ticket_id inválido",
        ):
            retention_service.schedule_ticket_attachment_retention(
                ticket_id=0,
            )

        self.session.scalars.assert_not_called()
        self.session.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
