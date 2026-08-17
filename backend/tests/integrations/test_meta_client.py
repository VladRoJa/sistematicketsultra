from datetime import date

from app.integrations.meta import MetaInsightsClient


class _FakeResponse:
    status_code = 200
    text = '{"data":[]}'


class _FakeHttpSession:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _FakeResponse()


def test_client_requests_complete_ad_level_insights_contract():
    http = _FakeHttpSession()
    client = MetaInsightsClient(
        api_version="v99.0",
        http_session=http,
    )

    response = client.fetch_insights_page(
        account_id="act_123",
        access_token="secret-token",
        date_from=date(2026, 8, 1),
        date_to=date(2026, 8, 31),
        after="cursor-a",
        limit=250,
    )

    url, kwargs = http.calls[0]
    assert url == (
        "https://graph.facebook.com/v99.0/act_123/insights"
    )
    assert kwargs["params"]["level"] == "ad"
    assert kwargs["params"]["after"] == "cursor-a"
    assert kwargs["params"]["limit"] == 250
    assert '"since":"2026-08-01"' in kwargs["params"][
        "time_range"
    ]
    assert '"until":"2026-08-31"' in kwargs["params"][
        "time_range"
    ]
    fields = set(kwargs["params"]["fields"].split(","))
    assert {
        "account_id",
        "account_name",
        "campaign_id",
        "campaign_name",
        "adset_id",
        "adset_name",
        "ad_id",
        "ad_name",
        "date_start",
        "date_stop",
        "spend",
        "reach",
        "impressions",
        "clicks",
        "actions",
    } <= fields
    assert response.request_cursor == "cursor-a"
    assert response.raw_payload == _FakeResponse.text
