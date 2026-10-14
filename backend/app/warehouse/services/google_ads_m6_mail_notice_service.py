"""Recognize Google Ads M6 scheduled-email notices without exposing download tokens.

Pure MIME classifier, not a downloader or source of spend. Call only on raw
messages fetched from the explicitly authorized Gmail account. Header signals
are observations, not standalone cryptographic proof of trusted transport.
No RAW Warehouse upload, structured facts, approval or publication occurs here.
"""
from __future__ import annotations

from datetime import datetime
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from hashlib import sha256
from html import unescape
import re
from urllib.parse import urlsplit

GOOGLE_ADS_SENDER = "ads-account-noreply@google.com"
REPORTS = {
    "Ya está listo tu informe de Google Ads: Informe de campaña":
        "google_ads_campaign_daily",
    "Ya está listo tu informe de Google Ads: Informe de grupo de anuncios":
        "google_ads_ad_group_daily",
}
MAX_MIME_BYTES = 256 * 1024
GOOGLE_REPORT_PATH = "/aw_reporting/email_download"
_HREF_RE = re.compile(r"""href\s*=\s*(?:"([^"]+)"|'([^']+)'|([^\s>]+))""", re.I)


class GoogleAdsM6MailNoticeError(RuntimeError):
    """Invalid or untrusted mail notice. No links appear in errors."""


def _claim_passes_google_auth(message) -> bool:
    """Examine Gmail's gateway header; caller must trust its source separately."""
    for header in message.get_all("Authentication-Results", []):
        value = " ".join(str(header).lower().split())
        checks = (
            value.startswith("mx.google.com;"),
            "dkim=pass" in value,
            "header.i=@google.com" in value,
            "spf=pass" in value,
            "dmarc=pass" in value,
            "header.from=google.com" in value,
        )
        if all(checks):
            return True
    return False


def _has_google_report_download(html_bodies: list[str]) -> bool:
    # Match VML/HTML hrefs, including Outlook conditional-comment links.
    # NEVER return or log a URL: its __tk / __ntk query tokens are sensitive.
    for body in html_bodies:
        for match in _HREF_RE.finditer(body):
            href = unescape(next(value for value in match.groups() if value))
            try:
                parsed = urlsplit(href)
            except ValueError:
                continue
            if (
                parsed.scheme == "https"
                and parsed.hostname == "ads.google.com"
                and parsed.username is None
                and parsed.password is None
                and parsed.path == GOOGLE_REPORT_PATH
                and bool(parsed.query)
            ):
                return True
    return False


def classify_google_ads_m6_mail_notice(
    raw_mime: bytes,
    *,
    expected_recipient: str,
    expected_customer_id: str,
) -> dict:
    """Classify only; a positive result never authorizes file ingestion.

    Business date cannot be inferred from mail arrival: wait until the XLSX
    has been downloaded via a separately authorized Google Ads mechanism and
    parsed by the existing strict XLSX parsers.
    """
    if not isinstance(raw_mime, bytes) or not (0 < len(raw_mime) <= MAX_MIME_BYTES):
        raise GoogleAdsM6MailNoticeError("INVALID_MIME")
    recipient = expected_recipient.strip().lower()
    customer = re.sub(r"\D", "", expected_customer_id)
    if not recipient or not re.fullmatch(r"[0-9]{10}", customer):
        raise GoogleAdsM6MailNoticeError("INVALID_CONFIGURATION")
    try:
        mail = BytesParser(policy=policy.default).parsebytes(raw_mime)
        sent_at = parsedate_to_datetime(str(mail.get("Date", "")))
    except (TypeError, ValueError, IndexError, OverflowError) as exc:
        raise GoogleAdsM6MailNoticeError("INVALID_MAIL_HEADERS") from exc
    if not isinstance(sent_at, datetime) or sent_at.tzinfo is None:
        raise GoogleAdsM6MailNoticeError("INVALID_MAIL_DATE")
    senders = [a.lower() for _, a in getaddresses(mail.get_all("From", []))]
    recipients = [a.lower() for _, a in getaddresses(mail.get_all("To", []))]
    delivered = str(mail.get("Delivered-To", "")).strip().lower()
    if (
        senders != [GOOGLE_ADS_SENDER]
        or recipient not in recipients
        or (delivered and delivered != recipient)
    ):
        raise GoogleAdsM6MailNoticeError("UNAUTHORIZED_MAIL_IDENTITY")
    subject = str(mail.get("Subject", ""))
    report_type = REPORTS.get(subject)
    if report_type is None:
        raise GoogleAdsM6MailNoticeError("UNKNOWN_GOOGLE_ADS_REPORT")

    plain_parts = []
    html_parts = []
    attachment_count = 0
    for part in mail.walk():
        if part.is_multipart():
            continue
        if part.get_content_disposition() == "attachment" or part.get_filename():
            attachment_count += 1
            continue
        kind = part.get_content_type()
        if kind in ("text/plain", "text/html"):
            try:
                content = part.get_content()
            except (UnicodeError, LookupError, ValueError):
                raise GoogleAdsM6MailNoticeError("INVALID_MAIL_BODY") from None
            (html_parts if kind == "text/html" else plain_parts).append(content)

    text = "\n".join(plain_parts + html_parts)
    escaped_customer = re.escape(customer)
    # Body must contain precisely the configured client number in either form.
    pattern = re.compile(
        r"(?<![0-9])" + escaped_customer[:3] + r"[\s-]*"
        + escaped_customer[3:6] + r"[\s-]*" + escaped_customer[6:] + r"(?![0-9])"
    )
    if not pattern.search(text):
        raise GoogleAdsM6MailNoticeError("CUSTOMER_ID_MISMATCH")
    has_link = _has_google_report_download(html_parts)
    gateway_auth_claim = _claim_passes_google_auth(mail)
    if attachment_count:
        status = "REQUIRES_REVIEW"
        reason = "UNEXPECTED_ATTACHMENT"
    elif not has_link:
        status = "REQUIRES_REVIEW"
        reason = "DOWNLOAD_LINK_MISSING"
    elif not gateway_auth_claim:
        status = "REQUIRES_REVIEW"
        reason = "MAIL_AUTH_HEADER_UNVERIFIED"
    else:
        status = "WAITING_AUTHENTICATED_DOWNLOAD"
        reason = None
    return {
        "status": status,
        "reason": reason,
        "report_type_key": report_type,
        "customer_id": customer,
        "recipient": recipient,
        "sent_at": sent_at.isoformat(),
        "mail_message_id": str(mail.get("Message-ID", "")).strip(),
        "mime_sha256": sha256(raw_mime).hexdigest(),
        "has_report_download_link": has_link,
        "attachment_count": attachment_count,
        "gateway_auth_header_claims_pass": gateway_auth_claim,
        "business_date": None,
        "eligible_for_warehouse_ingestion": False,
        "eligible_for_publication": False,
    }
