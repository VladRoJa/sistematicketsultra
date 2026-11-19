"""M2 cached monthly report: SQLite persistence and Marketing ACL isolation."""
from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, create_engine
from sqlalchemy.orm import Session

from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2CommercialSaleMonthORM,
)
from app.services.marketing_campaign_v2_sales_month_materialization_service import (
    materialize_sale_month, read_sale_month_cache,
)


FROM = date(2026, 10, 1)
TO = date(2026, 10, 31)
NOW = datetime(2026, 11, 18, 20, tzinfo=timezone.utc)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    for model in (MarketingCampaignV2ORM, MarketingCampaignV2CommercialSaleMonthORM):
        model.__table__.to_metadata(metadata)
    metadata.create_all(engine)
    with Session(engine) as active:
        active.add_all([
            MarketingCampaignV2ORM(
                id=1, name="Sucursal A", purpose="REACTIVATION",
                source="EXPIRED_MEMBERS",
                audience_definition_json={
                    "filters": {"allowed_sucursal_keys": ["AZAHARES_CUL"]}
                }, frozen_at=NOW, created_at=NOW, updated_at=NOW,
            ),
            MarketingCampaignV2ORM(
                id=2, name="Sucursal B", purpose="REACTIVATION",
                source="EXPIRED_MEMBERS",
                audience_definition_json={
                    "filters": {"allowed_sucursal_keys": ["SEND_CUL"]}
                }, frozen_at=NOW, created_at=NOW, updated_at=NOW,
            ),
        ])
        active.commit()
        yield active
    engine.dispose()


def payload():
    return {
        "status": "READY",
        "from": FROM.isoformat(), "to": TO.isoformat(),
        "window_days": 14,
        "rule_version": "M2_LAST_PROVEN_SUBMISSION_V1",
        "buyers_observed": 2,
        "revenue_observed_mxn": "1098.00",
        "transactions_observed": 2,
        "sale_snapshot_id": 301,
        "sale_business_date": TO.isoformat(),
        "campaigns": [
            {"campaign_id": 1, "buyers_observed": 1, "transactions_observed": 1,
             "revenue_observed_mxn": "549.00", "assisted_transactions": 1},
            {"campaign_id": 2, "buyers_observed": 1, "transactions_observed": 1,
             "revenue_observed_mxn": "549.00", "assisted_transactions": 0},
        ],
    }


def test_cache_missing_is_not_zero_sale(session):
    result = read_sale_month_cache(
        from_date=FROM.isoformat(), to_date=TO.isoformat(), window_days=14,
        allowed_sucursal_keys=None, session=session,
    )
    assert result["status"] == "NOT_MATERIALIZED"
    assert result["transactions_observed"] is None
    assert result["revenue_observed_mxn"] is None


def test_ready_materialization_restricts_campaigns_by_complete_scope(session):
    session.add(MarketingCampaignV2CommercialSaleMonthORM(
        sale_from=FROM, sale_to=TO, window_days=14,
        status="READY", result_json=payload(), checked_at=NOW,
    ))
    session.commit()
    full = read_sale_month_cache(
        from_date=FROM.isoformat(), to_date=TO.isoformat(), window_days=14,
        allowed_sucursal_keys=None, session=session,
    )
    assert full["status"] == "READY"
    assert full["transactions_observed"] == 2
    assert full["revenue_observed_mxn"] == "1098.00"
    assert full["buyers_observed"] == 2
    assert [c["name"] for c in full["campaigns"]] == ["Sucursal A", "Sucursal B"]

    scoped = read_sale_month_cache(
        from_date=FROM.isoformat(), to_date=TO.isoformat(), window_days=14,
        allowed_sucursal_keys=["AZAHARES_CUL"], session=session,
    )
    assert [row["campaign_id"] for row in scoped["campaigns"]] == [1]
    assert scoped["transactions_observed"] == 1
    assert scoped["revenue_observed_mxn"] == "549.00"
    assert scoped["buyers_observed"] is None
    assert "Sucursal B" not in repr(scoped)

    denied = read_sale_month_cache(
        from_date=FROM.isoformat(), to_date=TO.isoformat(), window_days=14,
        allowed_sucursal_keys=[], session=session,
    )
    assert denied["campaigns"] == []
    assert denied["transactions_observed"] == 0
    assert denied["revenue_observed_mxn"] == "0.00"
    assert denied["buyers_observed"] is None


def test_non_ready_cache_has_no_false_zero_or_cross_branch_detail(session):
    session.add(MarketingCampaignV2CommercialSaleMonthORM(
        sale_from=FROM, sale_to=TO, window_days=7,
        status="PENDING_PROVIDER_EVIDENCE",
        result_json={"status": "PENDING_PROVIDER_EVIDENCE", "reason": "pending"},
        checked_at=NOW,
    ))
    session.commit()
    result = read_sale_month_cache(
        from_date=FROM.isoformat(), to_date=TO.isoformat(), window_days=7,
        allowed_sucursal_keys=["AZAHARES_CUL"], session=session,
    )
    assert result["status"] == "PENDING_PROVIDER_EVIDENCE"
    assert result["revenue_observed_mxn"] is None
    assert result["campaigns"] == []


def test_worker_persists_aggregate_only_on_explicit_call(session):
    with patch(
        "app.services.marketing_campaign_v2_sales_month_materialization_service.reconcile_sale_month",
        return_value=payload(),
    ):
        result = materialize_sale_month(
            from_date=FROM.isoformat(), to_date=TO.isoformat(),
            window_days=14, checked_at=NOW, session=session,
        )
    assert result["status"] == "READY"
    record = session.get(
        MarketingCampaignV2CommercialSaleMonthORM, (FROM, TO, 14)
    )
    assert record.status == "READY"
    assert record.result_json["buyers_observed"] == 2
    assert "phone_mx10" not in repr(record.result_json)
    assert record.checked_at.replace(tzinfo=timezone.utc) == NOW


def test_worker_rejects_private_allocations_before_cache_write(session):
    bad = {**payload(), "allocations_private": [{"transaction_ref": "order:x"}]}
    with patch(
        "app.services.marketing_campaign_v2_sales_month_materialization_service.reconcile_sale_month",
        return_value=bad,
    ):
        with pytest.raises(ValueError, match="identidad"):
            materialize_sale_month(
                from_date=FROM.isoformat(), to_date=TO.isoformat(),
                window_days=14, checked_at=NOW, session=session,
            )
    assert session.get(MarketingCampaignV2CommercialSaleMonthORM, (FROM, TO, 14)) is None
