"""M6 Funnel read isolation and M5/M6 split: synthetic, read-only cases."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace as Item

import pytest

from app.services import marketing_google_ads_m6_attribution_service as reader
from app.services import marketing_sales_funnel_cutoff_service as cutoff
from app.services.marketing_access import MarketingAccess


def _access(*, global_=False):
    return MarketingAccess(
        type="GLOBAL" if global_ else "PRIMARY_BRANCH",
        is_global=global_, branch_ids=() if global_ else (1,),
        role="ADMINISTRADOR" if global_ else "GERENTE",
        can_edit_inputs=False,
    )


def _segment(from_, to, *, cost, account=None, global_=False):
    covered = (to - from_).days + 1
    value = {
        "status": "partial", "currency": "MXN",
        "allocation_basis": "APPROVED_PROVISIONAL_XLSX",
        "historical_from": from_.isoformat(),
        "historical_to": to.isoformat(),
        "observed_from": from_.isoformat(),
        "observed_to": to.isoformat(),
        "covered_days": covered,
        "rows": [{
            "sucursal_id": 1, "cost": cost,
            "clicks": 2 * covered,
            "impressions": 20 * covered,
            "free_pass_ads": 0.5 * covered,
            "web_purchase_ads": 0.25 * covered,
        }],
        "scope_attributed_cost": cost,
    }
    if global_:
        value.update({
            "account_cost_observed": account,
            "unassigned_cost_observed": account - cost,
            "account_reconciled": True,
        })
    return value


def _combined(global_=False, *, to=date(2026, 10, 12)):
    m5 = _segment(date(2026, 10, 1), date(2026, 10, 8),
                  cost=100, account=120, global_=global_)
    m6 = _segment(date(2026, 10, 9), date(2026, 10, 12),
                  cost=50, account=60, global_=global_)
    return reader.combine_m5_m6(
        m5, m6, month_start=date(2026, 10, 1), cutoff_date=to,
        is_global=global_,
    )


def test_combine_exact_boundary_8_and_9_no_duplication_and_no_global_leak():
    result = _combined()
    assert result["status"] == "complete"
    assert result["covered_days"] == 12
    assert result["missing_days"] == 0
    assert result["historical_to"] == "2026-10-12"
    assert result["scope_attributed_cost"] == 150
    assert result["rows"] == [{
        "sucursal_id": 1, "cost": 150.0, "clicks": 24.0,
        "impressions": 240.0, "free_pass_ads": 6.0,
        "web_purchase_ads": 3.0,
    }]
    for forbidden in ("account_cost_observed", "unassigned_cost_observed",
                      "account_reconciled"):
        assert forbidden not in result


def test_global_adds_account_once_and_maintains_unassigned():
    result = _combined(global_=True)
    assert result["account_cost_observed"] == 180.0
    assert result["scope_attributed_cost"] == 150.0
    assert result["unassigned_cost_observed"] == 30.0
    assert result["account_reconciled"] is True


def test_cutoff_after_12_remains_partial_not_invented_future_cost():
    result = _combined(to=date(2026, 10, 14))
    assert result["status"] == "partial"
    assert result["covered_days"] == 12
    assert result["missing_days"] == 2
    assert result["complete_to_cutoff"] is False


@pytest.mark.parametrize("state", ["unavailable", "pending_mapping", "scope_unavailable"])
def test_no_m6_approval_keeps_historical_m5_unchanged(state):
    m5 = _segment(date(2026, 10, 1), date(2026, 10, 8), cost=100)
    m6 = reader._empty(state, date(2026, 10, 1), date(2026, 10, 12))
    assert reader.combine_m5_m6(
        m5, m6, month_start=date(2026, 10, 1),
        cutoff_date=date(2026, 10, 12), is_global=False,
    ) is m5


def test_modified_or_incomplete_m6_fails_closed_without_m5_spend():
    m5 = _segment(date(2026, 10, 1), date(2026, 10, 8), cost=100)
    m6 = reader._empty("requires_review", date(2026, 10, 1), date(2026, 10, 12))
    result = reader.combine_m5_m6(
        m5, m6, month_start=date(2026, 10, 1),
        cutoff_date=date(2026, 10, 12), is_global=False,
    )
    assert result["status"] == "requires_review"
    assert result["rows"] == []
    assert result["scope_attributed_cost"] is None


def test_cutoff_8_does_not_invoke_m6_reader(monkeypatch):
    access = _access()
    monkeypatch.setattr(
        cutoff, "read_google_ads_branch_attribution",
        lambda **_kw: {"status": "complete", "rows": []},
    )
    monkeypatch.setattr(
        cutoff, "read_google_ads_m6_branch_attribution",
        lambda **_kw: pytest.fail("M6 must not run for M5 historical cutoff"),
    )
    payload = {"summary": {"investment": 100}}
    cutoff._attach_google_ads_branch_attribution(
        payload=payload, month_start=date(2026, 10, 1),
        cutoff_date=date(2026, 10, 8), access=access,
    )
    assert payload["google_ads_branch_attribution"]["status"] == "complete"


def test_cutoff_12_combines_both_readers_without_touching_meta(monkeypatch):
    access = _access()
    monkeypatch.setattr(
        cutoff, "read_google_ads_branch_attribution",
        lambda **_kw: _segment(date(2026, 10, 1), date(2026, 10, 8), cost=100),
    )
    monkeypatch.setattr(
        cutoff, "read_google_ads_m6_branch_attribution",
        lambda **_kw: _segment(date(2026, 10, 9), date(2026, 10, 12), cost=50),
    )
    payload = {
        "summary": {"investment": 110.0, "cpl": 8.3},
        "investment_sources": {"existing_cpl_cpt_cac_basis": "META_ASSIGNED_ONLY"},
    }
    cutoff._attach_google_ads_branch_attribution(
        payload=payload, month_start=date(2026, 10, 1),
        cutoff_date=date(2026, 10, 12), access=access,
    )
    assert payload["summary"] == {"investment": 110.0, "cpl": 8.3}
    assert payload["investment_sources"]["existing_cpl_cpt_cac_basis"] == "META_ASSIGNED_ONLY"
    assert payload["google_ads_branch_attribution"]["scope_attributed_cost"] == 150.0


def _fake_approved(monkeypatch, *, present=True, wrong_source=False, complete=True):
    access = _access()
    monkeypatch.setattr(reader, "load_visible_marketing_branches",
                        lambda _a: ([], (1,), {}))
    version = Item(
        id=1, customer_id=reader.CUSTOMER_ID,
        approval_reference=reader.M6_REFERENCE,
        source_approval_reference=reader.M5_REFERENCE,
        valid_from=reader.START, valid_to=None,
        source_campaign_upload_id=reader.CAMPAIGN_UPLOAD_ID,
        source_ad_group_upload_id=reader.GROUP_UPLOAD_ID,
        approved_by_user_id=47, approved_on=date(2026, 10, 14),
    )
    monkeypatch.setattr(reader, "_version", lambda: [version] if present else [])
    manifest = {
        "id": reader.M5_REFERENCE, "customer_id": reader.CUSTOMER_ID,
        "rows": [
            [None, None, "name:" + f"{n:064x}",
             "name:" + f"{n + 100:064x}", f"BRANCH_{n}", n, "0"]
            for n in range(1, 27)
        ],
    }
    monkeypatch.setattr(reader, "_load_m5", lambda: manifest)
    mapping = Item(
        id=99, approval_version_id=1,
        campaign_key=manifest["rows"][0][2],
        ad_group_key=manifest["rows"][0][3],
        sucursal_canon="BRANCH_1",
    )
    catalog = Item(sucursal_id=1, sucursal_canon="BRANCH_1", is_track_active=True)
    branch = Item(sucursal_id=1, operational_status="ACTIVA")
    monkeypatch.setattr(reader, "_mapping_rows", lambda *_: [(mapping, catalog, branch)])
    calls = {"facts": 0}
    def facts(*args):
        calls["facts"] += 1
        return [
            (Item(
                customer_id=reader.CUSTOMER_ID, campaign_key=mapping.campaign_key,
                ad_group_key=mapping.ad_group_key, campaign_id=None, ad_group_id=None,
                source_kind="WAREHOUSE_XLSX",
                source_upload_id=999 if wrong_source else reader.GROUP_UPLOAD_ID,
                report_date=date(2026, 10, d), currency_code="MXN",
                cost=Decimal("3"), clicks=4, impressions=50,
                free_pass_conversions=Decimal("0.25"),
                web_purchase_conversions=Decimal("0.5"),
            ), mapping, catalog)
            for d in (range(9, 13) if complete else range(9, 12))
        ]
    monkeypatch.setattr(reader, "_fact_rows", facts)
    monkeypatch.setattr(reader, "_global_campaigns",
                        lambda *args: pytest.fail("Restricted request read global ledger"))
    monkeypatch.setattr(reader, "_global_groups",
                        lambda *args: pytest.fail("Restricted request read foreign groups"))
    return access, calls


def test_scoped_reader_returns_approved_branch_only(monkeypatch):
    access, calls = _fake_approved(monkeypatch)
    result = reader.read_google_ads_m6_branch_attribution(
        month_start=date(2026, 10, 1), cutoff_date=date(2026, 10, 12),
        access=access,
    )
    assert result["status"] == "partial"
    assert result["covered_days"] == 4
    assert result["scope_attributed_cost"] == 12
    assert [r["sucursal_id"] for r in result["rows"]] == [1]
    assert "account_cost_observed" not in result
    assert calls["facts"] == 1


def test_scoped_reader_never_treats_missing_approval_as_zero(monkeypatch):
    access, calls = _fake_approved(monkeypatch, present=False)
    result = reader.read_google_ads_m6_branch_attribution(
        month_start=date(2026, 10, 1), cutoff_date=date(2026, 10, 12),
        access=access,
    )
    assert result["status"] == "pending_mapping"
    assert result["scope_attributed_cost"] is None
    assert calls["facts"] == 0


@pytest.mark.parametrize("kwargs", [{"wrong_source": True}, {"complete": False}])
def test_scoped_reader_rejects_provenance_or_incomplete_day(monkeypatch, kwargs):
    access, _ = _fake_approved(monkeypatch, **kwargs)
    result = reader.read_google_ads_m6_branch_attribution(
        month_start=date(2026, 10, 1), cutoff_date=date(2026, 10, 12),
        access=access,
    )
    assert result["status"] == "requires_review"
    assert result["rows"] == []
    assert result["scope_attributed_cost"] is None
