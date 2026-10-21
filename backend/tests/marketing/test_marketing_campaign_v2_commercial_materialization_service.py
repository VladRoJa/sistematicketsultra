from __future__ import annotations

from contextlib import nullcontext
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import BigInteger, Column, MetaData, Table, create_engine
from sqlalchemy.orm import Session

from app.models.marketing import MarketingCampaignV2CommercialResultORM
from app.services import marketing_campaign_v2_commercial_materialization_service as service


NOW = datetime(2026, 10, 21, 23, 0, tzinfo=timezone.utc)


class Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def join(self, *args):
        return self

    def yield_per(self, *args):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class ReadSession:
    def __init__(self, *query_results):
        self.query_results = iter(query_results)
        self.queries = 0
        self.no_autoflush = nullcontext()

    def query(self, *args):
        self.queries += 1
        return Query(next(self.query_results))


def _child(child_id, branch_id, channel, phone):
    return SimpleNamespace(
        id=child_id,
        campaign_v2_id=8,
        provider="IVENTAS",
        status="SUBMITTED",
        sucursal_id=branch_id,
        provider_campaign_id=f"external-{child_id}",
        submitted_at=NOW,
        submit_started_at=None,
        provider_channel_id=channel,
        recipient_count=1,
        request_snapshot_json={
            "provider_channel_id": channel,
            "leads": [{"phone": f"521{phone}"}],
        },
    )


def _sale(identifier, phone, branch, amount, *, order, time="18:00:00",
          status="ACTIVO", description="CONVENIOS $549"):
    return SimpleNamespace(
        id=identifier,
        snapshot_id=300,
        telefono=phone,
        sucursal=branch,
        estatus=status,
        descripcion=description,
        total=Decimal(str(amount)),
        fecha="2026-10-21",
        hora=time,
        id_orden=order,
        folio=f"F-{identifier}",
        clave_producto="MEMBRESIA",
        tipo="CONTRATO",
    )


def _source_session(*, incomplete=False):
    children = [
        _child(80, 16, "channel-a", "6861000001"),
        _child(81, 17, "channel-b", "6641000002"),
    ]
    recipients = [
        SimpleNamespace(id=801, campaign_id=8, phone_mx10="6861000001"),
        SimpleNamespace(id=802, campaign_id=8, phone_mx10="6641000002"),
    ]
    snapshots = [
        SimpleNamespace(
            id=180, provider_campaign_id="external-80", analytics_status="ok",
            raw_successful=1, fetched_at=NOW,
        ),
        SimpleNamespace(
            id=181, provider_campaign_id="external-81", analytics_status="ok",
            raw_successful=1, fetched_at=NOW,
        ),
    ]
    if incomplete:
        snapshots = snapshots[:1]
    observations = [
        (180, 801, "mx10:6861000001"),
        (181, 802, "mx10:6641000002"),
    ]
    canonical = SimpleNamespace(id=300, business_date=date(2026, 10, 21))
    aliases = [
        (
            SimpleNamespace(raw_branch_name="AZAHARES"),
            SimpleNamespace(sucursal_id=16),
        ),
        (
            SimpleNamespace(raw_branch_name="BRANCH B"),
            SimpleNamespace(sucursal_id=17),
        ),
    ]
    sales = [
        _sale(1, "6861000001", "AZAHARES", "549", order="A"),
        _sale(2, "6861000001", "AZAHARES", "-50", order="A"),
        _sale(3, "6641000002", "BRANCH B", "649", order="B"),
        _sale(4, "6641000002", "BRANCH B", "200", order="C",
              description="PENALIZACION"),
        _sale(5, "6861000001", "BRANCH B", "549", order="D"),
    ]
    if incomplete:
        return ReadSession(children, recipients, snapshots)
    return ReadSession(children, recipients, snapshots, observations,
                       [canonical], aliases, sales)


def test_multichild_worker_joins_proven_iventas_to_one_gasca_cut():
    session = _source_session()
    result = service.reconcile_multichild_campaign(
        campaign_id=8, session=session,
    )
    assert session.queries == 7
    assert result["status"] == "READY"
    assert result["submitted_child_ids"] == [80, 81]
    assert result["provider_snapshot_ids"] == [180, 181]
    assert result["venta_total_snapshot_id"] == 300
    assert result["successful_recipient_count"] == 2
    assert result["buyers_attributed"] == 2
    assert result["transactions_attributed"] == 2
    assert result["revenue_attributed_mxn"] == "1148.00"


def test_multichild_worker_missing_provider_snapshot_is_pending_not_zero():
    session = _source_session(incomplete=True)
    result = service.reconcile_multichild_campaign(
        campaign_id=8, session=session,
    )
    assert session.queries == 3
    assert result["status"] == "NO_PROVIDER_SNAPSHOT"
    assert result["buyers_attributed"] is None
    assert result["revenue_attributed_mxn"] is None


def test_multichild_materialized_cycle_upserts_and_rotates(monkeypatch):
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table(
        "marketing_campaign_v2_campaigns", metadata,
        Column("id", BigInteger, primary_key=True),
    )
    child_table = Table(
        "marketing_campaign_v2_provider_campaigns", metadata,
        Column("id", BigInteger, primary_key=True),
        Column("campaign_v2_id", BigInteger),
    )
    MarketingCampaignV2CommercialResultORM.__table__.to_metadata(metadata)
    metadata.create_all(engine)
    with Session(engine) as session:
        session.execute(child_table.insert(), [
            {"id": 80, "campaign_v2_id": 8},
            {"id": 81, "campaign_v2_id": 8},
            {"id": 90, "campaign_v2_id": 9},
            {"id": 91, "campaign_v2_id": 9},
        ])
        session.commit()

        checked = []

        def fake_reconcile(*, campaign_id, session):
            checked.append(campaign_id)
            return {
                "campaign_id": campaign_id,
                "status": "READY" if campaign_id == 8 else "NO_PROVIDER_SNAPSHOT",
                "buyers_attributed": 2 if campaign_id == 8 else None,
                "transactions_attributed": 2 if campaign_id == 8 else None,
                "revenue_attributed_mxn": "1198.00" if campaign_id == 8 else None,
            }

        monkeypatch.setattr(service, "reconcile_multichild_campaign", fake_reconcile)

        first = service.run_multichild_commercial_materialization_cycle(
            now=NOW, max_campaigns=1, session=session,
        )
        second = service.run_multichild_commercial_materialization_cycle(
            now=NOW, max_campaigns=1, session=session,
        )

        assert checked == [9, 8]
        assert first["selected"] == second["selected"] == 1
        assert first["pending"] == 1
        assert second["ready"] == 1
        assert session.get(MarketingCampaignV2CommercialResultORM, 9).result_json[
            "revenue_attributed_mxn"
        ] is None
        assert session.get(MarketingCampaignV2CommercialResultORM, 8).result_json[
            "revenue_attributed_mxn"
        ] == "1198.00"
    engine.dispose()
