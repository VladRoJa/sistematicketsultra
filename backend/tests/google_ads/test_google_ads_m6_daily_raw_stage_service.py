"""Strict M6 RAW staging behavior; no database or Google network traffic."""
from dataclasses import replace
from datetime import date
from hashlib import sha256

import pytest

from app.warehouse.services.google_ads_m6_report_download_service import (
    GoogleAdsM6DownloadedReport,
)
from app.warehouse.services.google_ads_m6_daily_raw_stage_service import (
    GoogleAdsM6RawStageError,
    stage_google_ads_m6_daily_pair_raw,
)
from test_google_ads_m6_daily_pair_preflight import _pair

DAY = date(2026, 10, 13)
TODAY = date(2026, 10, 14)


def args():
    kw = _pair()
    campaign_parsed = kw.pop("campaign_report")
    group_parsed = kw.pop("group_report")
    kw.pop("business_date")
    def make(kind, parsed, payload, mail):
        return GoogleAdsM6DownloadedReport(
            report_type_key=kind, business_date=DAY,
            customer_id="2739125201",
            mail_message_id=mail,
            mime_sha256=sha256(mail.encode()).hexdigest(),
            xlsx_sha256=sha256(payload).hexdigest(),
            size_bytes=len(payload), xlsx_bytes=payload, parsed_report=parsed,
        )
    return {
        "campaign": make("google_ads_campaign_daily", campaign_parsed,
                         b"campaign", "<campaign@google.com>"),
        "ad_group": make("google_ads_ad_group_daily", group_parsed,
                         b"group", "<group@google.com>"),
        "expected_customer_id": "273-912-5201", "uploaded_by_user_id": 7,
        **kw,
    }


def fake_store(captured, fail_second=False, dup=False):
    def store(**kw):
        captured.append(kw)
        if fail_second and len(captured) == 2:
            raise RuntimeError("transient stage failure")
        return {
            "warehouse_upload_id": 40 + len(captured),
            "report_type_key": kw["report_type_key"],
            "file_hash_sha256": sha256(kw["file_bytes"]).hexdigest(),
            "date_from": kw["date_from"].isoformat(),
            "date_to": kw["date_to"].isoformat(),
            "duplicate_detected": dup,
        }
    return store


def test_both_raw_files_saved_only_after_complete_preflight():
    captured = []
    r = stage_google_ads_m6_daily_pair_raw(
        **args(), upload=fake_store(captured)
    )
    assert r["status"] == "RAW_PAIR_STAGED"
    assert r["preflight"]["approved_branches"] == 26
    assert r["eligible_for_publication"] is False
    assert r["eligible_for_structured_ingestion"] is False
    assert [x["file_bytes"] for x in captured] == [b"campaign", b"group"]
    assert [x["report_type_key"] for x in captured] == [
        "google_ads_campaign_daily", "google_ads_ad_group_daily"
    ]
    assert all(x["uploaded_by_user_id"] == 7 for x in captured)
    assert all(x["cutoff_date"] == DAY for x in captured)
    assert all(x["date_from"] == DAY and x["date_to"] == DAY for x in captured)
    assert "<campaign@google.com>" not in str(captured)
    assert "mail_message_id_sha256" in captured[0]["audit_details"]


@pytest.mark.parametrize("missing", ["campaign", "ad_group"])
def test_missing_pair_member_never_writes(missing):
    kw = args()
    kw[missing] = None
    captured = []
    r = stage_google_ads_m6_daily_pair_raw(
        **kw, upload=fake_store(captured)
    )
    assert r["status"] == "WAITING_SOURCE"
    assert captured == []


@pytest.mark.parametrize("fault", [
    "wrong_account", "altered_content", "incorrect_hash", "wrong_date",
    "same_mail", "invalid_actor", "unclosed_day", "group_total_drift"
])
def test_invalid_pair_never_writes(fault):
    kw = args()
    if fault == "wrong_account":
        kw["campaign"] = replace(kw["campaign"], customer_id="0000000000")
    if fault == "altered_content":
        kw["campaign"] = replace(kw["campaign"], xlsx_bytes=b"changed")
    if fault == "incorrect_hash":
        kw["ad_group"] = replace(kw["ad_group"], xlsx_sha256="0" * 64)
    if fault == "wrong_date":
        kw["ad_group"] = replace(
            kw["ad_group"], business_date=date(2026, 10, 12)
        )
    if fault == "same_mail":
        kw["ad_group"] = replace(
            kw["ad_group"], mail_message_id=kw["campaign"].mail_message_id
        )
    if fault == "invalid_actor":
        kw["uploaded_by_user_id"] = 0
    if fault == "unclosed_day":
        kw["today_local"] = DAY
    if fault == "group_total_drift":
        kw["ad_group"].parsed_report.rows[0].cost += 1
    captured = []
    with pytest.raises(GoogleAdsM6RawStageError):
        stage_google_ads_m6_daily_pair_raw(
            **kw, upload=fake_store(captured)
        )
    assert captured == []


def test_second_upload_failure_leaves_no_structured_data_and_can_retry():
    captured = []
    with pytest.raises(
        GoogleAdsM6RawStageError, match="RAW_STAGE_INCOMPLETE_RETRY_OR_REVIEW"
    ):
        stage_google_ads_m6_daily_pair_raw(
            **args(), upload=fake_store(captured, fail_second=True)
        )
    assert len(captured) == 2
    replay = []
    r = stage_google_ads_m6_daily_pair_raw(
        **args(), upload=fake_store(replay, dup=True)
    )
    assert r["status"] == "RAW_PAIR_STAGED"
    assert all(x["duplicate_detected"] for x in r["uploads"].values())
    assert r["eligible_for_publication"] is False


def test_invalid_warehouse_result_fails_closed():
    captured = []
    def fake(**kw):
        captured.append(kw)
        return {"warehouse_upload_id": 1, "file_hash_sha256": "bad"}
    with pytest.raises(
        GoogleAdsM6RawStageError, match="RAW_STAGE_INCOMPLETE_RETRY_OR_REVIEW"
    ):
        stage_google_ads_m6_daily_pair_raw(**args(), upload=fake)
    assert len(captured) == 1
