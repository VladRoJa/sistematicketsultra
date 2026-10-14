"""Synthetic link downloads: no real mail links, network calls or DB writes."""
from datetime import date
from email.message import EmailMessage
from io import BytesIO
from types import SimpleNamespace

from openpyxl import Workbook
import pytest

from app.warehouse.services import google_ads_m6_report_download_service as service

RECIPIENT = "vrodriguez@ultragimnasios.com"
CUSTOMER = "2739125201"
TEST_URL = (
    "https://ads.google.com/aw_reporting/email_download?"
    "__tk=SYNTHETIC-DO-NOT-USE&__ntk=SYNTHETIC-DO-NOT-USE"
)
AUTH = (
    "mx.google.com; dkim=pass header.i=@google.com; "
    "spf=pass smtp.mailfrom=scoutcamp.bounces.google.com; "
    "dmarc=pass header.from=google.com"
)


def make_notice(kind="Informe de campaña", *, multiple=False):
    msg = EmailMessage()
    msg["From"] = "Google Ads <ads-account-noreply@google.com>"
    msg["To"] = RECIPIENT
    msg["Delivered-To"] = RECIPIENT
    msg["Date"] = "Wed, 14 Oct 2026 08:09:44 -0700"
    msg["Subject"] = f"Ya está listo tu informe de Google Ads: {kind}"
    msg["Message-ID"] = "<synthetic-1@google.com>"
    msg["Authentication-Results"] = AUTH
    msg.set_content("Tu ID de cliente: 273-912-5201\nVer informe")
    extra = (
        '<a href="' + TEST_URL + '&different=1">Report B</a>'
    ) if multiple else ""
    msg.add_alternative(
        '<html><body>273-912-5201<!-- <v:roundrect href="'
        + TEST_URL + '">Ver informe</v:roundrect> -->' + extra + '</body></html>',
        subtype="html"
    )
    return msg.as_bytes()


def make_campaign_xlsx(day=date(2026, 10, 13)):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Informe de campaña"])
    sheet.append([
        f"{day.day} de octubre de {day.year} - {day.day} de octubre de {day.year}"
    ])
    sheet.append([
        "Día", "Estado", "Campaña", "Código de moneda", "Coste",
        "Conversiones", "Valor de conv.", "Clics", "Impr."
    ])
    sheet.append([day, "Habilitada", "Campaña A", "MXN", 12.34, 1, 0, 5, 100])
    sheet.append([day, "Total: Cuenta", None, "MXN", 12.34, 1, 0, 5, 100])
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


class FakeResponse:
    def __init__(self, body, status=200, headers=None):
        self.body = body
        self.status_code = status
        self.headers = headers if headers is not None else {
            "Content-Type": service.XLSX_MIME
        }
        self.closed = False

    def iter_content(self, chunk_size):
        for i in range(0, len(self.body), chunk_size):
            yield self.body[i:i + chunk_size]

    def close(self):
        self.closed = True


def invoke(fetch, *, raw=None, today=date(2026, 10, 14)):
    return service.download_google_ads_m6_xlsx_from_notice(
        raw if raw is not None else make_notice(),
        expected_recipient=RECIPIENT,
        expected_customer_id=CUSTOMER,
        today_local=today, get=fetch,
    )


def test_real_xlsx_parser_receives_stream_without_logging_link():
    data = make_campaign_xlsx()
    resp = FakeResponse(data)
    seen = []

    def get(url, **kwargs):
        seen.append((url, kwargs))
        return resp

    result = invoke(get)
    assert result.business_date == date(2026, 10, 13)
    assert result.report_type_key == "google_ads_campaign_daily"
    assert result.size_bytes == len(data)
    assert len(result.parsed_report.rows) == 1
    assert result.xlsx_bytes == data
    assert result.eligible_for_publication is False
    assert resp.closed
    assert seen[0][0] == TEST_URL
    assert seen[0][1]["allow_redirects"] is False
    assert seen[0][1]["stream"] is True
    assert seen[0][1]["timeout"] == (5, 20)
    assert "__tk" not in repr(result)


def test_real_ad_group_parser_selected(monkeypatch):
    data = make_campaign_xlsx()
    dummy = SimpleNamespace(
        currency_code="MXN", date_from=date(2026, 10, 13),
        date_to=date(2026, 10, 13), rows=("group",),
    )
    received = []
    monkeypatch.setattr(
        service, "parse_google_ads_ad_group_daily_xlsx",
        lambda content: received.append(content) or dummy,
    )
    result = invoke(
        lambda *a, **k: FakeResponse(data),
        raw=make_notice("Informe de grupo de anuncios"),
    )
    assert result.report_type_key == "google_ads_ad_group_daily"
    assert received == [data]


@pytest.mark.parametrize("status,code", [
    (302, "REDIRECT_REQUIRES_REVIEW"),
    (403, "DOWNLOAD_AUTH_REQUIRED"),
    (401, "DOWNLOAD_AUTH_REQUIRED"),
    (429, "DOWNLOAD_UNAVAILABLE"),
    (500, "DOWNLOAD_UNAVAILABLE"),
])
def test_redirect_and_auth_fail_closed(status, code):
    response = FakeResponse(b"", status=status)
    with pytest.raises(service.GoogleAdsM6DownloadError, match=code):
        invoke(lambda *args, **kwargs: response)
    assert response.closed


def test_html_response_rejected():
    with pytest.raises(service.GoogleAdsM6DownloadError, match="NOT_XLSX_RESPONSE"):
        invoke(lambda *args, **kwargs: FakeResponse(
            b"<html>Login</html>", headers={"Content-Type": "text/html"}
        ))


def test_xlsx_magic_and_parser_required():
    for data in (b"random", b"PK\x03\x04not-a-valid-xlsx"):
        with pytest.raises(
            service.GoogleAdsM6DownloadError,
            match="NOT_XLSX_RESPONSE|INVALID_GOOGLE_ADS_XLSX",
        ):
            invoke(lambda *args, **kwargs: FakeResponse(data))


@pytest.mark.parametrize("day", [
    date(2026, 10, 12), date(2026, 10, 14)
])
def test_reject_historical_or_open_day(day):
    data = make_campaign_xlsx(day)
    with pytest.raises(
        service.GoogleAdsM6DownloadError, match="REPORT_DAY_NOT_CLOSED_OR_INVALID"
    ):
        invoke(lambda *args, **kwargs: FakeResponse(data))


def test_download_size_limits_from_header_and_stream():
    data = make_campaign_xlsx()
    with pytest.raises(service.GoogleAdsM6DownloadError, match="DOWNLOAD_TOO_LARGE"):
        invoke(lambda *args, **kwargs: FakeResponse(
            data, headers={"Content-Length": str(service.MAX_DOWNLOAD_BYTES + 1)}
        ))
    with pytest.raises(service.GoogleAdsM6DownloadError, match="DOWNLOAD_TOO_LARGE"):
        invoke(lambda *args, **kwargs: FakeResponse(b"x" * (service.MAX_DOWNLOAD_BYTES + 1)))


def test_ambiguous_link_does_not_request_network():
    called = []
    with pytest.raises(service.GoogleAdsM6DownloadError, match="AMBIGUOUS_DOWNLOAD_LINKS"):
        invoke(lambda *a, **k: called.append(True), raw=make_notice(multiple=True))
    assert not called


def test_transport_errors_do_not_leak_link():
    def broken(url, **kwargs):
        raise RuntimeError("proxy broke for " + url)

    with pytest.raises(service.GoogleAdsM6DownloadError) as exc:
        invoke(broken)
    assert str(exc.value) == "DOWNLOAD_TRANSPORT_ERROR"
    assert TEST_URL not in str(exc.value)
    assert exc.value.__cause__ is None


def test_untrusted_mail_is_blocked_before_network():
    raw = make_notice().replace(b"google.com", b"bad.invalid")
    called = []
    with pytest.raises(Exception):
        invoke(lambda *args, **kwargs: called.append(True), raw=raw)
    assert called == []
