from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, text
from sqlalchemy.orm import Session

from app.models import MarketingReactivationCampaignORM, MarketingReactivationCampaignRecipientORM
from app.services import marketing_reactivation_service as service
from app.services import marketing_campaign_audience_service as audiences
from app.models.warehouse import SociosActivosSnapshotORM, SociosActivosSnapshotRowORM


NOW = datetime(2026, 9, 8, 18, tzinfo=timezone.utc)
FILTERS = {"campaign_type": "BASCULA_RETENCION"}


@pytest.fixture(autouse=True)
def isolated_frequency(monkeypatch, request):
    if request.node.name != "test_real_canonical_source_and_frozen_database_recipients":
        monkeypatch.setattr(audiences, "exported_counts", lambda *args, **kwargs: {})


def active(row_id=1, phone="686 100 0001", branch="CENTRO", tariff=None):
    return SimpleNamespace(
        id=row_id, telefono_raw=phone, nombre="Ana", sucursal_raw=branch,
        fecha_vencimiento_date=date(2026, 10, 8), tarifa=tariff,
    )


@pytest.fixture
def source(monkeypatch):
    snapshot = SimpleNamespace(id=23, cutoff_date=date(2026, 9, 8), rows=[active()])
    def resolve(**kwargs):
        assert kwargs["minimum_cutoff_date"] == date(2026, 9, 8)
        return snapshot
    monkeypatch.setattr(service, "resolve_latest_canonical_socios_activos_snapshot", resolve)
    def forbidden(**kwargs):
        pytest.fail("Báscula must not invoke the reactivation engine")
    monkeypatch.setattr(service, "_build_campaign_plan", forbidden)
    return snapshot


def preview(**kwargs):
    return service.preview_marketing_reactivation_campaign(
        filters=kwargs.pop("filters", FILTERS), now=NOW, session=object(), **kwargs,
    )


@pytest.mark.parametrize("tariff", [None, "DOMICILIADO", "ANUAL"])
def test_preview_includes_active_without_reactivation_tariff(source, tariff):
    source.rows[0].tarifa = tariff
    result = preview()
    assert result["summary"]["eligible"] == 1
    assert result["summary"]["excluded_active"] == 0
    assert result["summary"]["excluded_tariff"] == 0
    assert result["sources"]["activos_snapshot_id"] == 23
    assert result["filters"]["campaign_type"] == "BASCULA_RETENCION"


def test_deduplicates_normalized_phones_and_excludes_invalid(source):
    source.rows += [active(2, "+52 6861000001"), active(3, "123")]
    result = preview()["summary"]
    assert result["total_candidates"] == 3
    assert result["eligible"] == 1
    assert result["duplicate_phone"] == 1
    assert result["excluded_invalid_phone"] == 1


@pytest.mark.parametrize("scope,branch,count", [
    (None, None, 2), (("CENTRO",), None, 1),
    (("CENTRO", "NORTE"), " centro ", 1), ((), None, 0),
])
def test_branch_scope(source, scope, branch, count):
    source.rows += [active(2, "6861000002", "NORTE")]
    result = preview(filters={**FILTERS, "sucursal": branch}, allowed_sucursal_keys=scope)
    assert result["summary"]["eligible"] == count


def test_rejects_branch_outside_permission_before_reading_source(monkeypatch):
    def forbidden(**kwargs):
        pytest.fail("Unauthorized branch must be rejected before Warehouse access")
    monkeypatch.setattr(service, "resolve_latest_canonical_socios_activos_snapshot", forbidden)
    with pytest.raises(service.MarketingReactivationValidationError, match="alcance"):
        preview(filters={**FILTERS, "sucursal": "NORTE"}, allowed_sucursal_keys=("CENTRO",))


@pytest.mark.parametrize("extra", [{"tarifa": "ANUAL"}, {"iventas_period_key": "2026-09"}, {"region": "NORTE"}])
def test_rejects_unsupported_filters(extra):
    with pytest.raises(service.MarketingReactivationValidationError, match="Filtros no permitidos"):
        preview(filters={**FILTERS, **extra})


@pytest.mark.parametrize("extra", [{"date_from": "2026-09-01"}, {"date_to": "2026-09-08"}, {"campaign_cooldown_days": 7}])
def test_rejects_dates_and_cooldown(extra):
    with pytest.raises(service.MarketingReactivationValidationError, match="sucursal"):
        preview(**extra)


@pytest.mark.parametrize("cutoff", [None, date(2026, 9, 7), date(2026, 9, 9)])
def test_missing_or_noncurrent_source_is_explicit(monkeypatch, cutoff):
    monkeypatch.setattr(service, "resolve_latest_canonical_socios_activos_snapshot",
                        lambda **kwargs: None if cutoff is None else SimpleNamespace(cutoff_date=cutoff))
    with pytest.raises(service.MarketingReactivationValidationError, match="corte de hoy"):
        preview()


def test_business_date_uses_tijuana(monkeypatch):
    def resolve(**kwargs):
        assert kwargs["minimum_cutoff_date"] == date(2026, 9, 7)
        return SimpleNamespace(id=22, cutoff_date=date(2026, 9, 7), rows=[])
    monkeypatch.setattr(service, "resolve_latest_canonical_socios_activos_snapshot", resolve)
    result = service.preview_marketing_reactivation_campaign(
        filters=FILTERS, now=datetime(2026, 9, 8, 1, tzinfo=timezone.utc), session=object(),
    )
    assert result["sources"]["date_from"] == "2026-09-07"


def test_create_freezes_active_recipient_and_auditable_source(source):
    class WriteSession:
        def __init__(self):
            self.added = []
            self.commits = 0
        def add(self, row):
            row.id = len(self.added) + 1
            self.added.append(row)
        def flush(self):
            pass
        def commit(self):
            self.commits += 1
        def rollback(self):
            pytest.fail("Unexpected rollback")
    session = WriteSession()
    result = service.create_marketing_reactivation_campaign(
        name="Báscula septiembre", filters=FILTERS, created_by_user_id=1,
        allowed_sucursal_keys=("CENTRO",), session=session, now=NOW,
    )
    campaign, recipient = session.added
    assert isinstance(campaign, MarketingReactivationCampaignORM)
    assert isinstance(recipient, MarketingReactivationCampaignRecipientORM)
    assert session.commits == 1
    assert result["recipient_count"] == 1
    assert result["status"] == "DRAFT"
    assert campaign.filters_json["campaign_type"] == "BASCULA_RETENCION"
    assert campaign.filters_json["sources"]["activos_snapshot_id"] == 23
    assert campaign.filters_json["scope"]["allowed_sucursal_keys"] == ["CENTRO"]
    assert recipient.socios_vencidos_cartera_id is None
    assert recipient.fecha_vencimiento_date == date(2026, 10, 8)
    assert recipient.operational_status == "ACTIVE"
    assert recipient.phone_mx10 == "6861000001"
    source.rows[0].nombre = "Nombre cambiado"
    detail = service._serialize_campaign_recipient(recipient)
    assert detail["member_name"] == "Ana"
    assert detail["socios_vencidos_cartera_id"] is None


def test_empty_audience_cannot_create(source):
    source.rows = [active(phone="123")]
    with pytest.raises(service.MarketingReactivationValidationError, match="elegibles"):
        service.create_marketing_reactivation_campaign(
            name="Vacía", filters=FILTERS, created_by_user_id=1, session=object(), now=NOW,
        )


def test_real_canonical_source_and_frozen_database_recipients(monkeypatch):
    engine = create_engine("sqlite://")
    metadata = MetaData()
    for name in ("users", "warehouse_uploads", "socios_vencidos_cartera"):
        Table(name, metadata, Column("id", Integer, primary_key=True))
    for model in (SociosActivosSnapshotORM, SociosActivosSnapshotRowORM,
                  MarketingReactivationCampaignORM, MarketingReactivationCampaignRecipientORM):
        table = model.__table__.to_metadata(metadata)
        # SQLite auto-increments only INTEGER primary keys.
        table.c.id.type = Integer()
    with engine.begin() as connection:
        connection.connection.create_function("btrim", 1, lambda value: value.strip() if value else value,
                                              deterministic=True)
        connection.execute(text("PRAGMA foreign_keys=ON"))
        metadata.create_all(connection)
        connection.execute(metadata.tables["users"].insert(), {"id": 1})
        connection.execute(metadata.tables["warehouse_uploads"].insert(), [{"id": 1}, {"id": 2}])
    # User serialization is covered separately; FK targets here are minimal.
    monkeypatch.setattr(service, "serialize_marketing_reactivation_campaign", lambda row: {"id": row.id})
    try:
        with Session(engine) as session:
            for snapshot_id, canonical in ((1, True), (2, False)):
                snapshot = SociosActivosSnapshotORM(
                    id=snapshot_id, warehouse_upload_id=snapshot_id, report_type_key="socios_activos",
                    cutoff_date=NOW.date(), captured_at=NOW, snapshot_kind="daily",
                    is_canonical=canonical, row_count_detected=3, row_count_valid=3,
                    row_count_rejected=0, created_at=NOW, updated_at=NOW,
                )
                for index, branch in enumerate(("CENTRO", "CENTRO", "NORTE"), 1):
                    snapshot.rows.append(SociosActivosSnapshotRowORM(
                        row_index=index, id_socio=str(index), pin=str(index), nombre="Ana",
                        sucursal_raw=branch, telefono_raw=("6861000001" if canonical else "6861000099"),
                        fecha_vencimiento_local=datetime(2026, 10, 8), fecha_vencimiento_date=date(2026, 10, 8),
                        aplica_kpi_raw="SI", aplica_kpi=True, row_hash=str(index) * 64,
                        created_at=NOW, updated_at=NOW,
                    ))
                session.add(snapshot)
            session.commit()
            result = service.preview_marketing_reactivation_campaign(
                filters=FILTERS, allowed_sucursal_keys=("CENTRO",), session=session, now=NOW,
            )
            assert result["sources"]["activos_snapshot_id"] == 1
            assert result["summary"]["total_candidates"] == 2
            assert result["summary"]["eligible"] == 1
            result = service.create_marketing_reactivation_campaign(
                name="Báscula", filters=FILTERS, allowed_sucursal_keys=("CENTRO",),
                created_by_user_id=1, session=session, now=NOW,
            )
            session.expunge_all()
            campaign = session.get(MarketingReactivationCampaignORM, result["id"])
            assert campaign.filters_json["campaign_type"] == "BASCULA_RETENCION"
            assert len(campaign.recipients) == 1
            recipient = campaign.recipients[0]
            assert recipient.phone_mx10 == "6861000001"
            assert recipient.socios_vencidos_cartera_id is None
            assert recipient.operational_status == "ACTIVE"
            source_row = session.query(SociosActivosSnapshotRowORM).first()
            source_row.nombre = "Nombre modificado"
            session.commit()
            assert recipient.member_name == "Ana"
    finally:
        engine.dispose()
