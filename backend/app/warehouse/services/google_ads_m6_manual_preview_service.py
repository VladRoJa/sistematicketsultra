"""Read-only Google Ads M6 manual XLSX pair preview.

Authenticates the *current* ADMICORP principal against PostgreSQL, not JWT
role claims. The historical reference is frozen M6 09-12-oct RAW (21604/21605)
plus the M5 authorized 26-identity manifest. Does not issue M6 approval, stage
RAW, import structured facts or publish the Funnel.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from hashlib import sha256
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from flask_jwt_extended import get_jwt_identity

from app.extensions import db
from app.warehouse.services.google_ads_daily_xlsx_parser import (
    GoogleAdsXlsxValidationError, parse_google_ads_daily_xlsx,
)
from app.warehouse.services.google_ads_ad_group_daily_xlsx_parser import (
    parse_google_ads_ad_group_daily_xlsx,
)
from app.warehouse.services.google_ads_m6_daily_pair_preflight import (
    GoogleAdsM6DailyPairError, preflight_daily_pair,
)
from app.warehouse.services.google_ads_m6_continuity_approval_service import (
    CUSTOMER_ID, START, END, _load_files, _triples, _load_m5,
)

MAX_CAMPAIGN_BYTES = 8 * 1024 * 1024
MAX_GROUP_BYTES = 10 * 1024 * 1024


class GoogleAdsM6ManualPreviewError(RuntimeError):
    """Safe diagnostic only; never include XLSX data or names."""


def require_current_admicorp() -> int:
    """Validate current DB user; neither JWT roles nor client IDs grant access."""
    identity = get_jwt_identity()
    try:
        user_id = int(identity)
    except (TypeError, ValueError):
        raise PermissionError("FORBIDDEN") from None
    if user_id <= 0:
        raise PermissionError("FORBIDDEN")
    with db.engine.connect() as connection:
        principal = connection.execute(sa.text("""
            SELECT id, username, rol FROM users WHERE id = :user_id
        """), {"user_id": user_id}).mappings().one_or_none()
    if not principal or (
        str(principal["username"]).strip().casefold() != "admicorp"
        or str(principal["rol"]).strip().upper() != "ADMINISTRADOR"
    ):
        raise PermissionError("FORBIDDEN")
    return user_id


def _historical_catalog() -> tuple[set[str], set[tuple[str, str]], dict]:
    """Use previously validated RAW files, never derive approval from new XLSX."""
    campaign_baseline, group_baseline = _load_files()
    if (
        (campaign_baseline.date_from, campaign_baseline.date_to) != (START, END)
        or (group_baseline.date_from, group_baseline.date_to) != (START, END)
    ):
        raise GoogleAdsM6ManualPreviewError("BASELINE_PERIOD_MISMATCH")

    campaign_by_day: dict[date, set[str]] = {}
    for row in campaign_baseline.rows:
        campaign_by_day.setdefault(row.report_date, set()).add(row.campaign_key)
    group_by_day: dict[date, set[tuple[str, str]]] = {}
    for row in group_baseline.rows:
        group_by_day.setdefault(row.report_date, set()).add(
            (row.campaign_key, row.ad_group_key)
        )
    days = {START + timedelta(days=i) for i in range((END - START).days + 1)}
    campaigns = set.union(*campaign_by_day.values()) if campaign_by_day else set()
    groups = set.union(*group_by_day.values()) if group_by_day else set()
    if (len(campaigns) != 27 or len(groups) != 43
            or set(campaign_by_day) != days or set(group_by_day) != days
            or any(keys != campaigns for keys in campaign_by_day.values())
            or any(keys != groups for keys in group_by_day.values())):
        raise GoogleAdsM6ManualPreviewError("HISTORICAL_CATALOG_DRIFT")

    identities = _triples(_load_m5())
    mapped = {
        (row["campaign_key"], row["ad_group_key"]): row["sucursal_canon"]
        for row in identities
    }
    if (len(identities) != len(mapped) or len(mapped) != 26
            or len(set(mapped.values())) != 26 or not set(mapped) <= groups):
        raise GoogleAdsM6ManualPreviewError("M5_IDENTITY_CATALOG_DRIFT")
    return campaigns, groups, mapped


def preview_manual_pair(*, campaign_bytes: bytes, group_bytes: bytes,
                        today_local: date | None = None) -> dict:
    """Pure preview after current-DB authorization; never write or approve."""
    if (
        not isinstance(campaign_bytes, bytes)
        or not 0 < len(campaign_bytes) <= MAX_CAMPAIGN_BYTES
        or not isinstance(group_bytes, bytes)
        or not 0 < len(group_bytes) <= MAX_GROUP_BYTES
    ):
        raise GoogleAdsM6ManualPreviewError("INVALID_XLSX_SIZE")
    today = today_local or datetime.now(ZoneInfo("America/Tijuana")).date()
    try:
        campaign = parse_google_ads_daily_xlsx(campaign_bytes)
        group = parse_google_ads_ad_group_daily_xlsx(group_bytes)
    except GoogleAdsXlsxValidationError:
        raise GoogleAdsM6ManualPreviewError("INVALID_GOOGLE_ADS_XLSX") from None
    if campaign.date_from != group.date_from or campaign.date_to != group.date_to:
        raise GoogleAdsM6ManualPreviewError("PAIR_PERIOD_MISMATCH")

    keys, pairs, mapping = _historical_catalog()
    try:
        check = preflight_daily_pair(
            business_date=campaign.date_from,
            today_local=today, campaign_report=campaign,
            group_report=group,
            historical_campaign_keys=keys,
            historical_group_pairs=pairs,
            approved_branch_by_pair=mapping,
        )
    except GoogleAdsM6DailyPairError as exc:
        raise GoogleAdsM6ManualPreviewError(str(exc)) from None

    return {
        **check,
        "customer_id": CUSTOMER_ID,
        "campaign_sha256": sha256(campaign_bytes).hexdigest(),
        "ad_group_sha256": sha256(group_bytes).hexdigest(),
        "historical_identity_reference": "M5_MANIFEST_MATCH_ONLY",
        "initial_m6_approval_verified": False,
        "ready_to_confirm": False,
        "eligible_for_structured_ingestion": False,
        "eligible_for_publication": False,
    }
