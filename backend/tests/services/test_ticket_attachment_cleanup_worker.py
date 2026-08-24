import unittest
from datetime import date, datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

import app.services.ticket_attachment_cleanup_worker as worker


TIJUANA = ZoneInfo("America/Tijuana")


class TicketAttachmentCleanupWorkerTest(unittest.TestCase):
    def test_execute_cleanup_uses_configured_batch_size(
        self,
    ):
        expected = {
            "examined": 2,
            "marked_deleted": 2,
            "files_deleted": 1,
            "files_already_missing": 1,
            "failed": [],
        }

        with (
            patch.dict(
                worker.os.environ,
                {
                    "TICKET_ATTACHMENT_CLEANUP_BATCH_SIZE":
                        "250",
                },
                clear=False,
            ),
            patch.object(
                worker,
                "cleanup_expired_ticket_attachments",
                return_value=expected,
            ) as cleanup_mock,
        ):
            result = (
                worker.execute_ticket_attachment_cleanup()
            )

        cleanup_mock.assert_called_once_with(limit=250)
        self.assertEqual(result, expected)

    def test_invalid_environment_value_uses_default(
        self,
    ):
        with patch.dict(
            worker.os.environ,
            {
                "TICKET_ATTACHMENT_CLEANUP_BATCH_SIZE":
                    "invalid",
            },
            clear=False,
        ):
            value = worker._env_positive_int(
                "TICKET_ATTACHMENT_CLEANUP_BATCH_SIZE",
                500,
            )

        self.assertEqual(value, 500)

    def test_default_run_time_is_0220(self):
        with patch.dict(
            worker.os.environ,
            {
                "TICKET_ATTACHMENT_CLEANUP_RUN_TIME": "",
            },
            clear=False,
        ):
            self.assertEqual(
                worker._resolve_run_time(),
                time(2, 20),
            )

    def test_cleanup_not_due_before_run_time(self):
        now_local = datetime(
            2026,
            8,
            25,
            2,
            19,
            tzinfo=TIJUANA,
        )

        self.assertFalse(
            worker._should_run_cleanup(
                now_local=now_local,
                run_time=time(2, 20),
                last_run_date=None,
            )
        )

    def test_cleanup_due_after_run_time(self):
        now_local = datetime(
            2026,
            8,
            25,
            2,
            21,
            tzinfo=TIJUANA,
        )

        self.assertTrue(
            worker._should_run_cleanup(
                now_local=now_local,
                run_time=time(2, 20),
                last_run_date=None,
            )
        )

    def test_cleanup_not_repeated_same_day(self):
        now_local = datetime(
            2026,
            8,
            25,
            10,
            0,
            tzinfo=TIJUANA,
        )

        self.assertFalse(
            worker._should_run_cleanup(
                now_local=now_local,
                run_time=time(2, 20),
                last_run_date=date(2026, 8, 25),
            )
        )


if __name__ == "__main__":
    unittest.main()
