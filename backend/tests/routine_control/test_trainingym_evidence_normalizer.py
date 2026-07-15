from __future__ import annotations

import hashlib
import tempfile
import unittest
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.utils.datetime import WINDOWS_EPOCH, to_excel

from app.routine_control.providers.trainingym_evidence_normalizer import (
    TrainingymInvalidRequiredValueError,
    TrainingymMissingHeaderError,
    TrainingymNormalizationError,
    load_trainingym_evidence_commands_from_xlsx,
    normalize_trainingym_evidence_row,
)


class TrainingymEvidenceNormalizerTestCase(unittest.TestCase):
    fixture_path = Path(__file__).parent / "fixtures" / "trainingym_workout.xlsx"
    observed_at = datetime(2026, 7, 15, 18, 0, tzinfo=timezone.utc)

    @classmethod
    def setUpClass(cls) -> None:
        workbook = load_workbook(cls.fixture_path, data_only=True)
        cls.sheet_names = workbook.sheetnames
        worksheet = workbook["Export"]
        cls.headers = tuple(cell.value for cell in worksheet[1])
        cls.epoch = workbook.epoch
        cls.fixture_rows = [
            dict(zip(cls.headers, values))
            for values in worksheet.iter_rows(
                min_row=2,
                max_row=worksheet.max_row,
                values_only=True,
            )
        ]
        workbook.close()
        cls.valid_row = next(
            row
            for row in cls.fixture_rows
            if isinstance(row["id"], int)
            and isinstance(row["NºRutinas"], int)
            and row["NºRutinas"] > 0
            and "automat" not in str(row["Técnico"]).lower()
        )
        cls.batch = load_trainingym_evidence_commands_from_xlsx(
            cls.fixture_path,
            observed_at_utc=cls.observed_at,
            provider_run_id=41,
        )

    def _normalize(self, row=None, **kwargs):
        return normalize_trainingym_evidence_row(
            dict(row or self.valid_row),
            observed_at_utc=kwargs.get("observed_at_utc", self.observed_at),
            provider_run_id=kwargs.get("provider_run_id", 41),
            center_resolver=kwargs.get("center_resolver"),
            excel_epoch=kwargs.get("excel_epoch", self.epoch),
        )

    def test_fixture_opens_export_sheet(self) -> None:
        self.assertEqual(self.sheet_names, ["Export"])

    def test_fixture_contains_required_headers(self) -> None:
        required = {
            "id",
            "Idsocioexterno",
            "Email",
            "Técnico",
            "NºRutinas",
            "NºPesajes",
            "Fecha",
            "Centro Origen",
        }
        self.assertTrue(required.issubset(self.headers))

    def test_fixture_excludes_non_operational_rows(self) -> None:
        reasons = Counter(row.reason_code for row in self.batch.rejected_rows)
        self.assertEqual(reasons["SUMMARY_ROW"], 1)
        self.assertEqual(reasons["EMPTY_ROW"], 1)
        self.assertEqual(reasons["FILTER_DESCRIPTION_ROW"], 1)

    def test_fixture_excludes_automatic_routines(self) -> None:
        reasons = Counter(row.reason_code for row in self.batch.rejected_rows)
        self.assertEqual(reasons["AUTOMATIC_ROUTINE"], 9)

    def test_weighing_without_routine_is_excluded(self) -> None:
        row = dict(self.valid_row)
        row["NºRutinas"] = 0
        row["NºPesajes"] = 1
        with self.assertRaises(TrainingymNormalizationError) as caught:
            self._normalize(row)
        self.assertEqual(caught.exception.reason_code, "WEIGHING_ONLY")

    def test_no_routine_is_excluded(self) -> None:
        row = dict(self.valid_row)
        row["NºRutinas"] = 0
        row["NºPesajes"] = None
        with self.assertRaises(TrainingymNormalizationError) as caught:
            self._normalize(row)
        self.assertEqual(caught.exception.reason_code, "NO_ROUTINE")

    def test_fixture_generates_human_routine_commands(self) -> None:
        self.assertEqual(self.batch.total_source_rows, 31)
        self.assertEqual(len(self.batch.commands), 19)
        self.assertTrue(all(command.routine_count > 0 for command in self.batch.commands))

    def test_provider_member_id_is_stable_string(self) -> None:
        command = self._normalize()
        self.assertIsInstance(command.provider_member_id, str)
        self.assertEqual(command.provider_member_id, str(self.valid_row["id"]))

    def test_external_member_placeholder_17_becomes_none(self) -> None:
        row = dict(self.valid_row)
        row["Idsocioexterno"] = "17"
        self.assertIsNone(self._normalize(row).external_member_id)

    def test_empty_external_member_id_becomes_none(self) -> None:
        row = dict(self.valid_row)
        row["Idsocioexterno"] = "  "
        self.assertIsNone(self._normalize(row).external_member_id)

    def test_valid_evidence_without_external_member_id_is_accepted(self) -> None:
        row = dict(self.valid_row)
        row["Idsocioexterno"] = None
        command = self._normalize(row)
        self.assertIsNone(command.external_member_id)
        self.assertEqual(command.provider_key, "trainingym")

    def test_excel_datetime_converts_to_date(self) -> None:
        command = self._normalize()
        self.assertIsInstance(self.valid_row["Fecha"], datetime)
        self.assertEqual(command.routine_activity_date, self.valid_row["Fecha"].date())

    def test_excel_serial_uses_supplied_epoch(self) -> None:
        row = dict(self.valid_row)
        expected = date(2026, 2, 3)
        row["Fecha"] = to_excel(expected, epoch=WINDOWS_EPOCH)
        command = self._normalize(row, excel_epoch=WINDOWS_EPOCH)
        self.assertEqual(command.routine_activity_date, expected)

    def test_center_normalization_removes_accents_period_and_extra_spaces(self) -> None:
        row = dict(self.valid_row)
        row["Centro Origen"] = "  Sucursál   Centro.  "
        command = self._normalize(row)
        self.assertEqual(command.provider_center_name, "Sucursál Centro.")
        self.assertEqual(command.provider_center_key, "sucursal centro")

    def test_instructor_normalization_removes_accents_and_extra_spaces(self) -> None:
        row = dict(self.valid_row)
        row["Técnico"] = "  José   Núñez  "
        command = self._normalize(row)
        self.assertEqual(command.instructor_name, "José Núñez")
        self.assertEqual(command.instructor_name_normalized, "jose nunez")

    def test_evidence_identity_key_is_stable(self) -> None:
        self.assertEqual(
            self._normalize().evidence_identity_key,
            self._normalize().evidence_identity_key,
        )

    def test_routine_count_does_not_change_identity(self) -> None:
        row = dict(self.valid_row)
        row["NºRutinas"] += 1
        self.assertEqual(
            self._normalize().evidence_identity_key,
            self._normalize(row).evidence_identity_key,
        )

    def test_routine_count_changes_payload_hash(self) -> None:
        row = dict(self.valid_row)
        row["NºRutinas"] += 1
        self.assertNotEqual(
            self._normalize().payload_hash,
            self._normalize(row).payload_hash,
        )

    def test_observed_at_does_not_change_payload_hash(self) -> None:
        later = self.observed_at + timedelta(days=1)
        self.assertEqual(
            self._normalize().payload_hash,
            self._normalize(observed_at_utc=later).payload_hash,
        )

    def test_email_is_normalized_but_not_part_of_identity(self) -> None:
        first_row = dict(self.valid_row)
        second_row = dict(self.valid_row)
        first_row["Email"] = " User@Example.COM "
        second_row["Email"] = "another@example.com"
        first = self._normalize(first_row)
        second = self._normalize(second_row)
        self.assertEqual(first.email_normalized, "user@example.com")
        self.assertEqual(first.evidence_identity_key, second.evidence_identity_key)

    def test_source_metadata_excludes_sensitive_fields(self) -> None:
        metadata = self._normalize().source_metadata or {}
        forbidden = {"Movil", "NombreApellidos", "Edad", "mobile", "name", "age"}
        self.assertTrue(forbidden.isdisjoint(metadata))

    def test_provider_run_id_is_propagated(self) -> None:
        self.assertEqual(self._normalize(provider_run_id=987).provider_run_id, 987)

    def test_center_resolver_receives_clean_original_name(self) -> None:
        row = dict(self.valid_row)
        row["Centro Origen"] = "  Centro   Norte.  "
        received = []
        command = self._normalize(
            row,
            center_resolver=lambda value: received.append(value) or 5,
        )
        self.assertEqual(received, ["Centro Norte."])
        self.assertEqual(command.sucursal_id, 5)

    def test_unresolved_optional_center_leaves_sucursal_none(self) -> None:
        command = self._normalize(center_resolver=lambda _center: None)
        self.assertIsNone(command.sucursal_id)

    def test_missing_required_header_fails_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "missing_header.xlsx"
            workbook = Workbook()
            worksheet = workbook.active
            worksheet.title = "Export"
            worksheet.append([header for header in self.headers if header != "Fecha"])
            workbook.save(path)
            workbook.close()
            with self.assertRaises(TrainingymMissingHeaderError):
                load_trainingym_evidence_commands_from_xlsx(
                    path,
                    observed_at_utc=self.observed_at,
                    provider_run_id=41,
                )

    def test_naive_observed_at_is_rejected(self) -> None:
        with self.assertRaises(TrainingymInvalidRequiredValueError):
            self._normalize(observed_at_utc=datetime(2026, 7, 15, 18, 0))

    def test_invalid_provider_run_id_type_is_rejected(self) -> None:
        with self.assertRaises(TrainingymInvalidRequiredValueError):
            self._normalize(provider_run_id="41")

    def test_loader_does_not_write_fixture(self) -> None:
        before = hashlib.sha256(self.fixture_path.read_bytes()).hexdigest()
        load_trainingym_evidence_commands_from_xlsx(
            self.fixture_path,
            observed_at_utc=self.observed_at,
            provider_run_id=41,
        )
        after = hashlib.sha256(self.fixture_path.read_bytes()).hexdigest()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()

