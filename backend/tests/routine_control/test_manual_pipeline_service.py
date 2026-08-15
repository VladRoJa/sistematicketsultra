from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from collections import Counter
from datetime import date, datetime, timezone
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
from app.routine_control.services.evidence_rematching_service import (
    _apply_evidence_matching_decision,
)


FIXTURES = Path(__file__).parent / "fixtures"
GASCA_FIXTURE = FIXTURES / "gasca_socios_nuevos_detallado.xlsx"
TRAININGYM_FIXTURE = FIXTURES / "trainingym_workout.xlsx"
OBSERVED_AT = datetime(2026, 7, 15, 18, 0, tzinfo=timezone.utc)
UNEXPECTED_ERROR_CODE = "ROUTINE_CONTROL_PIPELINE_UNEXPECTED_ERROR"
UNEXPECTED_PUBLIC_MESSAGE = (
    "El pipeline terminó por un error interno inesperado."
)
SENSITIVE_ERROR_VALUES = (
    "jairo@example.com",
    "JAIRO MENDOZA SANCHEZ",
    "postgresql://usuario:secreto@servidor/base",
    "INSERT INTO members (email) VALUES (%(email)s)",
    "token-ficticio-secreto",
)
MATCHING_RESULT_FIELDS = (
    "links_created",
    "links_existing",
    "unmatched_evidences",
    "ambiguous_evidences",
    "insufficient_identity_evidences",
    "reactivation_required_evidences",
    "links_by_external_id",
    "links_by_email",
)


class SensitivePersistenceFailure(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _matching_result_snapshot(result) -> dict[str, object]:
    snapshot = {
        field_name: getattr(result, field_name)
        for field_name in MATCHING_RESULT_FIELDS
    }
    snapshot["status_counts"] = dict(result.status_counts)
    return snapshot


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
            date_from=OBSERVED_AT.date(),
            date_to=OBSERVED_AT.date(),
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
        self.assertEqual(first.links_created, 0)
        self.assertEqual(first.links_by_external_id, 0)
        self.assertEqual(first.links_by_email, 0)
        self.assertEqual(first.unmatched_evidences, 19)
        self.assertEqual(first.members_reconciled, 33)
        self.assertEqual(
            dict(first.status_counts),
            {
                "CLASSIFIED/SIN_RUTINA": 29,
                "CLASSIFIED/CON_RUTINA": 0,
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
        self.assertEqual(distinct_linked, 0)
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
        self.assertEqual(
            (pipeline.business_date, pipeline.date_from, pipeline.date_to),
            (OBSERVED_AT.date(), OBSERVED_AT.date(), OBSERVED_AT.date()),
        )
        self.assertEqual(
            (gasca_run.date_from, gasca_run.date_to),
            (OBSERVED_AT.date(), OBSERVED_AT.date()),
        )
        self.assertEqual(
            (trainingym_run.date_from, trainingym_run.date_to),
            (OBSERVED_AT.date(), OBSERVED_AT.date()),
        )
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
        self.assertEqual(second.links_existing, 0)
        self.assertEqual(
            _matching_result_snapshot(second),
            _matching_result_snapshot(first),
        )
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
            0,
        )
        self.assertEqual(
            db.session.execute(select(func.count()).select_from(RoutineControlIncidentORM).where(RoutineControlIncidentORM.member_id.in_(member_ids), RoutineControlIncidentORM.is_active.is_(True))).scalar_one(),
            4,
        )
        versions_after = dict(db.session.execute(select(RoutineControlMemberORM.id, RoutineControlMemberORM.status_version).where(RoutineControlMemberORM.id.in_(member_ids))).all())
        self.assertEqual(versions_after, versions_before)


class ManualPipelineFocusedPostgresTestCase(unittest.TestCase):
    GASCA_HEADERS = ["IDSocio", "IDFolio", "Sucursal", "Nombre", "ApellidoPaterno", "ApellidoMaterno", "Email", "Telefono", "FechaPago", "FechaCreacion"]
    TRAININGYM_HEADERS = ["id", "Idsocioexterno", "NombreApellidos", "Email", "Técnico", "NºRutinas", "NºPesajes", "Fecha", "Centro Origen"]

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
    def _member(
        member_id,
        folio,
        email,
        branch="VILLAS DEL REY",
        sale_at="15-07-2026 10:00:00",
    ):
        return [
            member_id,
            folio,
            branch,
            "Test",
            "Member",
            "",
            email,
            "6861234567",
            sale_at,
            sale_at,
        ]

    @staticmethod
    def _evidence(provider_id, external_id, email, name="Test Member", activity_date=None):
        return [provider_id, external_id, name, email, "Instructor", 1, 0, activity_date or datetime(2026, 7, 15), "Centro"]

    def test_explicit_range_persists_and_changes_idempotency(self) -> None:
        seed = int(uuid4().hex[:8], 16) % 100000000 + 850000000
        gasca, trainingym = self._files(
            [
                self._member(
                    seed,
                    "91000000000000000001",
                    "range@example.test",
                )
            ],
            [
                self._evidence(
                    seed + 10,
                    seed,
                    "range@example.test",
                )
            ],
        )

        first = run_manual_routine_control_pipeline(
            gasca_xlsx=gasca,
            trainingym_xlsx=trainingym,
            observed_at_utc=OBSERVED_AT,
            date_from=date(2026, 7, 1),
            date_to=date(2026, 7, 24),
        )
        self.pipeline_ids.append(first.pipeline_run_id)

        second = run_manual_routine_control_pipeline(
            gasca_xlsx=gasca,
            trainingym_xlsx=trainingym,
            observed_at_utc=OBSERVED_AT,
            date_from=date(2026, 7, 1),
            date_to=date(2026, 7, 23),
        )
        self.pipeline_ids.append(second.pipeline_run_id)

        self.assertTrue(first.succeeded)
        self.assertTrue(second.succeeded)
        self.assertFalse(first.reused_existing_run)
        self.assertFalse(second.reused_existing_run)
        self.assertNotEqual(first.pipeline_run_id, second.pipeline_run_id)

        for result, expected_to in (
            (first, date(2026, 7, 24)),
            (second, date(2026, 7, 23)),
        ):
            pipeline = db.session.get(
                RoutineControlPipelineRunORM,
                result.pipeline_run_id,
            )
            provider_runs = db.session.execute(
                select(RoutineControlProviderRunORM)
                .where(
                    RoutineControlProviderRunORM.pipeline_run_id
                    == result.pipeline_run_id
                )
                .order_by(RoutineControlProviderRunORM.id)
            ).scalars().all()

            self.assertEqual(
                (
                    pipeline.business_date,
                    pipeline.date_from,
                    pipeline.date_to,
                ),
                (
                    expected_to,
                    date(2026, 7, 1),
                    expected_to,
                ),
            )
            self.assertEqual(len(provider_runs), 2)

            for provider_run in provider_runs:
                self.assertEqual(
                    (provider_run.date_from, provider_run.date_to),
                    (date(2026, 7, 1), expected_to),
                )

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
        self.assertEqual(cohorts.links_by_external_id, 0)
        self.assertEqual(cohorts.ambiguous_evidences, 1)

    def test_positive_identity_routes_use_shared_matching_coordinator(self) -> None:
        seed = int(uuid4().hex[:8], 16) % 100000000 + 820000000
        with patch(
            "app.routine_control.services.evidence_rematching_service."
            "_apply_evidence_matching_decision",
            wraps=_apply_evidence_matching_decision,
        ) as coordinator:
            id_and_email = self._run(
                [self._member(
                    seed,
                    "93000000000000000001",
                    "id-email@example.test",
                )],
                [self._evidence(
                    seed + 10,
                    seed,
                    "id-email@example.test",
                )],
            )

        self.assertTrue(coordinator.called)
        self.assertEqual(id_and_email.links_by_external_id, 1)

        id_and_name = self._run(
            [self._member(
                seed + 1,
                "93000000000000000002",
                "",
            )],
            [self._evidence(
                seed + 11,
                seed + 1,
                "",
            )],
        )
        self.assertEqual(id_and_name.links_by_external_id, 1)

        email_fallback = self._run(
            [self._member(
                seed + 2,
                "93000000000000000003",
                "fallback@example.test",
            )],
            [self._evidence(
                seed + 12,
                seed + 200,
                "fallback@example.test",
            )],
        )
        self.assertEqual(email_fallback.links_by_email, 1)

        evidence_ids = select(RoutineAssignmentEvidenceORM.id).where(
            RoutineAssignmentEvidenceORM.provider_member_id.in_({
                str(seed + 10),
                str(seed + 11),
                str(seed + 12),
            })
        )
        active_count = db.session.execute(
            select(func.count())
            .select_from(RoutineControlMemberEvidenceORM)
            .where(
                RoutineControlMemberEvidenceORM.evidence_id.in_(evidence_ids),
                RoutineControlMemberEvidenceORM.is_active.is_(True),
            )
        ).scalar_one()
        self.assertEqual(active_count, 3)

    def test_pipeline_atomically_replaces_wrong_link_and_rerun_is_idempotent(
        self,
    ) -> None:
        seed = int(uuid4().hex[:8], 16) % 100000000 + 830000000
        provider_id = seed + 50
        previous_row = self._member(
            seed,
            "94000000000000000001",
            "switch@example.test",
            sale_at="01-07-2026 10:00:00",
        )
        winner_row = self._member(
            seed,
            "94000000000000000002",
            "switch@example.test",
            sale_at="14-07-2026 10:00:00",
        )
        evidence_row = self._evidence(
            provider_id,
            seed,
            "switch@example.test",
            activity_date=datetime(2026, 7, 15),
        )

        first = self._run([previous_row], [evidence_row])
        self.assertEqual(first.links_created, 1)
        evidence = db.session.execute(select(
            RoutineAssignmentEvidenceORM
        ).where(
            RoutineAssignmentEvidenceORM.provider_member_id == str(provider_id)
        )).scalar_one()
        previous_member = db.session.execute(select(
            RoutineControlMemberORM
        ).where(
            RoutineControlMemberORM.external_sale_id
            == "94000000000000000001"
        )).scalar_one()
        previous_link = db.session.execute(select(
            RoutineControlMemberEvidenceORM
        ).where(
            RoutineControlMemberEvidenceORM.member_id == previous_member.id,
            RoutineControlMemberEvidenceORM.evidence_id == evidence.id,
        )).scalar_one()
        self.assertTrue(previous_link.is_active)

        gasca, trainingym = self._files(
            [previous_row, winner_row],
            [evidence_row],
        )
        second = run_manual_routine_control_pipeline(
            gasca_xlsx=gasca,
            trainingym_xlsx=trainingym,
            observed_at_utc=OBSERVED_AT,
        )
        self.pipeline_ids.append(second.pipeline_run_id)
        self.assertTrue(second.succeeded)

        winner = db.session.execute(select(
            RoutineControlMemberORM
        ).where(
            RoutineControlMemberORM.external_sale_id
            == "94000000000000000002"
        )).scalar_one()
        db.session.refresh(previous_link)
        self.assertFalse(previous_link.is_active)
        active_links = db.session.execute(select(
            RoutineControlMemberEvidenceORM
        ).where(
            RoutineControlMemberEvidenceORM.evidence_id == evidence.id,
            RoutineControlMemberEvidenceORM.is_active.is_(True),
        )).scalars().all()
        self.assertEqual(len(active_links), 1)
        self.assertEqual(active_links[0].member_id, winner.id)
        winner_link_id = active_links[0].id

        rerun = run_manual_routine_control_pipeline(
            gasca_xlsx=gasca,
            trainingym_xlsx=trainingym,
            observed_at_utc=OBSERVED_AT.replace(hour=19),
        )
        self.pipeline_ids.append(rerun.pipeline_run_id)
        self.assertTrue(rerun.succeeded)
        self.assertTrue(rerun.reused_existing_run)
        self.assertEqual(
            _matching_result_snapshot(rerun),
            _matching_result_snapshot(second),
        )
        active_links = db.session.execute(select(
            RoutineControlMemberEvidenceORM
        ).where(
            RoutineControlMemberEvidenceORM.evidence_id == evidence.id,
            RoutineControlMemberEvidenceORM.is_active.is_(True),
        )).scalars().all()
        self.assertEqual([link.id for link in active_links], [winner_link_id])

    def test_reused_temporal_tie_preserves_ambiguous_result(self) -> None:
        seed = int(uuid4().hex[:8], 16) % 100000000 + 860000000
        provider_id = seed + 50
        gasca, trainingym = self._files(
            [
                self._member(
                    seed,
                    "95000000000000000001",
                    "tie@example.test",
                    sale_at="14-07-2026 10:00:00",
                ),
                self._member(
                    seed,
                    "95000000000000000002",
                    "tie@example.test",
                    sale_at="16-07-2026 10:00:00",
                ),
            ],
            [self._evidence(
                provider_id,
                seed,
                "tie@example.test",
                activity_date=datetime(2026, 7, 15),
            )],
        )

        first = run_manual_routine_control_pipeline(
            gasca_xlsx=gasca,
            trainingym_xlsx=trainingym,
            observed_at_utc=OBSERVED_AT,
        )
        self.pipeline_ids.append(first.pipeline_run_id)
        reused = run_manual_routine_control_pipeline(
            gasca_xlsx=gasca,
            trainingym_xlsx=trainingym,
            observed_at_utc=OBSERVED_AT.replace(hour=19),
        )

        self.assertTrue(reused.reused_existing_run)
        self.assertEqual(reused.pipeline_run_id, first.pipeline_run_id)
        self.assertEqual(first.ambiguous_evidences, 1)
        self.assertEqual(
            _matching_result_snapshot(reused),
            _matching_result_snapshot(first),
        )
        evidence = db.session.execute(select(
            RoutineAssignmentEvidenceORM
        ).where(
            RoutineAssignmentEvidenceORM.provider_member_id == str(provider_id)
        )).scalar_one()
        active_count = db.session.execute(
            select(func.count())
            .select_from(RoutineControlMemberEvidenceORM)
            .where(
                RoutineControlMemberEvidenceORM.evidence_id == evidence.id,
                RoutineControlMemberEvidenceORM.is_active.is_(True),
            )
        ).scalar_one()
        self.assertEqual(active_count, 0)

    def test_reused_insufficient_identity_preserves_historical_link(self) -> None:
        seed = int(uuid4().hex[:8], 16) % 100000000 + 870000000
        provider_id = seed + 50
        member_row = self._member(
            seed,
            "96000000000000000001",
            "historical@example.test",
        )
        seed_gasca, seed_trainingym = self._files(
            [member_row],
            [self._evidence(
                provider_id,
                seed,
                "historical@example.test",
            )],
        )
        seeded = run_manual_routine_control_pipeline(
            gasca_xlsx=seed_gasca,
            trainingym_xlsx=seed_trainingym,
            observed_at_utc=OBSERVED_AT,
        )
        self.pipeline_ids.append(seeded.pipeline_run_id)

        gasca, trainingym = self._files(
            [member_row],
            [self._evidence(provider_id, None, "", name="")],
        )
        first = run_manual_routine_control_pipeline(
            gasca_xlsx=gasca,
            trainingym_xlsx=trainingym,
            observed_at_utc=OBSERVED_AT,
        )
        self.pipeline_ids.append(first.pipeline_run_id)
        link = db.session.execute(select(
            RoutineControlMemberEvidenceORM
        ).join(RoutineAssignmentEvidenceORM).where(
            RoutineAssignmentEvidenceORM.provider_member_id == str(provider_id)
        )).scalar_one()
        link_snapshot = (
            link.id,
            link.is_active,
            link.linked_at_utc,
            link.updated_at,
            link.identity_corroborator,
            link.temporal_delta_days,
            link.matching_contract_version,
        )

        reused = run_manual_routine_control_pipeline(
            gasca_xlsx=gasca,
            trainingym_xlsx=trainingym,
            observed_at_utc=OBSERVED_AT.replace(hour=19),
        )

        self.assertEqual(first.insufficient_identity_evidences, 1)
        self.assertEqual(
            _matching_result_snapshot(reused),
            _matching_result_snapshot(first),
        )
        db.session.refresh(link)
        self.assertEqual(
            (
                link.id,
                link.is_active,
                link.linked_at_utc,
                link.updated_at,
                link.identity_corroborator,
                link.temporal_delta_days,
                link.matching_contract_version,
            ),
            link_snapshot,
        )

    def test_reused_reactivation_required_does_not_create_or_reactivate(self) -> None:
        seed = int(uuid4().hex[:8], 16) % 100000000 + 880000000
        provider_id = seed + 50
        member_row = self._member(
            seed,
            "97000000000000000001",
            "reactivation@example.test",
        )
        evidence_row = self._evidence(
            provider_id,
            seed,
            "reactivation@example.test",
        )
        seed_gasca, seed_trainingym = self._files(
            [member_row],
            [evidence_row],
        )
        seeded = run_manual_routine_control_pipeline(
            gasca_xlsx=seed_gasca,
            trainingym_xlsx=seed_trainingym,
            observed_at_utc=OBSERVED_AT,
        )
        self.pipeline_ids.append(seeded.pipeline_run_id)
        link = db.session.execute(select(
            RoutineControlMemberEvidenceORM
        ).join(RoutineAssignmentEvidenceORM).where(
            RoutineAssignmentEvidenceORM.provider_member_id == str(provider_id)
        )).scalar_one()
        link.is_active = False
        link.unlinked_at_utc = OBSERVED_AT
        link.unlink_reason = "TEST_REACTIVATION_REQUIRED"
        db.session.commit()

        changed_evidence_row = list(evidence_row)
        changed_evidence_row[6] = 1
        gasca, trainingym = self._files(
            [member_row],
            [changed_evidence_row],
        )
        first = run_manual_routine_control_pipeline(
            gasca_xlsx=gasca,
            trainingym_xlsx=trainingym,
            observed_at_utc=OBSERVED_AT,
        )
        self.pipeline_ids.append(first.pipeline_run_id)
        reused = run_manual_routine_control_pipeline(
            gasca_xlsx=gasca,
            trainingym_xlsx=trainingym,
            observed_at_utc=OBSERVED_AT.replace(hour=19),
        )

        self.assertEqual(first.reactivation_required_evidences, 1)
        self.assertEqual(
            _matching_result_snapshot(reused),
            _matching_result_snapshot(first),
        )
        links = db.session.execute(select(
            RoutineControlMemberEvidenceORM
        ).where(
            RoutineControlMemberEvidenceORM.evidence_id == link.evidence_id
        )).scalars().all()
        self.assertEqual([stored.id for stored in links], [link.id])
        self.assertFalse(links[0].is_active)

    def test_reused_correct_link_is_read_only_and_preserves_audit(self) -> None:
        seed = int(uuid4().hex[:8], 16) % 100000000 + 890000000
        provider_id = seed + 50
        gasca, trainingym = self._files(
            [self._member(
                seed,
                "98000000000000000001",
                "correct@example.test",
            )],
            [self._evidence(
                provider_id,
                seed,
                "correct@example.test",
            )],
        )
        first = run_manual_routine_control_pipeline(
            gasca_xlsx=gasca,
            trainingym_xlsx=trainingym,
            observed_at_utc=OBSERVED_AT,
        )
        self.pipeline_ids.append(first.pipeline_run_id)
        link = db.session.execute(select(
            RoutineControlMemberEvidenceORM
        ).join(RoutineAssignmentEvidenceORM).where(
            RoutineAssignmentEvidenceORM.provider_member_id == str(provider_id)
        )).scalar_one()
        evidence = db.session.get(
            RoutineAssignmentEvidenceORM,
            link.evidence_id,
        )
        member = db.session.get(RoutineControlMemberORM, link.member_id)
        pipeline = db.session.get(
            RoutineControlPipelineRunORM,
            first.pipeline_run_id,
        )
        persisted_snapshot = (
            link.id,
            link.linked_at_utc,
            link.updated_at,
            link.identity_corroborator,
            link.temporal_delta_days,
            link.matching_contract_version,
            evidence.updated_at,
            member.updated_at,
            pipeline.updated_at,
        )

        with (
            patch(
                "app.routine_control.services.evidence_rematching_service."
                "link_routine_member_evidence"
            ) as link_service,
            patch(
                "app.routine_control.services.evidence_rematching_service."
                "unlink_routine_member_evidence"
            ) as unlink_service,
            patch(
                "app.routine_control.services.evidence_rematching_service."
                "reconcile_routine_member"
            ) as reconciliation_service,
            patch.object(db.session, "commit", wraps=db.session.commit) as commit,
        ):
            reused = run_manual_routine_control_pipeline(
                gasca_xlsx=gasca,
                trainingym_xlsx=trainingym,
                observed_at_utc=OBSERVED_AT.replace(hour=19),
            )

        link_service.assert_not_called()
        unlink_service.assert_not_called()
        reconciliation_service.assert_not_called()
        commit.assert_not_called()
        self.assertTrue(reused.reused_existing_run)
        self.assertEqual(reused.pipeline_run_id, first.pipeline_run_id)
        self.assertEqual(
            _matching_result_snapshot(reused),
            _matching_result_snapshot(first),
        )
        db.session.refresh(link)
        db.session.refresh(evidence)
        db.session.refresh(member)
        db.session.refresh(pipeline)
        self.assertEqual(
            (
                link.id,
                link.linked_at_utc,
                link.updated_at,
                link.identity_corroborator,
                link.temporal_delta_days,
                link.matching_contract_version,
                evidence.updated_at,
                member.updated_at,
                pipeline.updated_at,
            ),
            persisted_snapshot,
        )

    def test_reused_email_fallback_preserves_match_method(self) -> None:
        seed = int(uuid4().hex[:8], 16) % 100000000 + 900000000
        gasca, trainingym = self._files(
            [self._member(
                seed,
                "99000000000000000001",
                "rerun-fallback@example.test",
            )],
            [self._evidence(
                seed + 50,
                seed + 1,
                "rerun-fallback@example.test",
            )],
        )
        first = run_manual_routine_control_pipeline(
            gasca_xlsx=gasca,
            trainingym_xlsx=trainingym,
            observed_at_utc=OBSERVED_AT,
        )
        self.pipeline_ids.append(first.pipeline_run_id)
        reused = run_manual_routine_control_pipeline(
            gasca_xlsx=gasca,
            trainingym_xlsx=trainingym,
            observed_at_utc=OBSERVED_AT.replace(hour=19),
        )

        self.assertEqual((first.links_by_email, first.links_by_external_id), (1, 0))
        self.assertEqual(
            _matching_result_snapshot(reused),
            _matching_result_snapshot(first),
        )

    def test_pipeline_selects_one_nearest_cohort_and_keeps_one_active_link(self) -> None:
        seed = int(uuid4().hex[:8], 16) % 100000000 + 810000000
        result = self._run(
            [
                self._member(
                    seed,
                    "92000000000000000001",
                    "nearest@example.test",
                    sale_at="01-07-2026 10:00:00",
                ),
                self._member(
                    seed,
                    "92000000000000000002",
                    "nearest@example.test",
                    sale_at="14-07-2026 10:00:00",
                ),
            ],
            [
                self._evidence(
                    seed + 50,
                    seed,
                    "nearest@example.test",
                    activity_date=datetime(2026, 7, 15),
                )
            ],
        )
        self.assertEqual(result.links_created, 1)
        members = db.session.execute(select(RoutineControlMemberORM).where(
            RoutineControlMemberORM.external_member_id == str(seed)
        )).scalars().all()
        links = db.session.execute(
            select(RoutineControlMemberEvidenceORM)
            .where(
                RoutineControlMemberEvidenceORM.member_id.in_(
                    [member.id for member in members]
                ),
                RoutineControlMemberEvidenceORM.is_active.is_(True),
            )
        ).scalars().all()
        self.assertEqual(len(links), 1)
        winner = next(member for member in members if member.id == links[0].member_id)
        self.assertEqual(winner.sale_date, date(2026, 7, 14))
        self.assertEqual(links[0].temporal_delta_days, 1)

    def test_structural_failures_and_unexpected_error_leave_session_reusable(self) -> None:
        valid_gasca, valid_trainingym = self._files(
            [self._member(990000001, "90000000000000000006", "fatal@example.test")],
            [self._evidence(990000011, 990000001, "fatal@example.test")],
        )
        broken = Path(self.temp.name) / "broken.xlsx"; broken.write_bytes(b"not xlsx")
        gasca_failure = run_manual_routine_control_pipeline(gasca_xlsx=broken, trainingym_xlsx=valid_trainingym, observed_at_utc=OBSERVED_AT)
        self.pipeline_ids.append(gasca_failure.pipeline_run_id)
        self.assertFalse(gasca_failure.succeeded)
        gasca_pipeline = db.session.get(
            RoutineControlPipelineRunORM,
            gasca_failure.pipeline_run_id,
        )
        gasca_provider = db.session.get(
            RoutineControlProviderRunORM,
            gasca_failure.gasca_provider_run_id,
        )
        self.assertEqual(gasca_provider.status, "FAILED")
        self.assertEqual(
            (gasca_pipeline.error_code, gasca_pipeline.error_message),
            ("GascaInvalidWorkbookError", "GascaInvalidWorkbookError"),
        )
        self.assertIsNone(gasca_failure.error_code)
        self.assertIsNone(gasca_failure.error_message)

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

    def test_unexpected_failure_redacts_pii_from_log_state_and_result(self) -> None:
        seed = int(uuid4().hex[:8], 16) % 100000000 + 910000000
        gasca, trainingym = self._files(
            [self._member(
                seed,
                "99100000000000000001",
                "safe-fixture@example.test",
            )],
            [self._evidence(
                seed + 50,
                seed,
                "safe-fixture@example.test",
            )],
        )
        raw_error_message = " | ".join(SENSITIVE_ERROR_VALUES)

        with (
            self.assertLogs(
                "app.routine_control.pipeline.manual_pipeline_service",
                level="ERROR",
            ) as captured,
            patch(
                "app.routine_control.pipeline.manual_pipeline_service."
                "LOGGER.exception"
            ) as exception_log,
            patch.object(
                db.session,
                "rollback",
                wraps=db.session.rollback,
            ) as rollback,
            patch(
                "app.routine_control.pipeline.manual_pipeline_service."
                "load_trainingym_evidence_commands_from_xlsx",
                side_effect=SensitivePersistenceFailure(raw_error_message),
            ),
        ):
            result = run_manual_routine_control_pipeline(
                gasca_xlsx=gasca,
                trainingym_xlsx=trainingym,
                observed_at_utc=OBSERVED_AT,
            )

        self.pipeline_ids.append(result.pipeline_run_id)
        exception_log.assert_not_called()
        self.assertGreaterEqual(rollback.call_count, 1)
        self.assertTrue(captured.records)
        self.assertTrue(all(record.exc_info is None for record in captured.records))

        log_text = "\n".join(captured.output)
        pipeline = db.session.get(
            RoutineControlPipelineRunORM,
            result.pipeline_run_id,
        )
        provider = db.session.get(
            RoutineControlProviderRunORM,
            result.trainingym_provider_run_id,
        )
        member = db.session.execute(select(
            RoutineControlMemberORM
        ).where(
            RoutineControlMemberORM.external_member_id == str(seed)
        )).scalar_one()
        metadata_text = json.dumps(
            member.source_metadata or {},
            ensure_ascii=False,
            sort_keys=True,
        )
        persisted_text = " | ".join(
            (
                pipeline.error_code or "",
                pipeline.error_message or "",
                provider.error_code or "",
                provider.error_message or "",
            )
        )
        public_result_text = json.dumps(
            result.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
        )

        for sensitive_value in SENSITIVE_ERROR_VALUES:
            self.assertNotIn(sensitive_value, log_text)
            self.assertNotIn(sensitive_value, persisted_text)
            self.assertNotIn(sensitive_value, public_result_text)
            self.assertNotIn(sensitive_value, metadata_text)

        self.assertIn(UNEXPECTED_ERROR_CODE, log_text)
        self.assertIn("SensitivePersistenceFailure", log_text)
        self.assertIn(f"pipeline_run_id={result.pipeline_run_id}", log_text)
        self.assertIn("stage=TRAININGYM", log_text)
        self.assertIn("provider=trainingym", log_text)
        self.assertIn("generation_mode=MANUAL", log_text)
        self.assertIn("date_from=2026-07-15", log_text)
        self.assertIn("date_to=2026-07-15", log_text)
        self.assertEqual(
            (pipeline.status, provider.status),
            ("FAILED", "FAILED"),
        )
        self.assertEqual(
            (pipeline.error_code, pipeline.error_message),
            (UNEXPECTED_ERROR_CODE, UNEXPECTED_PUBLIC_MESSAGE),
        )
        self.assertEqual(
            (provider.error_code, provider.error_message),
            (UNEXPECTED_ERROR_CODE, UNEXPECTED_PUBLIC_MESSAGE),
        )
        self.assertEqual(
            (result.succeeded, result.error_code, result.error_message),
            (False, UNEXPECTED_ERROR_CODE, UNEXPECTED_PUBLIC_MESSAGE),
        )

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
