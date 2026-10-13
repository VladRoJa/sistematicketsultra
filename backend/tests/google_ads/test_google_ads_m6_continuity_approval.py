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


def test_approval_requires_admin_admicorp(monkeypatch):
    conn, campaigns, groups, mapping = _fake_facts()
    manifest = {
        "id": service.M5_REFERENCE, "customer_id": service.CUSTOMER_ID,
        "rows": [
            [None, None, item["campaign_key"], item["ad_group_key"],
             item["sucursal_canon"], i + 1, "0"]
            for i, item in enumerate(mapping)
        ],
    }
    monkeypatch.setattr(service, "_load_m5", lambda: manifest)
    monkeypatch.setattr(service, "_m5_preflight", lambda conn, apply: {
        "previous_identities": 26, "approved_identities": 26,
    })
    monkeypatch.setattr(service, "_check_existing", lambda conn, identities: (None, None))
    monkeypatch.setattr(service, "_verify_facts", lambda conn, c, g, ids: {})
    with pytest.raises(RuntimeError, match="requiere identificador"):
        service.run_on_connection(conn, apply=True, approved_by_user_id=None,
                                  parsed_files=(campaigns, groups))
