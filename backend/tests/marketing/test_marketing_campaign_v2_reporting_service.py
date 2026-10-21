from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import BigInteger, Column, Integer, MetaData, Table, create_engine, event
from sqlalchemy.orm import Session

from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2ProviderRecipientObservationORM,
    MarketingCampaignV2ProviderStatsSnapshotORM,
    MarketingCampaignV2RecipientEvidenceORM,
    MarketingCampaignV2RecipientORM,
)
from app.services.marketing_campaign_v2_query_service import (
    MarketingCampaignV2NotFoundError,
)
from app.services.marketing_campaign_v2_reporting_cost_service import (
    extract_campaign_cost_projection,
)
from app.services.marketing_campaign_v2_reporting_service import (
    build_campaign_v2_individual_report,
)


BASE = datetime(2026, 10, 1, 18, 0, tzinfo=timezone.utc)


def _definition(scope):
    return {
        "filters": {"allowed_sucursal_keys": scope},
        "preview": {
            "fingerprint": "freeze",
            "fingerprint_version": "campaign-v2-freeze-v1",
        },
    }


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    Table(
        "socios_vencidos_cartera",
        metadata,
        Column("id", BigInteger, primary_key=True),
    )
    Table(
        "socios_activos_snapshot_rows",
        metadata,
        Column("id", BigInteger, primary_key=True),
    )
    Table(
        "socios_activos_snapshots",
        metadata,
        Column("id", BigInteger, primary_key=True),
    )
    MarketingCampaignV2ORM.__table__.to_metadata(metadata)
    MarketingCampaignV2RecipientORM.__table__.to_metadata(metadata)
    MarketingCampaignV2RecipientEvidenceORM.__table__.to_metadata(metadata)
    MarketingCampaignV2ProviderStatsSnapshotORM.__table__.to_metadata(metadata)
    MarketingCampaignV2ProviderRecipientObservationORM.__table__.to_metadata(
        metadata
    )
    metadata.create_all(engine)

    with Session(engine) as value:
        value.add_all(
            [
                _campaign(1, "Reportable", ["BRANCH A"]),
                _campaign(2, "Zero recipients", ["BRANCH A"]),
                _campaign(3, "No snapshot", ["BRANCH A"]),
                _campaign(4, "Outside", ["BRANCH B"]),
            ]
        )
        value.add_all(
            [
                _recipient(10, 1, "6861111111", "BRANCH A", "DOMICILIADO"),
                _recipient(11, 1, "6862222222", "BRANCH A", "DOMICILIADO"),
                _recipient(12, 1, "6863333333", "BRANCH A", "CONVENIO"),
                _recipient(13, 1, "6864444444", None, None),
                _recipient(14, 1, "6865555555", None, None),
                _recipient(30, 3, "6867777777", "BRANCH A", "TRIMESTRAL"),
                _recipient(31, 3, "6868888888", "BRANCH A", "TRIMESTRAL"),
            ]
        )
        value.flush()
        value.add(
            MarketingCampaignV2RecipientEvidenceORM(
                id=1,
                recipient_id=14,
                evidence_order=0,
                source="EXPIRED_MEMBERS",
                phone_raw="6865555555",
                phone_mx10="6865555555",
                sucursal="Branch A",
                sucursal_key="BRANCH A",
                audience_family="SEMESTRE",
                evidence_json=[],
                created_at=BASE,
            )
        )

        old = _snapshot(
            99,
            campaign_id=1,
            fetched_at=BASE,
            fingerprint="9" * 64,
            raw=(2, 1, 1, 1, 0, 0, 0, 0),
            coverage=(3, 0, 2),
            analytics={"responders": 4, "interactions": {"freeText": 1}},
        )
        tie_lower = _snapshot(
            100,
            campaign_id=1,
            fetched_at=BASE + timedelta(hours=1),
            fingerprint="a" * 64,
            raw=(4, 2, 2, 1, 1, 3, 1, 5),
            coverage=(4, 1, 1),
            analytics={"responders": 70, "interactions": {"freeText": 15}},
        )
        latest = _snapshot(
            101,
            campaign_id=1,
            fetched_at=BASE + timedelta(hours=1),
            fingerprint="b" * 64,
            raw=(6, 2, 2, 2, 2, 7, 1, 4),
            coverage=(4, 1, 1),
            analytics={
                "responders": 79,
                "interactions": {"freeText": 16},
                "cost": {},
            },
            button_interactions=[
                {
                    "label": "INFORMACION",
                    "raw_item_count": 4,
                    "recipient_phones": [
                        "mx10:6863333333",
                        "mx10:6869999999",
                    ],
                }
            ],
        )
        value.add_all([old, tie_lower, latest])
        value.flush()

        value.add_all(
            [
                _obs(99, "mx10:6861111111", 10, "SUCCESSFUL", "SENT"),
                _obs(99, "mx10:6862222222", 11, "SUCCESSFUL", "DELIVERED"),
                _obs(99, "mx10:6864444444", 13, "FAILED", None),
                _obs(100, "mx10:6861111111", 10, "SUCCESSFUL", "SENT"),
                _obs(100, "mx10:6862222222", 11, "SUCCESSFUL", "DELIVERED"),
                _obs(100, "mx10:6863333333", 12, "SUCCESSFUL", "VIEWED"),
                _obs(100, "mx10:6864444444", 13, "FAILED", None),
                _obs(100, "mx10:6869999999", None, "FAILED", None),
                _obs(101, "mx10:6861111111", 10, "SUCCESSFUL", "SENT"),
                _obs(101, "mx10:6862222222", 11, "SUCCESSFUL", "DELIVERED"),
                _obs(
                    101,
                    "mx10:6863333333",
                    12,
                    "SUCCESSFUL",
                    "VIEWED",
                    ["INFORMACION"],
                ),
                _obs(101, "mx10:6864444444", 13, "FAILED", None),
                _obs(
                    101,
                    "mx10:6869999999",
                    None,
                    "FAILED",
                    None,
                    ["INFORMACION"],
                ),
            ]
        )
        value.commit()
        yield value

    engine.dispose()


def _campaign(campaign_id, name, scope):
    return MarketingCampaignV2ORM(
        id=campaign_id,
        name=name,
        purpose="REACTIVATION",
        source="EXPIRED_MEMBERS",
        provider="IVENTAS",
        provider_campaign_id=f"external-{campaign_id}",
        audience_definition_json=_definition(scope),
        frozen_at=BASE,
        created_at=BASE,
        updated_at=BASE,
    )


def _recipient(recipient_id, campaign_id, phone, branch, family):
    return MarketingCampaignV2RecipientORM(
        id=recipient_id,
        campaign_id=campaign_id,
        phone_mx10=phone,
        source="EXPIRED_MEMBERS",
        sucursal=branch,
        audience_family=family,
        created_at=BASE,
    )


def _snapshot(
    snapshot_id,
    *,
    campaign_id,
    fetched_at,
    fingerprint,
    raw,
    coverage,
    analytics,
    button_interactions=None,
):
    (
        successful,
        failed,
        sent,
        delivered,
        viewed,
        answered,
        interaction_groups,
        interaction_items,
    ) = raw
    matched, unmatched, without_status = coverage
    return MarketingCampaignV2ProviderStatsSnapshotORM(
        id=snapshot_id,
        campaign_v2_id=campaign_id,
        provider="IVENTAS",
        provider_campaign_id=f"external-{campaign_id}",
        analytics_status="ok",
        fetched_at=fetched_at,
        raw_successful=successful,
        raw_failed=failed,
        raw_sent=sent,
        raw_delivered=delivered,
        raw_viewed=viewed,
        raw_answered=answered,
        raw_interaction_groups=interaction_groups,
        raw_interaction_items=interaction_items,
        analytics_json=analytics,
        button_interactions_json=button_interactions or [],
        provider_recipient_count=matched + unmatched,
        matched_recipient_count=matched,
        unmatched_provider_count=unmatched,
        frozen_recipient_without_provider_status_count=without_status,
        fingerprint=fingerprint,
        created_at=fetched_at,
    )


def _obs(
    snapshot_id,
    phone,
    recipient_id,
    outcome,
    delivery_bucket,
    labels=None,
):
    return MarketingCampaignV2ProviderRecipientObservationORM(
        snapshot_id=snapshot_id,
        normalized_phone=phone,
        campaign_recipient_id=recipient_id,
        outcome=outcome,
        delivery_bucket=delivery_bucket,
        button_labels_json=labels or [],
        created_at=BASE,
    )


def _report(session, campaign_id=1, scope=("BRANCH A",)):
    return build_campaign_v2_individual_report(
        campaign_id=campaign_id,
        allowed_sucursal_keys=scope,
        session=session,
    )


def test_latest_snapshot_uses_fetched_at_then_higher_id(session):
    report = _report(session)

    assert report["observation"] == {
        "snapshot_id": 101,
        "latest_observed_at": (BASE + timedelta(hours=1)).isoformat(),
        "analytics_status": "ok",
        "fingerprint": "b" * 64,
    }


def test_frozen_denominator_normalized_rates_coverage_and_unmatched(session):
    report = _report(session)

    assert report["audience"]["total_recipients"] == 5
    assert report["normalized"] == {
        "successful": 3,
        "failed": 1,
        "sent": 1,
        "delivered": 1,
        "viewed": 1,
        "reach_count": 2,
    }
    assert report["rates"] == {
        "successful_rate": 0.6,
        "reach_rate": 0.4,
        "read_rate": 0.5,
        "failure_rate": 0.2,
    }
    assert report["coverage"] == {
        "matched_recipient_count": 4,
        "unmatched_provider_count": 1,
        "frozen_recipient_without_provider_status_count": 1,
        "status_coverage_rate": 0.8,
    }
    assert (
        report["normalized"]["successful"] + report["normalized"]["failed"]
        < report["audience"]["total_recipients"]
    )


def test_provider_raw_remains_separate_from_normalized(session):
    report = _report(session)

    assert report["provider_raw"] == {
        "successful": 6,
        "failed": 2,
        "sent": 2,
        "delivered": 2,
        "viewed": 2,
        "answered": 7,
        "interaction_groups": 1,
        "interaction_items": 4,
    }
    assert report["provider_raw"]["successful"] != report["normalized"]["successful"]
    assert report["provider_raw"]["failed"] != report["normalized"]["failed"]


def test_button_interactions_separate_raw_items_and_unique_frozen_recipients(session):
    report = _report(session)

    assert report["interactions"]["unique_button_recipients"] == 1
    assert report["interactions"]["button_groups"] == [
        {
            "label": "INFORMACION",
            "unique_recipient_count": 1,
            "raw_item_count": 4,
        }
    ]




def test_duplicate_button_groups_sum_raw_items_without_duplicate_recipient(session):
    latest = session.get(MarketingCampaignV2ProviderStatsSnapshotORM, 101)
    latest.button_interactions_json = [
        {
            "label": "INFORMACION",
            "raw_item_count": 4,
            "recipient_phones": ["mx10:6863333333"],
        },
        {
            "label": "INFORMACION",
            "raw_item_count": 2,
            "recipient_phones": ["mx10:6863333333"],
        },
    ]
    latest.raw_interaction_groups = 2
    latest.raw_interaction_items = 6
    session.commit()

    report = _report(session)

    assert report["interactions"]["unique_button_recipients"] == 1
    assert report["interactions"]["button_groups"] == [
        {
            "label": "INFORMACION",
            "unique_recipient_count": 1,
            "raw_item_count": 6,
        }
    ]


def test_analytics_aggregates_and_cost_unavailable(session):
    report = _report(session)

    assert report["interactions"]["responders_aggregate"] == 79
    assert report["interactions"]["free_text_aggregate"] == 16
    assert report["cost"] == {
        "status": "unavailable",
        "currency": None,
        "total": None,
    }


@pytest.mark.parametrize(
    "analytics",
    [
        None,
        {},
        {"cost": {}},
        {"cost": {"currency": "MXN", "real": {"total": 100}}},
    ],
)
def test_cost_projection_never_invents_unsupported_fields(analytics):
    assert extract_campaign_cost_projection(analytics) == {
        "status": "unavailable",
        "currency": None,
        "total": None,
    }


def test_malformed_analytics_are_null_not_zero(session):
    latest = session.get(MarketingCampaignV2ProviderStatsSnapshotORM, 101)
    latest.analytics_json = {
        "responders": "79",
        "interactions": {"freeText": False},
        "cost": {},
    }
    session.commit()

    report = _report(session)

    assert report["interactions"]["responders_aggregate"] is None
    assert report["interactions"]["free_text_aggregate"] is None


def test_evolution_uses_each_snapshot_state_and_deterministic_order(session):
    report = _report(session)

    assert [row["snapshot_id"] for row in report["evolution"]] == [99, 100, 101]
    assert report["evolution"][0]["normalized"] == {
        "successful": 2,
        "failed": 1,
        "sent": 1,
        "delivered": 1,
        "viewed": 0,
        "reach_count": 1,
    }
    assert report["evolution"][2]["normalized"] == report["normalized"]
    assert report["evolution"][2]["observed_at"] == (
        BASE + timedelta(hours=1)
    ).isoformat()


def test_dimensions_use_frozen_scope_and_evidence_without_proration(session):
    report = _report(session)

    assert report["dimensions"]["scope"] == {
        "is_global": False,
        "allowed_sucursal_keys": ["BRANCH A"],
    }
    assert report["dimensions"]["branches"] == [
        {"value": "BRANCH A", "recipient_count": 4},
        {"value": "UNKNOWN", "recipient_count": 1},
    ]
    assert report["dimensions"]["audience_families"] == [
        {"value": "CONVENIO", "recipient_count": 1},
        {"value": "DOMICILIADO", "recipient_count": 2},
        {"value": "SEMESTRE", "recipient_count": 1},
        {"value": "UNKNOWN", "recipient_count": 1},
    ]


def test_campaign_without_snapshot_is_valid_and_does_not_complete_from_provider(session):
    report = _report(session, campaign_id=3)

    assert report["audience"]["total_recipients"] == 2
    assert report["observation"] == {
        "snapshot_id": None,
        "latest_observed_at": None,
        "analytics_status": None,
        "fingerprint": None,
    }
    assert report["normalized"] == {
        "successful": 0,
        "failed": 0,
        "sent": 0,
        "delivered": 0,
        "viewed": 0,
        "reach_count": 0,
    }
    assert report["rates"] == {
        "successful_rate": 0.0,
        "reach_rate": 0.0,
        "read_rate": None,
        "failure_rate": 0.0,
    }
    assert report["coverage"] == {
        "matched_recipient_count": 0,
        "unmatched_provider_count": 0,
        "frozen_recipient_without_provider_status_count": 2,
        "status_coverage_rate": 0.0,
    }
    assert report["provider_raw"] is None
    assert report["evolution"] == []


def test_zero_recipient_campaign_has_null_denominator_rates(session):
    report = _report(session, campaign_id=2)

    assert report["audience"]["total_recipients"] == 0
    assert report["rates"] == {
        "successful_rate": None,
        "reach_rate": None,
        "read_rate": None,
        "failure_rate": None,
    }
    assert report["coverage"]["status_coverage_rate"] is None


def test_campaign_outside_scope_is_not_found(session):
    with pytest.raises(MarketingCampaignV2NotFoundError):
        _report(session, campaign_id=4, scope=("BRANCH A",))


def test_same_persisted_state_produces_same_report(session):
    assert _report(session) == _report(session)


def test_reporting_never_calls_provider_readthrough_or_capture(session):
    with (
        patch(
            "app.services.marketing_campaign_v2_provider_stats_service."
            "get_campaign_v2_provider_stats",
            side_effect=AssertionError("Reporting must not call provider"),
        ),
        patch(
            "app.services.marketing_campaign_v2_provider_stats_snapshot_service."
            "capture_campaign_v2_provider_stats_snapshot",
            side_effect=AssertionError("Reporting must not capture provider"),
        ),
    ):
        report = _report(session)

    assert report["observation"]["snapshot_id"] == 101


def test_individual_report_uses_bulk_query_pattern_without_n_plus_one(session):
    statements = []

    def before_cursor_execute(
        _conn,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ):
        statements.append(statement)

    event.listen(
        session.get_bind(),
        "before_cursor_execute",
        before_cursor_execute,
    )
    try:
        report = _report(session)
    finally:
        event.remove(
            session.get_bind(),
            "before_cursor_execute",
            before_cursor_execute,
        )

    assert report["audience"]["total_recipients"] == 5
    assert len(statements) <= 5


def test_commercial_attribution_simple_rule_successful_not_failed():
    """Azahares: 549 and 649 count, failed 399, passes and penalties do not."""
    from datetime import datetime
    from decimal import Decimal
    from types import SimpleNamespace
    from zoneinfo import ZoneInfo

    from app.services.marketing_campaign_v2_reporting_service import (
        _summarize_campaign_v2_membership_movements,
    )

    def sale(
        identifier, phone, product, total, *,
        when="18:47:00", status="ACTIVO", branch="AZAHARES CULIACAN",
        order=None, pin="PIN-OTHER", clave="MEMBRESIA",
    ):
        return SimpleNamespace(
            id=identifier, telefono=phone, sucursal=branch,
            estatus=status, descripcion=product, total=Decimal(str(total)),
            fecha="2026-10-20", hora=when,
            id_orden=order or f"ORDER-{identifier}",
            folio=f"FOLIO-{identifier}", pin=pin,
            clave_producto=clave, tipo="CONTRATO",
        )

    rows = [
        sale(1, "6861000001", "CONVENIOS $549", "549", when="18:47:00"),
        sale(2, "6861000002", "DOMICILIADO 6 MESES $399 JULIO", "399"),
        sale(3, "5216861000003", "RECURRENTE $649 LE", "649"),
        sale(4, "6861000001", "PENALIZACION PAGO", "100"),
        sale(5, "6861000001", "PASE GYMPASS", "0"),
        sale(6, "6861000001", "CONVENIOS $549", "549", when="15:59:00"),
        sale(7, "6861000001", "CONVENIOS $549", "549", branch="OTRA SUCURSAL"),
        sale(8, "6861000001", "CONVENIOS $549", "549", status="CANCELADO"),
    ]
    result = _summarize_campaign_v2_membership_movements(
        rows=rows,
        sent_local=datetime(2026, 10, 20, 16, 0, 53, tzinfo=ZoneInfo("America/Tijuana")),
        successful_phones={"6861000001", "6861000003"},
        branch_id=16,
        alias_map={"AZAHARES CULIACAN": 16, "OTRA SUCURSAL": 17},
    )
    assert result == {
        "buyers_attributed": 2,
        "transactions_attributed": 2,
        "revenue_attributed_mxn": "1198.00",
    }


def test_commercial_attribution_groups_invoice_lines_once():
    from datetime import datetime
    from decimal import Decimal
    from types import SimpleNamespace
    from zoneinfo import ZoneInfo

    from app.services.marketing_campaign_v2_reporting_service import (
        _summarize_campaign_v2_membership_movements,
    )

    def line(identifier, order, amount, description="CONVENIOS $549"):
        return SimpleNamespace(
            id=identifier, telefono="6861000001", sucursal="AZAHARES CULIACAN",
            estatus="ACTIVO", descripcion=description,
            total=Decimal(str(amount)), fecha="2026-10-21",
            hora="06:00:00", id_orden=order, folio="FOLIO-1",
            clave_producto="MEMBRESIA", tipo="CONTRATO",
        )

    result = _summarize_campaign_v2_membership_movements(
        rows=[
            line(1, "A", 549),
            line(2, "A", -50),
            line(3, "B", 399, "DOMICILIADO $399"),
            line(4, "C", -200),
            line(5, "D", 0, "PASE RECORRIDO"),
        ],
        sent_local=datetime(2026, 10, 20, 16, 0, 53, tzinfo=ZoneInfo("America/Tijuana")),
        successful_phones={"6861000001"},
        branch_id=16,
        alias_map={"AZAHARES CULIACAN": 16},
    )
    assert result == {
        "buyers_attributed": 1,
        "transactions_attributed": 2,
        "revenue_attributed_mxn": "898.00",
    }


def test_commercial_attribution_batch_validation_rejects_bad_ids():
    from app.services.marketing_campaign_v2_reporting_service import (
        MarketingCampaignV2ReportingValidationError,
        _validate_commercial_batch_ids,
    )

    for bad in ([], [True], ["26"], [0], [-1], [26, 26], list(range(1, 102)), None):
        with pytest.raises(MarketingCampaignV2ReportingValidationError):
            _validate_commercial_batch_ids(bad)
    assert _validate_commercial_batch_ids([27, 26]) == (27, 26)


def test_commercial_attribution_batch_is_scoped_and_has_constant_query_count(monkeypatch):
    from contextlib import nullcontext
    from datetime import date
    from decimal import Decimal
    from app.services.marketing_campaign_v2_reporting_service import (
        build_campaign_v2_commercial_attribution_batch,
    )
    import app.services.marketing_sales_funnel_service as funnel

    class Query:
        def __init__(self, values):
            self.values = values

        def filter(self, *args):
            return self

        def join(self, *args):
            return self

        def order_by(self, *args):
            return self

        def yield_per(self, *args):
            return self

        def all(self):
            return self.values

        def __iter__(self):
            return iter(self.values)

    class FakeSession:
        def __init__(self, data):
            self.data = iter(data)
            self.queries = 0
            self.no_autoflush = nullcontext()

        def query(self, *args):
            self.queries += 1
            return Query(next(self.data))

    def campaign(identifier, scope="AZAHARES CUL"):
        return SimpleNamespace(
            id=identifier,
            audience_definition_json={
                "filters": {"allowed_sucursal_keys": [scope]}
            },
        )

    when = datetime(2026, 10, 20, 23, 0, 53, tzinfo=timezone.utc)

    def child(identifier, provider, submitted=when):
        return SimpleNamespace(
            campaign_v2_id=identifier, provider_campaign_id=provider,
            submitted_at=submitted, sucursal_id=16,
        )

    def sale(identifier, phone, product, amount):
        return SimpleNamespace(
            id=identifier, snapshot_id=3332, telefono=phone,
            sucursal="AZAHARES CUL", estatus="ACTIVO",
            descripcion=product, total=Decimal(amount),
            fecha="2026-10-21", hora="10:27:00",
            clave_producto="MEMBRESIA", tipo="CONTRATO",
            id_orden=f"ORDER-{identifier}", folio=f"FOLIO-{identifier}",
        )

    session = FakeSession([
        # 1. Campaign visibility in ONE query, not one per campaign.
        [campaign(i) for i in (26, 27, 28, 29, 30)],
        # 2. All child records for requested campaigns.
        [child(26, "provider-26"), child(28, "p-28a"),
         child(28, "p-28b"), child(29, "provider-29"),
         child(30, None, None)],
        # 3. Provider snapshots.
        [SimpleNamespace(
            id=1, campaign_v2_id=26, provider_campaign_id="provider-26",
            fetched_at=when,
        )],
        # 4. One later canonical month-cut.
        [SimpleNamespace(
            id=3332, business_date=date(2026, 10, 21),
            captured_at=datetime(2026, 10, 21, 18, 0, tzinfo=timezone.utc),
        )],
        # 5. Already filtered SUCCESSFUL+joined recipient observations.
        [(1, 26, "6861111111"), (1, 26, "6863333333")],
        # 6. Sales read once for the page, including an unrelated failure.
        [sale(1, "6861111111", "CONVENIOS $549", "549"),
         sale(2, "6862222222", "DOMICILIADO $399", "399"),
         sale(3, "6863333333", "RECURRENTE $649 LE", "649")],
    ])
    monkeypatch.setattr(
        funnel, "_load_branch_alias_map",
        lambda: {"AZAHARES CUL": 16},
    )

    result = build_campaign_v2_commercial_attribution_batch(
        campaign_ids=[27, 26, 28, 29, 30],
        allowed_sucursal_keys=None,
        session=session,
    )
    assert session.queries == 6  # Constant read count for a whole page.
    rows = result["rows"]
    assert [r["campaign_id"] for r in rows] == [27, 26, 28, 29, 30]
    assert [r["status"] for r in rows] == [
        "UNSUPPORTED_MULTICHILD_OR_UNSENT", "READY",
        "UNSUPPORTED_MULTICHILD_OR_UNSENT", "NO_PROVIDER_SNAPSHOT",
        "NOT_SUBMITTED",
    ]
    assert rows[1]["buyers_attributed"] == 2
    assert rows[1]["transactions_attributed"] == 2
    assert rows[1]["revenue_attributed_mxn"] == "1198.00"
    assert rows[1]["successful_recipient_count"] == 2
    assert all(r["revenue_attributed_mxn"] is None for i, r in enumerate(rows) if i != 1)

    denied_session = FakeSession([[campaign(26, "AZAHARES CUL")]])
    with pytest.raises(MarketingCampaignV2NotFoundError):
        build_campaign_v2_commercial_attribution_batch(
            campaign_ids=[26],
            allowed_sucursal_keys=["OTRA SUCURSAL"],
            session=denied_session,
        )
    assert denied_session.queries == 1

    # A giant submitted campaign on the same visible page cannot hide
    # legitimate results of a smaller one (#26).
    big_phones = [f"6{i:09d}" for i in range(10001)]
    big_session = FakeSession([
        [campaign(25), campaign(26)],
        [child(25, "provider-25"), child(26, "provider-26")],
        [
            SimpleNamespace(
                id=25, campaign_v2_id=25,
                provider_campaign_id="provider-25", fetched_at=when,
            ),
            SimpleNamespace(
                id=1, campaign_v2_id=26,
                provider_campaign_id="provider-26", fetched_at=when,
            ),
        ],
        [SimpleNamespace(
            id=3332, business_date=date(2026, 10, 21),
            captured_at=datetime(2026, 10, 21, 18, 0, tzinfo=timezone.utc),
        )],
        ([(25, 25, phone) for phone in big_phones] +
         [(1, 26, "6861111111")]),
        [sale(1, "6861111111", "CONVENIOS $549", "549")],
    ])
    big_result = build_campaign_v2_commercial_attribution_batch(
        campaign_ids=[25, 26], allowed_sucursal_keys=None, session=big_session,
    )
    assert big_session.queries == 6
    assert big_result["rows"][0]["status"] == "BATCH_SCOPE_TOO_LARGE"
    assert big_result["rows"][0]["revenue_attributed_mxn"] is None
    assert big_result["rows"][1]["status"] == "READY"
    assert big_result["rows"][1]["revenue_attributed_mxn"] == "549.00"


def test_commercial_attribution_multichild_resolves_submitted_branch_payloads():
    """Two sent branches are separate; an untouched HELD child contributes nothing."""
    from app.services.marketing_campaign_v2_commercial_attribution_service import (
        resolve_submitted_child_recipients,
    )

    when = datetime(2026, 10, 21, 19, 0, tzinfo=timezone.utc)
    frozen = [
        SimpleNamespace(id=1, campaign_id=40, phone_mx10="6861000001"),
        SimpleNamespace(id=2, campaign_id=40, phone_mx10="6861000002"),
        SimpleNamespace(id=3, campaign_id=40, phone_mx10="6641000003"),
    ]

    def child(identifier, branch, channel, phones, *, status="SUBMITTED"):
        return SimpleNamespace(
            id=identifier,
            campaign_v2_id=40,
            sucursal_id=branch,
            provider="IVENTAS",
            provider_campaign_id=(f"provider-{identifier}" if status == "SUBMITTED" else None),
            status=status,
            submitted_at=(when if status == "SUBMITTED" else None),
            submit_started_at=None,
            provider_channel_id=channel,
            recipient_count=len(phones),
            request_snapshot_json={
                "provider_channel_id": channel,
                "leads": [{"phone": f"521{phone}"} for phone in phones],
            },
        )

    resolution = resolve_submitted_child_recipients(
        campaign_id=40,
        # Deliberately out of order: resolver must be deterministic by child ID.
        children=[
            child(102, 18, "channel-18", [], status="HELD"),
            child(101, 17, "channel-17", ["6641000003"]),
            child(100, 16, "channel-16", ["6861000001", "6861000002"]),
        ],
        frozen_recipients=frozen,
    )
    assert resolution.not_sent_child_ids == (102,)
    assert resolution.unresolved_child_ids == ()
    assert [
        (row.child_id, row.sucursal_id, row.provider_campaign_id, row.recipients)
        for row in resolution.submitted
    ] == [
        (100, 16, "provider-100", (("6861000001", 1), ("6861000002", 2))),
        (101, 17, "provider-101", (("6641000003", 3),)),
    ]


def test_commercial_attribution_multichild_sums_only_valid_separate_branch_sales():
    """Two iVentas children, different send times, no repeated buyers or orders."""
    from decimal import Decimal
    from zoneinfo import ZoneInfo

    from app.services.marketing_campaign_v2_reporting_service import (
        MarketingCampaignV2ReportingValidationError,
        _summarize_campaign_v2_multichild_membership_movements,
    )

    def sale(identifier, phone, branch, amount, *, order=None, when="19:00:00",
             status="ACTIVO", description="CONVENIOS $549"):
        return SimpleNamespace(
            id=identifier,
            telefono=phone,
            sucursal=branch,
            estatus=status,
            descripcion=description,
            total=Decimal(str(amount)),
            fecha="2026-10-20",
            hora=when,
            id_orden=order or f"ORDER-{identifier}",
            folio=f"FOLIO-{identifier}",
            clave_producto="MEMBRESIA",
            tipo="CONTRATO",
        )

    tz = ZoneInfo("America/Tijuana")
    # Child 100 sent at 16:00, child 101 at 18:00. Every later sale
    # must match the corresponding branch, never just the frozen campaign.
    branch_a_rows = [
        sale(1, "6861000001", "AZAHARES", 549, order="A"),
        sale(2, "6861000001", "AZAHARES", -50, order="A"),
        sale(3, "6861000002", "AZAHARES", 399),
        sale(4, "6861000001", "BRANCH B", 549),
        sale(5, "6861000001", "AZAHARES", 100, description="PENALIZACION"),
    ]
    branch_b_rows = [
        sale(6, "6641000003", "BRANCH B", 649),
        sale(7, "6641000003", "BRANCH B", 649, when="17:59:00"),
        sale(8, "6641000003", "BRANCH B", 649, status="CANCELADO"),
        sale(9, "6861000001", "BRANCH B", 549),
    ]
    inputs = [
        {
            "child_id": 101,
            "branch_id": 17,
            "sent_local": datetime(2026, 10, 20, 18, 0, tzinfo=tz),
            "successful_phones": {"6641000003"},
            "rows": branch_b_rows,
        },
        {
            "child_id": 100,
            "branch_id": 16,
            "sent_local": datetime(2026, 10, 20, 16, 0, tzinfo=tz),
            "successful_phones": {"6861000001"},
            "rows": branch_a_rows,
        },
    ]
    result = _summarize_campaign_v2_multichild_membership_movements(
        child_inputs=inputs, alias_map={"AZAHARES": 16, "BRANCH B": 17},
    )
    assert result == {
        "successful_recipient_count": 2,
        "buyers_attributed": 2,
        "transactions_attributed": 2,
        "revenue_attributed_mxn": "1148.00",
        "children": [
            {
                "child_id": 100,
                "successful_recipient_count": 1,
                "buyers_attributed": 1,
                "transactions_attributed": 1,
                "revenue_attributed_mxn": "499.00",
            },
            {
                "child_id": 101,
                "successful_recipient_count": 1,
                "buyers_attributed": 1,
                "transactions_attributed": 1,
                "revenue_attributed_mxn": "649.00",
            },
        ],
    }

    with pytest.raises(MarketingCampaignV2ReportingValidationError, match="dos children"):
        duplicate = [
            {**inputs[0], "successful_phones": {"6861000001"}},
            inputs[1],
        ]
        _summarize_campaign_v2_multichild_membership_movements(
            child_inputs=duplicate, alias_map={"AZAHARES": 16, "BRANCH B": 17},
        )
