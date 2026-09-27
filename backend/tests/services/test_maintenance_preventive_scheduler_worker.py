from datetime import date, datetime, time, timedelta
import unittest
from zoneinfo import ZoneInfo

from app.services import maintenance_preventive_scheduler_worker as worker


TZ = ZoneInfo("America/Tijuana")


class MaintenancePreventiveSchedulerWorkerTest(unittest.TestCase):
    def test_should_not_run_before_configured_time(self):
        now_local = datetime(2026, 9, 21, 0, 9, tzinfo=TZ)

        self.assertFalse(
            worker._should_run(
                now_local=now_local,
                run_time=time(0, 10),
                last_success_date=None,
                next_retry_at=None,
            )
        )

    def test_should_run_once_time_is_reached(self):
        now_local = datetime(2026, 9, 21, 0, 10, tzinfo=TZ)

        self.assertTrue(
            worker._should_run(
                now_local=now_local,
                run_time=time(0, 10),
                last_success_date=None,
                next_retry_at=None,
            )
        )

    def test_should_not_repeat_after_success_same_day(self):
        now_local = datetime(2026, 9, 21, 8, 0, tzinfo=TZ)

        self.assertFalse(
            worker._should_run(
                now_local=now_local,
                run_time=time(0, 10),
                last_success_date=date(2026, 9, 21),
                next_retry_at=None,
            )
        )

    def test_should_wait_until_retry_window(self):
        now_local = datetime(2026, 9, 21, 0, 20, tzinfo=TZ)
        retry_at = now_local + timedelta(minutes=5)

        self.assertFalse(
            worker._should_run(
                now_local=now_local,
                run_time=time(0, 10),
                last_success_date=None,
                next_retry_at=retry_at,
            )
        )


if __name__ == "__main__":
    unittest.main()
