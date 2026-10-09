"""Google Ads M2: narrow, synchronous, strictly read-only REST client.

No Ads mutations, DB writes, schedulers, caching or raw token responses.
Only fixed GAQL queries against the configured customer are permitted.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import os
import re

import requests
from cryptography.fernet import InvalidToken

from app.extensions import db
from app.models.google_ads_oauth import GoogleAdsOAuthCredentialORM
from app.routes.google_ads_oauth_routes import TOKEN_ENDPOINT, _settings


ADS_API_ORIGIN = "https://googleads.googleapis.com"
API_VERSION_DEFAULT = "v25"  # Supported on 2026-10-09; check sunset schedule regularly.
MAX_DAYS = 31
MAX_REPORT_ROWS = 5000
MAX_API_BATCHES = 100


class GoogleAdsReadError(Exception):
    """Public error must never include provider payload or credentials."""

    def __init__(self, code: str, status: int):
        self.code = code
        self.status = status
        super().__init__(code)


def _digits(value: str) -> str:
    return str(value or "").replace("-", "").strip()


def _read_settings() -> dict:
    # M2 has its own kill switch; M1 consent may be enabled independently.
    if os.getenv("GOOGLE_ADS_READONLY_ENABLED", "").lower().strip() != "true":
        raise GoogleAdsReadError("GOOGLE_ADS_READONLY_DISABLED", 503)
    oauth_settings = _settings()
    if oauth_settings is None:
        raise GoogleAdsReadError("GOOGLE_ADS_OAUTH_DISABLED_OR_UNCONFIGURED", 503)

    version = os.getenv("GOOGLE_ADS_API_VERSION", API_VERSION_DEFAULT).strip()
    if not re.fullmatch(r"v[0-9]{1,2}", version):
        raise GoogleAdsReadError("GOOGLE_ADS_API_VERSION_INVALID", 503)

    login_customer_id = _digits(os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", ""))
    if login_customer_id and not re.fullmatch(r"[0-9]{10}", login_customer_id):
        raise GoogleAdsReadError("GOOGLE_ADS_LOGIN_CUSTOMER_ID_INVALID", 503)

    return {
        **oauth_settings,
        "api_version": version,
        "login_customer_id": login_customer_id or None,
    }


def _load_refresh_token(settings: dict) -> str:
    record = db.session.get(GoogleAdsOAuthCredentialORM, 1)
    if record is None:
        raise GoogleAdsReadError("GOOGLE_ADS_NOT_CONNECTED", 409)
    # Do not accidentally use an OAuth grant saved for another Ads customer.
    if record.customer_id != settings["customer_id"]:
        raise GoogleAdsReadError("GOOGLE_ADS_CUSTOMER_BINDING_MISMATCH", 409)
    try:
        token = settings["fernet"].decrypt(
            record.encrypted_refresh_token.encode("ascii"),
        ).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError):
        raise GoogleAdsReadError("GOOGLE_ADS_REFRESH_TOKEN_UNREADABLE", 503) from None
    if not token:
        raise GoogleAdsReadError("GOOGLE_ADS_REFRESH_TOKEN_UNREADABLE", 503)
    return token


def _json_payload(response, *, expected_type):
    try:
        body = response.json()
    except (ValueError, TypeError):
        raise GoogleAdsReadError("GOOGLE_ADS_INVALID_PROVIDER_RESPONSE", 502) from None
    if not isinstance(body, expected_type):
        raise GoogleAdsReadError("GOOGLE_ADS_INVALID_PROVIDER_RESPONSE", 502)
    return body


def _access_token(settings: dict, refresh_token: str) -> str:
    try:
        reply = requests.post(
            TOKEN_ENDPOINT,
            data={
                "client_id": settings["client_id"],
                "client_secret": settings["client_secret"],
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=(3, 12),
            allow_redirects=False,
        )
    except requests.RequestException:
        raise GoogleAdsReadError("GOOGLE_ADS_OAUTH_UPSTREAM_UNAVAILABLE", 502) from None
    if reply.status_code == 400:
        # Never return Google's free-form message (may contain sensitive data).
        raise GoogleAdsReadError("GOOGLE_ADS_REAUTHORIZATION_REQUIRED", 409)
    if reply.status_code != 200:
        raise GoogleAdsReadError("GOOGLE_ADS_OAUTH_UPSTREAM_ERROR", 502)
    body = _json_payload(reply, expected_type=dict)
    token = body.get("access_token")
    if not isinstance(token, str) or not token.strip():
        raise GoogleAdsReadError("GOOGLE_ADS_INVALID_PROVIDER_RESPONSE", 502)
    return token


def _headers(settings: dict, access_token: str, *, for_manager: bool) -> dict:
    headers = {
        "Authorization": "Bearer " + access_token,
        "Content-Type": "application/json",
    }
    if for_manager and settings["login_customer_id"]:
        headers["login-customer-id"] = settings["login_customer_id"]
    return headers


def _google_response(response):
    if response.status_code in (401, 403):
        raise GoogleAdsReadError("GOOGLE_ADS_ACCOUNT_ACCESS_DENIED", 502)
    if response.status_code == 429:
        raise GoogleAdsReadError("GOOGLE_ADS_API_QUOTA_OR_RATE_LIMIT", 503)
    if response.status_code != 200:
        raise GoogleAdsReadError("GOOGLE_ADS_API_UPSTREAM_ERROR", 502)
    if response.headers.get("Location"):
        raise GoogleAdsReadError("GOOGLE_ADS_API_UNEXPECTED_REDIRECT", 502)
    return response


def _get_accessible(settings: dict, access_token: str) -> list[str]:
    url = (
        f"{ADS_API_ORIGIN}/{settings['api_version']}"
        "/customers:listAccessibleCustomers"
    )
    try:
        reply = requests.get(
            url,
            headers=_headers(settings, access_token, for_manager=False),
            timeout=(3, 20),
            allow_redirects=False,
        )
    except requests.RequestException:
        raise GoogleAdsReadError("GOOGLE_ADS_API_UPSTREAM_UNAVAILABLE", 502) from None
    payload = _json_payload(_google_response(reply), expected_type=dict)
    names = payload.get("resourceNames", [])
    if not isinstance(names, list) or not all(isinstance(x, str) for x in names):
        raise GoogleAdsReadError("GOOGLE_ADS_INVALID_PROVIDER_RESPONSE", 502)
    # Direct access list is NOT a complete list of MCC-managed child accounts.
    ids = []
    for name in names:
        match = re.fullmatch(r"customers/([0-9]{10})", name)
        if not match:
            raise GoogleAdsReadError("GOOGLE_ADS_INVALID_PROVIDER_RESPONSE", 502)
        ids.append(match.group(1))
    return sorted(set(ids))


def _search_stream(settings: dict, access_token: str, query: str) -> list[dict]:
    url = (
        f"{ADS_API_ORIGIN}/{settings['api_version']}"
        f"/customers/{settings['customer_id']}/googleAds:searchStream"
    )
    try:
        reply = requests.post(
            url,
            json={"query": query},
            headers=_headers(settings, access_token, for_manager=True),
            timeout=(3, 30),
            allow_redirects=False,
        )
    except requests.RequestException:
        raise GoogleAdsReadError("GOOGLE_ADS_API_UPSTREAM_UNAVAILABLE", 502) from None
    batches = _json_payload(_google_response(reply), expected_type=list)
    if len(batches) > MAX_API_BATCHES:
        raise GoogleAdsReadError("GOOGLE_ADS_RESPONSE_TOO_LARGE", 502)
    rows: list[dict] = []
    for batch in batches:
        if not isinstance(batch, dict):
            raise GoogleAdsReadError("GOOGLE_ADS_INVALID_PROVIDER_RESPONSE", 502)
        results = batch.get("results", [])
        if not isinstance(results, list):
            raise GoogleAdsReadError("GOOGLE_ADS_INVALID_PROVIDER_RESPONSE", 502)
        if len(rows) + len(results) > MAX_REPORT_ROWS:
            # Fail explicitly instead of silently truncating any campaigns/dates.
            raise GoogleAdsReadError("GOOGLE_ADS_RESPONSE_TOO_LARGE", 502)
        if not all(isinstance(row, dict) for row in results):
            raise GoogleAdsReadError("GOOGLE_ADS_INVALID_PROVIDER_RESPONSE", 502)
        rows.extend(results)
    return rows


def _account(settings: dict, access_token: str) -> dict:
    rows = _search_stream(
        settings,
        access_token,
        "SELECT customer.id, customer.descriptive_name, "
        "customer.currency_code, customer.time_zone, customer.manager "
        "FROM customer LIMIT 1",
    )
    if len(rows) != 1 or not isinstance(rows[0].get("customer"), dict):
        raise GoogleAdsReadError("GOOGLE_ADS_ACCOUNT_RESPONSE_INVALID", 502)
    info = rows[0]["customer"]
    if str(info.get("id", "")) != settings["customer_id"]:
        raise GoogleAdsReadError("GOOGLE_ADS_CUSTOMER_ID_UNEXPECTED", 502)
    currency = info.get("currencyCode")
    timezone = info.get("timeZone")
    if (
        not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency)
        or not isinstance(timezone, str) or not timezone
    ):
        raise GoogleAdsReadError("GOOGLE_ADS_ACCOUNT_RESPONSE_INVALID", 502)
    return {
        "customer_id": settings["customer_id"],
        "descriptive_name": str(info.get("descriptiveName") or ""),
        "currency_code": currency,
        "timezone": timezone,
        "manager": info.get("manager") is True,
    }


def _get_client() -> tuple[dict, str]:
    settings = _read_settings()
    refresh_token = _load_refresh_token(settings)
    return settings, _access_token(settings, refresh_token)


def verify_account() -> dict:
    settings, token = _get_client()
    accessible = _get_accessible(settings, token)
    # This read against the EXACT bound customer is the actual access proof.
    account = _account(settings, token)
    return {
        "account_access_verified": True,
        "account": account,
        "directly_accessible_customer_ids": accessible,
        "target_directly_accessible": settings["customer_id"] in accessible,
        "login_customer_id": settings["login_customer_id"],
        "api_version": settings["api_version"],
        "mode": "read_only",
        "verified_live": True,
    }


def _date_range(raw_start: str | None, raw_end: str | None) -> tuple[date, date]:
    try:
        if not raw_start or not raw_end:
            raise ValueError("missing")
        start = date.fromisoformat(raw_start)
        end = date.fromisoformat(raw_end)
        if (
            not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw_start)
            or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw_end)
            or end < start
            or end - start >= timedelta(days=MAX_DAYS)
        ):
            raise ValueError("range")
    except (TypeError, ValueError):
        raise GoogleAdsReadError("GOOGLE_ADS_DATE_RANGE_INVALID", 400) from None
    return start, end


def _nonnegative_int(value) -> int:
    try:
        if isinstance(value, bool):
            raise ValueError
        result = int(str(value))
        if result < 0:
            raise ValueError
        return result
    except (TypeError, ValueError):
        raise GoogleAdsReadError("GOOGLE_ADS_INVALID_METRIC", 502) from None


def _decimal_string(value) -> str:
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0:
            raise InvalidOperation
        return format(result, "f")
    except (InvalidOperation, ValueError, TypeError):
        raise GoogleAdsReadError("GOOGLE_ADS_INVALID_METRIC", 502) from None


def get_campaign_daily(*, date_from: str | None, date_to: str | None) -> dict:
    start, end = _date_range(date_from, date_to)
    settings, token = _get_client()
    account = _account(settings, token)  # Fail closed on wrong/customer mismatch.
    if account["manager"]:
        raise GoogleAdsReadError("GOOGLE_ADS_TARGET_IS_MANAGER", 409)

    query = (
        "SELECT segments.date, campaign.id, campaign.name, campaign.status, "
        "campaign.advertising_channel_type, metrics.impressions, metrics.clicks, "
        "metrics.cost_micros, metrics.conversions "
        "FROM campaign "
        f"WHERE segments.date BETWEEN '{start.isoformat()}' "
        f"AND '{end.isoformat()}' "
        "ORDER BY segments.date ASC, campaign.id ASC"
    )
    raw_rows = _search_stream(settings, token, query)
    rows = []
    total_cost_micros = 0
    total_impressions = 0
    total_clicks = 0
    total_conversions = Decimal("0")
    for raw in raw_rows:
        c = raw.get("campaign")
        m = raw.get("metrics", {})
        s = raw.get("segments")
        if not isinstance(c, dict) or not isinstance(m, dict) or not isinstance(s, dict):
            raise GoogleAdsReadError("GOOGLE_ADS_INVALID_PROVIDER_RESPONSE", 502)
        day = s.get("date")
        try:
            parsed = date.fromisoformat(day)
        except (ValueError, TypeError):
            raise GoogleAdsReadError("GOOGLE_ADS_INVALID_PROVIDER_RESPONSE", 502) from None
        if parsed < start or parsed > end:
            raise GoogleAdsReadError("GOOGLE_ADS_INVALID_PROVIDER_RESPONSE", 502)
        campaign_id = str(c.get("id", ""))
        if not re.fullmatch(r"[0-9]+", campaign_id):
            raise GoogleAdsReadError("GOOGLE_ADS_INVALID_PROVIDER_RESPONSE", 502)
        cost_micros = _nonnegative_int(m.get("costMicros", "0"))
        clicks = _nonnegative_int(m.get("clicks", "0"))
        impressions = _nonnegative_int(m.get("impressions", "0"))
        conversions = Decimal(_decimal_string(m.get("conversions", "0")))
        total_cost_micros += cost_micros
        total_clicks += clicks
        total_impressions += impressions
        total_conversions += conversions
        rows.append({
            "date": day,
            "campaign_id": campaign_id,
            "campaign_name": str(c.get("name") or ""),
            "campaign_status": str(c.get("status") or ""),
            "advertising_channel_type": str(c.get("advertisingChannelType") or ""),
            "impressions": impressions,
            "clicks": clicks,
            "cost_micros": cost_micros,
            "cost": format(Decimal(cost_micros) / Decimal(1000000), "f"),
            "conversions": format(conversions, "f"),
        })
    return {
        "account": account,
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "api_version": settings["api_version"],
        "source": "GOOGLE_ADS_API_LIVE",
        "snapshot_persisted": False,
        "totals": {
            "impressions": total_impressions,
            "clicks": total_clicks,
            "cost_micros": total_cost_micros,
            "cost": format(Decimal(total_cost_micros) / Decimal(1000000), "f"),
            "conversions": format(total_conversions, "f"),
        },
        "conversions_note": (
            "Conversiones atribuidas por Google Ads; no equivalen "
            "a compras pagadas validadas en GASCA/iVentas."
        ),
        "rows": rows,
    }
