"""Issue 856/B — manual MXN cost versions and safe preflight estimates."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, Column, Integer, MetaData, Table, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.marketing import (
    MarketingCampaignV2ChannelBindingORM,
    MarketingCampaignV2CostRateRevisionORM,
    MarketingCampaignV2TemplateORM,
)
from app.models.sucursal_model import Sucursal
from app.models.warehouse import TrackBranchCatalogORM
from app.services import marketing_campaign_v2_budget_service as budget


@compiles(BigInteger, "sqlite")
def _sqlite_bigint_as_integer(_type, _compiler, **_kwargs):
    return "INTEGER"


NOW = datetime(2026, 10, 13, 16, 0, tzinfo=timezone.utc)


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    Sucursal.__table__.to_metadata(metadata)
    TrackBranchCatalogORM.__table__.to_metadata(metadata)
    MarketingCampaignV2TemplateORM.__table__.to_metadata(metadata)
    MarketingCampaignV2ChannelBindingORM.__table__.to_metadata(metadata)
    MarketingCampaignV2CostRateRevisionORM.__table__.to_metadata(metadata)
    metadata.create_all(engine)
    with Session(engine) as active:
        active.execute(Table("users", MetaData(), autoload_with=engine).insert().values(id=7))
        active.execute(Table("sucursales", MetaData(), autoload_with=engine).insert().values(
            sucursal_id=4, serie="TEC", sucursal="Tecnológico", estado="BC",
            operational_status="ACTIVA", is_demo=False, municipio="Mexicali",
            direccion="synthetic",
        ))
        active.add(TrackBranchCatalogORM(
            sucursal_canon="TEC_MXL", sucursal_id=4,
            track_label="TEC MXL", display_order=4, is_track_active=True,
        ))
        active.add(MarketingCampaignV2ChannelBindingORM(
            provider="IVENTAS", sucursal_id=4, sucursal_canon="TEC_MXL",
            provider_channel_id="channel-tec", is_active=True, is_default=True,
            created_by_user_id=7, updated_by_user_id=7,
        ))
        active.add(MarketingCampaignV2TemplateORM(
            provider="IVENTAS", template_name="synthetic_approved", label="QA",
            is_active=True, purposes_json=["REACTIVATION"], variables_json={},
            compatible_channel_ids_json=["channel-tec"],
            metadata_json={}, created_by_user_id=7, updated_by_user_id=7,
        ))
        active.commit()
        yield active
    engine.dispose()


def _quote(session, price="0.825"):
    return budget.register_cost_rate_revision(
        template_id=1, provider_channel_id="channel-tec",
        unit_cost_mxn=price, source_reference="operator synthetic pricing acceptance",
        actor_user_id=7, session=session, now=NOW,
    )


def _plan(ready=True, extra=False):
    batches = [SimpleNamespace(
        template_id=1, provider_channel_id="channel-tec",
        sucursal_canon="TEC_MXL",
        recipients=[object()] * 3,
    )]
    if extra:
        batches.append(SimpleNamespace(
            template_id=1, provider_channel_id="channel-without-price",
            sucursal_canon="OTHER", recipients=[object()] * 2,
        ))
    return SimpleNamespace(
        ready=ready, batches=batches, sendable_phones=["x"] * (5 if extra else 3),
    )


def test_cost_rate_registration_is_revisioned_not_overwritten(session):
    first = _quote(session, "0.825")
    second = budget.register_cost_rate_revision(
        template_id=1, provider_channel_id="channel-tec",
        unit_cost_mxn="1.250000", source_reference="new synthetic quote",
        actor_user_id=7, session=session, now=NOW + timedelta(hours=1),
    )
    history = budget.list_cost_rate_revisions(template_id=1, session=session)
    assert [row["revision_id"] for row in history] == [second["revision_id"], first["revision_id"]]
    assert history[0]["unit_cost_mxn"] == "1.250000"
    assert history[1]["unit_cost_mxn"] == "0.825000"
    assert budget.current_cost_rates(
        template_id=1, session=session, now=NOW + timedelta(minutes=30)
    )["channel-tec"]["revision_id"] == first["revision_id"]
    assert budget.current_cost_rates(
        template_id=1, session=session, now=NOW + timedelta(hours=2)
    )["channel-tec"]["revision_id"] == second["revision_id"]


@pytest.mark.parametrize("price", [None, "", "0", "-0.2", "NaN", "Infinity", "1001", "0.0000001", True, 0.5])
def test_budget_rejects_invented_or_invalid_prices(session, price):
    with pytest.raises(budget.CampaignV2BudgetValidationError):
        budget.register_cost_rate_revision(
            template_id=1, provider_channel_id="channel-tec",
            unit_cost_mxn=price, source_reference="approved synthetic source",
            actor_user_id=7, session=session, now=NOW,
        )
    assert not budget.list_cost_rate_revisions(session=session)


def test_budget_requires_source_and_existing_active_channel(session):
    with pytest.raises(budget.CampaignV2BudgetValidationError, match="origen"):
        budget.register_cost_rate_revision(
            template_id=1, provider_channel_id="channel-tec",
            unit_cost_mxn="0.82", source_reference=" ",
            actor_user_id=7, session=session, now=NOW,
        )
    with pytest.raises(budget.CampaignV2BudgetValidationError, match="Canal inexistente"):
        budget.register_cost_rate_revision(
            template_id=1, provider_channel_id="channel-fabricated",
            unit_cost_mxn="0.82", source_reference="approved ref",
            actor_user_id=7, session=session, now=NOW,
        )


def test_budget_complete_exact_cents_and_revision_evidence(session):
    registered = _quote(session)
    value = budget.estimate_preflight_cost(
        plan=_plan(), session=session, now=NOW + timedelta(minutes=1),
    )
    assert value["status"] == "COMPLETE"
    assert value["currency"] == "MXN"
    assert value["total_estimated_mxn"] == "2.48"
    assert value["priced_subtotal_mxn"] == "2.48"
    assert value["batches"][0]["revision_id"] == registered["revision_id"]
    assert value["batches"][0]["source_reference"] == "operator synthetic pricing acceptance"


def test_budget_missing_price_or_blocked_plan_never_shows_fake_total(session):
    _quote(session)
    missing = budget.estimate_preflight_cost(
        plan=_plan(extra=True), session=session, now=NOW + timedelta(minutes=1),
    )
    assert missing["status"] == "INCOMPLETE"
    assert missing["total_estimated_mxn"] is None
    assert missing["priced_recipients"] == 3
    assert missing["missing_rate_channels"] == [{"sucursal_canon": "OTHER", "recipient_count": 2}]
    blocked = budget.estimate_preflight_cost(
        plan=_plan(ready=False), session=session, now=NOW + timedelta(minutes=1),
    )
    assert blocked["status"] == "INCOMPLETE"
    assert blocked["total_estimated_mxn"] is None


def test_budget_missing_all_prices_is_not_zero_cost(session):
    value = budget.estimate_preflight_cost(
        plan=_plan(), session=session, now=NOW,
    )
    assert value["status"] == "INCOMPLETE"
    assert value["total_estimated_mxn"] is None
    assert value["priced_subtotal_mxn"] == "0.00"
    assert value["priced_recipients"] == 0


def test_rounding_each_branch_before_total_reconciles_visible_rows(session):
    _quote(session, "0.825")
    plan = _plan()
    plan.batches.append(SimpleNamespace(
        template_id=1, provider_channel_id="channel-tec",
        sucursal_canon="SECOND_TEST_BRANCH",
        recipients=[object()] * 3,
    ))
    plan.sendable_phones.extend(["y"] * 3)
    quote = budget.estimate_preflight_cost(
        plan=plan, session=session, now=NOW + timedelta(minutes=1),
    )
    assert quote["status"] == "COMPLETE"
    assert [x["estimated_mxn"] for x in quote["batches"]] == ["2.48", "2.48"]
    assert quote["total_estimated_mxn"] == "4.96"


def test_same_total_new_rate_revision_invalidates_quote_fingerprint(session):
    _quote(session, "0.825")
    first = budget.estimate_preflight_cost(
        plan=_plan(), session=session, now=NOW,
    )
    budget.register_cost_rate_revision(
        template_id=1, provider_channel_id="channel-tec",
        unit_cost_mxn="0.825", source_reference="new revision same price",
        actor_user_id=7, session=session, now=NOW + timedelta(minutes=1),
    )
    second = budget.estimate_preflight_cost(
        plan=_plan(), session=session, now=NOW + timedelta(minutes=2),
    )
    assert first["total_estimated_mxn"] == second["total_estimated_mxn"]
    assert first["quote_fingerprint"] != second["quote_fingerprint"]
