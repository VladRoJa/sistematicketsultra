import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.services.ticket_attachment_cleanup_worker as worker


class TicketAttachmentCleanupWorkerTest(unittest.TestCase):
    def test_execute_cleanup_uses_configured_batch_size(self):
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
                    "TICKET_ATTACHMENT_CLEANUP_BATCH_SIZE": "250",
                },
                clear=False,
            ),
            patch.object(
                worker,
                "cleanup_expired_ticket_attachments",
                return_value=expected,
            ) as cleanup_mock,
        ):
            result = worker.execute_ticket_attachment_cleanup()

        cleanup_mock.assert_called_once_with(
            limit=250,
        )
        self.assertEqual(result, expected)

    def test_invalid_environment_value_uses_default(self):
        with patch.dict(
            worker.os.environ,
            {
                "TICKET_ATTACHMENT_CLEANUP_BATCH_SIZE": "invalid",
            },
            clear=False,
        ):
            value = worker._env_positive_int(
                "TICKET_ATTACHMENT_CLEANUP_BATCH_SIZE",
                500,
            )

        self.assertEqual(value, 500)

    def test_loop_removes_database_session_after_cycle(self):
        session = MagicMock()

        class FakeAppContext:
            def __enter__(self):
                return self

            def __exit__(
                self,
                exc_type,
                exc,
                traceback,
            ):
                return False

        fake_app = SimpleNamespace(
            app_context=lambda: FakeAppContext(),
        )

        with (
            patch.object(
                worker,
                "create_app",
                return_value=fake_app,
            ),
            patch.object(
                worker,
                "db",
                SimpleNamespace(session=session),
            ),
            patch.object(
                worker,
                "execute_ticket_attachment_cleanup",
                return_value={
                    "examined": 0,
                    "marked_deleted": 0,
                    "files_deleted": 0,
                    "files_already_missing": 0,
                    "failed": [],
                },
            ) as execute_mock,
            patch.object(
                worker.time,
                "sleep",
                side_effect=KeyboardInterrupt,
            ),
        ):
            with self.assertRaises(KeyboardInterrupt):
                worker.run_cleanup_loop()

        execute_mock.assert_called_once_with()
        session.remove.assert_called_once_with()

    def test_cleanup_exception_does_not_skip_session_remove(self):
        session = MagicMock()

        class FakeAppContext:
            def __enter__(self):
                return self

            def __exit__(
                self,
                exc_type,
                exc,
                traceback,
            ):
                return False

        fake_app = SimpleNamespace(
            app_context=lambda: FakeAppContext(),
        )

        with (
            patch.object(
                worker,
                "create_app",
                return_value=fake_app,
            ),
            patch.object(
                worker,
                "db",
                SimpleNamespace(session=session),
            ),
            patch.object(
                worker,
                "execute_ticket_attachment_cleanup",
                side_effect=RuntimeError("cleanup failed"),
            ),
            patch.object(
                worker.time,
                "sleep",
                side_effect=KeyboardInterrupt,
            ),
        ):
            with self.assertRaises(KeyboardInterrupt):
                worker.run_cleanup_loop()

        session.remove.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
