from __future__ import annotations

import unittest
from datetime import (
    date,
    datetime,
    time,
    timezone,
)
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.routine_control.scheduler import (
    routine_control_scheduler_worker as worker,
)


TIJUANA = ZoneInfo("America/Tijuana")


class RoutineControlSchedulerWorkerTest(
    unittest.TestCase
):
    def test_default_run_times_are_four_daily_slots(
        self,
    ) -> None:
        with patch.dict(
            "os.environ",
            {
                "ROUTINE_CONTROL_RUN_TIMES": "",
                "ROUTINE_CONTROL_DAILY_TIME": "",
            },
            clear=False,
        ):
            run_times = worker._resolve_run_times()

        self.assertEqual(
            run_times,
            (
                time(9, 20),
                time(13, 20),
                time(17, 20),
                time(21, 20),
            ),
        )

    def test_legacy_daily_time_is_still_supported(
        self,
    ) -> None:
        with patch.dict(
            "os.environ",
            {
                "ROUTINE_CONTROL_RUN_TIMES": "",
                "ROUTINE_CONTROL_DAILY_TIME": "08:30",
            },
            clear=False,
        ):
            run_times = worker._resolve_run_times()

        self.assertEqual(
            run_times,
            (time(8, 30),),
        )

    def test_latest_elapsed_slot_is_selected(
        self,
    ) -> None:
        result = worker._resolve_due_scheduled_time(
            now_local=datetime(
                2026,
                8,
                24,
                14,
                0,
                tzinfo=TIJUANA,
            ),
            run_times=(
                time(9, 20),
                time(13, 20),
                time(17, 20),
                time(21, 20),
            ),
        )

        self.assertEqual(
            result,
            time(13, 20),
        )

    def test_before_first_slot_does_not_resolve(
        self,
    ) -> None:
        result = worker._resolve_due_scheduled_time(
            now_local=datetime(
                2026,
                8,
                24,
                9,
                19,
                tzinfo=TIJUANA,
            ),
            run_times=(
                time(9, 20),
                time(13, 20),
            ),
        )

        self.assertIsNone(result)

    def test_pending_slot_runs_after_scheduled_time(
        self,
    ) -> None:
        now_local = datetime(
            2026,
            8,
            24,
            9,
            21,
            tzinfo=TIJUANA,
        )

        decision = (
            worker.decide_routine_control_scheduler_action(
                now_local,
                scheduled_time=time(9, 20),
                has_successful_run=False,
                already_attempted=False,
            )
        )

        self.assertIsNotNone(decision)
        assert decision is not None

        self.assertEqual(
            decision.business_date,
            date(2026, 8, 24),
        )
        self.assertEqual(
            decision.slot_key,
            (
                date(2026, 8, 24),
                9,
                20,
            ),
        )
        self.assertEqual(
            decision.trigger_source,
            "ROUTINE_CONTROL_SCHEDULER_09_20",
        )
        self.assertEqual(
            decision.date_from,
            date(2026, 8, 1),
        )
        self.assertEqual(
            decision.date_to,
            date(2026, 8, 24),
        )

    def test_successful_slot_is_not_repeated(
        self,
    ) -> None:
        decision = (
            worker.decide_routine_control_scheduler_action(
                datetime(
                    2026,
                    8,
                    24,
                    9,
                    30,
                    tzinfo=TIJUANA,
                ),
                scheduled_time=time(9, 20),
                has_successful_run=True,
                already_attempted=False,
            )
        )

        self.assertIsNone(decision)

    def test_same_process_slot_attempt_is_not_repeated(
        self,
    ) -> None:
        decision = (
            worker.decide_routine_control_scheduler_action(
                datetime(
                    2026,
                    8,
                    24,
                    9,
                    30,
                    tzinfo=TIJUANA,
                ),
                scheduled_time=time(9, 20),
                has_successful_run=False,
                already_attempted=True,
            )
        )

        self.assertIsNone(decision)

    def test_execution_uses_slot_specific_metadata(
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

        decision = worker.RoutineControlSchedulerDecision(
            business_date=date(2026, 8, 24),
            date_from=date(2026, 8, 1),
            date_to=date(2026, 8, 24),
            observed_at_utc=datetime(
                2026,
                8,
                24,
                16,
                20,
                tzinfo=timezone.utc,
            ),
            scheduled_time=time(9, 20),
            slot_key=(
                date(2026, 8, 24),
                9,
                20,
            ),
            trigger_source=(
                "ROUTINE_CONTROL_SCHEDULER_09_20"
            ),
            reason="scheduled_slot_pending",
        )

        result = (
            worker.execute_routine_control_scheduler_decision(
                decision,
                pipeline_service=pipeline,
            )
        )

        self.assertTrue(result.succeeded)
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            calls[0]["generation_mode"],
            worker.SCHEDULED_GENERATION_MODE,
        )
        self.assertEqual(
            calls[0]["trigger_source"],
            "ROUTINE_CONTROL_SCHEDULER_09_20",
        )
        self.assertTrue(
            calls[0]["headless"]
        )


if __name__ == "__main__":
    unittest.main()
