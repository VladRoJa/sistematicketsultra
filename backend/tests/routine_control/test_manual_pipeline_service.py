from __future__ import annotations

import hashlib
import tempfile
import unittest
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from openpyxl import Workbook
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app import create_app
from app.extensions import db
from app.models.routine_control import (
    RoutineAssignmentEvidenceORM,
    RoutineControlIncidentORM,
    RoutineControlMemberEvidenceORM,
    RoutineControlMemberORM,
    RoutineControlPipelineRunORM,
    RoutineControlProviderRunORM,
)
from app.models.warehouse import TrackBranchAliasORM, TrackBranchCatalogORM
from app.routine_control.pipeline.branch_resolver import resolve_gasca_branch_id
from app.routine_control.pipeline.manual_pipeline_service import (
    run_manual_routine_control_pipeline,
)
from app.routine_control.pipeline.run_repository import (
    build_manual_pipeline_idempotency_key,
)
from app.routine_control.providers.gasca_member_normalizer import (
    load_gasca_member_commands_from_xlsx,
)
from app.routine_control.providers.trainingym_evidence_normalizer import (
    load_trainingym_evidence_commands_from_xlsx,
)


FIXTURES = Path(__file__).parent / "fixtures"
GASCA_FIXTURE = FIXTURES / "gasca_socios_nuevos_detallado.xlsx"
TRAININGYM_FIXTURE = FIXTURES / "trainingym_workout.xlsx"
OBSERVED_AT = datetime(2026, 7, 15, 18, 0, tzinfo=timezone.utc)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BranchResolverPostgresTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = create_app()
        cls.context = cls.app.app_context()
        cls.context.push()
        if db.engine.dialect.name != "postgresql":
            raise RuntimeError("Estas pruebas requieren PostgreSQL real.")

    @classmethod
    def tearDownClass(cls) -> None:
        db.session.remove()
        cls.context.pop()

    def test_known_unknown_outer_spaces_and_injected_session(self) -> None:
        factory = sessionmaker(bind=db.engine, class_=Session)
        injected = factory()
        try:
            known = resolve_gasca_branch_id(
                "  VILLAS DEL REY  ",
                session=injected,
            )
            unknown = resolve_gasca_branch_id(
                "NO EXISTE EN TRACK",
                session=injected,
            )
        finally:
            injected.close()
        self.assertIsInstance(known, int)
        self.assertGreater(known, 0)
        self.assertIsNone(unknown)

    def test_catalog_without_sucursal_id_returns_none(self) -> None:
        key = f"TEST_NULL_{uuid4().hex}"
        catalog = TrackBranchCatalogORM(
            sucursal_canon=key,
            sucursal_id=None,
            track_label=key,
            display_order=9999,
            is_track_active=True,
        )
        alias = TrackBranchAliasORM(
            source_family="gasca_family",
            raw_branch_name=key,
            sucursal_canon=key,
            is_active=True,
        )
        db.session.add(catalog)
        db.session.flush()
        db.session.add(alias)
        db.session.commit()
        try:
            self.assertIsNone(resolve_gasca_branch_id(key, session=db.session))
        finally:
            db.session.delete(alias)
            db.session.delete(catalog)
            db.session.commit()

    def test_gasca_opt_out_persists_unresolved_command(self) -> None:
        batch = load_gasca_member_commands_from_xlsx(
            GASCA_FIXTURE,
            observed_at_utc=OBSERVED_AT,
            branch_resolver=lambda _branch: None,
            require_resolved_branch=False,
        )
        self.assertEqual(len(batch.commands), 33)
        self.assertTrue(all(command.sucursal_id is None for command in batch.commands))


class ManualPipelineFixturePostgresTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = create_app()
        cls.context = cls.app.app_context()
        cls.context.push()
        if db.engine.dialect.name != "postgresql":
            raise RuntimeError("Estas pruebas requieren PostgreSQL real.")
        cls.gasca_commands = load_gasca_member_commands_from_xlsx(
            GASCA_FIXTURE,
            observed_at_utc=OBSERVED_AT,
            branch_resolver=lambda _branch: 1,
        ).commands
        cls.trainingym_commands = load_trainingym_evidence_commands_from_xlsx(
            TRAININGYM_FIXTURE,
            observed_at_utc=OBSERVED_AT,
            provider_run_id=None,
        ).commands
        cls.source_record_ids = [command.source_record_id for command in cls.gasca_commands]
        cls.evidence_keys = [command.evidence_identity_key for command in cls.trainingym_commands]
        cls.idempotency_key = build_manual_pipeline_idempotency_key(
            gasca_content_hash=_sha256(GASCA_FIXTURE),
            trainingym_content_hash=_sha256(TRAININGYM_FIXTURE),
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._cleanup()
        db.session.remove()
        cls.context.pop()

    @classmethod
    def _cleanup(cls) -> None:
        db.session.rollback()
        member_ids = select(RoutineControlMemberORM.id).where(
            RoutineControlMemberORM.source_system == "gasca",
            RoutineControlMemberORM.source_record_id.in_(cls.source_record_ids),
        )
        evidence_ids = select(RoutineAssignmentEvidenceORM.id).where(
            RoutineAssignmentEvidenceORM.provider_key == "trainingym",
            RoutineAssignmentEvidenceORM.evidence_identity_key.in_(cls.evidence_keys),
        )
        db.session.execute(delete(RoutineControlIncidentORM).where(RoutineControlIncidentORM.member_id.in_(member_ids)))
        db.session.execute(delete(RoutineControlMemberEvidenceORM).where((RoutineControlMemberEvidenceORM.member_id.in_(member_ids)) | (RoutineControlMemberEvidenceORM.evidence_id.in_(evidence_ids))))
        db.session.execute(delete(RoutineAssignmentEvidenceORM).where(RoutineAssignmentEvidenceORM.id.in_(evidence_ids)))
        db.session.execute(delete(RoutineControlMemberORM).where(RoutineControlMemberORM.id.in_(member_ids)))
        pipeline_ids = select(RoutineControlPipelineRunORM.id).where(RoutineControlPipelineRunORM.idempotency_key == cls.idempotency_key)
        db.session.execute(delete(RoutineControlProviderRunORM).where(RoutineControlProviderRunORM.pipeline_run_id.in_(pipeline_ids)))
        db.session.execute(delete(RoutineControlPipelineRunORM).where(RoutineControlPipelineRunORM.id.in_(pipeline_ids)))
        db.session.commit()

    def setUp(self) -> None:
        self._cleanup()

    def tearDown(self) -> None:
        self._cleanup()

    def test_end_to_end_fixture_and_identical_reexecution(self) -> None:
        first = run_manual_routine_control_pipeline(
            gasca_xlsx=GASCA_FIXTURE,
            trainingym_xlsx=TRAININGYM_FIXTURE,
            observed_at_utc=OBSERVED_AT,
        )
        self.assertTrue(first.succeeded)
        self.assertFalse(first.reused_existing_run)
        self.assertEqual((first.gasca_source_rows, first.gasca_accepted), (33, 33))
        self.assertEqual(first.members_created, 33)
        self.assertEqual((first.trainingym_accepted, first.trainingym_rejected), (19, 12))
        rejection_reasons = Counter(
            rejected.reason_code
            for rejected in load_trainingym_evidence_commands_from_xlsx(
                TRAININGYM_FIXTURE,
                observed_at_utc=OBSERVED_AT,
                provider_run_id=first.trainingym_provider_run_id,
            ).rejected_rows
        )
        self.assertEqual(
            rejection_reasons,
            Counter(
                {
                    "AUTOMATIC_ROUTINE": 9,
                    "SUMMARY_ROW": 1,
                    "EMPTY_ROW": 1,
                    "FILTER_DESCRIPTION_ROW": 1,
                }
            ),
        )
        self.assertEqual(first.evidences_created, 19)
        self.assertEqual(first.links_created, 16)
        self.assertEqual(first.links_by_external_id, 16)
        self.assertEqual(first.links_by_email, 0)
        self.assertEqual(first.unmatched_evidences, 3)
        self.assertEqual(first.members_reconciled, 33)
        self.assertEqual(
            dict(first.status_counts),
            {
                "CLASSIFIED/SIN_RUTINA": 22,
                "CLASSIFIED/CON_RUTINA": 7,
                "CLASSIFIED/NO_DESEA_RUTINA": 0,
                "INCIDENT/NULL": 4,
            },
        )

        member_ids = select(RoutineControlMemberORM.id).where(
            RoutineControlMemberORM.source_record_id.in_(self.source_record_ids)
        )
        incidents = db.session.execute(
            select(RoutineControlIncidentORM.incident_type, func.count())
            .where(
                RoutineControlIncidentORM.member_id.in_(member_ids),
                RoutineControlIncidentORM.is_active.is_(True),
            )
            .group_by(RoutineControlIncidentORM.incident_type)
        ).all()
        self.assertEqual(dict(incidents), {"EMAIL_DUPLICADO_GASCA": 2, "EMAIL_VACIO": 2})
        distinct_linked = db.session.execute(
            select(func.count(func.distinct(RoutineControlMemberEvidenceORM.member_id))).where(
                RoutineControlMemberEvidenceORM.member_id.in_(member_ids),
                RoutineControlMemberEvidenceORM.is_active.is_(True),
            )
        ).scalar_one()
        self.assertEqual(distinct_linked, 11)
        incident_with_evidence = db.session.execute(
            select(RoutineControlMemberORM)
            .join(RoutineControlIncidentORM)
            .join(RoutineControlMemberEvidenceORM, RoutineControlMemberEvidenceORM.member_id == RoutineControlMemberORM.id)
            .where(RoutineControlMemberORM.id.in_(member_ids))
            .limit(1)
        ).scalar_one_or_none()
        if incident_with_evidence is not None:
            self.assertIsNotNone(incident_with_evidence.first_routine_at)

        pipeline = db.session.get(RoutineControlPipelineRunORM, first.pipeline_run_id)
        gasca_run = db.session.get(RoutineControlProviderRunORM, first.gasca_provider_run_id)
        trainingym_run = db.session.get(RoutineControlProviderRunORM, first.trainingym_provider_run_id)
        self.assertEqual((pipeline.status, gasca_run.status, trainingym_run.status), ("SUCCESS", "SUCCESS", "SUCCESS"))
        self.assertEqual(gasca_run.content_hash, _sha256(GASCA_FIXTURE))
        self.assertEqual(trainingym_run.content_hash, _sha256(TRAININGYM_FIXTURE))

        versions_before = dict(db.session.execute(select(RoutineControlMemberORM.id, RoutineControlMemberORM.status_version).where(RoutineControlMemberORM.id.in_(member_ids))).all())
        second = run_manual_routine_control_pipeline(
            gasca_xlsx=GASCA_FIXTURE,
            trainingym_xlsx=TRAININGYM_FIXTURE,
            observed_at_utc=OBSERVED_AT.replace(hour=19),
        )
        self.assertTrue(second.succeeded)
        self.assertTrue(second.reused_existing_run)
        self.assertEqual(second.pipeline_run_id, first.pipeline_run_id)
        self.assertEqual(second.links_existing, 16)
        self.assertEqual(
            db.session.execute(select(func.count()).select_from(RoutineControlMemberORM).where(RoutineControlMemberORM.id.in_(member_ids))).scalar_one(),
            33,
        )
        self.assertEqual(
            db.session.execute(select(func.count()).select_from(RoutineAssignmentEvidenceORM).where(RoutineAssignmentEvidenceORM.evidence_identity_key.in_(self.evidence_keys))).scalar_one(),
            19,
        )
        self.assertEqual(
            db.session.execute(select(func.count()).select_from(RoutineControlMemberEvidenceORM).where(RoutineControlMemberEvidenceORM.member_id.in_(member_ids))).scalar_one(),
            16,
        )
        self.assertEqual(
            db.session.execute(select(func.count()).select_from(RoutineControlIncidentORM).where(RoutineControlIncidentORM.member_id.in_(member_ids), RoutineControlIncidentORM.is_active.is_(True))).scalar_one(),
            4,
        )
        versions_after = dict(db.session.execute(select(RoutineControlMemberORM.id, RoutineControlMemberORM.status_version).where(RoutineControlMemberORM.id.in_(member_ids))).all())
        self.assertEqual(versions_after, versions_before)


class ManualPipelineFocusedPostgresTestCase(unittest.TestCase):
    GASCA_HEADERS = ["IDSocio", "IDFolio", "Sucursal", "Nombre", "ApellidoPaterno", "ApellidoMaterno", "Email", "FechaPago", "FechaCreacion"]
    TRAININGYM_HEADERS = ["id", "Idsocioexterno", "Email", "Técnico", "NºRutinas", "NºPesajes", "Fecha", "Centro Origen"]

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = create_app()
        cls.context = cls.app.app_context()
        cls.context.push()
        if db.engine.dialect.name != "postgresql":
            raise RuntimeError("Estas pruebas requieren PostgreSQL real.")

    @classmethod
    def tearDownClass(cls) -> None:
        db.session.remove()
        cls.context.pop()

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.pipeline_ids: list[int] = []
        self.external_ids: set[str] = set()
        self.provider_ids: set[str] = set()

    def tearDown(self) -> None:
        db.session.rollback()
        member_ids = select(RoutineControlMemberORM.id).where(RoutineControlMemberORM.external_member_id.in_(self.external_ids or {"__none__"}))
        evidence_ids = select(RoutineAssignmentEvidenceORM.id).where(RoutineAssignmentEvidenceORM.provider_member_id.in_(self.provider_ids or {"__none__"}))
        db.session.execute(delete(RoutineControlIncidentORM).where(RoutineControlIncidentORM.member_id.in_(member_ids)))
        db.session.execute(delete(RoutineControlMemberEvidenceORM).where((RoutineControlMemberEvidenceORM.member_id.in_(member_ids)) | (RoutineControlMemberEvidenceORM.evidence_id.in_(evidence_ids))))
        db.session.execute(delete(RoutineAssignmentEvidenceORM).where(RoutineAssignmentEvidenceORM.id.in_(evidence_ids)))
        db.session.execute(delete(RoutineControlMemberORM).where(RoutineControlMemberORM.id.in_(member_ids)))
        if self.pipeline_ids:
            db.session.execute(delete(RoutineControlProviderRunORM).where(RoutineControlProviderRunORM.pipeline_run_id.in_(self.pipeline_ids)))
            db.session.execute(delete(RoutineControlPipelineRunORM).where(RoutineControlPipelineRunORM.id.in_(self.pipeline_ids)))
        db.session.commit()
        self.temp.cleanup()

    def _files(self, members, evidences):
        gasca = Path(self.temp.name) / f"gasca-{uuid4().hex}.xlsx"
        trainingym = Path(self.temp.name) / f"trainingym-{uuid4().hex}.xlsx"
        workbook = Workbook(); sheet = workbook.active; sheet.title = "Socios"; sheet.append(self.GASCA_HEADERS)
        for row in members: sheet.append(row)
        workbook.save(gasca); workbook.close()
        workbook = Workbook(); sheet = workbook.active; sheet.title = "Export"; sheet.append(self.TRAININGYM_HEADERS)
        for row in evidences: sheet.append(row)
        workbook.save(trainingym); workbook.close()
        self.external_ids.update(str(row[0]) for row in members)
        self.provider_ids.update(str(row[0]) for row in evidences if isinstance(row[0], int))
        return gasca, trainingym

    def _run(self, members, evidences):
        gasca, trainingym = self._files(members, evidences)
        result = run_manual_routine_control_pipeline(gasca_xlsx=gasca, trainingym_xlsx=trainingym, observed_at_utc=OBSERVED_AT)
        self.pipeline_ids.append(result.pipeline_run_id)
        return result

    @staticmethod
    def _member(member_id, folio, email, branch="VILLAS DEL REY"):
        return [member_id, folio, branch, "Test", "Member", "", email, "15-07-2026 10:00:00", "15-07-2026 09:00:00"]

    @staticmethod
    def _evidence(provider_id, external_id, email):
        return [provider_id, external_id, email, "Instructor", 1, 0, datetime(2026, 7, 15), "Centro"]

    def test_email_fallback_ambiguous_and_multiple_cohorts(self) -> None:
        seed = int(uuid4().hex[:8], 16) % 100000000 + 800000000
        unique = self._run([self._member(seed, "90000000000000000001", "unique@example.test")], [self._evidence(seed + 10, None, "unique@example.test")])
        self.assertEqual((unique.links_by_email, unique.ambiguous_evidences), (1, 0))

        ambiguous = self._run(
            [self._member(seed + 1, "90000000000000000002", "amb@example.test"), self._member(seed + 2, "90000000000000000003", "amb@example.test")],
            [self._evidence(seed + 11, None, "amb@example.test")],
        )
        self.assertEqual((ambiguous.links_created, ambiguous.ambiguous_evidences), (0, 1))

        cohorts = self._run(
            [self._member(seed + 3, "90000000000000000004", "c1@example.test"), self._member(seed + 3, "90000000000000000005", "c1@example.test")],
            [self._evidence(seed + 12, seed + 3, "c1@example.test")],
        )
        self.assertEqual(cohorts.links_by_external_id, 2)

    def test_structural_failures_and_unexpected_error_leave_session_reusable(self) -> None:
        valid_gasca, valid_trainingym = self._files(
            [self._member(990000001, "90000000000000000006", "fatal@example.test")],
            [self._evidence(990000011, 990000001, "fatal@example.test")],
        )
        broken = Path(self.temp.name) / "broken.xlsx"; broken.write_bytes(b"not xlsx")
        gasca_failure = run_manual_routine_control_pipeline(gasca_xlsx=broken, trainingym_xlsx=valid_trainingym, observed_at_utc=OBSERVED_AT)
        self.pipeline_ids.append(gasca_failure.pipeline_run_id)
        self.assertFalse(gasca_failure.succeeded)
        self.assertEqual(db.session.get(RoutineControlProviderRunORM, gasca_failure.gasca_provider_run_id).status, "FAILED")

        trainingym_failure = run_manual_routine_control_pipeline(gasca_xlsx=valid_gasca, trainingym_xlsx=broken, observed_at_utc=OBSERVED_AT)
        self.pipeline_ids.append(trainingym_failure.pipeline_run_id)
        self.assertFalse(trainingym_failure.succeeded)
        self.assertEqual(db.session.get(RoutineControlProviderRunORM, trainingym_failure.gasca_provider_run_id).status, "SUCCESS")
        self.assertEqual(db.session.get(RoutineControlProviderRunORM, trainingym_failure.trainingym_provider_run_id).status, "FAILED")
        self.assertEqual(
            db.session.get(
                RoutineControlPipelineRunORM,
                trainingym_failure.pipeline_run_id,
            ).members_created,
            1,
        )

        with patch("app.routine_control.pipeline.manual_pipeline_service.load_gasca_member_commands_from_xlsx", side_effect=RuntimeError("unexpected")):
            unexpected = run_manual_routine_control_pipeline(gasca_xlsx=valid_gasca, trainingym_xlsx=valid_trainingym, observed_at_utc=OBSERVED_AT.replace(day=16))
        self.pipeline_ids.append(unexpected.pipeline_run_id)
        self.assertFalse(unexpected.succeeded)
        self.assertEqual(db.session.execute(text("SELECT 1")).scalar_one(), 1)

    def test_later_run_resolves_member_and_matching_incidents(self) -> None:
        seed = int(uuid4().hex[:8], 16) % 100000000 + 700000000
        first = self._run(
            [
                self._member(
                    seed,
                    "91000000000000000001",
                    "",
                    branch="UNKNOWN TEST BRANCH",
                ),
                self._member(
                    seed + 1,
                    "91000000000000000002",
                    "duplicate@example.test",
                ),
                self._member(
                    seed + 2,
                    "91000000000000000003",
                    "duplicate@example.test",
                ),
            ],
            [
                self._evidence(
                    seed + 20,
                    None,
                    "duplicate@example.test",
                )
            ],
        )
        self.assertTrue(first.succeeded)
        self.assertEqual(first.ambiguous_evidences, 1)
        self.assertEqual(
            (first.gasca_accepted, first.gasca_rejected),
            (3, 0),
            first.to_dict(),
        )
        initially_unresolved = db.session.execute(
            select(RoutineControlMemberORM).where(
                RoutineControlMemberORM.source_system == "gasca",
                RoutineControlMemberORM.external_member_id == str(seed),
            )
        ).scalar_one()
        initial_types = set(
            db.session.execute(
                select(RoutineControlIncidentORM.incident_type).where(
                    RoutineControlIncidentORM.member_id
                    == initially_unresolved.id,
                    RoutineControlIncidentORM.is_active.is_(True),
                )
            ).scalars()
        )
        self.assertEqual(
            initial_types,
            {"EMAIL_VACIO", "SUCURSAL_NO_RESUELTA"},
        )

        second = self._run(
            [
                self._member(
                    seed,
                    "91000000000000000001",
                    "resolved@example.test",
                ),
                self._member(
                    seed + 1,
                    "91000000000000000002",
                    "duplicate@example.test",
                ),
                self._member(
                    seed + 2,
                    "91000000000000000003",
                    "separated@example.test",
                ),
            ],
            [
                self._evidence(
                    seed + 20,
                    None,
                    "duplicate@example.test",
                ),
                self._evidence(
                    seed + 21,
                    None,
                    "separated@example.test",
                ),
            ],
        )
        self.assertTrue(second.succeeded)
        self.assertGreaterEqual(second.incidents_resolved, 6)

        members = db.session.execute(
            select(RoutineControlMemberORM).where(
                RoutineControlMemberORM.external_member_id.in_(
                    (str(seed), str(seed + 1), str(seed + 2))
                )
            )
        ).scalars().all()
        member_ids = [int(member.id) for member in members]
        active_types = db.session.execute(
            select(RoutineControlIncidentORM.incident_type).where(
                RoutineControlIncidentORM.member_id.in_(member_ids),
                RoutineControlIncidentORM.is_active.is_(True),
            )
        ).scalars().all()
        self.assertEqual(active_types, [])
        resolved = db.session.execute(
            select(RoutineControlIncidentORM).where(
                RoutineControlIncidentORM.member_id.in_(member_ids),
                RoutineControlIncidentORM.is_active.is_(False),
                RoutineControlIncidentORM.resolved_at_utc.is_not(None),
            )
        ).scalars().all()
        resolved_types = {incident.incident_type for incident in resolved}
        self.assertTrue(
            {
                "EMAIL_VACIO",
                "SUCURSAL_NO_RESUELTA",
                "EMAIL_DUPLICADO_GASCA",
                "COINCIDENCIA_AMBIGUA",
            }.issubset(resolved_types),
            resolved_types,
        )


if __name__ == "__main__":
    unittest.main()
