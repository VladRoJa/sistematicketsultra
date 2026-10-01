from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
import importlib.util
import inspect
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect as sa_inspect, text
from sqlalchemy.exc import IntegrityError

from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2RecipientEvidenceORM,
    MarketingCampaignV2RecipientORM,
)
from app.services import marketing_campaign_v2_audience_service as audience
from app.services import marketing_campaign_v2_creation_service as creation


NOW = datetime(2026, 9, 30, 20, 0, tzinfo=timezone.utc)


def _evidence(
    row_id: int,
    *,
    phone: str = "6861000001",
    source: str = audience.SOURCE_EXPIRED_MEMBERS,
    name: str | None = "Socio",
    branch: str | None = "BRANCH A",
    tariff: str | None = "DOM",
    tariff_key: str | None = "DOM",
    category: str | None = "Domiciliado",
    family: str | None = "DOMICILIADO",
    snapshot_id: int | None = None,
    current_status: str | None = None,
):
    return audience.MarketingCampaignV2AudienceCandidate(
        source=source,
        source_ref_type=(
            "SOCIOS_VENCIDOS_CARTERA"
            if source == audience.SOURCE_EXPIRED_MEMBERS
            else "SOCIOS_ACTIVOS_SNAPSHOT_ROW"
        ),
        source_ref_id=row_id,
        source_snapshot_id=snapshot_id,
        phone_raw=phone,
        phone_mx10=phone,
        member_id=(
            None
            if source == audience.SOURCE_EXPIRED_MEMBERS
            else f"SOCIO-{row_id}"
        ),
        member_pin=f"PIN-{row_id}",
        member_name=name,
        sucursal=branch,
        sucursal_key=branch,
        tarifa_raw=tariff,
        tarifa_key=tariff_key,
        categoria_tarifa=category,
        audience_family=family,
        fecha_vencimiento=date(2026, 8, 20),
        current_status=(
            current_status
            if current_status is not None
            else (
                audience.current_status.STATUS_NOT_FOUND
                if source == audience.SOURCE_EXPIRED_MEMBERS
                else None
            )
        ),
        evidence=(
            "CURRENT_STATUS:NOT_FOUND",
            f"TARIFF_FAMILY:{family}",
        ),
    )


def _recipient(
    *,
    phone: str = "6861000001",
    evidence_rows=None,
    conflict_fields=(),
    member_name: str | None = "Socio",
    branch: str | None = "BRANCH A",
    tariff: str | None = "DOM",
    tariff_key: str | None = "DOM",
    category: str | None = "Domiciliado",
    family: str | None = "DOMICILIADO",
):
    rows = tuple(evidence_rows or (_evidence(10, phone=phone),))
    return audience.MarketingCampaignV2RecipientCandidate(
        source=rows[0].source,
        phone_mx10=phone,
        member_id=rows[0].member_id,
        member_pin=rows[0].member_pin if not conflict_fields else None,
        member_name=member_name,
        sucursal=branch,
        tarifa_raw=tariff,
        tarifa_key=tariff_key,
        categoria_tarifa=category,
        audience_family=family,
        fecha_vencimiento=date(2026, 8, 20),
        inclusion_reason="AUDIENCE_FAMILY_MATCH",
        conflict_fields=tuple(conflict_fields),
        evidence_rows=rows,
    )


def _plan(
    recipients,
    *,
    source=audience.SOURCE_EXPIRED_MEMBERS,
    filters=None,
    source_metadata=None,
):
    recipients = tuple(recipients)
    evidence_rows = tuple(
        row
        for recipient in recipients
        for row in recipient.evidence_rows
    )
    family_counts = {
        family: 0
        for family in audience.ALL_AUDIENCE_FAMILIES
    }
    for row in evidence_rows:
        if row.audience_family in family_counts:
            family_counts[row.audience_family] += 1

    if filters is None:
        filters = {
            "source": source,
            "expiration_date_from": "2026-08-01",
            "expiration_date_to": "2026-08-31",
            "allowed_sucursal_keys": ["BRANCH A"],
            "audience_families": ["DOMICILIADO"],
        }
    if source_metadata is None:
        source_metadata = {
            "expired_storage": "socios_vencidos_cartera",
            "expiration_date_from": "2026-08-01",
            "expiration_date_to": "2026-08-31",
            "current_status_activos_snapshot_id": 88,
            "current_status_activos_cutoff_date": "2026-08-31",
        }

    duplicate_rows = tuple(
        row
        for recipient in recipients
        for row in recipient.evidence_rows[1:]
    )
    return audience._AudiencePlan(
        source=source,
        filters=filters,
        source_metadata=source_metadata,
        universe_count=len(evidence_rows),
        scoped_count=len(evidence_rows),
        current_status_counts={audience.current_status.STATUS_NOT_FOUND: len(evidence_rows)},
        current_status_blocked=(),
        classified_candidates=evidence_rows,
        selected_candidates=evidence_rows,
        invalid_phone_rows=(),
        duplicate_rows=duplicate_rows,
        recipients=recipients,
        family_counts=family_counts,
        unclassified_family_count=0,
        out_of_segment_count=0,
    )


def _install_plan(monkeypatch, plan):
    calls = []

    def rebuild(**kwargs):
        calls.append(kwargs)
        return plan

    monkeypatch.setattr(
        audience,
        "_build_campaign_v2_audience_plan",
        rebuild,
    )
    return calls


class WriteSession:
    def __init__(self, *, flush_error=None, commit_error=None):
        self.added = []
        self.flushes = 0
        self.commits = 0
        self.rollbacks = 0
        self.flush_error = flush_error
        self.commit_error = commit_error

    def add(self, value):
        self.added.append(value)

    def flush(self):
        self.flushes += 1
        if self.flush_error is not None:
            raise self.flush_error
        for value in self.added:
            if isinstance(value, MarketingCampaignV2ORM) and value.id is None:
                value.id = 501

    def commit(self):
        self.commits += 1
        if self.commit_error is not None:
            raise self.commit_error

    def rollback(self):
        self.rollbacks += 1


def _preview_fingerprint(monkeypatch, plan):
    _install_plan(monkeypatch, plan)
    return creation.build_campaign_v2_freeze_preview(
        source=plan.source,
        audience_families=plan.filters["audience_families"],
        allowed_sucursal_keys=plan.filters.get("allowed_sucursal_keys"),
        expiration_date_from=plan.filters.get("expiration_date_from"),
        expiration_date_to=plan.filters.get("expiration_date_to"),
        session=object(),
    )["preview_fingerprint"]


def test_creation_api_accepts_business_definition_not_arbitrary_recipients():
    parameters = set(inspect.signature(creation.freeze_campaign_v2).parameters)
    assert {
        "name",
        "purpose",
        "source",
        "audience_families",
        "allowed_sucursal_keys",
        "expected_preview_fingerprint",
        "created_by_user_id",
    } <= parameters
    assert not {
        "recipients",
        "recipient_ids",
        "phones",
        "source_record_ids",
        "preview_rows",
    } & parameters


def test_fingerprint_is_deterministic_for_different_recipient_and_evidence_order():
    first_a = _evidence(10, phone="6861000001")
    first_b = _evidence(20, phone="6861000001", name="Socio")
    second = _evidence(30, phone="6861000002")
    recipient_a = _recipient(
        phone="6861000001",
        evidence_rows=(first_a, first_b),
    )
    recipient_a_reordered = replace(
        recipient_a,
        evidence_rows=(first_b, first_a),
    )
    recipient_b = _recipient(
        phone="6861000002",
        evidence_rows=(second,),
    )

    plan_a = _plan((recipient_a, recipient_b))
    plan_b = _plan((recipient_b, recipient_a_reordered))

    assert creation._fingerprint_plan(plan_a) == creation._fingerprint_plan(plan_b)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda plan: replace(
            plan,
            filters={**plan.filters, "allowed_sucursal_keys": ["BRANCH B"]},
        ),
        lambda plan: replace(
            plan,
            source_metadata={
                **plan.source_metadata,
                "current_status_activos_snapshot_id": 99,
            },
        ),
        lambda plan: replace(
            plan,
            recipients=(
                replace(plan.recipients[0], phone_mx10="6869999999"),
            ),
        ),
        lambda plan: replace(
            plan,
            recipients=(
                replace(
                    plan.recipients[0],
                    evidence_rows=(
                        replace(
                            plan.recipients[0].evidence_rows[0],
                            source_ref_id=999,
                        ),
                    ),
                ),
            ),
        ),
    ],
)
def test_fingerprint_changes_on_material_preview_changes(mutator):
    base = _plan((_recipient(),))
    changed = mutator(base)

    assert len(base.recipients) == len(changed.recipients)
    assert creation._fingerprint_plan(base) != creation._fingerprint_plan(changed)


def test_freeze_rebuilds_server_side_and_freezes_campaign_recipients_and_evidence(
    monkeypatch,
):
    evidence_a = _evidence(
        10,
        phone="6861000001",
        name="Nombre A",
        tariff="DOM",
    )
    evidence_b = _evidence(
        20,
        phone="6861000001",
        name="Nombre B",
        tariff="TRI",
        tariff_key="TRI",
        category="Trimestre",
        family="TRIMESTRAL",
    )
    conflicted = _recipient(
        phone="6861000001",
        evidence_rows=(evidence_a, evidence_b),
        conflict_fields=(
            "audience_family",
            "categoria_tarifa",
            "member_name",
            "tarifa_key",
            "tarifa_raw",
        ),
        member_name=None,
        tariff=None,
        tariff_key=None,
        category=None,
        family=None,
    )
    single = _recipient(
        phone="6861000002",
        evidence_rows=(_evidence(30, phone="6861000002"),),
    )
    plan = _plan((conflicted, single))
    calls = _install_plan(monkeypatch, plan)
    fingerprint = creation._fingerprint_plan(plan)
    session = WriteSession()

    result = creation.freeze_campaign_v2(
        name=" Freeze agosto ",
        purpose="reactivation",
        source="EXPIRED_MEMBERS",
        audience_families=["DOMICILIADO"],
        allowed_sucursal_keys=["BRANCH A"],
        expected_preview_fingerprint=fingerprint,
        created_by_user_id=7,
        expiration_date_from="2026-08-01",
        expiration_date_to="2026-08-31",
        session=session,
        now=NOW,
    )

    assert len(calls) == 1
    assert calls[0]["session"] is session
    assert session.flushes == 1
    assert session.commits == 1
    assert session.rollbacks == 0
    assert result["campaign_id"] == 501
    assert result["recipient_count"] == 2
    assert result["preview_fingerprint"] == fingerprint

    campaign = session.added[0]
    assert campaign.name == "Freeze agosto"
    assert campaign.purpose == "REACTIVATION"
    assert campaign.source == "EXPIRED_MEMBERS"
    assert campaign.created_by_user_id == 7
    assert campaign.frozen_at == NOW
    assert campaign.audience_definition_json["filters"] == plan.filters
    assert (
        campaign.audience_definition_json["source_metadata"]
        == plan.source_metadata
    )
    assert (
        campaign.audience_definition_json["preview"]["fingerprint"]
        == fingerprint
    )
    assert "recipients" not in campaign.audience_definition_json

    by_phone = {
        recipient.phone_mx10: recipient
        for recipient in campaign.recipients
    }
    conflict_row = by_phone["6861000001"]
    single_row = by_phone["6861000002"]

    assert conflict_row.member_name is None
    assert conflict_row.tarifa_raw is None
    assert conflict_row.audience_family is None
    assert conflict_row.socios_vencidos_cartera_id is None
    assert conflict_row.socios_activos_snapshot_row_id is None
    assert sorted(conflict_row.conflict_fields_json) == sorted(
        conflicted.conflict_fields
    )
    assert [row.evidence_order for row in conflict_row.evidence_rows] == [0, 1]
    assert [row.socios_vencidos_cartera_id for row in conflict_row.evidence_rows] == [
        10,
        20,
    ]
    assert [row.tarifa_raw for row in conflict_row.evidence_rows] == ["DOM", "TRI"]

    assert single_row.socios_vencidos_cartera_id == 30
    assert single_row.socios_activos_snapshot_row_id is None
    assert single_row.conflict_fields_json == []
    assert len(single_row.evidence_rows) == 1


def test_active_member_evidence_keeps_snapshot_and_row_reference(monkeypatch):
    active_evidence = _evidence(
        55,
        phone="6861000055",
        source=audience.SOURCE_ACTIVE_MEMBERS,
        snapshot_id=7,
        current_status=None,
    )
    recipient = _recipient(
        phone="6861000055",
        evidence_rows=(active_evidence,),
    )
    recipient = replace(
        recipient,
        source=audience.SOURCE_ACTIVE_MEMBERS,
        member_id="SOCIO-55",
    )
    plan = _plan(
        (recipient,),
        source=audience.SOURCE_ACTIVE_MEMBERS,
        filters={
            "source": "ACTIVE_MEMBERS",
            "allowed_sucursal_keys": None,
            "audience_families": ["DOMICILIADO"],
        },
        source_metadata={
            "activos_snapshot_id": 7,
            "activos_cutoff_date": "2026-09-30",
            "activos_captured_at": "2026-09-30T08:00:00",
            "snapshot_kind": "daily",
        },
    )
    _install_plan(monkeypatch, plan)
    session = WriteSession()
    fingerprint = creation._fingerprint_plan(plan)

    creation.freeze_campaign_v2(
        name="Activos",
        purpose="ACTIVE_MEMBERS",
        source="ACTIVE_MEMBERS",
        audience_families=["DOMICILIADO"],
        allowed_sucursal_keys=None,
        expected_preview_fingerprint=fingerprint,
        created_by_user_id=7,
        session=session,
        now=NOW,
    )

    recipient_orm = session.added[0].recipients[0]
    evidence_orm = recipient_orm.evidence_rows[0]
    assert recipient_orm.socios_activos_snapshot_row_id == 55
    assert recipient_orm.socios_vencidos_cartera_id is None
    assert evidence_orm.socios_activos_snapshot_row_id == 55
    assert evidence_orm.socios_activos_snapshot_id == 7


def test_preview_mismatch_and_empty_audience_fail_before_persistence(monkeypatch):
    original = _plan((_recipient(),))
    fingerprint = creation._fingerprint_plan(original)

    changed = _plan(
        (
            _recipient(
                phone="6869999999",
                evidence_rows=(
                    _evidence(10, phone="6869999999"),
                ),
            ),
        )
    )
    _install_plan(monkeypatch, changed)
    mismatch_session = WriteSession()

    with pytest.raises(creation.MarketingCampaignV2PreviewMismatchError):
        creation.freeze_campaign_v2(
            name="Mismatch",
            purpose="REACTIVATION",
            source="EXPIRED_MEMBERS",
            audience_families=["DOMICILIADO"],
            allowed_sucursal_keys=["BRANCH A"],
            expected_preview_fingerprint=fingerprint,
            created_by_user_id=7,
            expiration_date_from="2026-08-01",
            expiration_date_to="2026-08-31",
            session=mismatch_session,
            now=NOW,
        )
    assert mismatch_session.added == []
    assert mismatch_session.commits == 0

    empty = _plan(())
    _install_plan(monkeypatch, empty)
    empty_session = WriteSession()

    with pytest.raises(creation.MarketingCampaignV2EmptyAudienceError):
        creation.freeze_campaign_v2(
            name="Empty",
            purpose="REACTIVATION",
            source="EXPIRED_MEMBERS",
            audience_families=["DOMICILIADO"],
            allowed_sucursal_keys=["BRANCH A"],
            expected_preview_fingerprint=creation._fingerprint_plan(empty),
            created_by_user_id=7,
            expiration_date_from="2026-08-01",
            expiration_date_to="2026-08-31",
            session=empty_session,
            now=NOW,
        )
    assert empty_session.added == []
    assert empty_session.commits == 0


def test_invalid_source_or_filter_fails_before_persistence(monkeypatch):
    def fail(**_kwargs):
        raise audience.MarketingCampaignV2AudienceValidationError(
            "source inválido"
        )

    monkeypatch.setattr(
        audience,
        "_build_campaign_v2_audience_plan",
        fail,
    )
    session = WriteSession()

    with pytest.raises(
        creation.MarketingCampaignV2CreationValidationError,
        match="source inválido",
    ):
        creation.freeze_campaign_v2(
            name="Invalid",
            purpose="REACTIVATION",
            source="INVALID",
            audience_families=["DOMICILIADO"],
            allowed_sucursal_keys=None,
            expected_preview_fingerprint="0" * 64,
            created_by_user_id=7,
            session=session,
            now=NOW,
        )

    assert session.added == []
    assert session.flushes == 0
    assert session.commits == 0


def test_integrity_failure_rolls_back_whole_object_graph(monkeypatch):
    plan = _plan((_recipient(),))
    _install_plan(monkeypatch, plan)
    session = WriteSession(
        flush_error=IntegrityError(
            "insert",
            {},
            RuntimeError("boom"),
        )
    )

    with pytest.raises(creation.MarketingCampaignV2PersistenceError):
        creation.freeze_campaign_v2(
            name="Atomic",
            purpose="REACTIVATION",
            source="EXPIRED_MEMBERS",
            audience_families=["DOMICILIADO"],
            allowed_sucursal_keys=["BRANCH A"],
            expected_preview_fingerprint=creation._fingerprint_plan(plan),
            created_by_user_id=7,
            expiration_date_from="2026-08-01",
            expiration_date_to="2026-08-31",
            session=session,
            now=NOW,
        )

    assert session.flushes == 1
    assert session.commits == 0
    assert session.rollbacks == 1


def _migration():
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "f6c1d8a3b2e4_add_campaign_v2_recipient_evidence.py"
    )
    spec = importlib.util.spec_from_file_location(
        "campaign_v2_recipient_evidence",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_migration_prerequisites(connection):
    connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    connection.execute(text(
        """
        CREATE TABLE marketing_campaign_v2_campaigns (
            id INTEGER PRIMARY KEY,
            name VARCHAR(255) NOT NULL
        )
        """
    ))
    connection.execute(text(
        """
        CREATE TABLE marketing_campaign_v2_recipients (
            id INTEGER PRIMARY KEY,
            campaign_id INTEGER NOT NULL,
            phone_mx10 VARCHAR(10) NOT NULL,
            FOREIGN KEY(campaign_id)
                REFERENCES marketing_campaign_v2_campaigns(id)
                ON DELETE CASCADE
        )
        """
    ))
    connection.execute(text(
        """
        CREATE TABLE socios_vencidos_cartera (
            id INTEGER PRIMARY KEY,
            nombre VARCHAR(255),
            tarifa VARCHAR(255)
        )
        """
    ))
    connection.execute(text(
        """
        CREATE TABLE socios_activos_snapshots (
            id INTEGER PRIMARY KEY,
            cutoff_date DATE
        )
        """
    ))
    connection.execute(text(
        """
        CREATE TABLE socios_activos_snapshot_rows (
            id INTEGER PRIMARY KEY,
            snapshot_id INTEGER NOT NULL,
            nombre VARCHAR(255),
            tarifa VARCHAR(255),
            FOREIGN KEY(snapshot_id)
                REFERENCES socios_activos_snapshots(id)
                ON DELETE CASCADE
        )
        """
    ))
    connection.execute(text(
        """
        CREATE TABLE marketing_reactivation_campaigns (
            id INTEGER PRIMARY KEY,
            marker VARCHAR(50) NOT NULL
        )
        """
    ))


def test_evidence_migration_upgrade_constraints_immutability_cascade_and_downgrade():
    migration = _migration()
    engine = create_engine("sqlite://")

    try:
        with engine.begin() as connection:
            _create_migration_prerequisites(connection)
            connection.execute(text(
                "INSERT INTO marketing_campaign_v2_campaigns (id, name) "
                "VALUES (1, 'Campaign')"
            ))
            connection.execute(text(
                "INSERT INTO marketing_campaign_v2_recipients "
                "(id, campaign_id, phone_mx10) VALUES (10, 1, '6861000001')"
            ))
            connection.execute(text(
                "INSERT INTO socios_vencidos_cartera (id, nombre, tarifa) "
                "VALUES (100, 'Nombre vivo', 'Tarifa viva')"
            ))
            connection.execute(text(
                "INSERT INTO socios_activos_snapshots (id, cutoff_date) "
                "VALUES (7, '2026-09-30')"
            ))
            connection.execute(text(
                "INSERT INTO socios_activos_snapshot_rows "
                "(id, snapshot_id, nombre, tarifa) "
                "VALUES (200, 7, 'Activo vivo', 'Tarifa activa')"
            ))
            connection.execute(text(
                "INSERT INTO marketing_reactivation_campaigns (id, marker) "
                "VALUES (900, 'legacy')"
            ))

            context = MigrationContext.configure(connection)
            with Operations.context(context):
                migration.upgrade()

            columns = {
                column["name"]
                for column in sa_inspect(connection).get_columns(
                    "marketing_campaign_v2_recipients"
                )
            }
            assert "conflict_fields_json" in columns
            assert connection.scalar(text(
                "SELECT conflict_fields_json "
                "FROM marketing_campaign_v2_recipients WHERE id=10"
            )) == "[]"

            connection.execute(text(
                """
                INSERT INTO marketing_campaign_v2_recipient_evidence (
                    id, recipient_id, evidence_order, source,
                    phone_raw, phone_mx10, socios_vencidos_cartera_id,
                    member_name, tarifa_raw, audience_family,
                    evidence_json
                ) VALUES (
                    1000, 10, 0, 'EXPIRED_MEMBERS',
                    '6861000001', '6861000001', 100,
                    'Nombre congelado', 'Tarifa congelada',
                    'DOMICILIADO', '["CURRENT_STATUS:NOT_FOUND"]'
                )
                """
            ))

            connection.execute(text(
                "UPDATE socios_vencidos_cartera "
                "SET nombre='Cambio', tarifa='Cambio' WHERE id=100"
            ))
            frozen = connection.execute(text(
                "SELECT member_name, tarifa_raw "
                "FROM marketing_campaign_v2_recipient_evidence WHERE id=1000"
            )).one()
            assert frozen == ("Nombre congelado", "Tarifa congelada")

            with pytest.raises(IntegrityError):
                connection.execute(text(
                    "DELETE FROM socios_vencidos_cartera WHERE id=100"
                ))

            connection.execute(text(
                "DELETE FROM marketing_campaign_v2_campaigns WHERE id=1"
            ))
            assert connection.scalar(text(
                "SELECT COUNT(*) FROM marketing_campaign_v2_recipients"
            )) == 0
            assert connection.scalar(text(
                "SELECT COUNT(*) FROM marketing_campaign_v2_recipient_evidence"
            )) == 0
            assert connection.scalar(text(
                "SELECT COUNT(*) FROM socios_vencidos_cartera WHERE id=100"
            )) == 1

            with Operations.context(context):
                migration.downgrade()

            tables = set(sa_inspect(connection).get_table_names())
            assert "marketing_campaign_v2_recipient_evidence" not in tables
            columns = {
                column["name"]
                for column in sa_inspect(connection).get_columns(
                    "marketing_campaign_v2_recipients"
                )
            }
            assert "conflict_fields_json" not in columns
            assert connection.scalar(text(
                "SELECT marker FROM marketing_reactivation_campaigns WHERE id=900"
            )) == "legacy"
    finally:
        engine.dispose()


def test_evidence_model_contract_preserves_explicit_canonical_references():
    columns = MarketingCampaignV2RecipientEvidenceORM.__table__.c
    assert columns.recipient_id.nullable is False
    assert columns.phone_mx10.nullable is False
    assert columns.socios_vencidos_cartera_id.nullable is True
    assert columns.socios_activos_snapshot_row_id.nullable is True
    assert columns.socios_activos_snapshot_id.nullable is True
    assert "source_record_id" not in columns

    fks = {
        fk.parent.name: (fk.target_fullname, fk.ondelete)
        for fk in MarketingCampaignV2RecipientEvidenceORM.__table__.foreign_keys
    }
    assert fks["recipient_id"] == (
        "marketing_campaign_v2_recipients.id",
        "CASCADE",
    )
    assert fks["socios_vencidos_cartera_id"] == (
        "socios_vencidos_cartera.id",
        "RESTRICT",
    )
    assert fks["socios_activos_snapshot_row_id"] == (
        "socios_activos_snapshot_rows.id",
        "RESTRICT",
    )
    assert fks["socios_activos_snapshot_id"] == (
        "socios_activos_snapshots.id",
        "RESTRICT",
    )
    assert MarketingCampaignV2RecipientORM.__table__.c.conflict_fields_json.nullable is False
