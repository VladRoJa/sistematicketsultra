from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace as NS

import pytest
from openpyxl import load_workbook
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, text
from sqlalchemy.orm import Session

from app.models.marketing import MarketingReactivationCampaignORM as Campaign, MarketingReactivationCampaignRecipientORM as Recipient
from app.services import marketing_campaign_audience_service as audience
from app.services import marketing_reactivation_service as service

NOW = datetime(2026, 9, 8, 18, tzinfo=timezone.utc)


class Query:
    def __init__(self, result):
        self.result = result
    def filter(self, *args):
        return self
    def order_by(self, *args):
        return self
    def first(self):
        return self.result


def plan(rows=None):
    rows = rows or []
    return {"sources": {}, "summary": {"eligible": len(rows)}, "eligible_rows": rows}


@pytest.mark.parametrize("filters,lower,upper", [
    ({"campaign_type": "VENCIDOS_RECIENTES"}, 1, 7),
    ({"campaign_type": "WINBACK", "segment": "WINBACK_30"}, 8, 30),
    ({"campaign_type": "WINBACK", "segment": "WINBACK_60"}, 31, 60),
    ({"campaign_type": "WINBACK", "segment": "WINBACK_90"}, 61, 90),
    ({"campaign_type": "COBRANZA_LIGERA", "dias_desde": 12, "dias_hasta": 42}, 12, 42),
])
def test_expiration_intervals_reuse_existing_engine(monkeypatch, filters, lower, upper):
    calls = {}
    monkeypatch.setattr(audience, "exported_counts", lambda *a, **k: {})
    def expired(**kwargs):
        calls.update(kwargs)
        return plan()
    result = audience.prepare_v1_plan(
        filters=filters, allowed_sucursal_keys=("CENTRO",), now=NOW,
        session=NS(query=lambda *a: Query(NS(period_key="CANONICAL"))),
        expired_builder=expired, active_builder=None,
    )
    assert calls["date_from"] == NOW.date() - timedelta(days=upper)
    assert calls["date_to"] == NOW.date() - timedelta(days=lower)
    assert calls["filters"]["iventas_period_key"] == "CANONICAL"
    assert calls["allowed_sucursal_keys"] == ("CENTRO",)
    assert result["filters"] == filters


@pytest.mark.parametrize("lower,upper", [(None, None), (0, 7), (8, 7), (True, 7), (1.5, 7), (1, "7")])
def test_collection_has_no_default_and_requires_valid_days(lower, upper):
    with pytest.raises(service.MarketingReactivationValidationError):
        audience.prepare_v1_plan(filters={"campaign_type": "COBRANZA_LIGERA", "dias_desde": lower, "dias_hasta": upper},
                                 allowed_sucursal_keys=None, session=None, now=NOW, active_builder=None, expired_builder=None)


@pytest.mark.parametrize("offset,expected", [(-1, 0), (0, 1), (5, 1), (6, 0)])
def test_upcoming_inclusive_dates(monkeypatch, offset, expected):
    monkeypatch.setattr(service, "resolve_latest_canonical_socios_activos_snapshot", lambda **k: NS(
        id=1, cutoff_date=NOW.date(), rows=[NS(id=1, telefono_raw="6861000001", nombre="Ana", sucursal_raw="CENTRO",
                                            tarifa=None, fecha_vencimiento_date=NOW.date() + timedelta(days=offset))]))
    result = service._build_bascula_campaign_plan(filters={"campaign_type": "PROXIMOS_VENCER"},
                                                  allowed_sucursal_keys=None, session=None, now=NOW)
    assert result["summary"]["eligible"] == expected


def new_row(row_id, payment, phone="6861000001", branch="CENTRO"):
    return NS(id=row_id, fecha_pago_at=payment, telefono=phone, nombre="Ana", apellido_paterno="Pérez",
              apellido_materno="", sucursal_raw=branch, tarifa="ANUAL")


def test_new_members_week_crosses_month_and_uses_payment_timezone():
    snapshots = iter([
        NS(id=10, rows=[new_row(1, datetime(2026, 9, 1, 1, tzinfo=timezone.utc)),
                        new_row(2, datetime(2026, 8, 31, 6, tzinfo=timezone.utc))]),
        NS(id=11, rows=[new_row(3, datetime(2026, 9, 2, 18, tzinfo=timezone.utc))]),
    ])
    clauses = []
    class SnapshotQuery(Query):
        def filter(self, *args):
            clauses.extend(args)
            return self
    rows, sources = audience.new_member_rows(today=date(2026, 9, 2), session=NS(query=lambda *a: SnapshotQuery(next(snapshots))))
    assert len(rows) == 2  # Aug 31 local and Sep 2; Aug 30 local is outside.
    assert sources == {"date_from": "2026-08-31", "date_to": "2026-09-06", "nuevos_snapshot_ids": [10, 11]}
    bound_dates = [getattr(getattr(clause, "right", None), "value", None) for clause in clauses]
    assert date(2026, 8, 31) in bound_dates
    assert date(2026, 9, 2) in bound_dates
    assert rows[0]["vencido_row_id"] is None


def test_new_members_fails_if_one_month_is_missing():
    snapshots = iter([NS(id=1, rows=[]), None])
    with pytest.raises(service.MarketingReactivationValidationError, match="2026-09-02"):
        audience.new_member_rows(today=date(2026, 9, 2), session=NS(query=lambda *a: Query(next(snapshots))))


def test_new_members_deduplicate_invalid_and_scope(monkeypatch):
    rows = [{"telefono": phone, "sucursal": branch, "vencido_row_id": None} for phone, branch in [
        ("6861000001", "CENTRO"), ("+52 6861000001", "CENTRO"), ("123", "CENTRO"), ("6861000002", "NORTE")]]
    monkeypatch.setattr(audience, "new_member_rows", lambda **k: (rows, {}))
    monkeypatch.setattr(audience, "exported_counts", lambda *a, **k: {})
    result = audience.prepare_v1_plan(filters={"campaign_type": "INVITA_GANA"}, allowed_sucursal_keys=("CENTRO",),
                                      session=None, now=NOW, active_builder=None, expired_builder=None)
    assert result["summary"]["eligible"] == 1
    assert result["summary"]["duplicate_phone"] == 1
    assert result["summary"]["excluded_invalid_phone"] == 1


def test_region_intersects_permissions_and_rejects_wrong_branch(monkeypatch):
    monkeypatch.setattr(audience, "region_branches", lambda **k: [NS(sucursal="CENTRO"), NS(sucursal="NORTE")])
    monkeypatch.setattr(audience, "exported_counts", lambda *a, **k: {})
    calls = {}
    def active(**kwargs):
        calls.update(kwargs)
        return plan()
    kwargs = dict(allowed_sucursal_keys=("CENTRO", "SUR"), session=None, now=NOW, active_builder=active, expired_builder=None)
    result = audience.prepare_v1_plan(filters={"campaign_type": "BASCULA_RETENCION", "region_id": 1}, **kwargs)
    assert calls["allowed_sucursal_keys"] == ("CENTRO",)
    assert result["scope"]["allowed_sucursal_keys"] == ["CENTRO"]
    with pytest.raises(service.MarketingReactivationValidationError):
        audience.prepare_v1_plan(filters={"campaign_type": "BASCULA_RETENCION", "region_id": 1, "sucursal": "SUR"}, **kwargs)


def test_frequency_warns_before_third_export_in_preview(monkeypatch):
    monkeypatch.setattr(audience, "exported_counts", lambda *a, **k: {"6861000001": 2, "6861000002": 1})
    result = audience.prepare_v1_plan(filters={"campaign_type": "BASCULA_RETENCION"}, allowed_sucursal_keys=None,
        session=None, now=NOW, expired_builder=None,
        active_builder=lambda **k: plan([{"phone_mx10": "6861000001"}, {"phone_mx10": "6861000002"}]))
    assert result["eligible_rows"] == [{"phone_mx10": "6861000001"}, {"phone_mx10": "6861000002"}]
    assert result["summary"]["weekly_limit_contacts"] == 1
    assert result["summary"]["weekly_frequency_decision_required"] is True
    assert result["summary"]["excluded_weekly_limit"] == 0


@pytest.fixture
def frequency_session():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    for name in ("users", "socios_vencidos_cartera"):
        Table(name, metadata, Column("id", Integer, primary_key=True))
    for model in (Campaign, Recipient):
        table = model.__table__.to_metadata(metadata)
        table.c.id.type = Integer()
    metadata.create_all(engine)
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def test_frequency_real_query_ignores_drafts_cancelled_and_previous_week(frequency_session):
    session = frequency_session
    start, end = audience.week_window(NOW)
    for index, (status, exported) in enumerate([
        ("EXPORTED", start), ("EXPORTED", end - timedelta(seconds=1)),
        ("DRAFT", NOW), ("CANCELLED", NOW), ("EXPORTED", start - timedelta(seconds=1)),
        ("EXPORTED", end), ("SENT", NOW),
    ], 1):
        campaign = Campaign(id=index, name="Test", status=status, date_from=NOW.date(), date_to=NOW.date(),
                            created_at=NOW, updated_at=NOW, exported_at=exported, filters_json={}, recipient_count=1)
        campaign.recipients = [Recipient(id=index, phone_mx10="6861000001", sucursal="CENTRO",
            operational_status="ACTIVE", operational_reason="ACTIVE_CONFIRMED", inclusion_status="ELIGIBLE", created_at=NOW)]
        session.add(campaign)
    session.commit()
    assert audience.exported_counts({"6861000001"}, session=session, now=NOW) == {"6861000001": 2}


@pytest.mark.parametrize("source_id,expiration", [(10, date(2026, 8, 1)), (None, date(2026, 10, 1)), (None, None)])
def test_export_one_column_all_origins_without_reading_sources(monkeypatch, source_id, expiration):
    row = NS(phone_mx10="6861000001", sucursal="CENTRO", socios_vencidos_cartera_id=source_id, fecha_vencimiento_date=expiration)
    campaign = NS(id=1, status="DRAFT", recipients=[row], filters_json={}, exported_at=None)
    monkeypatch.setattr(service, "_read_campaign", lambda **k: campaign)
    monkeypatch.setattr(service, "_build_campaign_plan", lambda **k: pytest.fail("source queried"))
    monkeypatch.setattr(audience, "exported_counts", lambda *a, **k: {})
    monkeypatch.setattr(audience, "lock_export_phones", lambda *a, **k: None)
    result, _ = service.export_marketing_reactivation_campaign(campaign_id=1, session=NS(commit=lambda: None), now=NOW)
    assert list(load_workbook(BytesIO(result)).active.values) == [("telefono",), ("6861000001",)]
    assert campaign.status == "EXPORTED"


def test_export_rechecks_frequency_after_freezing(monkeypatch):
    campaign = NS(id=1, status="DRAFT", recipients=[NS(phone_mx10="6861000001", sucursal="CENTRO")], filters_json={})
    monkeypatch.setattr(service, "_read_campaign", lambda **k: campaign)
    events = []
    monkeypatch.setattr(audience, "lock_export_phones", lambda *a, **k: events.append("lock"))
    monkeypatch.setattr(audience, "exported_counts", lambda *a, **k: events.append("count") or {"6861000001": 2})
    with pytest.raises(service.MarketingReactivationConflictError):
        service.export_marketing_reactivation_campaign(campaign_id=1, session=NS(commit=lambda: pytest.fail("committed")), now=NOW)
    assert events == ["lock", "count"]
    assert campaign.status == "DRAFT"


def test_repeat_export_does_not_count_again(monkeypatch):
    campaign = NS(id=1, status="EXPORTED", recipients=[NS(phone_mx10="6861000001", sucursal="CENTRO")], filters_json={}, exported_at=NOW)
    monkeypatch.setattr(service, "_read_campaign", lambda **k: campaign)
    monkeypatch.setattr(audience, "exported_counts", lambda *a, **k: pytest.fail("Re-export must not consume quota"))
    service.export_marketing_reactivation_campaign(campaign_id=1, session=NS(commit=lambda: None), now=NOW + timedelta(days=7))
    assert campaign.exported_at == NOW


def test_postgres_export_policy_uses_one_shared_transaction_lock():
    calls = []
    session = NS(get_bind=lambda: NS(dialect=NS(name="postgresql")), execute=lambda sql, values: calls.append((str(sql), values)))
    audience.lock_export_phones({"6861000002", "6861000001"}, session=session)
    first = list(calls)
    calls.clear()
    audience.lock_export_phones({"6861000001", "6861000002"}, session=session)
    assert calls == first
    assert len(calls) == 1
    assert all("pg_advisory_xact_lock" in sql for sql, values in calls)


def test_region_catalog_uses_current_assignments_and_user_scope():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    for model in (audience.Sucursal, audience.SuiteRegionORM, audience.SuiteSucursalRegionAssignmentORM):
        model.__table__.to_metadata(metadata)
    metadata.create_all(engine)
    try:
        with Session(engine) as session:
            session.add_all([
                audience.SuiteRegionORM(id=1, region_key="REGION", region_label="Región", is_active=True),
                audience.SuiteRegionORM(id=2, region_key="INACTIVE", region_label="Inactiva", is_active=False),
            ])
            for index, (name, current, start, end, region) in enumerate([
                ("CENTRO", True, NOW.date(), NOW.date(), 1),
                ("NORTE", True, None, None, 1),
                ("HISTORICA", False, None, None, 1),
                ("FUTURA", True, NOW.date() + timedelta(days=1), None, 1),
                ("VENCIDA", True, None, NOW.date() - timedelta(days=1), 1),
                ("INACTIVA", True, None, None, 2),
            ], 1):
                session.add(audience.Sucursal(sucursal_id=index, serie=str(index), sucursal=name,
                                             estado="BC", municipio="Tijuana", direccion="Test"))
                session.add(audience.SuiteSucursalRegionAssignmentORM(
                    sucursal_id=index, region_id=region, is_current=current, valid_from=start, valid_to=end))
            session.commit()
            assert {row.sucursal for row in audience.region_branches(region_id=1, today=NOW.date(), session=session)} == {"CENTRO", "NORTE"}
            assert audience.region_branches(region_id=2, today=NOW.date(), session=session) == []
            options = audience.campaign_options(allowed_sucursal_keys=("CENTRO",), session=session, now=NOW)
            assert options == {"branches": [{"key": "CENTRO", "label": "CENTRO"}],
                               "regions": [{"id": 1, "label": "Región", "branch_keys": ["CENTRO"]}]}
    finally:
        engine.dispose()


def test_v1_expired_deduplication_keeps_eligibility_rules(monkeypatch):
    rows = []
    for index, status, tariff_group in [(1, "CONTACT_HISTORY_UNKNOWN", "REACTIVATE"),
                                       (2, "CONTACT_HISTORY_UNKNOWN", "REACTIVATE"),
                                       (3, "EXCLUDED_ACTIVE", "REACTIVATE"),
                                       (4, "CONTACT_HISTORY_UNKNOWN", "EXCLUDE")]:
        rows.append({"vencido_row_id": index, "telefono": "6861000001" if index < 3 else f"686100000{index}",
                     "status": status, "reason": "NO_OUTBOUND_EVIDENCE", "operational_status": "AVAILABLE",
                     "tarifa_group": tariff_group})
    monkeypatch.setattr(service, "_build_marketing_reactivation_campaign_segment", lambda **k: {"rows": rows, "sources": {}})
    monkeypatch.setattr(service, "_read_last_suite_campaign_sent_at", lambda **k: {})
    result = service._build_campaign_plan(
        date_from="2026-08-01", date_to="2026-08-31", filters={"iventas_period_key": "TEST"},
        campaign_cooldown_days=None, allowed_sucursal_keys=None, session=None, now=NOW, deduplicate_phones=True,
    )
    assert len(result["eligible_rows"]) == 1
    assert result["summary"]["duplicate_phone"] == 1
    assert result["summary"]["excluded_active"] == 1
    assert result["summary"]["excluded_tariff"] == 1


@pytest.mark.parametrize("filters", [{"campaign_type": []}, {"campaign_type": "WINBACK", "segment": []}])
def test_malformed_campaign_parameters_return_validation_error(filters):
    with pytest.raises(service.MarketingReactivationValidationError):
        audience.prepare_v1_plan(filters=filters, allowed_sucursal_keys=None, session=None, now=NOW,
                                 active_builder=None, expired_builder=None)

def test_custom_active_reuses_active_builder(monkeypatch):
    calls = {}
    monkeypatch.setattr(audience, "exported_counts", lambda *a, **k: {})

    def active(**kwargs):
        calls.update(kwargs)
        return plan([{"phone_mx10": "6861000001"}])

    filters = {"campaign_type": "PERSONALIZADA", "universo": "ACTIVOS"}
    result = audience.prepare_v1_plan(
        filters=filters,
        allowed_sucursal_keys=("CENTRO",),
        session=None,
        now=NOW,
        active_builder=active,
        expired_builder=None,
    )

    assert calls["filters"] == {"campaign_type": "BASCULA_RETENCION", "sucursal": None}
    assert calls["allowed_sucursal_keys"] == ("CENTRO",)
    assert result["filters"] == filters
    assert result["summary"]["eligible"] == 1


def test_custom_expired_supports_open_ended_91_plus(monkeypatch):
    calls = {}
    monkeypatch.setattr(audience, "exported_counts", lambda *a, **k: {})

    def expired(**kwargs):
        calls.update(kwargs)
        return plan()

    filters = {"campaign_type": "PERSONALIZADA", "universo": "VENCIDOS", "dias_desde": 91}
    audience.prepare_v1_plan(
        filters=filters,
        allowed_sucursal_keys=("CENTRO",),
        session=NS(query=lambda *a: Query(NS(period_key="CANONICAL"))),
        now=NOW,
        active_builder=None,
        expired_builder=expired,
    )

    assert calls["date_from"] == date.min
    assert calls["date_to"] == NOW.date() - timedelta(days=91)
    assert calls["allowed_sucursal_keys"] == ("CENTRO",)


@pytest.mark.parametrize("filters", [
    {"campaign_type": "PERSONALIZADA"},
    {"campaign_type": "PERSONALIZADA", "universo": "OTRO"},
    {"campaign_type": "PERSONALIZADA", "universo": "ACTIVOS", "dias_desde": 1},
    {"campaign_type": "PERSONALIZADA", "universo": "VENCIDOS"},
    {"campaign_type": "PERSONALIZADA", "universo": "VENCIDOS", "dias_desde": 0},
    {"campaign_type": "PERSONALIZADA", "universo": "VENCIDOS", "dias_desde": 91, "dias_hasta": 90},
])
def test_custom_rejects_invalid_filters(monkeypatch, filters):
    monkeypatch.setattr(audience, "exported_counts", lambda *a, **k: {})
    with pytest.raises(service.MarketingReactivationValidationError):
        audience.prepare_v1_plan(
            filters=filters,
            allowed_sucursal_keys=None,
            session=None,
            now=NOW,
            active_builder=lambda **k: plan(),
            expired_builder=lambda **k: plan(),
        )