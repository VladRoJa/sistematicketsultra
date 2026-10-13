"""M6 guarded one-time approval for continuing the exact 26 M5 identities.

The approval is independent of daily Warehouse uploads. This module only
authorizes the identity relation; it never updates M5 mappings, original
facts, Funnel or any daily ingestion scheduler.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from hashlib import sha256

import sqlalchemy as sa

from app.extensions import db
from app.warehouse.services.google_ads_daily_ingestion_service import _upload_content
from app.warehouse.services.google_ads_daily_xlsx_parser import parse_google_ads_daily_xlsx
from app.warehouse.services.google_ads_ad_group_daily_xlsx_parser import parse_google_ads_ad_group_daily_xlsx
from app.warehouse.services.google_ads_m5_identity_seed_service import (
    _load as _load_m5,
    _verify_original_file as _verify_m5_raw,
    run_on_connection as _m5_preflight,
)

CUSTOMER_ID = "2739125201"
M5_REFERENCE = "GOOGLE_ADS_M5_IDENTITY_20261012_V1"
M6_REFERENCE = "GOOGLE_ADS_M6_CONTINUITY_20261013_V1"
START = date(2026, 10, 9)
END = date(2026, 10, 12)
CAMPAIGN_UPLOAD_ID = 21604
GROUP_UPLOAD_ID = 21605
DAYS = {START + timedelta(days=n) for n in range(4)}
ACCOUNT_TOTAL = Decimal("5562.11")
LOCAL_TOTAL = Decimal("5211.74")
UNASSIGNED_TOTAL = Decimal("350.37")


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise RuntimeError("Google Ads M6: " + reason)


def _triples(manifest: dict) -> list[dict]:
    _require(
        manifest["id"] == M5_REFERENCE
        and manifest["customer_id"] == CUSTOMER_ID,
        "manifiesto M5 no autorizado",
    )
    return [
        {"campaign_key": row[2], "ad_group_key": row[3], "sucursal_canon": row[4]}
        for row in manifest["rows"]
    ]


def _load_files():
    campaign_upload, campaign_raw = _upload_content(
        CAMPAIGN_UPLOAD_ID, report_type_key="google_ads_campaign_daily",
    )
    group_upload, group_raw = _upload_content(
        GROUP_UPLOAD_ID, report_type_key="google_ads_ad_group_daily",
    )
    for upload, raw in ((campaign_upload, campaign_raw), (group_upload, group_raw)):
        _require(
            upload.date_from == START and upload.date_to == END
            and upload.source_file_deleted_at is None
            and upload.file_hash_sha256 == sha256(raw).hexdigest()
            and upload.file_size_bytes == len(raw),
            f"upload RAW {upload.id} no íntegro o período distinto",
        )
    campaigns = parse_google_ads_daily_xlsx(campaign_raw)
    groups = parse_google_ads_ad_group_daily_xlsx(group_raw)
    _require(
        (campaigns.date_from, campaigns.date_to) == (START, END)
        and (groups.date_from, groups.date_to) == (START, END),
        "fechas XLSX no coinciden con el período aprobado",
    )
    return campaigns, groups


def _campaign_values(item) -> tuple:
    return (
        item.campaign_name, item.currency_code,
        Decimal(item.cost), int(item.clicks), int(item.impressions),
        Decimal(item.conversions), Decimal(item.conversion_value),
    )


def _group_values(item) -> tuple:
    return (
        item.campaign_name, item.ad_group_name, item.currency_code,
        Decimal(item.cost), int(item.clicks), int(item.impressions),
        Decimal(item.conversions), Decimal(item.free_pass_conversions),
        Decimal(item.web_purchase_conversions), Decimal(item.conversion_value),
    )


def _check_fact_provenance(rows: list, *, upload_id: int) -> None:
    _require(all(
        r["customer_id"] == CUSTOMER_ID
        and r["source_upload_id"] == upload_id
        and r["source_kind"] == "WAREHOUSE_XLSX"
        and r["campaign_id"] is None
        and (("ad_group_id" not in r) or r["ad_group_id"] is None)
        and r["report_date"] in DAYS
        and r["currency_code"] == "MXN"
        for r in rows
    ), f"procedencia incorrecta para upload {upload_id}")


def _verify_facts(conn, campaigns, groups, identities: list[dict]) -> dict:
    params = {"customer": CUSTOMER_ID, "start": START, "end": END}
    campaign_db = conn.execute(sa.text("""
        SELECT customer_id, campaign_id, campaign_key, campaign_name,
               report_date, currency_code, cost, clicks, impressions,
               conversions, conversion_value, source_kind, source_upload_id
        FROM google_ads_daily_metrics
        WHERE customer_id = :customer AND report_date BETWEEN :start AND :end
    """), params).mappings().all()
    group_db = conn.execute(sa.text("""
        SELECT customer_id, campaign_id, ad_group_id, campaign_key, ad_group_key,
               campaign_name, ad_group_name, report_date, currency_code, cost,
               clicks, impressions, conversions, free_pass_conversions,
               web_purchase_conversions, conversion_value, source_kind,
               source_upload_id
        FROM google_ads_ad_group_daily_metrics
        WHERE customer_id = :customer AND report_date BETWEEN :start AND :end
    """), params).mappings().all()
    _require(
        len(campaigns.rows) == len(campaign_db) == 108
        and len(groups.rows) == len(group_db) == 172,
        "faltan filas estructuradas 108 campañas / 172 grupos",
    )
    _check_fact_provenance(campaign_db, upload_id=CAMPAIGN_UPLOAD_ID)
    _check_fact_provenance(group_db, upload_id=GROUP_UPLOAD_ID)

    expected_c = {(r.report_date, r.campaign_key): _campaign_values(r) for r in campaigns.rows}
    actual_c = {(r["report_date"], r["campaign_key"]): _campaign_values(r) for r in campaign_db}
    expected_g = {
        (r.report_date, r.campaign_key, r.ad_group_key): _group_values(r)
        for r in groups.rows
    }
    actual_g = {
        (r["report_date"], r["campaign_key"], r["ad_group_key"]): _group_values(r)
        for r in group_db
    }
    _require(
        len(expected_c) == len(actual_c) == 108 and actual_c == expected_c,
        "campañas estructuradas difieren del XLSX original",
    )
    _require(
        len(expected_g) == len(actual_g) == 172 and actual_g == expected_g,
        "grupos estructurados difieren del XLSX original",
    )

    all_keys = {(r.campaign_key, r.ad_group_key) for r in groups.rows}
    historical_keys = {
        (r["campaign_key"], r["ad_group_key"])
        for r in conn.execute(sa.text("""
            SELECT DISTINCT campaign_key, ad_group_key
            FROM google_ads_ad_group_daily_metrics
            WHERE customer_id = :customer
              AND source_upload_id = 21499
              AND report_date BETWEEN DATE '2026-09-24' AND DATE '2026-10-08'
        """), {"customer": CUSTOMER_ID}).mappings().all()
    }
    _require(
        len(all_keys) == len(historical_keys) == 43
        and all_keys == historical_keys,
        "identidad nueva, perdida o renombrada frente al catálogo M5",
    )
    for day in DAYS:
        _require(
            {r.campaign_key for r in campaigns.rows if r.report_date == day}
            == {r.campaign_key for r in campaigns.rows}
            and {
                (r.campaign_key, r.ad_group_key) for r in groups.rows if r.report_date == day
            } == all_keys,
            "cobertura diaria de campañas/grupos incompleta",
        )

    approved = {(row["campaign_key"], row["ad_group_key"]) for row in identities}
    _require(len(approved) == len(identities) == 26, "26 asociaciones no únicas")
    local_total = sum(
        (r.cost for r in groups.rows
         if (r.campaign_key, r.ad_group_key) in approved),
        Decimal("0"),
    )
    account_total = sum((r.cost for r in campaigns.rows), Decimal("0"))
    group_total = sum((r.cost for r in groups.rows), Decimal("0"))
    _require(
        account_total == group_total == ACCOUNT_TOTAL
        and local_total == LOCAL_TOTAL
        and account_total - local_total == UNASSIGNED_TOTAL,
        "total de cuenta, local o no asignado distinto de evidencia aprobada",
    )
    _require(
        sum((r.clicks for r in campaigns.rows), 0)
        == sum((r.clicks for r in groups.rows), 0) == 2130
        and sum((r.impressions for r in campaigns.rows), 0)
        == sum((r.impressions for r in groups.rows), 0) == 21072
        and sum((r.conversions for r in campaigns.rows), Decimal("0"))
        == sum((r.conversions for r in groups.rows), Decimal("0")) == 29,
        "clics, impresiones o conversiones no concilian",
    )
    _require(
        sum((r.free_pass_conversions for r in groups.rows), Decimal("0")) == 23
        and sum((r.web_purchase_conversions for r in groups.rows), Decimal("0")) == 6,
        "acciones Ads no concilian",
    )

    totals_by_campaign_day = defaultdict(lambda: [Decimal("0"), 0, 0])
    for row in groups.rows:
        metrics = totals_by_campaign_day[(row.report_date, row.campaign_key)]
        metrics[0] += row.cost
        metrics[1] += row.clicks
        metrics[2] += row.impressions
    for row in campaigns.rows:
        _require(
            tuple(totals_by_campaign_day[(row.report_date, row.campaign_key)])
            == (row.cost, row.clicks, row.impressions),
            "campaña/día y grupos/día no concilian",
        )
    _require(
        {(row.report_date, row.campaign_key) for row in groups.rows}
        <= set(expected_c),
        "grupo con campaña/día ausente",
    )
    return {
        "campaign_day_rows": 108, "group_day_rows": 172,
        "account_cost_mxn": str(account_total),
        "local_cost_mxn": str(local_total),
        "unassigned_cost_mxn": str(account_total - local_total),
    }


def _check_existing(conn, identities: list[dict]) -> tuple[int | None, dict | None]:
    versions = conn.execute(sa.text("""
        SELECT id, customer_id, approval_reference, source_approval_reference,
               valid_from, valid_to, source_campaign_upload_id,
               source_ad_group_upload_id, approved_by_user_id, approved_on
        FROM google_ads_branch_approval_versions
        WHERE customer_id = :customer
    """), {"customer": CUSTOMER_ID}).mappings().all()
    _require(len(versions) <= 1, "versiones M6 múltiples o superpuestas")
    if not versions:
        _require(not conn.execute(sa.text(
            "SELECT id FROM google_ads_branch_approved_identities LIMIT 1"
        )).first(), "identidades M6 huérfanas o ajenas")
        return None, None
    version = versions[0]
    _require(
        version["approval_reference"] == M6_REFERENCE
        and version["source_approval_reference"] == M5_REFERENCE
        and version["valid_from"] == START
        and version["valid_to"] is None
        and version["source_campaign_upload_id"] == CAMPAIGN_UPLOAD_ID
        and version["source_ad_group_upload_id"] == GROUP_UPLOAD_ID,
        "versión existente ajena a la aprobación M6 inicial",
    )
    existing = conn.execute(sa.text("""
        SELECT campaign_key, ad_group_key, sucursal_canon
        FROM google_ads_branch_approved_identities
        WHERE approval_version_id = :version_id
    """), {"version_id": version["id"]}).mappings().all()
    _require(
        len(existing) == 26
        and {(r["campaign_key"], r["ad_group_key"], r["sucursal_canon"]) for r in existing}
        == {(r["campaign_key"], r["ad_group_key"], r["sucursal_canon"]) for r in identities},
        "identidades M6 existentes no concilian con M5",
    )
    return int(version["id"]), version


def run_on_connection(conn, *, apply: bool, approved_by_user_id: int | None, parsed_files) -> dict:
    """Read-only preflight; reject direct approval until authenticated workflow."""
    _require(
        not apply and approved_by_user_id is None,
        "APPLY deshabilitado: se requiere identidad autenticada en backend.",
    )
    data = _load_m5()
    original = _m5_preflight(conn, apply=False)
    _require(
        original["previous_identities"] == original["approved_identities"] == 26,
        "M5 no está íntegramente aprobado",
    )
    identities = _triples(data)
    _require(
        len({r["sucursal_canon"] for r in identities}) == 26,
        "sucursales M5 duplicadas",
    )
    campaigns, groups = parsed_files
    metrics = _verify_facts(conn, campaigns, groups, identities)
    existing_id, existing = _check_existing(conn, identities)

    return {
        "action": "CHECK_ONLY",
        "customer_id": CUSTOMER_ID,
        "approval_reference": M6_REFERENCE,
        "approved_identities": 26,
        "already_approved": existing_id is not None,
        "approval_version_id": existing_id,
        "source_campaign_upload_id": CAMPAIGN_UPLOAD_ID,
        "source_ad_group_upload_id": GROUP_UPLOAD_ID,
        "valid_from": START.isoformat(),
        "valid_to": None,
        **metrics,
    }


def run_approval(*, apply: bool = False, approved_by_user_id: int | None = None) -> dict:
    """Always read-only: approval requires a future authenticated admin action."""
    _require(
        not apply and approved_by_user_id is None,
        "APPLY deshabilitado: se requiere identidad autenticada en backend.",
    )
    _verify_m5_raw(_load_m5())
    files = _load_files()
    with db.engine.connect() as conn:
        return run_on_connection(
            conn, apply=False, approved_by_user_id=None, parsed_files=files,
        )
