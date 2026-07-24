from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.routine_control.pipeline.automated_pipeline_service import (
    run_automated_routine_control_pipeline,
)
from app.routine_control.providers.runtime import (
    ProviderArtifact,
    ProviderExtractionResult,
)


OBSERVED_AT = datetime(2026, 7, 23, 18, 0, tzinfo=timezone.utc)


@dataclass
class _ManualResult:
    succeeded: bool

    def to_dict(self):
        return {"pipeline_run_id": 41, "succeeded": self.succeeded}


class _Extractor:
    def __init__(self, result: ProviderExtractionResult) -> None:
        self.result = result
        self.calls = 0

    def extract(self, **_kwargs):
        self.calls += 1
        return self.result


class AutomatedPipelineServiceTestCase(unittest.TestCase):
    def _environment(self, root: str) -> dict[str, str]:
        return {
            "DIRECCION_LOGIN_URL": "https://gasca.invalid/login",
            "DIRECCION_REPORTE_URL": "https://gasca.invalid/report",
            "DIRECCION_USER": "gasca-user-secret",
            "DIRECCION_PASS": "gasca-pass-secret",
            "TRAININGYM_LOGIN_URL": "https://trainingym.invalid/auth",
            "TRAININGYM_USER": "trainingym-user-secret",
            "TRAININGYM_PASS": "trainingym-pass-secret",
            "TRAININGYM_CENTER_NAME": "UltraGym & Fitness - Azahares",
            "TRAININGYM_WORKOUT_URL": (
                "https://trainingym.invalid/reports/workout"
            ),
            "ROUTINE_CONTROL_ARTIFACT_DIR": root,
        }

    def _success(self, provider: str, dataset: str, path: Path) -> ProviderExtractionResult:
        path.write_bytes(b"xlsx-placeholder")
        return ProviderExtractionResult(
            succeeded=True,
            artifact=ProviderArtifact(
                provider_key=provider,
                dataset_key=dataset,
                local_path=path,
                sha256="a" * 64,
                size_bytes=path.stat().st_size,
                extracted_at_utc=OBSERVED_AT,
                business_date_from=date(2026, 7, 1),
                business_date_to=date(2026, 7, 23),
                source_filename=path.name,
            ),
            attempts=1,
            elapsed_seconds=0.01,
        )

    def _failed(self, code: str) -> ProviderExtractionResult:
        return ProviderExtractionResult(
            succeeded=False,
            artifact=None,
            attempts=1,
            elapsed_seconds=0.01,
            error_code=code,
            error_message="private C:/absolute socio@example.com",
        )

    def test_gasca_failure_skips_trainingym_and_manual_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            gasca = _Extractor(self._failed("GASCA_LOGIN_FAILED"))
            trainingym = _Extractor(self._failed("SHOULD_NOT_RUN"))
            manual_calls = 0

            def manual(**_kwargs):
                nonlocal manual_calls
                manual_calls += 1

            result = run_automated_routine_control_pipeline(
                date_from=date(2026, 7, 1),
                date_to=date(2026, 7, 23),
                observed_at_utc=OBSERVED_AT,
                gasca_extractor=gasca,
                trainingym_extractor=trainingym,
                manual_pipeline=manual,
            )
        self.assertEqual(result.status, "FAILED")
        self.assertEqual(gasca.calls, 1)
        self.assertEqual(trainingym.calls, 0)
        self.assertEqual(manual_calls, 0)

    def test_trainingym_failure_preserves_gasca_and_skips_manual(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            gasca = _Extractor(
                self._success("gasca", "new_members", Path(temp_dir) / "gasca.xlsx")
            )
            trainingym = _Extractor(self._failed("TRAININGYM_EXPORT_FAILED"))
            result = run_automated_routine_control_pipeline(
                date_from=date(2026, 7, 1),
                date_to=date(2026, 7, 23),
                observed_at_utc=OBSERVED_AT,
                gasca_extractor=gasca,
                trainingym_extractor=trainingym,
                manual_pipeline=lambda **_kwargs: self.fail("No debe invocarse"),
            )
            self.assertEqual(result.status, "PARTIAL")
            self.assertTrue(result.gasca.artifact.local_path.exists())
            self.assertIsNone(result.manual_pipeline)

    def test_both_artifacts_invoke_manual_once_and_release_lock(self) -> None:
        lock_events: list[str] = []

        @contextmanager
        def lock_factory(*_args, **_kwargs):
            lock_events.append("acquire")
            try:
                yield
            finally:
                lock_events.append("release")

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            gasca_path = Path(temp_dir) / "gasca.xlsx"
            trainingym_path = Path(temp_dir) / "trainingym.xlsx"
            gasca = _Extractor(self._success("gasca", "new_members", gasca_path))
            trainingym = _Extractor(
                self._success(
                    "trainingym",
                    "routine_assignments",
                    trainingym_path,
                )
            )
            calls: list[dict[str, object]] = []

            def manual(**kwargs):
                calls.append(kwargs)
                return _ManualResult(succeeded=True)

            result = run_automated_routine_control_pipeline(
                date_from=date(2026, 7, 1),
                date_to=date(2026, 7, 23),
                observed_at_utc=OBSERVED_AT,
                gasca_extractor=gasca,
                trainingym_extractor=trainingym,
                manual_pipeline=manual,
                lock_factory=lock_factory,
            )
        self.assertTrue(result.succeeded)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["gasca_xlsx"], gasca_path)
        self.assertEqual(calls[0]["trainingym_xlsx"], trainingym_path)
        self.assertEqual(lock_events, ["acquire", "release"])

    def test_json_summary_has_short_hashes_and_no_paths_or_pii(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            gasca = _Extractor(
                self._success(
                    "gasca",
                    "new_members",
                    Path(temp_dir) / "socio@example.com.xlsx",
                )
            )
            trainingym = _Extractor(self._failed("TRAININGYM_FAILED"))
            result = run_automated_routine_control_pipeline(
                date_from=date(2026, 7, 1),
                date_to=date(2026, 7, 23),
                observed_at_utc=OBSERVED_AT,
                gasca_extractor=gasca,
                trainingym_extractor=trainingym,
            )
            payload = json.dumps(result.to_dict())
        self.assertIn('"sha256": "aaaaaaaaaaaa"', payload)
        self.assertNotIn(temp_dir, payload)
        self.assertNotIn("socio@example.com", payload)
        self.assertNotIn("private C:/absolute", payload)
        
    def test_default_pipeline_uses_real_trainingym_extractor(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            self._environment(temp_dir),
            clear=True,
        ):
            gasca_result = self._success(
                "gasca",
                "new_members",
                Path(temp_dir) / "gasca.xlsx",
            )
            trainingym_result = self._success(
                "trainingym",
                "workout",
                Path(temp_dir) / "trainingym.xlsx",
            )

            gasca = _Extractor(gasca_result)
            trainingym = _Extractor(trainingym_result)

            with patch(
                (
                    "app.routine_control.pipeline."
                    "automated_pipeline_service."
                    "GascaNewMembersExtractor"
                ),
                return_value=gasca,
            ) as gasca_class, patch(
                (
                    "app.routine_control.pipeline."
                    "automated_pipeline_service."
                    "TrainingymWorkoutExtractor"
                ),
                return_value=trainingym,
            ) as trainingym_class:
                result = run_automated_routine_control_pipeline(
                    date_from=date(2026, 7, 1),
                    date_to=date(2026, 7, 23),
                    observed_at_utc=OBSERVED_AT,
                    manual_pipeline=lambda **_kwargs: _ManualResult(
                        succeeded=True,
                    ),
                )

        self.assertTrue(result.succeeded)
        gasca_class.assert_called_once_with()
        trainingym_class.assert_called_once_with()
        self.assertEqual(gasca.calls, 1)
        self.assertEqual(trainingym.calls, 1)        


if __name__ == "__main__":
    unittest.main()

