"""Synthetic Gmail MIME notices; no live token, mailbox access or writes."""
from email.message import EmailMessage
from datetime import date

import pytest

from app.warehouse.services.google_ads_m6_mail_notice_service import (
    GoogleAdsM6MailNoticeError, classify_google_ads_m6_mail_notice,
)

RECIPIENT = "vrodriguez@ultragimnasios.com"
CLIENT = "2739125201"
URL = (
    "https://ads.google.com/aw_reporting/email_download?"
    "__tk=TEST-NOT-REAL&__ntk=TEST-NOT-REAL"
)
AUTH = (
    "mx.google.com; dkim=pass header.i=@google.com; "
    "spf=pass smtp.mailfrom=scoutcamp.bounces.google.com; "
    "dmarc=pass header.from=google.com"
)


def _make(*, report="Informe de campaña", sender="ads-account-noreply@google.com",
          recipient=RECIPIENT, customer="273-912-5201", link=True,
          authentication=True, attachment=False):
    email = EmailMessage()
    email["From"] = f"Google Ads <{sender}>"
    email["To"] = recipient
    email["Delivered-To"] = recipient
    email["Subject"] = f"Ya está listo tu informe de Google Ads: {report}"
    email["Date"] = "Wed, 14 Oct 2026 08:09:44 -0700"
    email["Message-ID"] = "<synthetic-report-001@google.com>"
    if authentication:
        email["Authentication-Results"] = AUTH
    email.set_content(
        f"Tu ID de cliente: {customer}\nYa está listo tu informe\nVer informe"
    )
    # Google's real notice includes a VML direct link in an HTML comment.
    href = f'<v:roundrect href="{URL}">Ver informe</v:roundrect>' if link else ""
    email.add_alternative(
        f'<html><body>{customer}<!-- {href} --></body></html>',
        subtype="html"
    )
    if attachment:
        email.add_attachment(
            b"synthetic", maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename="fake.xlsx"
        )
    return email.as_bytes()


def _run(mime, **kwargs):
    return classify_google_ads_m6_mail_notice(
        mime, expected_recipient=RECIPIENT,
        expected_customer_id=CLIENT, **kwargs
    )


@pytest.mark.parametrize(
    "report,kind",
    [
        ("Informe de campaña", "google_ads_campaign_daily"),
        ("Informe de grupo de anuncios", "google_ads_ad_group_daily"),
    ],
)
def test_link_only_notices_are_awaiting_authenticated_download(report, kind):
    result = _run(_make(report=report))
    assert result["report_type_key"] == kind
    assert result["status"] == "WAITING_AUTHENTICATED_DOWNLOAD"
    assert result["business_date"] is None
    assert result["attachment_count"] == 0
    assert result["has_report_download_link"] is True
    assert result["gateway_auth_header_claims_pass"] is True
    assert result["eligible_for_warehouse_ingestion"] is False
    assert result["eligible_for_publication"] is False
    assert "2026-10-14T08:09:44-07:00" == result["sent_at"]
    assert "__tk" not in str(result) and "TEST-NOT-REAL" not in str(result)


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"sender": "ads-account-noreply@evil.example"}, "UNAUTHORIZED_MAIL_IDENTITY"),
        ({"recipient": "unknown@example.com"}, "UNAUTHORIZED_MAIL_IDENTITY"),
        ({"customer": "123-456-7890"}, "CUSTOMER_ID_MISMATCH"),
        ({"report": "No aprobado"}, "UNKNOWN_GOOGLE_ADS_REPORT"),
    ],
)
def test_invalid_identity_or_subject_fails_closed(changes, reason):
    with pytest.raises(GoogleAdsM6MailNoticeError, match=reason):
        _run(_make(**changes))


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"authentication": False}, "MAIL_AUTH_HEADER_UNVERIFIED"),
        ({"link": False}, "DOWNLOAD_LINK_MISSING"),
        ({"attachment": True}, "UNEXPECTED_ATTACHMENT"),
    ],
)
def test_not_ready_with_missing_auth_link_or_unexpected_attachment(changes, reason):
    result = _run(_make(**changes))
    assert result["status"] == "REQUIRES_REVIEW"
    assert result["reason"] == reason
    assert result["eligible_for_publication"] is False


def test_empty_message_rejected():
    with pytest.raises(GoogleAdsM6MailNoticeError, match="INVALID_MIME"):
        _run(b"")


def test_customer_configuration_rejected():
    with pytest.raises(GoogleAdsM6MailNoticeError, match="INVALID_CONFIGURATION"):
        classify_google_ads_m6_mail_notice(
            _make(), expected_recipient=RECIPIENT, expected_customer_id="123"
        )
