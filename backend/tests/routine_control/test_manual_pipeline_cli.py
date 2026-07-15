from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from app.routine_control.cli.manual_pipeline import main
from app.routine_control.pipeline.manual_pipeline_service import (
    ManualRoutineControlPipelineResult,
)


class _App:
    class _Context:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def app_context(self):
        return self._Context()


def _result(*, succeeded: bool) -> ManualRoutineControlPipelineResult:
    return ManualRoutineControlPipelineResult(
        pipeline_run_id=1,
        reused_existing_run=False,
        gasca_provider_run_id=2,
        trainingym_provider_run_id=3,
        gasca_source_rows=33,
        gasca_accepted=33,
        gasca_rejected=0,
        members_created=33,
        members_updated=0,
        trainingym_source_rows=31,
        trainingym_accepted=19,
        trainingym_rejected=12,
        evidences_created=19,
        evidences_updated=0,
        links_created=16,
        links_existing=0,
        links_by_external_id=16,
        links_by_email=0,
        unmatched_evidences=3,
        ambiguous_evidences=0,
        incidents_created=4,
        incidents_resolved=0,
        members_reconciled=33,
        status_counts=MappingProxyType(
            {
                "CLASSIFIED/SIN_RUTINA": 22,
                "CLASSIFIED/CON_RUTINA": 7,
                "CLASSIFIED/NO_DESEA_RUTINA": 0,
                "INCIDENT/NULL": 4,
            }
        ),
        succeeded=succeeded,
    )


class ManualPipelineCliTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.gasca = Path(self.temp.name) / "gasca.xlsx"
        self.trainingym = Path(self.temp.name) / "trainingym.xlsx"
        self.gasca.write_bytes(b"gasca")
        self.trainingym.write_bytes(b"trainingym")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _argv(self, *, as_json: bool = False) -> list[str]:
        values = [
            "--gasca-xlsx",
            str(self.gasca),
            "--trainingym-xlsx",
            str(self.trainingym),
            "--observed-at-utc",
            "2026-07-15T18:00:00+00:00",
            "--requested-by",
            "operator<script>",
        ]
        if as_json:
            values.append("--json")
        return values

    def test_json_is_deterministic_and_success_returns_zero(self) -> None:
        output = io.StringIO()
        with patch(
            "app.routine_control.cli.manual_pipeline.create_app",
            return_value=_App(),
        ), patch(
            "app.routine_control.cli.manual_pipeline.run_manual_routine_control_pipeline",
            return_value=_result(succeeded=True),
        ) as service, redirect_stdout(output):
            code = main(self._argv(as_json=True))

        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertTrue(payload["succeeded"])
        self.assertEqual(payload["status_counts"]["INCIDENT/NULL"], 4)
        self.assertNotIn("operator", output.getvalue())
        self.assertEqual(
            service.call_args.kwargs["observed_at_utc"],
            datetime(2026, 7, 15, 18, 0, tzinfo=timezone.utc),
        )

    def test_failed_result_returns_nonzero(self) -> None:
        output = io.StringIO()
        with patch(
            "app.routine_control.cli.manual_pipeline.create_app",
            return_value=_App(),
        ), patch(
            "app.routine_control.cli.manual_pipeline.run_manual_routine_control_pipeline",
            return_value=_result(succeeded=False),
        ), redirect_stdout(output):
            code = main(self._argv())
        self.assertEqual(code, 1)
        self.assertIn("succeeded=false", output.getvalue())

    def test_unexpected_error_is_sanitized_and_returns_nonzero(self) -> None:
        error = io.StringIO()
        with patch(
            "app.routine_control.cli.manual_pipeline.create_app",
            return_value=_App(),
        ), patch(
            "app.routine_control.cli.manual_pipeline.run_manual_routine_control_pipeline",
            side_effect=RuntimeError("secret@example.com"),
        ), redirect_stderr(error):
            code = main(self._argv())
        self.assertEqual(code, 1)
        self.assertEqual(error.getvalue().strip(), "manual_pipeline_failed=RuntimeError")


if __name__ == "__main__":
    unittest.main()
