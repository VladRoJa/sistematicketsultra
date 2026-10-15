"""Published M6 daily branch reader: closed dates, scope isolation, continuity."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace as Item

import pytest

from app.services import marketing_google_ads_m6_daily_attribution_service as daily
from app.services.marketing_access import MarketingAccess
from test_google_ads_m6_attribution_reader import _segment


def _access(*, global_=False):
    return MarketingAccess(
        type="GLOBAL" if global_ else "PRIMARY_BRANCH",
        is_global=global_, branch_ids=() if global_ else (1,),
        role="ADMINISTRADOR" if global_ else "GERENTE",
        can_edit_inputs=False,
    )


def _fake(monkeypatch, *, dates=(13,), wrong_source=False,
          stale_hash=False, global_=False):
    approved = [
        ["Camp", "Group", "name:" + f"{i:064x}",
         "name:" + f"{i + 100:064x}", f"BRANCH_{i}", i, "0"]
        for i in range(1, 27)
    ]
    manifest = {
        "id": daily.M5_REFERENCE, "customer_id": daily.CUSTOMER_ID,
        "rows": approved,
    }
    version = Item(
        id=17, customer_id=daily.CUSTOMER_ID,
        approval_reference="GOOGLE_ADS_M6_CONTINUITY_20261013_V1",
        source_approval_reference=daily.M5_REFERENCE,
        valid_from=date(2026, 10, 9), valid_to=None,
        source_campaign_upload_id=21604, source_ad_group_upload_id=21605,
        approved_by_user_id=47, approved_on=date(2026, 10, 14),
    )
    # Use the production M6 reference to avoid an approval mock bypass.
    from app.services import marketing_google_ads_m6_attribution_service as history
    version.approval_reference = history.M6_REFERENCE
    mapping = Item(id=12, approval_version_id=17,
                   campaign_key=approved[0][2], ad_group_key=approved[0][3],
                   sucursal_canon="BRANCH_1")
    catalog = Item(sucursal_id=1, sucursal_canon="BRANCH_1", is_track_active=True)
    branch = Item(sucursal_id=1, operational_status="ACTIVA")
    monkeypatch.setattr(daily, "_version", lambda: [version])
    monkeypatch.setattr(daily, "_load_m5", lambda: manifest)
    monkeypatch.setattr(daily, "_mapping_rows",
                        lambda *_: [(mapping, catalog, branch)])
    monkeypatch.setattr(daily, "load_visible_marketing_branches",
                        lambda _: ([], (1,), {}))
    published = []
    for n in dates:
        day = date(2026, 10, n)
        pub = Item(
            business_date=day, customer_id=daily.CUSTOMER_ID,
            is_canonical=True, revision=1,
            campaign_upload_id=22000 + n, ad_group_upload_id=23000 + n,
            campaign_sha256="a" * 64, ad_group_sha256="b" * 64,
        )
        camp = Item(
            id=pub.campaign_upload_id, status="ACTIVE",
            source_file_deleted_at=None,
            file_hash_sha256="z"*64 if stale_hash else pub.campaign_sha256,
            cutoff_date=day, date_from=day, date_to=day,
        )
        group = Item(
            id=pub.ad_group_upload_id, status="ACTIVE",
            source_file_deleted_at=None, file_hash_sha256=pub.ad_group_sha256,
            cutoff_date=day, date_from=day, date_to=day,
        )
        published.append((pub, camp, group))
    monkeypatch.setattr(daily, "_published_days", lambda *_: published)

    fact_rows = []
    for pub, _, _ in published:
        fact = Item(
            report_date=pub.business_date, customer_id=daily.CUSTOMER_ID,
            source_upload_id=(99999 if wrong_source else pub.ad_group_upload_id),
            source_kind="WAREHOUSE_XLSX", currency_code="MXN",
            campaign_id=None, ad_group_id=None,
            campaign_key=mapping.campaign_key, ad_group_key=mapping.ad_group_key,
            cost=Decimal("20.00"), clicks=4, impressions=60,
            free_pass_conversions=Decimal(".50"),
            web_purchase_conversions=Decimal(".25"),
        )
        fact_rows.append((fact, mapping, catalog))
    monkeypatch.setattr(daily, "_restricted_group_facts",
                        lambda *_: fact_rows)
    if global_:
        monkeypatch.setattr(daily, "_global_day_cost",
                            lambda p, attributed: Decimal("23"))
    else:
        monkeypatch.setattr(
            daily, "_global_day_cost",
            lambda *args: pytest.fail("Restricted user queried global spend"),
        )
    return _access(global_=global_)


def _read(access, *, cutoff=14):
    return daily.read_google_ads_m6_daily_branch_attribution(
        month_start=date(2026, 10, 1),
        cutoff_date=date(2026, 10, cutoff), access=access,
    )


def test_scoped_published_13_no_14_and_no_global_spend(monkeypatch):
    access = _fake(monkeypatch)
    result = _read(access)
    assert result["status"] == "partial"
    assert result["observed_from"] == result["observed_to"] == "2026-10-13"
    assert result["covered_days"] == 1
    assert result["scope_attributed_cost"] == 20
    assert result["rows"][0]["sucursal_id"] == 1
    assert result["rows"][0]["clicks"] == 4
    for forbidden in ("account_cost_observed", "unassigned_cost_observed",
                      "account_reconciled"):
        assert forbidden not in result


def test_missing_first_canonical_day_never_skips_forward(monkeypatch):
    access = _fake(monkeypatch, dates=(14,))
    result = _read(access)
    assert result["status"] == "requires_review"
    assert result["rows"] == []
    assert result["scope_attributed_cost"] is None


def test_two_published_days_add_scoped_metrics_once(monkeypatch):
    access = _fake(monkeypatch, dates=(13, 14))
    result = _read(access)
    assert result["covered_days"] == 2
    assert result["scope_attributed_cost"] == 40
    assert result["rows"][0]["clicks"] == 8


@pytest.mark.parametrize("options", [{"wrong_source": True}, {"stale_hash": True}])
def test_wrong_group_source_or_raw_hash_fail_closed(monkeypatch, options):
    access = _fake(monkeypatch, **options)
    result = _read(access)
    assert result["status"] == "requires_review"
    assert result["rows"] == []


def test_unpublished_day_is_unavailable_and_never_claims_zero(monkeypatch):
    access = _fake(monkeypatch, dates=())
    result = _read(access)
    assert result["status"] == "unavailable"
    assert result["scope_attributed_cost"] is None


def test_historical_bridge_full_october_13_with_no_m5_double_count(monkeypatch):
    access = _fake(monkeypatch)
    month = date(2026, 10, 1)
    history = _segment(month, date(2026, 10, 12), cost=100)
    result = daily.combine_historical_with_daily(
        history, _read(access, cutoff=13),
        month_start=month, cutoff_date=date(2026, 10, 13),
        is_global=False,
    )
    assert result["covered_days"] == 13
    assert result["status"] == "complete"
    assert result["scope_attributed_cost"] == 120
    assert result["historical_to"] == "2026-10-13"


def test_historical_bridge_keeps_partial_if_daily_not_published(monkeypatch):
    access = _fake(monkeypatch, dates=())
    month = date(2026, 10, 1)
    history = _segment(month, date(2026, 10, 12), cost=100)
    assert daily.combine_historical_with_daily(
        history, _read(access),
        month_start=month, cutoff_date=date(2026, 10, 14),
        is_global=False,
    ) is history


def test_scoped_query_compiles_branch_and_approved_upload_filters(monkeypatch):
    captured = []
    class Query:
        def join(self, *args): return self
        def filter(self, *clauses):
            captured.extend(clauses)
            return self
        def all(self): return []
    class Session:
        def query(self, *args):
            # Scoped readers may only query ad-group facts, mapped groups
            # and branch catalog, never the global campaign ledger.
            assert args[0] is daily.GoogleAdsAdGroupDailyMetricORM
            return Query()
    monkeypatch.setattr(daily, "db", Item(session=Session()))
    daily._restricted_group_facts((1,), (23013,), date(2026, 10, 13),
                                  date(2026, 10, 13), 17)
    sql = " AND ".join(str(x.compile(
        compile_kwargs={"literal_binds": True})) for x in captured).lower()
    assert "sucursal_id in (1)" in sql
    assert "source_upload_id in (23013)" in sql
    assert "customer_id = '2739125201'" in sql
