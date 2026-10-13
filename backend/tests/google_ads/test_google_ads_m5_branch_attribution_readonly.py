"""M5-CORE: strictly scoped read-only historical Google Ads attribution."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services import marketing_google_ads_branch_attribution_service as service
from app.services.marketing_access import MarketingAccess


def access(*, global_=False, branch_ids=(1,)):
    return MarketingAccess(
        type="GLOBAL" if global_ else "PRIMARY_BRANCH",
        is_global=global_,
        branch_ids=() if global_ else tuple(branch_ids),
        role="ADMINISTRADOR" if global_ else "GERENTE",
        can_edit_inputs=global_,
    )


def mapping(branch_id=1):
    return SimpleNamespace(
        id=branch_id + 10, customer_id=service.CUSTOMER_ID,
        campaign_key="name:" + ("a" * 64 if branch_id == 1 else f"{branch_id:064x}"),
        ad_group_key="name:" + ("b" * 64 if branch_id == 1 else f"{branch_id + 100:064x}"),
        sucursal_canon="VILLAS_DEL_REY" if branch_id == 1 else f"BRANCH_{branch_id}",
        source_upload_id=21499,
        valid_from=date(2026, 9, 24),
        valid_to=date(2026, 10, 8),
        approval_status=service.APPROVAL_STATUS,
        approval_reference=service.APPROVAL_REFERENCE,
        approved_on=date(2026, 10, 12),
    )


def catalog(branch_id=1):
    return SimpleNamespace(
        sucursal_id=branch_id,
        sucursal_canon="VILLAS_DEL_REY" if branch_id == 1 else f"BRANCH_{branch_id}",
        is_track_active=True,
    )


def branch(branch_id=1):
    return SimpleNamespace(sucursal_id=branch_id, operational_status="ACTIVA")


def fact(day, cost=1, branch_id=1):
    m = mapping(branch_id)
    return SimpleNamespace(
        customer_id=service.CUSTOMER_ID,
        campaign_key=m.campaign_key,
        ad_group_key=m.ad_group_key,
        report_date=day,
        source_kind="WAREHOUSE_XLSX",
        source_upload_id=21499,
        currency_code="MXN",
        campaign_id=None, ad_group_id=None,
        cost=Decimal(str(cost)), clicks=2, impressions=10,
        free_pass_conversions=Decimal("0.5000"),
        web_purchase_conversions=Decimal("0.2500"),
    )


def prepare(monkeypatch, *, global_=False, mappings=None, facts=None,
            permitted=(1,), ledger=None):
    calls = {"mapping_scopes": [], "fact_scopes": [], "ledger": 0, "validation": 0}
    monkeypatch.setattr(
        service, "load_visible_marketing_branches",
        lambda _access: ([], tuple(permitted), {}),
    )
    if global_ and permitted == (1,):
        permitted = tuple(range(1, 27))
    if mappings is None:
        mappings = [
            (mapping(i), catalog(i), branch(i))
            for i in (range(1, 27) if global_ else (1,))
        ]
    if facts is None:
        facts = [
            (fact(date(2026, 10, day), branch_id=i), mapping(i), catalog(i))
            for i in (range(1, 27) if global_ else (1,))
            for day in range(1, 9)
        ]
    def scoped_mappings(ids):
        calls["mapping_scopes"].append(ids)
        return mappings
    def scoped_facts(*, branch_ids, start, end):
        calls["fact_scopes"].append((branch_ids, start, end))
        return [
            (f, m, c) for f, m, c in facts
            if start <= f.report_date <= end
        ]
    def ledger_rows(start, end):
        calls["ledger"] += 1
        if not global_:
            pytest.fail("Restricted access queried the global ledger")
        if ledger is not None:
            return ledger
        return [
            SimpleNamespace(report_date=date(2026,10,day),
                            currency_code="MXN", cost=Decimal("27.00"))
            for day in range(1,9)
        ]
    def validate(*args, **kwargs):
        calls["validation"] += 1
        if not global_:
            pytest.fail("Restricted access read the global historical source")
    monkeypatch.setattr(service, "_load_scoped_mapping_rows", scoped_mappings)
    monkeypatch.setattr(service, "_load_scoped_fact_rows", scoped_facts)
    monkeypatch.setattr(service, "_load_global_ledger_rows", ledger_rows)
    monkeypatch.setattr(service, "_validate_historical_source", validate)
    approved_rows = [
        ["Campaign", "Group", mapping(i).campaign_key,
         mapping(i).ad_group_key, mapping(i).sucursal_canon, i, "0.00"]
        for i in range(1, 27)
    ]
    monkeypatch.setattr(
        service, "_load_approved_manifest",
        lambda: {"id": "test", "rows": approved_rows},
    )
    monkeypatch.setattr(
        service, "db",
        SimpleNamespace(session=SimpleNamespace(connection=lambda: object())),
    )
    return calls


def read(*, global_=False, month_start=date(2026,10,1),
         cutoff=date(2026,10,8), branch_ids=(1,)):
    return service.read_google_ads_branch_attribution(
        month_start=month_start,
        cutoff_date=cutoff,
        access=access(global_=global_, branch_ids=branch_ids),
    )


def test_scoped_october_complete_without_ever_reading_global_ledger(monkeypatch):
    calls = prepare(monkeypatch)
    result = read()
    assert result["status"] == "complete"
    assert result["complete_to_cutoff"] is True
    assert result["covered_days"] == result["expected_days"] == 8
    assert result["scope_attributed_cost"] == 8.0
    assert result["rows"] == [{
        "sucursal_id": 1, "cost": 8.0, "clicks": 16,
        "impressions": 80, "free_pass_ads": 4.0, "web_purchase_ads": 2.0,
    }]
    assert "account_cost_observed" not in result
    assert "unassigned_cost_observed" not in result
    assert calls["ledger"] == calls["validation"] == 0
    assert calls["fact_scopes"] == [((1,), date(2026,10,1), date(2026,10,8))]


def test_cutoff_after_october_eighth_is_partial_without_inventing_zeros(monkeypatch):
    prepare(monkeypatch)
    result = read(cutoff=date(2026,10,12))
    assert result["status"] == "partial"
    assert result["complete_to_cutoff"] is False
    assert result["missing_days"] == 4
    assert result["scope_attributed_cost"] == 8.0
    assert result["observed_to"] == "2026-10-08"


def test_september_before_twenty_fourth_is_partial(monkeypatch):
    rows = [
        (fact(date(2026,9,24) + timedelta(days=i)), mapping(), catalog())
        for i in range(7)
    ]
    prepare(monkeypatch, facts=rows)
    result = read(month_start=date(2026,9,1), cutoff=date(2026,9,30))
    assert result["status"] == "partial"
    assert result["covered_days"] == 7
    assert result["missing_days"] == 23


def test_missing_historical_day_fails_closed(monkeypatch):
    facts = [
        (fact(date(2026,10,day)), mapping(), catalog())
        for day in range(1,8)
    ]
    prepare(monkeypatch, facts=facts)
    result = read()
    assert result["status"] == "requires_review"
    assert result["rows"] == []
    assert result["scope_attributed_cost"] is None


@pytest.mark.parametrize("field,value", [
    ("customer_id", "0000000000"),
    ("approval_status", "VERIFIED_OFFICIAL_IDS"),
    ("valid_to", date(2026,10,12)),
    ("source_upload_id", 100),
    ("sucursal_canon", "VILLA_VERDE"),
    ("campaign_key", "name:" + "f" * 64),
    ("ad_group_key", "name:" + "f" * 64),
])
def test_unauthorized_mapping_fails_closed(monkeypatch, field, value):
    m = mapping()
    setattr(m, field, value)
    prepare(monkeypatch, mappings=[(m, catalog(), branch())])
    result = read()
    assert result["status"] == "requires_review"
    assert result["rows"] == []
    assert result["scope_attributed_cost"] is None


def test_no_mapping_is_not_a_zero_spend(monkeypatch):
    calls = prepare(monkeypatch, mappings=[])
    result = read()
    assert result["status"] == "pending_mapping"
    assert result["scope_attributed_cost"] is None
    assert calls["fact_scopes"] == []


def test_no_authorized_branches_runs_no_fact_query(monkeypatch):
    calls = prepare(monkeypatch, permitted=())
    result = read(branch_ids=())
    assert result["status"] == "scope_unavailable"
    assert calls["mapping_scopes"] == calls["fact_scopes"] == []


def test_historical_period_absent_never_reads_mappings(monkeypatch):
    calls = prepare(monkeypatch)
    result = read(month_start=date(2026,11,1), cutoff=date(2026,11,2))
    assert result["status"] == "unavailable"
    assert result["scope_attributed_cost"] is None
    assert calls["mapping_scopes"] == calls["fact_scopes"] == []


def test_global_read_reconciles_without_double_counting(monkeypatch):
    calls = prepare(monkeypatch, global_=True)
    result = read(global_=True)
    assert result["status"] == "complete"
    assert result["account_cost_observed"] == 216.0
    assert result["scope_attributed_cost"] == 208.0
    assert result["unassigned_cost_observed"] == 8.0
    assert result["account_reconciled"] is True
    assert calls["ledger"] == calls["validation"] == 1


def test_global_account_drift_fails_closed(monkeypatch):
    prepare(monkeypatch, global_=True, ledger=[
        SimpleNamespace(report_date=date(2026,10,day),
                        currency_code="MXN", cost=Decimal("0"))
        for day in range(1,9)
    ])
    result = read(global_=True)
    assert result["status"] == "requires_review"
    assert result["rows"] == []
    assert result["scope_attributed_cost"] is None


def test_wrong_fact_source_fails_closed(monkeypatch):
    f = fact(date(2026,10,1))
    f.source_upload_id = 999
    facts = [(f, mapping(), catalog())] + [
        (fact(date(2026,10,day)), mapping(), catalog()) for day in range(2,9)
    ]
    prepare(monkeypatch, facts=facts)
    result = read()
    assert result["status"] == "requires_review"


def test_invalid_dates_rejected():
    with pytest.raises(ValueError, match="Rango M5"):
        read(month_start=date(2026,10,2), cutoff=date(2026,10,1))


def test_global_requires_all_26_exactly_approved_mappings(monkeypatch):
    mappings = [
        (mapping(i), catalog(i), branch(i))
        for i in range(1, 26)
    ]
    calls = prepare(monkeypatch, global_=True, mappings=mappings)
    result = read(global_=True)
    assert result["status"] == "pending_mapping"
    assert result["rows"] == []
    assert calls["ledger"] == 0


def test_regional_partial_mapping_is_not_exposed_as_complete(monkeypatch):
    calls = prepare(monkeypatch, permitted=(1, 2))
    result = read(branch_ids=(1, 2))
    assert result["status"] == "pending_mapping"
    assert result["scope_attributed_cost"] is None
    assert calls["ledger"] == calls["validation"] == 0
