"""Conservative in-memory HTTP transport for Google Ads M6 email downloads.

The caller must supply raw MIME from the authorized Gmail connector. Do not
store or log signed URLs: __tk/__ntk are bearer-like access credentials.
No redirects, cookies, RAW writes, database work, automatic approval, or
publication. A download from the browser does not prove headless access.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from email import policy
from email.parser import BytesParser
from hashlib import sha256
from html import unescape
import re
from typing import Any, Callable
from urllib.parse import urlsplit

import requests

from app.warehouse.services.google_ads_m6_mail_notice_service import (
    _HREF_RE,
    GOOGLE_REPORT_PATH,
    classify_google_ads_m6_mail_notice,
)
from app.warehouse.services.google_ads_daily_xlsx_parser import (
    GoogleAdsXlsxValidationError,
    parse_google_ads_daily_xlsx,
)
from app.warehouse.services.google_ads_ad_group_daily_xlsx_parser import (
    parse_google_ads_ad_group_daily_xlsx,
)

MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024
FIRST_UNAPPROVED_DAY = date(2026, 10, 13)
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class GoogleAdsM6DownloadError(RuntimeError):
    """Stable error codes only; never interpolate a sensitive URL."""


@dataclass(frozen=True)
class GoogleAdsM6DownloadedReport:
    report_type_key: str
    business_date: date
    customer_id: str
    mail_message_id: str
    mime_sha256: str
    xlsx_sha256: str
    size_bytes: int
    xlsx_bytes: bytes = field(repr=False)
    parsed_report: Any = field(repr=False)
    # Downstream still requires RAW provenance, daily pair preflight and approval.
    eligible_for_publication: bool = False


def _extract_direct_download_link(raw_mime: bytes) -> str:
    mail = BytesParser(policy=policy.default).parsebytes(raw_mime)
    matches = set()
    for part in mail.walk():
        if part.is_multipart() or part.get_content_type() != "text/html":
            continue
        if part.get_content_disposition() == "attachment":
            continue
        try:
            html = part.get_content()
        except (UnicodeError, LookupError, ValueError):
            raise GoogleAdsM6DownloadError("INVALID_HTML_NOTICE") from None
        for match in _HREF_RE.finditer(html):
            href = unescape(next(value for value in match.groups() if value))
            try:
                parsed = urlsplit(href)
            except ValueError:
                continue
            if (
                parsed.scheme == "https"
                and parsed.netloc == "ads.google.com"
                and parsed.path == GOOGLE_REPORT_PATH
                and not parsed.fragment
                and bool(parsed.query)
                and "\r" not in href
                and "\n" not in href
            ):
                matches.add(href)
    if not matches:
        raise GoogleAdsM6DownloadError("DOWNLOAD_LINK_MISSING")
    if len(matches) != 1:
        raise GoogleAdsM6DownloadError("AMBIGUOUS_DOWNLOAD_LINKS")
    return next(iter(matches))


def download_google_ads_m6_xlsx_from_notice(
    raw_mime: bytes,
    *,
    expected_recipient: str,
    expected_customer_id: str,
    today_local: date,
    get: Callable[..., Any] | None = None,
) -> GoogleAdsM6DownloadedReport:
    """Fetch link-only notice, validate real XLSX and return unpersisted bytes.

    The HTTP client does NOT follow redirects; a 3xx is a separate unresolved
    integration requirement. The caller must never log exceptions from HTTP
    libraries with the token-bearing URL or serialize xlsx_bytes publicly.
    """
    if not isinstance(today_local, date):
        raise GoogleAdsM6DownloadError("INVALID_LOCAL_DATE")
    notice = classify_google_ads_m6_mail_notice(
        raw_mime,
        expected_recipient=expected_recipient,
        expected_customer_id=expected_customer_id,
    )
    if notice["status"] != "WAITING_AUTHENTICATED_DOWNLOAD":
        raise GoogleAdsM6DownloadError("NOTICE_REQUIRES_REVIEW")
    url = _extract_direct_download_link(raw_mime)
    request_get = get if get is not None else requests.get
    response = None
    try:
        response = request_get(
            url,
            allow_redirects=False,
            stream=True,
            timeout=(5, 20),
            headers={"Accept": XLSX_MIME + ", application/octet-stream"},
        )
        status = int(response.status_code)
        if 300 <= status < 400:
            raise GoogleAdsM6DownloadError("REDIRECT_REQUIRES_REVIEW")
        if status in (401, 403):
            raise GoogleAdsM6DownloadError("DOWNLOAD_AUTH_REQUIRED")
        if status != 200:
            raise GoogleAdsM6DownloadError("DOWNLOAD_UNAVAILABLE")
        mime_type = str(response.headers.get("Content-Type", "")).split(";")[0].strip().lower()
        if mime_type and mime_type not in (XLSX_MIME, "application/octet-stream", "application/zip"):
            raise GoogleAdsM6DownloadError("NOT_XLSX_RESPONSE")
        try:
            declared = int(response.headers.get("Content-Length", "0"))
        except (TypeError, ValueError):
            raise GoogleAdsM6DownloadError("INVALID_CONTENT_LENGTH") from None
        if declared < 0 or declared > MAX_DOWNLOAD_BYTES:
            raise GoogleAdsM6DownloadError("DOWNLOAD_TOO_LARGE")
        chunks = []
        total = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_DOWNLOAD_BYTES:
                raise GoogleAdsM6DownloadError("DOWNLOAD_TOO_LARGE")
            chunks.append(chunk)
        content = b"".join(chunks)
    except GoogleAdsM6DownloadError:
        raise
    except Exception:
        # Requests exceptions can embed URLs or proxy details; suppress context.
        raise GoogleAdsM6DownloadError("DOWNLOAD_TRANSPORT_ERROR") from None
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                pass
    if not content.startswith(b"PK\x03\x04"):
        raise GoogleAdsM6DownloadError("NOT_XLSX_RESPONSE")
    parser = (
        parse_google_ads_daily_xlsx
        if notice["report_type_key"] == "google_ads_campaign_daily"
        else parse_google_ads_ad_group_daily_xlsx
    )
    try:
        parsed = parser(content)
    except (GoogleAdsXlsxValidationError, ValueError, KeyError):
        raise GoogleAdsM6DownloadError("INVALID_GOOGLE_ADS_XLSX") from None
    if (
        parsed.currency_code != "MXN"
        or parsed.date_from != parsed.date_to
        or parsed.date_from < FIRST_UNAPPROVED_DAY
        or parsed.date_to >= today_local
    ):
        raise GoogleAdsM6DownloadError("REPORT_DAY_NOT_CLOSED_OR_INVALID")
    return GoogleAdsM6DownloadedReport(
        report_type_key=notice["report_type_key"],
        business_date=parsed.date_from,
        customer_id=notice["customer_id"],
        mail_message_id=notice["mail_message_id"],
        mime_sha256=notice["mime_sha256"],
        xlsx_sha256=sha256(content).hexdigest(),
        size_bytes=len(content),
        xlsx_bytes=content,
        parsed_report=parsed,
    )
