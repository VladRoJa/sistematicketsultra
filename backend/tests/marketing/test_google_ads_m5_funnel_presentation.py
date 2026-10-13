"""M5-FUNNEL: adding optional Ads branch evidence cannot change Meta KPIs."""
from __future__ import annotations

from copy import deepcopy
from datetime import date

import pytest

from app.services import marketing_sales_funnel_cutoff_service as cutoff
from app.services.marketing_access import MarketingAccess


def _access(*, global_: bool):
    return MarketingAccess(
        type="GLOBAL" if global_ else "PRIMARY_BRANCH",
        is_global=global_, branch_ids=() if global_ else (1,),
        role="ADMINISTRADOR" if global_ else "GERENTE", can_edit_inputs=False,
    )


@pytest.mark.parametrize("global_", [False, True])
def test_m5_attaches_independent_payload_without_changing_meta(monkeypatch, global_):
    payload = {
        "summary": {"investment": 500.0, "sales_total": 14, "cpl": 8.50},
        "branches": [
            {"sucursal_id": 1, "investment": 100.0, "sales_total": 4},
            {"sucursal_id": 2, "investment": 400.0, "sales_total": 10},
        ],
        "investment_sources": {
            "meta_assigned": 500.0,
            "google_ads": {"amount": None if not global_ else 200.0},
            "combined": None,
            "existing_cpl_cpt_cac_basis": "META_ASSIGNED_ONLY",
        },
        "data_quality": {"limitations": [], "crm_history_available": True},
    }
    original = deepcopy(payload)
    captured = []
    extra = {
        "status": "partial", "rows": [{"sucursal_id": 1, "cost": 25.0}],
        "scope_attributed_cost": 25.0,
        "complete_to_cutoff": False,
    }

    def reader(*, month_start, cutoff_date, access):
        captured.append((month_start, cutoff_date, access))
        return extra

    monkeypatch.setattr(cutoff, "read_google_ads_branch_attribution", reader)
    access = _access(global_=global_)
    cutoff._attach_google_ads_branch_attribution(
        payload=payload,
        month_start=date(2026, 10, 1),
        cutoff_date=date(2026, 10, 8),
        access=access,
    )
    assert captured == [(date(2026, 10, 1), date(2026, 10, 8), access)]
    assert payload["google_ads_branch_attribution"] is extra
    assert all(payload[key] == original[key] for key in original)
    assert payload["investment_sources"]["existing_cpl_cpt_cac_basis"] == "META_ASSIGNED_ONLY"


def test_m5_reader_failure_never_overwrites_existing_funnel_payload(monkeypatch):
    payload = {"summary": {"investment": 120}, "branches": [
        {"sucursal_id": 1, "investment": 120},
    ]}
    old = deepcopy(payload)

    def fail(**kwargs):
        raise RuntimeError("Source requires review")

    monkeypatch.setattr(cutoff, "read_google_ads_branch_attribution", fail)
    cutoff._attach_google_ads_branch_attribution(
        payload=payload,
        month_start=date(2026, 10, 1),
        cutoff_date=date(2026, 10, 8),
        access=_access(global_=False),
    )
    evidence = payload.pop("google_ads_branch_attribution")
    assert payload == old
    assert evidence["status"] == "requires_review"
    assert evidence["scope_attributed_cost"] is None
    assert evidence["rows"] == []
    assert "account_cost_observed" not in evidence
    assert "unassigned_cost_observed" not in evidence
    assert evidence["complete_to_cutoff"] is False
