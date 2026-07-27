from __future__ import annotations

import unittest
from datetime import date

from app.routine_control.pipeline.run_repository import (
    build_manual_pipeline_idempotency_key,
)


class RoutineControlRunRepositoryTest(unittest.TestCase):
    def test_idempotency_separates_run_provenance(
        self,
    ) -> None:
        values = {
            "gasca_content_hash": "a" * 64,
            "trainingym_content_hash": "b" * 64,
            "date_from": date(2026, 7, 1),
            "date_to": date(2026, 7, 26),
        }

        historical_manual = (
            build_manual_pipeline_idempotency_key(
                **values
            )
        )

        explicit_manual = (
            build_manual_pipeline_idempotency_key(
                **values,
                generation_mode="MANUAL",
                trigger_source="MANUAL_CLI",
            )
        )

        automated_cli = (
            build_manual_pipeline_idempotency_key(
                **values,
                generation_mode="MANUAL",
                trigger_source=(
                    "AUTOMATED_PROVIDER_CLI"
                ),
            )
        )

        scheduled = (
            build_manual_pipeline_idempotency_key(
                **values,
                generation_mode="SCHEDULED",
                trigger_source=(
                    "ROUTINE_CONTROL_SCHEDULER"
                ),
            )
        )

        self.assertEqual(
            historical_manual,
            explicit_manual,
        )
        self.assertTrue(
            historical_manual.startswith("manual:")
        )
        self.assertTrue(
            automated_cli.startswith("pipeline:")
        )
        self.assertTrue(
            scheduled.startswith("pipeline:")
        )
        self.assertNotEqual(
            historical_manual,
            automated_cli,
        )
        self.assertNotEqual(
            historical_manual,
            scheduled,
        )
        self.assertNotEqual(
            automated_cli,
            scheduled,
        )


if __name__ == "__main__":
    unittest.main()
