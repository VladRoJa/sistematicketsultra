"""M6 approval preflight: synthetic rows; no real uploads, credentials or writes."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace as Row

import pytest

from app.warehouse.services import google_ads_m6_continuity_approval_service as service


class RowMap(dict):
    __getattr__ = dict.__getitem__


class Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class ReadOnlyConnection:
    def __init__(self, campaigns, groups, historical_keys):
        self.campaigns = campaigns
        self.groups = groups
        self.historical_keys = historical_keys

    def execute(self, sql, params):
        statement = str(sql)
        if "SELECT DISTINCT campaign_key" in statement:
            return Result([
                RowMap(campaign_key=ck, ad_group_key=gk)
                for ck, gk in self.historical_keys
            ])
        if "FROM google_ads_ad_group_daily_metrics" in statement:
            return Result(self.groups)
        if "FROM google_ads_daily_metrics" in statement:
            return Result(self.campaigns)
        raise AssertionError("Unexpected SQL query: " + statement)


def _fake_facts():
    days = [service.START + timedelta(days=n) for n in range(4)]
    campaign_keys = ["name:" + format(i + 1, "064x") for i in range(27)]
    group_keys = ["name:" + format(i + 100, "064x") for i in range(43)]
    mapping = [
        dict(campaign_key=campaign_keys[i], ad_group_key=group_keys[i],
             sucursal_canon=f"LAB_BRANCH_{i}")
        for i in range(26)
    ]
    assigned_cost = list(map(Decimal, ("1000", "1200", "1100", "1911.74")))
    unknown_cost = list(map(Decimal, ("73.97", "56.83", "94.34", "125.23")))
    clicks = (449, 501, 454, 726)
    impressions = (4366, 4806, 4586, 7314)
    conversions = (5, 6, 7, 11)
    passes = (4, 5, 5, 9)
    purchases = (1, 1, 2, 2)
    campaign_rows = []
    group_rows = []
    campaign_db = []
    group_db = []
    for n, day in enumerate(days):
        for ci, key in enumerate(campaign_keys):
            row = Row(
                customer_id=service.CUSTOMER_ID,
                campaign_key=key, campaign_name=f"Campaign {ci}",
                report_date=day, currency_code="MXN",
                cost=assigned_cost[n] if ci == 0 else unknown_cost[n] if ci == 26 else Decimal("0"),
                clicks=clicks[n] if ci == 0 else 0,
                impressions=impressions[n] if ci == 0 else 0,
                conversions=Decimal(conversions[n]) if ci == 0 else Decimal("0"),
                conversion_value=Decimal("0"),
            )
            campaign_rows.append(row)
            campaign_db.append(RowMap(
                **vars(row), campaign_id=None,
                source_upload_id=service.CAMPAIGN_UPLOAD_ID, source_kind="WAREHOUSE_XLSX",
            ))
        for gi, gk in enumerate(group_keys):
            ci = gi if gi < 26 else 26
            row = Row(
                customer_id=service.CUSTOMER_ID,
                campaign_key=campaign_keys[ci],
                ad_group_key=gk,
                campaign_name=f"Campaign {ci}", ad_group_name=f"Group {gi}",
                report_date=day, currency_code="MXN",
                cost=assigned_cost[n] if gi == 0 else unknown_cost[n] if gi == 26 else Decimal("0"),
                clicks=clicks[n] if gi == 0 else 0,
                impressions=impressions[n] if gi == 0 else 0,
                conversions=Decimal(conversions[n]) if gi == 0 else Decimal("0"),
                free_pass_conversions=Decimal(passes[n]) if gi == 0 else Decimal("0"),
                web_purchase_conversions=Decimal(purchases[n]) if gi == 0 else Decimal("0"),
                conversion_value=Decimal("0"),
            )
            group_rows.append(row)
            group_db.append(RowMap(
                **vars(row), campaign_id=None, ad_group_id=None,
                source_upload_id=service.GROUP_UPLOAD_ID, source_kind="WAREHOUSE_XLSX",
            ))
    conn = ReadOnlyConnection(campaign_db, group_db, {
        (r.campaign_key, r.ad_group_key) for r in group_rows
    })
    return conn, Row(rows=tuple(campaign_rows)), Row(rows=tuple(group_rows)), mapping


def test_reconciled_26_existing_identities_pass_readonly():
    conn, campaigns, groups, mapping = _fake_facts()
    assert service._verify_facts(conn, campaigns, groups, mapping) == {
        "campaign_day_rows": 108, "group_day_rows": 172,
        "account_cost_mxn": "5562.11", "local_cost_mxn": "5211.74",
        "unassigned_cost_mxn": "350.37",
    }


def test_extra_or_renamed_group_is_rejected_even_with_unchanged_totals():
    conn, campaigns, groups, mapping = _fake_facts()
    original = groups.rows[0]
    other_key = "name:" + "f"*64
    rows = tuple(
        Row(**{**vars(r), "ad_group_key": other_key})
        if r.ad_group_key == original.ad_group_key else r
        for r in groups.rows
    )
    conn.groups = [
        RowMap(**{**dict(r), "ad_group_key": other_key})
        if r["ad_group_key"] == original.ad_group_key else r
        for r in conn.groups
    ]
    with pytest.raises(RuntimeError, match="identidad nueva"):
        service._verify_facts(conn, campaigns, Row(rows=rows), mapping)


def test_wrong_group_source_upload_is_rejected():
    conn, campaigns, groups, mapping = _fake_facts()
    conn.groups[0]["source_upload_id"] = 21499
    with pytest.raises(RuntimeError, match="procedencia incorrecta"):
        service._verify_facts(conn, campaigns, groups, mapping)


def test_missing_campaign_day_is_rejected():
    conn, campaigns, groups, mapping = _fake_facts()
    conn.campaigns.pop()
    with pytest.raises(RuntimeError, match="faltan filas estructuradas"):
        service._verify_facts(conn, campaigns, groups, mapping)


def test_cost_drift_is_rejected():
    conn, campaigns, groups, mapping = _fake_facts()
    conn.campaigns[0]["cost"] += Decimal("0.01")
    with pytest.raises(RuntimeError, match="campañas estructuradas difieren"):
        service._verify_facts(conn, campaigns, groups, mapping)


def test_direct_apply_is_blocked_even_with_admicorp_user_id():
    # An arbitrary numeric user ID does not authenticate the CLI operator.
    for actor_id in (None, 47, 1):
        with pytest.raises(RuntimeError, match="APPLY deshabilitado"):
            service.run_on_connection(
                None, apply=True, approved_by_user_id=actor_id,
                parsed_files=None,
            )


def test_public_approval_entry_rejects_all_write_attempts(monkeypatch):
    def should_not_be_called(*args, **kwargs):
        raise AssertionError("No file or DB reads should occur for rejected APPLY")

    monkeypatch.setattr(service, "_load_m5", should_not_be_called)
    monkeypatch.setattr(service, "_load_files", should_not_be_called)
    for actor_id in (None, 47, 1):
        with pytest.raises(RuntimeError, match="APPLY deshabilitado"):
            service.run_approval(apply=True, approved_by_user_id=actor_id)


def test_cli_has_no_apply_option():
    from pathlib import Path

    cli_path = (
        Path(__file__).resolve().parents[2]
        / "scripts/apply_google_ads_m6_continuity.py"
    )
    code = cli_path.read_text(encoding="utf-8")
    assert "parser.add_argument(\"--apply\"" not in code
    assert "parser.add_argument(\"--approved-by-user-id\"" not in code
    assert "parser.parse_args()" in code
    assert 'result = run_approval()' in code
