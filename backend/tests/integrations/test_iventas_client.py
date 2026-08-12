from __future__ import annotations

import requests
import pytest

from app.integrations.iventas import (
    IventasClient,
    IventasConfigurationError,
    IventasPayloadError,
    IventasProviderError,
    IventasTransportError,
)


FROM_UTC = "2026-08-01T07:00:00.000Z"
TO_UTC = "2026-08-03T06:59:59.999Z"


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload,
        raw_payload: str,
        *,
        json_error: bool = False,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = raw_payload
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise ValueError("invalid json")

        return self._payload


class FakeSession:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def get(
        self,
        url,
        *,
        headers,
        params,
        timeout,
    ):
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "params": dict(params),
                "timeout": timeout,
            }
        )

        if not self.responses:
            raise AssertionError(
                "FakeSession recibió más requests "
                "de los esperados."
            )

        response = self.responses.pop(0)

        if isinstance(response, Exception):
            raise response

        return response


def ok_response(
    *,
    contacts=None,
    has_more: bool = False,
    next_cursor=None,
    raw_payload: str = '{"contacts":[]}',
):
    return FakeResponse(
        200,
        {
            "contacts": (
                []
                if contacts is None
                else contacts
            ),
            "pagination": {
                "hasMore": has_more,
                "nextCursor": next_cursor,
            },
            "branch": {
                "code": "papalote",
                "label": "Papalote",
            },
        },
        raw_payload,
    )


def build_client(
    responses,
    *,
    clock: FakeClock | None = None,
) -> tuple[
    IventasClient,
    FakeSession,
    FakeClock,
]:
    resolved_clock = clock or FakeClock()
    session = FakeSession(responses)

    client = IventasClient(
        token="dummy-test-token",
        session=session,
        sleeper=resolved_clock.sleep,
        monotonic=resolved_clock.monotonic,
    )

    return (
        client,
        session,
        resolved_clock,
    )


def fetch_default(
    client: IventasClient,
):
    return client.fetch_page(
        branch="papalote",
        from_utc=FROM_UTC,
        to_utc=TO_UTC,
        limit=100,
    )


def test_token_is_required() -> None:
    with pytest.raises(
        IventasConfigurationError
    ):
        IventasClient(token="")


def test_limit_must_be_between_1_and_100() -> None:
    client, _, _ = build_client([])

    with pytest.raises(ValueError):
        client.fetch_page(
            branch="papalote",
            from_utc=FROM_UTC,
            to_utc=TO_UTC,
            limit=0,
        )

    with pytest.raises(ValueError):
        client.fetch_page(
            branch="papalote",
            from_utc=FROM_UTC,
            to_utc=TO_UTC,
            limit=101,
        )


def test_fetch_page_preserves_raw_payload_exactly() -> None:
    raw_payload = (
        '{ "contacts" : [], '
        '"pagination":{"hasMore":false,'
        '"nextCursor":null},'
        '"branch":{"code":"papalote",'
        '"label":"Papalote"} }'
    )

    response = FakeResponse(
        200,
        {
            "contacts": [],
            "pagination": {
                "hasMore": False,
                "nextCursor": None,
            },
            "branch": {
                "code": "papalote",
                "label": "Papalote",
            },
        },
        raw_payload,
    )

    client, _, _ = build_client([
        response,
    ])

    page = fetch_default(client)

    assert page.raw_payload == raw_payload


def test_request_uses_expected_endpoint_headers_params_and_timeout(
) -> None:
    client, session, _ = build_client([
        ok_response(),
    ])

    fetch_default(client)

    assert len(session.calls) == 1

    call = session.calls[0]

    assert call["url"].endswith(
        "/v1/integrations/contacts"
    )

    assert call["params"] == {
        "branch": "papalote",
        "from": FROM_UTC,
        "to": TO_UTC,
        "limit": 100,
    }

    assert call["timeout"] == (
        10.0,
        30.0,
    )

    assert (
        call["headers"]["Accept"]
        == "application/json"
    )

    assert (
        call["headers"]["Authorization"]
        == "Bearer dummy-test-token"
    )


def test_iter_pages_uses_cursor_and_rate_limit() -> None:
    client, session, clock = build_client([
        ok_response(
            contacts=[{"id": "A"}],
            has_more=True,
            next_cursor="CURSOR_2",
            raw_payload='{"page":1}',
        ),
        ok_response(
            contacts=[{"id": "B"}],
            raw_payload='{"page":2}',
        ),
    ])

    pages = list(
        client.iter_pages(
            branch="papalote",
            from_utc=FROM_UTC,
            to_utc=TO_UTC,
            limit=100,
        )
    )

    assert len(pages) == 2

    assert "cursor" not in session.calls[
        0
    ]["params"]

    assert (
        session.calls[1]["params"]["cursor"]
        == "CURSOR_2"
    )

    assert clock.sleeps == [1.5]


@pytest.mark.parametrize(
    "status_code",
    [
        429,
        500,
        503,
    ],
)
def test_retryable_status_retries_then_succeeds(
    status_code: int,
) -> None:
    client, session, clock = build_client([
        FakeResponse(
            status_code,
            {
                "error": "TEMPORARY_ERROR",
            },
            '{"error":"TEMPORARY_ERROR"}',
        ),
        ok_response(),
    ])

    page = fetch_default(client)

    assert page.http_status == 200
    assert len(session.calls) == 2
    assert clock.sleeps == [2.0]


def test_retry_exhaustion_uses_2_5_10_backoff(
) -> None:
    responses = [
        FakeResponse(
            503,
            {
                "error": "SERVICE_UNAVAILABLE",
            },
            '{"error":"SERVICE_UNAVAILABLE"}',
        )
        for _ in range(4)
    ]

    client, session, clock = build_client(
        responses
    )

    with pytest.raises(
        IventasProviderError
    ) as exc_info:
        fetch_default(client)

    error = exc_info.value

    assert error.status_code == 503
    assert error.retryable is True
    assert (
        error.provider_code
        == "SERVICE_UNAVAILABLE"
    )

    assert len(session.calls) == 4

    assert clock.sleeps == [
        2.0,
        5.0,
        10.0,
    ]


def test_non_retryable_status_fails_immediately(
) -> None:
    client, session, clock = build_client([
        FakeResponse(
            403,
            {
                "error": "FORBIDDEN",
            },
            '{"error":"FORBIDDEN"}',
        ),
    ])

    with pytest.raises(
        IventasProviderError
    ) as exc_info:
        fetch_default(client)

    error = exc_info.value

    assert error.status_code == 403
    assert error.provider_code == "FORBIDDEN"
    assert error.retryable is False

    assert len(session.calls) == 1
    assert clock.sleeps == []


def test_timeout_becomes_transport_error() -> None:
    client, session, _ = build_client([
        requests.Timeout(),
    ])

    with pytest.raises(
        IventasTransportError
    ):
        fetch_default(client)

    assert len(session.calls) == 1


def test_request_exception_becomes_transport_error(
) -> None:
    client, session, _ = build_client([
        requests.ConnectionError(),
    ])

    with pytest.raises(
        IventasTransportError
    ):
        fetch_default(client)

    assert len(session.calls) == 1


def test_http_200_invalid_json_is_payload_error(
) -> None:
    client, _, _ = build_client([
        FakeResponse(
            200,
            None,
            "not-json",
            json_error=True,
        ),
    ])

    with pytest.raises(
        IventasPayloadError
    ):
        fetch_default(client)


def test_contacts_must_be_list() -> None:
    client, _, _ = build_client([
        FakeResponse(
            200,
            {
                "contacts": {},
                "pagination": {
                    "hasMore": False,
                    "nextCursor": None,
                },
            },
            '{"contacts":{}}',
        ),
    ])

    with pytest.raises(
        IventasPayloadError,
        match="contacts",
    ):
        fetch_default(client)


def test_pagination_must_be_object() -> None:
    client, _, _ = build_client([
        FakeResponse(
            200,
            {
                "contacts": [],
                "pagination": None,
            },
            '{"contacts":[]}',
        ),
    ])

    with pytest.raises(
        IventasPayloadError,
        match="pagination",
    ):
        fetch_default(client)


def test_has_more_requires_next_cursor() -> None:
    client, _, _ = build_client([
        ok_response(
            has_more=True,
            next_cursor=None,
        ),
    ])

    with pytest.raises(
        IventasPayloadError,
        match="nextCursor",
    ):
        fetch_default(client)


def test_iter_pages_rejects_repeated_cursor(
) -> None:
    client, _, _ = build_client([
        ok_response(
            has_more=True,
            next_cursor="CURSOR_A",
        ),
        ok_response(
            has_more=True,
            next_cursor="CURSOR_A",
        ),
    ])

    with pytest.raises(
        IventasPayloadError,
        match="cursor",
    ):
        list(
            client.iter_pages(
                branch="papalote",
                from_utc=FROM_UTC,
                to_utc=TO_UTC,
                limit=100,
            )
        )


def test_provider_branch_is_exposed_without_business_mapping(
) -> None:
    client, _, _ = build_client([
        ok_response(),
    ])

    page = fetch_default(client)

    assert (
        page.provider_branch_code
        == "papalote"
    )

    assert (
        page.provider_branch_label
        == "Papalote"
    )


def test_raw_non_200_is_available_before_parse_error(
) -> None:
    raw_body = '{"error":"FORBIDDEN"}'

    client, session, _ = build_client([
        FakeResponse(
            403,
            {
                "error": "FORBIDDEN",
            },
            raw_body,
        ),
    ])

    raw = client.request_page_raw(
        branch="papalote",
        from_utc=FROM_UTC,
        to_utc=TO_UTC,
        limit=100,
    )

    assert len(session.calls) == 1
    assert raw.http_status == 403
    assert raw.raw_payload == raw_body

    with pytest.raises(
        IventasProviderError
    ) as exc_info:
        client.parse_page(raw)

    assert exc_info.value.status_code == 403
    assert (
        exc_info.value.provider_code
        == "FORBIDDEN"
    )


def test_raw_invalid_json_is_available_before_parse_error(
) -> None:
    raw_body = "not-json"

    client, _, _ = build_client([
        FakeResponse(
            200,
            None,
            raw_body,
            json_error=True,
        ),
    ])

    raw = client.request_page_raw(
        branch="papalote",
        from_utc=FROM_UTC,
        to_utc=TO_UTC,
    )

    assert raw.http_status == 200
    assert raw.raw_payload == raw_body

    with pytest.raises(
        IventasPayloadError
    ):
        client.parse_page(raw)


def test_retry_exhaustion_raw_response_is_still_available(
) -> None:
    responses = [
        FakeResponse(
            503,
            {
                "error": "SERVICE_UNAVAILABLE",
            },
            '{"error":"SERVICE_UNAVAILABLE"}',
        )
        for _ in range(4)
    ]

    client, session, clock = build_client(
        responses
    )

    raw = client.request_page_raw(
        branch="papalote",
        from_utc=FROM_UTC,
        to_utc=TO_UTC,
    )

    assert raw.http_status == 503
    assert len(session.calls) == 4
    assert clock.sleeps == [
        2.0,
        5.0,
        10.0,
    ]

    with pytest.raises(
        IventasProviderError
    ) as exc_info:
        client.parse_page(raw)

    assert exc_info.value.status_code == 503
    assert exc_info.value.retryable is True
