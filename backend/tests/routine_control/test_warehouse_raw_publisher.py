from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from flask import Flask

from app.routine_control.pipeline.warehouse_raw_publisher import (
    RoutineControlWarehousePublishError,
    publish_gasca_new_members_artifact_to_warehouse,
)
from app.routine_control.providers.runtime import ProviderArtifact


OBSERVED_AT = datetime(2026, 7, 27, 16, 30, tzinfo=timezone.utc)


class WarehouseRawPublisherTestCase(unittest.TestCase):
    def _artifact(
        self,
        path: Path,
        *,
        provider_key: str = "gasca",
        dataset_key: str = "new_members",
    ) -> ProviderArtifact:
        path.write_bytes(b"xlsx-placeholder")

        return ProviderArtifact(
            provider_key=provider_key,
            dataset_key=dataset_key,
            local_path=path,
            sha256="a" * 64,
            size_bytes=path.stat().st_size,
            extracted_at_utc=OBSERVED_AT,
            business_date_from=date(2026, 7, 1),
            business_date_to=date(2026, 7, 27),
            source_filename="gasca-new-members.xlsx",
        )

    def test_maps_provider_artifact_to_warehouse_upload_creator(self) -> None:
        app = Flask(__name__)
        calls: list[dict[str, object]] = []

        def upload_creator(**kwargs):
            calls.append(kwargs)
            return {
                "warehouse_upload_id": 71,
                "upload_status": "created",
                "metadata": {
                    "duplicate_detected": False,
                    "duplicate_upload_id": None,
                },
            }

        app.config["WAREHOUSE_INTERNAL_UPLOAD_CREATOR"] = upload_creator

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = self._artifact(
                Path(temp_dir) / "gasca-new-members.xlsx"
            )

            with app.app_context():
                result = (
                    publish_gasca_new_members_artifact_to_warehouse(
                        artifact=artifact,
                        generation_mode="SCHEDULED",
                        trigger_source="ROUTINE_CONTROL_SCHEDULER",
                    )
                )

        self.assertEqual(result.warehouse_upload_id, 71)
        self.assertEqual(result.upload_status, "created")
        self.assertFalse(result.duplicate_detected)
        self.assertEqual(len(calls), 1)

        call = calls[0]
        self.assertEqual(
            call["report_type_key"],
            "ventas_nuevos_socios_detalle",
        )
        self.assertEqual(
            call["original_filename"],
            "gasca-new-members.xlsx",
        )
        self.assertEqual(
            call["captured_at"],
            OBSERVED_AT,
        )
        self.assertEqual(
            call["metadata"]["date_from"],
            "2026-07-01",
        )
        self.assertEqual(
            call["metadata"]["date_to"],
            "2026-07-27",
        )
        self.assertEqual(
            call["metadata"]["generation_mode"],
            "SCHEDULED",
        )
        self.assertEqual(
            call["metadata"]["trigger_source"],
            "ROUTINE_CONTROL_SCHEDULER",
        )

    def test_preserves_reused_existing_result(self) -> None:
        app = Flask(__name__)

        app.config["WAREHOUSE_INTERNAL_UPLOAD_CREATOR"] = (
            lambda **_kwargs: {
                "warehouse_upload_id": 88,
                "upload_status": "reused_existing",
                "metadata": {
                    "duplicate_detected": True,
                    "duplicate_upload_id": 88,
                },
            }
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = self._artifact(
                Path(temp_dir) / "gasca-new-members.xlsx"
            )

            with app.app_context():
                result = (
                    publish_gasca_new_members_artifact_to_warehouse(
                        artifact=artifact,
                        generation_mode="SCHEDULED",
                        trigger_source="ROUTINE_CONTROL_SCHEDULER",
                    )
                )

        self.assertEqual(result.warehouse_upload_id, 88)
        self.assertEqual(result.upload_status, "reused_existing")
        self.assertTrue(result.duplicate_detected)
        self.assertEqual(result.duplicate_upload_id, 88)

    def test_rejects_non_gasca_artifact_before_upload(self) -> None:
        app = Flask(__name__)
        upload_calls = 0

        def upload_creator(**_kwargs):
            nonlocal upload_calls
            upload_calls += 1

        app.config["WAREHOUSE_INTERNAL_UPLOAD_CREATOR"] = upload_creator

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = self._artifact(
                Path(temp_dir) / "invalid.xlsx",
                provider_key="trainingym",
            )

            with app.app_context():
                with self.assertRaises(
                    RoutineControlWarehousePublishError
                ):
                    publish_gasca_new_members_artifact_to_warehouse(
                        artifact=artifact,
                        generation_mode="SCHEDULED",
                        trigger_source="ROUTINE_CONTROL_SCHEDULER",
                    )

        self.assertEqual(upload_calls, 0)

    def test_requires_registered_warehouse_upload_creator(self) -> None:
        app = Flask(__name__)

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = self._artifact(
                Path(temp_dir) / "gasca-new-members.xlsx"
            )

            with app.app_context():
                with self.assertRaisesRegex(
                    RoutineControlWarehousePublishError,
                    "WAREHOUSE_INTERNAL_UPLOAD_CREATOR",
                ):
                    publish_gasca_new_members_artifact_to_warehouse(
                        artifact=artifact,
                        generation_mode="SCHEDULED",
                        trigger_source="ROUTINE_CONTROL_SCHEDULER",
                    )


if __name__ == "__main__":
    unittest.main()
