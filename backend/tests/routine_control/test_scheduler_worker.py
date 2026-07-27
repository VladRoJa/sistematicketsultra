from __future__ import annotations

import unittest
from datetime import (
    date,
    datetime,
    time,
    timezone,
)
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.routine_control.scheduler.routine_control_scheduler_worker import (
    SCHEDULED_GENERATION_MODE,
    SCHEDULER_TRIGGER_SOURCE,
    RoutineControlSchedulerDecision,
    decide_routine_control_scheduler_action,
    execute_routine_control_scheduler_decision,
)


TIJUANA = ZoneInfo("America/Tijuana")


class RoutineControlSchedulerWorkerTest(
    unittest.TestCase
):
    def test_before_daily_time_does_not_run(
        self,
    ) -> None:
        decision = (
            decide_routine_control_scheduler_action(
                datetime(
                    2026,
                    7,
                    26,
                    8,
                    29,
                    tzinfo=TIJUANA,
                ),
                scheduled_time=time(8, 30),
                has_successful_run=False,
                already_attempted=False,
            )
        )

        self.assertIsNone(decision)

    def test_pending_cutoff_runs_after_daily_time(
        self,
    ) -> None:
        now_local = datetime(
            2026,
            7,
            26,
            8,
            31,
            tzinfo=TIJUANA,
        )

        decision = (
            decide_routine_control_scheduler_action(
                now_local,
                scheduled_time=time(8, 30),
                has_successful_run=False,
                already_attempted=False,
            )
        )

        self.assertIsNotNone(decision)
        self.assertEqual(
            decision.business_date,
            date(2026, 7, 26),
        )
        self.assertEqual(
            decision.date_from,
            date(2026, 7, 1),
        )
        self.assertEqual(
            decision.date_to,
            date(2026, 7, 26),
        )
        self.assertEqual(
            decision.observed_at_utc,
            now_local.astimezone(timezone.utc),
        )

    def test_successful_cutoff_is_not_repeated(
        self,
    ) -> None:
        decision = (
            decide_routine_control_scheduler_action(
                datetime(
                    2026,
                    7,
                    26,
                    9,
                    0,
                    tzinfo=TIJUANA,
                ),
                scheduled_time=time(8, 30),
                has_successful_run=True,
                already_attempted=False,
            )
        )

        self.assertIsNone(decision)

    def test_same_process_attempt_is_not_repeated(
        self,
    ) -> None:
        decision = (
            decide_routine_control_scheduler_action(
                datetime(
                    2026,
                    7,
                    26,
                    9,
                    0,
                    tzinfo=TIJUANA,
                ),
                scheduled_time=time(8, 30),
                has_successful_run=False,
                already_attempted=True,
            )
        )

        self.assertIsNone(decision)

    def test_execution_uses_scheduled_metadata(
        self,
    ) -> None:
        calls: list[dict[str, object]] = []

        def pipeline(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                status="SUCCESS",
                succeeded=True,
                error_code=None,
            )

        decision = RoutineControlSchedulerDecision(
            business_date=date(2026, 7, 26),
            date_from=date(2026, 7, 1),
            date_to=date(2026, 7, 26),
            observed_at_utc=datetime(
                2026,
                7,
                26,
                15,
                30,
                tzinfo=timezone.utc,
            ),
            reason="daily_cutoff_pending",
        )

        result = (
            execute_routine_control_scheduler_decision(
                decision,
                pipeline_service=pipeline,
            )
        )

        self.assertTrue(result.succeeded)
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            calls[0]["date_from"],
            date(2026, 7, 1),
        )
        self.assertEqual(
            calls[0]["date_to"],
            date(2026, 7, 26),
        )
        self.assertEqual(
            calls[0]["generation_mode"],
            SCHEDULED_GENERATION_MODE,
        )
        self.assertEqual(
            calls[0]["trigger_source"],
            SCHEDULER_TRIGGER_SOURCE,
        )
        self.assertTrue(calls[0]["headless"])


if __name__ == "__main__":
    unittest.main()
