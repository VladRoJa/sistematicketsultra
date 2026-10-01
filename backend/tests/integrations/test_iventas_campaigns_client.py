from datetime import datetime, timezone
from email.utils import format_datetime

import pytest
import requests

from app.integrations.iventas.campaigns_client import (
    IVentasCampaignsClient,
    IVentasCampaignsConfigurationError,
    IVentasCampaignsPayloadError,
    IVentasCampaignsProviderError,
    IVentasCampaignsTransportError,
)


class FakeResponse:
    def __init__(
        self,
        status_code,
        payload,
        *,
        headers=None,
        json_error=False,
        text="",
    ):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self._json_error = json_error
        self.text = text
    def json(self):
        if self._json_error:
            raise ValueError("invalid json")
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, *, headers, timeout):
        self.calls.append({
            "method": "GET",
            "url": url,
            "headers": dict(headers),
            "timeout": timeout,
        })
        if not self.responses:
            raise AssertionError(
                "more requests than expected"
            )
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeSleeper:
    def __init__(self):
        self.calls = []

    def __call__(self, seconds):
        self.calls.append(seconds)
def build_client(
    responses,
    *,
    sleeper=None,
    now_utc=None,
    max_sync_retry_after_seconds=60.0,
):
    session = FakeSession(responses)
    fake_sleep = sleeper or FakeSleeper()
    client = IVentasCampaignsClient(
        api_key="campaigns-secret",
        session=session,
        sleeper=fake_sleep,
        now_utc=now_utc,
        max_sync_retry_after_seconds=(
            max_sync_retry_after_seconds
        ),
    )
    return client, session, fake_sleep


_DEFAULT_PAYLOAD = object()


def ok_response(payload=_DEFAULT_PAYLOAD):
    return FakeResponse(
        200,
        (
            {"successfulMessages": []}
            if payload is _DEFAULT_PAYLOAD
            else payload
        ),
    )


def test_uses_campaigns_api_key_env_only(
    monkeypatch,
):
    monkeypatch.setenv(
        "IVENTAS_CAMPAIGNS_API_KEY",
        "campaign-key",
    )
    monkeypatch.setenv(
        "IVENTAS_API_TOKEN",
        "legacy-token",
    )
    session = FakeSession([ok_response()])

    client = IVentasCampaignsClient(
        session=session,
    )
    client.get_campaign_stats("abc")

    authorization = session.calls[0][
        "headers"
    ]["Authorization"]
    assert authorization == "Bearer campaign-key"
    assert "legacy-token" not in authorization


def test_does_not_fallback_to_legacy_token(
    monkeypatch,
):
    monkeypatch.delenv(
        "IVENTAS_CAMPAIGNS_API_KEY",
        raising=False,
    )
    monkeypatch.setenv(
        "IVENTAS_API_TOKEN",
        "legacy-token",
    )

    with pytest.raises(
        IVentasCampaignsConfigurationError
    ):
        IVentasCampaignsClient()
def test_uses_optional_campaigns_base_url(
    monkeypatch,
):
    monkeypatch.setenv(
        "IVENTAS_CAMPAIGNS_API_KEY",
        "campaign-key",
    )
    monkeypatch.setenv(
        "IVENTAS_CAMPAIGNS_API_BASE_URL",
        "https://example.test/root/",
    )
    session = FakeSession([ok_response()])

    client = IVentasCampaignsClient(
        session=session,
    )
    client.get_campaign_stats("abc")

    assert session.calls[0]["url"] == (
        "https://example.test/root"
        "/v2/broadcast/stats/abc"
    )


def test_get_uses_expected_path_timeout_and_escaping():
    client, session, _ = build_client([
        ok_response(),
    ])

    client.get_campaign_stats(
        "campaign / with?unsafe",
    )

    call = session.calls[0]
    assert call["method"] == "GET"
    assert call["url"].endswith(
        "/v2/broadcast/stats/"
        "campaign%20%2F%20with%3Funsafe"
    )
    assert call["timeout"] == (10.0, 30.0)


def test_empty_campaign_id_is_rejected_before_request():
    client, session, _ = build_client([])

    with pytest.raises(
        ValueError,
        match="campaign_id",
    ):
        client.get_campaign_stats("   ")

    assert session.calls == []


def test_200_returns_json_object():
    expected = {
        "successfulMessages": ["6861111111"],
    }
    client, session, _ = build_client([
        ok_response(expected),
    ])

    result = client.get_campaign_stats("abc")

    assert result == expected
    assert len(session.calls) == 1


@pytest.mark.parametrize("status_code", [401, 403])
def test_auth_errors_do_not_retry(status_code):
    client, session, sleeper = build_client([
        FakeResponse(
            status_code,
            {
                "error": "AUTH_ERROR",
                "supportRef": "SAFE_REF",
            },
        ),
    ])

    with pytest.raises(
        IVentasCampaignsProviderError
    ) as exc_info:
        client.get_campaign_stats("abc")

    error = exc_info.value
    assert error.status_code == status_code
    assert error.retryable is False
    assert error.provider_code == "AUTH_ERROR"
    assert error.support_ref == "SAFE_REF"
    assert error.retry_after_seconds is None
    assert len(session.calls) == 1
    assert sleeper.calls == []


def test_429_delta_retry_after_is_respected():
    client, session, sleeper = build_client([
        FakeResponse(
            429,
            {"error": "RATE_LIMIT"},
            headers={"Retry-After": "7"},
        ),
        ok_response(),
    ])
    result = client.get_campaign_stats("abc")

    assert result["successfulMessages"] == []
    assert len(session.calls) == 2
    assert sleeper.calls == [7.0]


def test_429_http_date_retry_after_is_respected():
    now = datetime(
        2026, 10, 1, 20, 0, 0,
        tzinfo=timezone.utc,
    )
    retry_at = datetime(
        2026, 10, 1, 20, 0, 11,
        tzinfo=timezone.utc,
    )
    client, session, sleeper = build_client(
        [
            FakeResponse(
                429,
                {"error": "RATE_LIMIT"},
                headers={
                    "Retry-After": format_datetime(
                        retry_at,
                        usegmt=True,
                    ),
                },
            ),
            ok_response(),
        ],
        now_utc=lambda: now,
    )

    client.get_campaign_stats("abc")
    assert len(session.calls) == 2
    assert sleeper.calls == [11.0]


def test_retry_after_above_sync_limit_stops_without_sleep():
    client, session, sleeper = build_client([
        FakeResponse(
            429,
            {"error": "RATE_LIMIT"},
            headers={"Retry-After": "120"},
        ),
    ])

    with pytest.raises(
        IVentasCampaignsProviderError
    ) as exc_info:
        client.get_campaign_stats("abc")

    error = exc_info.value
    assert error.status_code == 429
    assert error.retryable is True
    assert error.retry_after_seconds == 120.0
    assert len(session.calls) == 1
    assert sleeper.calls == []


def test_invalid_retry_after_uses_fallback_delays():
    client, session, sleeper = build_client([
        FakeResponse(
            429,
            {"error": "RATE_LIMIT"},
            headers={"Retry-After": "invalid"},
        ),
        FakeResponse(
            429,
            {"error": "RATE_LIMIT"},
            headers={"Retry-After": "still-invalid"},
        ),
        ok_response(),
    ])

    client.get_campaign_stats("abc")

    assert len(session.calls) == 3
    assert sleeper.calls == [2.0, 5.0]


@pytest.mark.parametrize(
    "status_code",
    [500, 502, 503, 504],
)
def test_retryable_5xx_retries_then_succeeds(
    status_code,
):
    client, session, sleeper = build_client([
        FakeResponse(
            status_code,
            {"error": "TEMPORARY"},
        ),
        ok_response(),
    ])

    client.get_campaign_stats("abc")

    assert len(session.calls) == 2
    assert sleeper.calls == [2.0]
def test_5xx_exhaustion_is_provider_error():
    client, session, sleeper = build_client([
        FakeResponse(
            503,
            {"error": "UNAVAILABLE"},
        ),
        FakeResponse(
            503,
            {"error": "UNAVAILABLE"},
        ),
        FakeResponse(
            503,
            {"error": "UNAVAILABLE"},
        ),
    ])

    with pytest.raises(
        IVentasCampaignsProviderError
    ) as exc_info:
        client.get_campaign_stats("abc")

    error = exc_info.value
    assert error.status_code == 503
    assert error.retryable is True
    assert len(session.calls) == 3
    assert sleeper.calls == [2.0, 5.0]


def test_transport_retries_exactly_three_attempts():
    client, session, sleeper = build_client([
        requests.Timeout(),
        requests.ConnectionError(),
        requests.Timeout(),
    ])
    with pytest.raises(
        IVentasCampaignsTransportError
    ):
        client.get_campaign_stats("abc")

    assert len(session.calls) == 3
    assert sleeper.calls == [2.0, 5.0]


def test_transport_retry_can_recover():
    client, session, sleeper = build_client([
        requests.Timeout(),
        ok_response(),
    ])

    result = client.get_campaign_stats("abc")

    assert result["successfulMessages"] == []
    assert len(session.calls) == 2
    assert sleeper.calls == [2.0]


def test_http_200_invalid_json_is_payload_error():
    client, session, sleeper = build_client([
        FakeResponse(
            200,
            None,
            json_error=True,
            text="raw secret provider body",
        ),
    ])

    with pytest.raises(
        IVentasCampaignsPayloadError
    ) as exc_info:
        client.get_campaign_stats("abc")
    assert "raw secret provider body" not in str(
        exc_info.value
    )
    assert len(session.calls) == 1
    assert sleeper.calls == []


@pytest.mark.parametrize(
    "payload",
    [
        [],
        "string",
        123,
        None,
    ],
)
def test_http_200_json_root_must_be_object(payload):
    client, session, sleeper = build_client([
        ok_response(payload),
    ])

    with pytest.raises(
        IVentasCampaignsPayloadError
    ):
        client.get_campaign_stats("abc")

    assert len(session.calls) == 1
    assert sleeper.calls == []


def test_provider_error_does_not_expose_token_or_raw_body():
    token = "campaigns-secret"
    client, session, _ = build_client([
        FakeResponse(
            403,
            {
                "error": token,
                "supportRef": token,
            },
            text=(
                "raw-body-with-"
                + token
            ),
        ),
    ])

    with pytest.raises(
        IVentasCampaignsProviderError
    ) as exc_info:
        client.get_campaign_stats("abc")

    error = exc_info.value
    rendered = str(error)

    assert token not in rendered
    assert token not in (error.provider_code or "")
    assert token not in (error.support_ref or "")
    assert "raw-body" not in rendered
    assert len(session.calls) == 1


def test_retry_after_on_5xx_is_also_respected():
    client, session, sleeper = build_client([
        FakeResponse(
            503,
            {"error": "UNAVAILABLE"},
            headers={"Retry-After": "4"},
        ),
        ok_response(),
    ])
    client.get_campaign_stats("abc")

    assert len(session.calls) == 2
    assert sleeper.calls == [4.0]


def test_expired_http_date_retry_after_allows_immediate_retry():
    now = datetime(
        2026, 10, 1, 20, 0, 10,
        tzinfo=timezone.utc,
    )
    retry_at = datetime(
        2026, 10, 1, 20, 0, 0,
        tzinfo=timezone.utc,
    )
    client, session, sleeper = build_client(
        [
            FakeResponse(
                429,
                {"error": "RATE_LIMIT"},
                headers={
                    "Retry-After": format_datetime(
                        retry_at,
                        usegmt=True,
                    ),
                },
            ),
            ok_response(),
        ],
        now_utc=lambda: now,
    )

    client.get_campaign_stats("abc")

    assert len(session.calls) == 2
    assert sleeper.calls == [0.0]
