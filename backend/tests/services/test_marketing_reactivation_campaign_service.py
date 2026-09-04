from __future__ import annotations

from datetime import date, datetime, timezone
from io import BytesIO
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook
from sqlalchemy import UniqueConstraint, select
from sqlalchemy.dialects import postgresql

from app.models import (
    MarketingReactivationCampaignORM,
    MarketingReactivationCampaignRecipientORM,
)
from app.models.warehouse import SociosVencidosCarteraORM
from app.services import marketing_reactivation_service as service


NOW = datetime(2026, 9, 3, 18, 0, tzinfo=timezone.utc)


def _candidate(
    row_id: int,
    *,
    phone: str | None,
    status: str = "CONTACT_HISTORY_UNKNOWN",
    reason: str = "NO_OUTBOUND_EVIDENCE",
):
    return {
        "vencido_row_id": row_id,
        "pin": f"PIN-{row_id}",
        "nombre": f"Socio {row_id}",
        "sucursal": "CENTRO",
        "telefono": phone,
        "correo": None,
        "fecha_vencimiento": "2026-08-23",
        "fecha_ultimo_pago": None,
        "tarifa": "ANUAL",
        "adeudo": None,
        "status": status,
        "reason": reason,
        "active_status": "NOT_FOUND",
        "active_id_socio": None,
        "iventas_contact_id": None,
        "latest_outbound_at_utc": None,
    }


def _candidate_response(rows):
    return {
        "sources": {
            "date_from": "2026-08-23",
            "date_to": "2026-08-23",
            "activos_snapshot_id": 8,
            "iventas_sync_run_id": 26,
            "iventas_period_key": "IVENTAS-2026-08",
        },
        "summary": {"total_rows": len(rows)},
        "rows": rows,
    }


def _filters(**overrides):
    values = {
        "iventas_period_key": "IVENTAS-2026-08",
        "sucursal": None,
        "operational_status": "ALL",
        "search": None,
        "tarifa": None,
    }
    values.update(overrides)
    return values


class WriteSession:
    def __init__(self, *, flush_error: Exception | None = None):
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.flush_error = flush_error
        self.next_campaign_id = 1

    def add(self, row):
        if isinstance(row, MarketingReactivationCampaignORM) and row.id is None:
            row.id = self.next_campaign_id
            self.next_campaign_id += 1
        self.added.append(row)

    def flush(self):
        if self.flush_error is not None:
            raise self.flush_error

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_preview_uses_one_engine_and_classifies_every_decision(monkeypatch):
    rows = [
        _candidate(1, phone="686 100 0001"),
        _candidate(
            2,
            phone="686 100 0002",
            status="EXCLUDED_ACTIVE",
            reason="ACTIVE_CONFIRMED",
        ),
        _candidate(3, phone="123"),
        _candidate(
            4,
            phone="686 100 0004",
            status="REVIEW_ACTIVE_MATCH",
            reason="ACTIVE_REVIEW",
        ),
        _candidate(5, phone="686 100 0005"),
        _candidate(6, phone="6861000005"),
        _candidate(7, phone="686 100 0007"),
    ]
    monkeypatch.setattr(
        service,
        "build_marketing_reactivation_candidates",
        lambda **kwargs: _candidate_response(rows),
    )
    monkeypatch.setattr(
        service,
        "_read_last_suite_campaign_sent_at",
        lambda **kwargs: {"6861000007": NOW},
    )
    session = SimpleNamespace()

    result = service.preview_marketing_reactivation_campaign(
        date_from="2026-08-23",
        date_to="2026-08-23",
        filters=_filters(),
        campaign_cooldown_days=30,
        session=session,
        now=NOW,
    )

    assert result["summary"] == {
        "total_candidates": 7,
        "eligible": 1,
        "excluded_active": 1,
        "excluded_invalid_phone": 1,
        "review_identity": 1,
        "duplicate_phone": 2,
        "excluded_tariff": 0,
        "excluded_recent_campaign": 1,
        "review": 3,
    }
    assert not hasattr(session, "added")


def test_cooldown_is_not_applied_without_explicit_configuration(monkeypatch):
    rows = [_candidate(1, phone="6861000001")]
    monkeypatch.setattr(
        service,
        "build_marketing_reactivation_candidates",
        lambda **kwargs: _candidate_response(rows),
    )
    monkeypatch.setattr(
        service,
        "_read_last_suite_campaign_sent_at",
        lambda **kwargs: {"6861000001": NOW},
    )

    result = service.preview_marketing_reactivation_campaign(
        date_from="2026-08-23",
        date_to="2026-08-23",
        filters=_filters(),
        session=SimpleNamespace(),
        now=NOW,
    )

    assert result["summary"]["eligible"] == 1
    assert result["summary"]["excluded_recent_campaign"] == 0


def test_no_match_current_run_is_operational_evidence_not_never_contacted(monkeypatch):
    rows = [
        _candidate(
            1,
            phone="6861000001",
            reason="NO_MATCH_CURRENT_IVENTAS_RUN",
        )
    ]
    monkeypatch.setattr(
        service,
        "build_marketing_reactivation_candidates",
        lambda **kwargs: _candidate_response(rows),
    )
    monkeypatch.setattr(
        service,
        "_read_last_suite_campaign_sent_at",
        lambda **kwargs: {},
    )

    plan = service._build_campaign_plan(
        date_from="2026-08-23",
        date_to="2026-08-23",
        filters=_filters(),
        campaign_cooldown_days=None,
        session=SimpleNamespace(),
        now=NOW,
    )

    assert plan["decision_rows"][0]["operational_status"] == (
        "NO_CONTACT_IN_PERIOD"
    )
    assert plan["decision_rows"][0]["campaign_eligibility"] == "ELIGIBLE"


def test_create_campaign_is_atomic_and_snapshots_only_eligible_rows(monkeypatch):
    plan = {
        "sources": _candidate_response([])["sources"],
        "filters": _filters(),
        "summary": {"total_candidates": 1, "eligible": 1},
        "eligible_rows": [
            {
                **_candidate(10, phone="6861000010"),
                "phone_mx10": "6861000010",
                "operational_status": "NO_OUTBOUND_MESSAGE",
            }
        ],
    }
    monkeypatch.setattr(service, "_build_campaign_plan", lambda **kwargs: plan)
    session = WriteSession()

    result = service.create_marketing_reactivation_campaign(
        name="Septiembre Centro",
        date_from="2026-08-23",
        date_to="2026-08-23",
        filters=_filters(),
        notes="Exportación externa",
        created_by_user_id=3,
        session=session,
        now=NOW,
    )

    assert result["status"] == "DRAFT"
    assert result["recipient_count"] == 1
    assert session.commits == 1
    assert session.rollbacks == 0
    recipients = [
        row
        for row in session.added
        if isinstance(row, MarketingReactivationCampaignRecipientORM)
    ]
    assert len(recipients) == 1
    assert recipients[0].phone_mx10 == "6861000010"
    assert recipients[0].inclusion_status == "ELIGIBLE"


def test_create_rolls_back_complete_campaign_when_flush_fails(monkeypatch):
    monkeypatch.setattr(
        service,
        "_build_campaign_plan",
        lambda **kwargs: {
            "sources": _candidate_response([])["sources"],
            "filters": _filters(),
            "summary": {"eligible": 1},
            "eligible_rows": [
                {
                    **_candidate(1, phone="6861000001"),
                    "phone_mx10": "6861000001",
                    "operational_status": "NO_OUTBOUND_MESSAGE",
                }
            ],
        },
    )
    session = WriteSession(flush_error=RuntimeError("flush failed"))

    with pytest.raises(RuntimeError, match="flush failed"):
        service.create_marketing_reactivation_campaign(
            name="Lote",
            date_from="2026-08-23",
            date_to="2026-08-23",
            filters=_filters(),
            created_by_user_id=3,
            session=session,
            now=NOW,
        )

    assert session.commits == 0
    assert session.rollbacks == 1


def test_empty_campaign_is_rejected_without_writes(monkeypatch):
    monkeypatch.setattr(
        service,
        "_build_campaign_plan",
        lambda **kwargs: {
            "sources": _candidate_response([])["sources"],
            "filters": _filters(),
            "summary": {"eligible": 0},
            "eligible_rows": [],
        },
    )
    session = WriteSession()

    with pytest.raises(
        service.MarketingReactivationValidationError,
        match="no contiene destinatarios",
    ):
        service.create_marketing_reactivation_campaign(
            name="Vacía",
            date_from="2026-08-23",
            date_to="2026-08-23",
            filters=_filters(),
            created_by_user_id=3,
            session=session,
            now=NOW,
        )

    assert session.added == []
    assert session.commits == 0


def test_same_phone_is_allowed_in_different_campaigns(monkeypatch):
    plan = {
        "sources": _candidate_response([])["sources"],
        "filters": _filters(),
        "summary": {"eligible": 1},
        "eligible_rows": [
            {
                **_candidate(1, phone="6861000001"),
                "phone_mx10": "6861000001",
                "operational_status": "NO_OUTBOUND_MESSAGE",
            }
        ],
    }
    monkeypatch.setattr(service, "_build_campaign_plan", lambda **kwargs: plan)
    session = WriteSession()

    first = service.create_marketing_reactivation_campaign(
        name="Primera",
        date_from="2026-08-23",
        date_to="2026-08-23",
        filters=_filters(),
        created_by_user_id=3,
        session=session,
        now=NOW,
    )
    second = service.create_marketing_reactivation_campaign(
        name="Segunda",
        date_from="2026-08-23",
        date_to="2026-08-23",
        filters=_filters(),
        created_by_user_id=3,
        session=session,
        now=NOW,
    )

    assert first["id"] != second["id"]
    recipients = [
        row
        for row in session.added
        if isinstance(row, MarketingReactivationCampaignRecipientORM)
    ]
    assert {row.campaign_id for row in recipients} == {first["id"], second["id"]}
    assert {row.phone_mx10 for row in recipients} == {"6861000001"}


def test_recipient_unique_constraint_is_scoped_to_campaign_and_phone():
    constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in MarketingReactivationCampaignRecipientORM.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert constraints[
        "uq_marketing_reactivation_recipients_campaign_phone"
    ] == ("campaign_id", "phone_mx10")


def _campaign(status="DRAFT"):
    recipient = SimpleNamespace(
        id=1,
        socios_vencidos_cartera_id=10,
        phone_mx10="6861000010",
        member_name="Ana Pérez",
        sucursal="CENTRO",
        fecha_vencimiento_date=date(2026, 8, 23),
        tarifa="ANUAL",
        inclusion_status="ELIGIBLE",
        exclusion_reason=None,
        operational_status="NO_OUTBOUND_MESSAGE",
        operational_reason="NO_OUTBOUND_EVIDENCE",
        created_at=NOW,
    )
    return SimpleNamespace(
        id=9,
        name="Campaña 9",
        status=status,
        date_from=date(2026, 8, 23),
        date_to=date(2026, 8, 23),
        created_by_user_id=3,
        created_by_user=SimpleNamespace(username="admin"),
        created_at=NOW,
        updated_at=NOW,
        exported_at=None,
        sent_at=None,
        notes=None,
        filters_json={"filters": _filters()},
        recipient_count=1,
        recipients=[recipient],
    )


def test_export_builds_xlsx_and_transitions_draft_after_success(monkeypatch):
    campaign = _campaign()
    session = WriteSession()
    monkeypatch.setattr(service, "_read_campaign", lambda **kwargs: campaign)
    monkeypatch.setattr(
        service,
        "_build_campaign_plan",
        lambda **kwargs: {
            "eligible_rows": [
                {"vencido_row_id": 10, "phone_mx10": "6861000010"}
            ]
        },
    )

    file_bytes, filename = service.export_marketing_reactivation_campaign(
        campaign_id=9,
        session=session,
        now=NOW,
    )

    workbook = load_workbook(BytesIO(file_bytes), read_only=True)
    rows = list(workbook["Destinatarios"].iter_rows(values_only=True))
    assert rows[0] == (
        "Nombre",
        "Teléfono",
        "Sucursal",
        "Fecha vencimiento",
        "Tarifa",
    )
    assert rows[1] == (
        "Ana Pérez",
        "6861000010",
        "CENTRO",
        "2026-08-23",
        "ANUAL",
    )
    assert filename == "reactivacion_campana_9.xlsx"
    assert campaign.status == "EXPORTED"
    assert campaign.exported_at == NOW
    assert session.commits == 1


def test_export_does_not_mark_exported_when_revalidation_changes(monkeypatch):
    campaign = _campaign()
    session = WriteSession()
    monkeypatch.setattr(service, "_read_campaign", lambda **kwargs: campaign)
    monkeypatch.setattr(
        service,
        "_build_campaign_plan",
        lambda **kwargs: {"eligible_rows": []},
    )

    with pytest.raises(service.MarketingReactivationConflictError):
        service.export_marketing_reactivation_campaign(
            campaign_id=9,
            session=session,
            now=NOW,
        )

    assert campaign.status == "DRAFT"
    assert campaign.exported_at is None
    assert session.commits == 0


def test_export_writer_failure_does_not_mark_exported(monkeypatch):
    campaign = _campaign()
    session = WriteSession()
    monkeypatch.setattr(service, "_read_campaign", lambda **kwargs: campaign)
    monkeypatch.setattr(
        service,
        "_build_campaign_plan",
        lambda **kwargs: {
            "eligible_rows": [
                {"vencido_row_id": 10, "phone_mx10": "6861000010"}
            ]
        },
    )

    class BrokenWorkbook:
        def __init__(self, **kwargs):
            pass

        def create_sheet(self, title):
            return SimpleNamespace(append=lambda row: None)

        def save(self, output):
            raise RuntimeError("xlsx failed")

    monkeypatch.setattr(service, "Workbook", BrokenWorkbook)

    with pytest.raises(RuntimeError, match="xlsx failed"):
        service.export_marketing_reactivation_campaign(
            campaign_id=9,
            session=session,
            now=NOW,
        )

    assert campaign.status == "DRAFT"
    assert campaign.exported_at is None
    assert session.commits == 0


def test_mark_sent_requires_exported_and_uses_small_transaction(monkeypatch):
    campaign = _campaign(status="EXPORTED")
    session = WriteSession()
    monkeypatch.setattr(service, "_read_campaign", lambda **kwargs: campaign)

    result = service.mark_marketing_reactivation_campaign_sent(
        campaign_id=9,
        session=session,
        now=NOW,
    )

    assert result["status"] == "SENT"
    assert campaign.sent_at == NOW
    assert session.commits == 1


def test_draft_cannot_transition_directly_to_sent(monkeypatch):
    campaign = _campaign(status="DRAFT")
    session = WriteSession()
    monkeypatch.setattr(service, "_read_campaign", lambda **kwargs: campaign)

    with pytest.raises(service.MarketingReactivationInvalidTransitionError):
        service.mark_marketing_reactivation_campaign_sent(
            campaign_id=9,
            session=session,
            now=NOW,
        )

    assert campaign.status == "DRAFT"
    assert session.commits == 0


@pytest.mark.parametrize(
    ("date_from", "date_to"),
    [("invalid", "2026-08-23"), ("2026-08-24", "2026-08-23")],
)
def test_preview_validates_date_range(date_from, date_to):
    with pytest.raises(service.MarketingReactivationValidationError):
        service.preview_marketing_reactivation_campaign(
            date_from=date_from,
            date_to=date_to,
            filters=_filters(),
            session=SimpleNamespace(),
            now=NOW,
        )


class AggregateQuery:
    def __init__(self, rows):
        self.rows = rows
        self.criteria = []

    def filter(self, *criteria):
        self.criteria.extend(criteria)
        return self

    def group_by(self, *args):
        return self

    def order_by(self, *args):
        return self

    def all(self):
        return self.rows


class AggregateSession:
    def __init__(self, rows):
        self.query_object = AggregateQuery(rows)

    def query(self, *entities):
        return self.query_object


def test_tariff_lookup_filters_range_in_sql_and_returns_counts():
    session = AggregateSession([("ANUAL", 4), (None, 2)])

    result = service.list_marketing_reactivation_tariffs(
        date_from=date(2026, 8, 1),
        date_to=date(2026, 8, 31),
        session=session,
    )

    statement = select(SociosVencidosCarteraORM.tarifa).where(
        *session.query_object.criteria
    )
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()
    assert "fecha_vencimiento_date between '2026-08-01' and '2026-08-31'" in sql
    assert result["rows"] == [
        {"tarifa": "ANUAL", "count": 4},
        {"tarifa": None, "count": 2},
    ]
