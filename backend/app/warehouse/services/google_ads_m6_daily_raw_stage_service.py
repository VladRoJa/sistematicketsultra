"""M6 closed-day Google Ads paired Warehouse RAW upload (never publish).

Caller supplies downloads validated independently, a real authorized actor,
and a reviewed historical identity catalog. No credentials, emails, links,
structured facts, schedule, approvals, or Funnel writes are performed.
"""
from __future__ import annotations

from datetime import date
from hashlib import sha256
import re
from typing import Callable

from app.warehouse.services.google_ads_m6_daily_pair_preflight import (
    GoogleAdsM6DailyPairError,
    preflight_daily_pair,
)
from app.warehouse.services.google_ads_m6_report_download_service import (
    GoogleAdsM6DownloadedReport,
    XLSX_MIME,
)
from app.warehouse.services.warehouse_document_upload_service import (
    create_warehouse_document_upload,
)

REPORT_KEYS = ("google_ads_campaign_daily", "google_ads_ad_group_daily")
MAX_BYTES = 10 * 1024 * 1024


class GoogleAdsM6RawStageError(RuntimeError):
    """Static diagnostic codes, never original HTTP errors or tokens."""


def _verify(report, *, kind: str, customer: str) -> None:
    if not isinstance(report, GoogleAdsM6DownloadedReport):
        raise GoogleAdsM6RawStageError("INVALID_DOWNLOADED_REPORT")
    if report.report_type_key != kind or report.customer_id != customer:
        raise GoogleAdsM6RawStageError("REPORT_KIND_OR_ACCOUNT_MISMATCH")
    data = report.xlsx_bytes
    if (not isinstance(data, bytes) or not 0 < len(data) <= MAX_BYTES
            or report.size_bytes != len(data)
            or sha256(data).hexdigest() != report.xlsx_sha256):
        raise GoogleAdsM6RawStageError("DOWNLOADED_BYTES_INTEGRITY_FAILED")
    if (report.business_date != report.parsed_report.date_from
            or report.business_date != report.parsed_report.date_to):
        raise GoogleAdsM6RawStageError("DOWNLOADED_DATE_MISMATCH")
    if (not report.mail_message_id
            or not re.fullmatch(r"[a-f0-9]{64}", report.mime_sha256)):
        raise GoogleAdsM6RawStageError("NOTICE_PROVENANCE_INVALID")


def stage_google_ads_m6_daily_pair_raw(
    *,
    campaign: GoogleAdsM6DownloadedReport | None,
    ad_group: GoogleAdsM6DownloadedReport | None,
    today_local: date,
    expected_customer_id: str,
    uploaded_by_user_id: int,
    historical_campaign_keys: set[str],
    historical_group_pairs: set[tuple[str, str]],
    approved_branch_by_pair: dict[tuple[str, str], str],
    upload: Callable[..., dict] | None = None,
) -> dict:
    """Validate complete pair, then stage both RAW files with hash dedup.

    uploaded_by_user_id MUST originate in real authenticated authorization.
    A partial RAW failure is re-runnable because Warehouse deduplicates equal
    hashes by report type and period; no structured ingestion is attempted.
    """
    customer = expected_customer_id.strip().replace("-", "")
    if (not isinstance(today_local, date)
            or not isinstance(uploaded_by_user_id, int)
            or isinstance(uploaded_by_user_id, bool)
            or uploaded_by_user_id <= 0
            or not re.fullmatch(r"[0-9]{10}", customer)):
        raise GoogleAdsM6RawStageError("INVALID_STAGING_CONTEXT")

    if campaign is None or ad_group is None:
        return {
            "status": "WAITING_SOURCE",
            "missing": [kind for kind, source in (
                ("campaign", campaign), ("ad_group", ad_group)
            ) if source is None],
            "eligible_for_publication": False,
        }
    _verify(campaign, kind=REPORT_KEYS[0], customer=customer)
    _verify(ad_group, kind=REPORT_KEYS[1], customer=customer)
    if campaign.business_date != ad_group.business_date:
        raise GoogleAdsM6RawStageError("PAIR_DATE_MISMATCH")
    if (campaign.mail_message_id == ad_group.mail_message_id
            or campaign.mime_sha256 == ad_group.mime_sha256):
        raise GoogleAdsM6RawStageError("REUSED_MAIL_PROVENANCE")

    try:
        preflight = preflight_daily_pair(
            business_date=campaign.business_date, today_local=today_local,
            campaign_report=campaign.parsed_report,
            group_report=ad_group.parsed_report,
            historical_campaign_keys=historical_campaign_keys,
            historical_group_pairs=historical_group_pairs,
            approved_branch_by_pair=approved_branch_by_pair,
        )
    except GoogleAdsM6DailyPairError:
        raise GoogleAdsM6RawStageError("DAILY_PAIR_PREFLIGHT_REJECTED") from None
    if preflight["status"] != "PREFLIGHT_OK":
        raise GoogleAdsM6RawStageError("DAILY_PAIR_NOT_READY")

    factory = upload if upload is not None else create_warehouse_document_upload
    stored = {}
    for source in (campaign, ad_group):
        kind = source.report_type_key
        day = source.business_date
        try:
            result = factory(
                report_type_key=kind,
                original_filename=f"{kind}_{day.isoformat()}.xlsx",
                content_type=XLSX_MIME,
                file_bytes=source.xlsx_bytes,
                uploaded_by_user_id=uploaded_by_user_id,
                cutoff_date=day, date_from=day, date_to=day,
                audit_details={
                    "source": "GOOGLE_ADS_M6_EMAIL_RAW_ONLY",
                    "customer_id": customer,
                    "mail_message_id_sha256": sha256(
                        source.mail_message_id.encode("utf-8")
                    ).hexdigest(),
                    "mail_mime_sha256": source.mime_sha256,
                    "xlsx_sha256": source.xlsx_sha256,
                    "publication_gate": "NOT_AUTHORIZED",
                },
            )
            if (not isinstance(result, dict)
                    or type(result.get("warehouse_upload_id")) is not int
                    or result["warehouse_upload_id"] <= 0
                    or result.get("report_type_key") != kind
                    or result.get("file_hash_sha256") != source.xlsx_sha256
                    or result.get("date_from") != day.isoformat()
                    or result.get("date_to") != day.isoformat()):
                raise GoogleAdsM6RawStageError("INVALID_WAREHOUSE_RESPONSE")
        except Exception:
            raise GoogleAdsM6RawStageError(
                "RAW_STAGE_INCOMPLETE_RETRY_OR_REVIEW"
            ) from None
        stored[kind] = {
            "warehouse_upload_id": result["warehouse_upload_id"],
            "xlsx_sha256": source.xlsx_sha256,
            "duplicate_detected": bool(result.get("duplicate_detected")),
        }
    return {
        "status": "RAW_PAIR_STAGED",
        "business_date": campaign.business_date.isoformat(),
        "customer_id": customer,
        "uploads": stored,
        "preflight": preflight,
        "eligible_for_structured_ingestion": False,
        "eligible_for_publication": False,
    }
