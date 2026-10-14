"""Warehouse structured ingestion of Google Ads daily ad-group detail.

Campaign/day facts remain the account spend authority; group/day facts are
non-additive detail. Never update existing rows or allocate spend to clubs
without an approved mapping.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from flask import current_app

from app.extensions import db
from app.models.google_ads_daily import GoogleAdsDailyMetricORM
from app.models.google_ads_ad_group_daily import GoogleAdsAdGroupDailyMetricORM
from app.utils.warehouse_audit import log_warehouse_audit
from app.warehouse.services.google_ads_daily_ingestion_service import (
    GoogleAdsDailyIngestionError,
    _customer_id,
    _upload_content,
)
from app.warehouse.services.google_ads_ad_group_daily_xlsx_parser import (
    parse_google_ads_ad_group_daily_xlsx,
)
from app.warehouse.services.google_ads_daily_xlsx_parser import (
    GoogleAdsXlsxValidationError,
)

REPORT_TYPE_KEY = "google_ads_ad_group_daily"


class GoogleAdsAdGroupDailyIngestionError(RuntimeError):
    pass


def _assert_campaign_reconciliation(
    *, customer_id: str, parsed
) -> dict:
    """If campaign facts exist, each day/campaign must reconcile exactly.

    Campaigns absent in the group export must have ZERO spend and traffic.
    Missing campaign facts for future dates are allowed; the workbook's
    independently reconciled daily account totals remain mandatory.
    """
    existing = (
        db.session.query(GoogleAdsDailyMetricORM)
        .filter(
            GoogleAdsDailyMetricORM.customer_id == customer_id,
            GoogleAdsDailyMetricORM.report_date.between(
                parsed.date_from, parsed.date_to,
            ),
        )
        .all()
    )
    by_campaign = defaultdict(lambda: (Decimal("0"), 0, 0))
    for row in parsed.rows:
        key = (row.report_date, row.campaign_key)
        cost, clicks, impressions = by_campaign[key]
        by_campaign[key] = (
            cost + row.cost, clicks + row.clicks,
            impressions + row.impressions,
        )
    matched = 0
    for fact in existing:
        key = (fact.report_date, fact.campaign_key)
        expected = (
            Decimal(fact.cost), int(fact.clicks), int(fact.impressions),
        )
        if by_campaign.get(key, (Decimal("0"), 0, 0)) != expected:
            raise GoogleAdsAdGroupDailyIngestionError(
                "No coincide con el histórico campañas-día de Warehouse: "
                f"{fact.campaign_name} ({fact.report_date.isoformat()})."
            )
        matched += 1
    # Also reject non-zero groups for a campaign/day when that day has a
    # complete reference campaign ledger, so renamed campaigns cannot hide
    # under a new provisional name.
    reference_days = {fact.report_date for fact in existing}
    reference_keys = {
        (fact.report_date, fact.campaign_key) for fact in existing
    }
    for key, values in by_campaign.items():
        if key[0] in reference_days and key not in reference_keys:
            if values != (Decimal("0"), 0, 0):
                raise GoogleAdsAdGroupDailyIngestionError(
                    "Grupo con inversión o tráfico sin campaña histórica conciliable."
                )
    return {
        "referenced_campaign_day_rows": matched,
        "campaign_days_reconciled": len(reference_days),
    }


def import_google_ads_ad_group_warehouse_upload(*, warehouse_upload_id: int) -> dict:
    try:
        upload, content = _upload_content(
            warehouse_upload_id, report_type_key=REPORT_TYPE_KEY,
            max_file_bytes=10 * 1024 * 1024,
        )
        parsed = parse_google_ads_ad_group_daily_xlsx(content)
    except (GoogleAdsDailyIngestionError, GoogleAdsXlsxValidationError) as exc:
        raise GoogleAdsAdGroupDailyIngestionError(str(exc)) from exc

    if parsed.date_from != upload.date_from or parsed.date_to != upload.date_to:
        raise GoogleAdsAdGroupDailyIngestionError(
            "Periodo Warehouse distinto del Excel."
        )
    if parsed.date_to >= datetime.now(ZoneInfo("America/Tijuana")).date():
        raise GoogleAdsAdGroupDailyIngestionError(
            "Solo pueden importarse días cerrados."
        )

    try:
        customer_id = _customer_id()
    except GoogleAdsDailyIngestionError as exc:
        raise GoogleAdsAdGroupDailyIngestionError(str(exc)) from exc

    reconciliation = _assert_campaign_reconciliation(
        customer_id=customer_id, parsed=parsed,
    )
    previous = (
        db.session.query(GoogleAdsAdGroupDailyMetricORM)
        .filter(
            GoogleAdsAdGroupDailyMetricORM.customer_id == customer_id,
            GoogleAdsAdGroupDailyMetricORM.report_date.between(
                parsed.date_from, parsed.date_to,
            ),
        )
        .all()
    )
    if len(previous) > 12000:
        raise GoogleAdsAdGroupDailyIngestionError("Demasiados registros previos.")

    by_key = {
        (item.report_date, item.campaign_key, item.ad_group_key): item
        for item in previous
    }
    old_by_day = defaultdict(set)
    new_by_day = defaultdict(set)
    for item in previous:
        old_by_day[item.report_date].add((item.campaign_key, item.ad_group_key))
    for row in parsed.rows:
        new_by_day[row.report_date].add((row.campaign_key, row.ad_group_key))
    for day, old_keys in old_by_day.items():
        if old_keys != new_by_day[day]:
            raise GoogleAdsAdGroupDailyIngestionError(
                f"Catálogo de grupos cambió para {day.isoformat()}; "
                "se requiere reconciliación manual antes de reimportar."
            )

    inserts = []
    unchanged = 0
    fields = (
        "currency_code", "cost", "clicks", "impressions", "conversions",
        "free_pass_conversions", "web_purchase_conversions",
        "conversion_value",
    )
    for row in parsed.rows:
        key = (row.report_date, row.campaign_key, row.ad_group_key)
        item = by_key.get(key)
        if item is not None:
            if any(getattr(item, field) != getattr(row, field) for field in fields):
                raise GoogleAdsAdGroupDailyIngestionError(
                    "Valores Google Ads modificados para "
                    f"{row.ad_group_name} ({row.report_date.isoformat()}); "
                    "corrección tardía requiere reconciliación explícita."
                )
            unchanged += 1
            continue
        inserts.append(GoogleAdsAdGroupDailyMetricORM(
            customer_id=customer_id,
            campaign_id=None, ad_group_id=None,
            campaign_key=row.campaign_key, ad_group_key=row.ad_group_key,
            campaign_name=row.campaign_name, ad_group_name=row.ad_group_name,
            report_date=row.report_date, currency_code=row.currency_code,
            cost=row.cost, clicks=row.clicks, impressions=row.impressions,
            conversions=row.conversions,
            free_pass_conversions=row.free_pass_conversions,
            web_purchase_conversions=row.web_purchase_conversions,
            conversion_value=row.conversion_value,
            source_kind="WAREHOUSE_XLSX", source_upload_id=upload.id,
        ))

    try:
        db.session.add_all(inserts)
        log_warehouse_audit(
            action="GOOGLE_ADS_AD_GROUP_IMPORT",
            performed_by_user_id=upload.uploaded_by_user_id,
            upload_id=upload.id,
            details={
                "customer_id": customer_id,
                "date_from": parsed.date_from.isoformat(),
                "date_to": parsed.date_to.isoformat(),
                "created_rows": len(inserts),
                "unchanged_rows": unchanged,
                "group_day_rows": len(parsed.rows),
                "total_cost_in_file": str(parsed.total_cost),
                "passes_ads": str(parsed.total_free_pass),
                "web_purchases_ads": str(parsed.total_web_purchase),
                **reconciliation,
            },
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Google Ads groups: persistence failed for %s",
            warehouse_upload_id,
        )
        raise GoogleAdsAdGroupDailyIngestionError(
            "No se pudo guardar la carga estructurada Google Ads por grupo."
        ) from None

    return {
        "status": "ingested",
        "source": "WAREHOUSE_XLSX",
        "warehouse_upload_id": upload.id,
        "customer_id": customer_id,
        "date_from": parsed.date_from.isoformat(),
        "date_to": parsed.date_to.isoformat(),
        "group_day_rows": len(parsed.rows),
        "created_rows": len(inserts),
        "unchanged_rows": unchanged,
        "total_cost_in_file": str(parsed.total_cost),
        "passes_ads": str(parsed.total_free_pass),
        "web_purchases_ads": str(parsed.total_web_purchase),
        "campaign_ad_group_ids": "PENDING_EXPLICIT_MAPPING",
        "branch_assignment": "NOT_ASSIGNED",
        **reconciliation,
    }
