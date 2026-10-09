"""Google Ads M2 isolated tests: mock provider, no real credentials or Ads writes."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.models.google_ads_oauth import GoogleAdsOAuthCredentialORM
from app.routes import google_ads_readonly_routes as api
from app.services import google_ads_readonly_service as service


class FakeUser:
    def __init__(self, role=True):
        self.allowed = role

    def es_admin(self):
        return self.allowed


class Reply:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status
        self.headers = {}

    def json(self):
        return self.payload


@pytest.fixture
def ctx(monkeypatch):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="google-ads-m2-secret-key-for-tests-only",
        JWT_SECRET_KEY="google-ads-m2-jwt-key-for-tests-only",
    )
    JWTManager(app)
    app.register_blueprint(api.google_ads_readonly_bp, url_prefix="/google-ads")
    fernet_key = Fernet.generate_key()
    fernet = Fernet(fernet_key)
    users = {"7": FakeUser(role=True)}
    monkeypatch.setattr(
        api,
        "_admin",
        lambda: users["7"] if users["7"].es_admin() else None,
    )
    monkeypatch.setenv("GOOGLE_ADS_READONLY_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_ADS_OAUTH_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_ADS_OAUTH_CLIENT_ID", "qa-client-id")
    monkeypatch.setenv("GOOGLE_ADS_OAUTH_CLIENT_SECRET", "qa-client-secret")
    monkeypatch.setenv("GOOGLE_ADS_OAUTH_CUSTOMER_ID", "273-912-5201")
    monkeypatch.setenv("GOOGLE_ADS_OAUTH_TOKEN_ENCRYPTION_KEY", fernet_key.decode())
    monkeypatch.setenv("GOOGLE_ADS_DEVELOPER_TOKEN", "qa-developer-token")
    monkeypatch.setenv("GOOGLE_ADS_API_VERSION", "v25")
    monkeypatch.delenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", raising=False)

    grant = GoogleAdsOAuthCredentialORM(
        id=1,
        customer_id="2739125201",
        encrypted_refresh_token=fernet.encrypt(b"fake-refresh-token").decode(),
        authorized_by_user_id=7,
    )
    store = SimpleNamespace(row=grant)
    fake_db = SimpleNamespace(session=SimpleNamespace(
        get=lambda model, pk: store.row
    ))
    monkeypatch.setattr(service, "db", fake_db)

    calls = []

    def fake_get(url, **kwargs):
        calls.append(("GET", url, kwargs))
        assert url == "https://googleads.googleapis.com/v25/customers:listAccessibleCustomers"
        assert "login-customer-id" not in kwargs["headers"]
        return Reply({"resourceNames": ["customers/1234567890"]})

    def fake_post(url, **kwargs):
        calls.append(("POST", url, kwargs))
        if url == service.TOKEN_ENDPOINT:
            assert kwargs["data"]["refresh_token"] == "fake-refresh-token"
            return Reply({"access_token": "fake-access-token"})
        assert url == "https://googleads.googleapis.com/v25/customers/2739125201/googleAds:searchStream"
        assert kwargs["headers"]["Authorization"] == "Bearer fake-access-token"
        assert kwargs["headers"]["developer-token"] == "qa-developer-token"
        query = kwargs["json"]["query"]
        if "FROM customer" in query:
            return Reply([{"results": [{
                "customer": {
                    "id": "2739125201",
                    "descriptiveName": "Ultra Gym Marketing",
                    "currencyCode": "MXN",
                    "timeZone": "America/Tijuana",
                    "manager": False,
                }
            }]}])
        assert "FROM campaign" in query
        return Reply([{"results": [
            {"segments": {"date": "2026-10-01"},
             "campaign": {"id": "111", "name": "Ultra Tijuana",
                          "status": "ENABLED",
                          "advertisingChannelType": "SEARCH"},
             "metrics": {"costMicros": "10000000", "clicks": "20",
                         "impressions": "800", "conversions": 1.5}},
            {"segments": {"date": "2026-10-02"},
             "campaign": {"id": "111", "name": "Ultra Tijuana",
                          "status": "ENABLED",
                          "advertisingChannelType": "SEARCH"},
             "metrics": {"costMicros": "1250000", "clicks": "5",
                         "impressions": "120", "conversions": 0.25}},
        ]}])

    monkeypatch.setattr(service.requests, "get", fake_get)
    monkeypatch.setattr(service.requests, "post", fake_post)
    with app.app_context():
        jwt = create_access_token(identity="7")

    return SimpleNamespace(
        app=app,
        client=app.test_client(),
        headers={"Authorization": "Bearer " + jwt},
        calls=calls,
        store=store,
        users=users,
    )


def test_account_check_requires_jwt_and_suite_admin(ctx):
    assert ctx.client.get("/google-ads/account-check").status_code == 401
    ctx.users["7"] = FakeUser(role=False)
    res = ctx.client.get("/google-ads/account-check", headers=ctx.headers)
    assert res.status_code == 403
    assert ctx.calls == []


def test_report_requires_admin(ctx):
    ctx.users["7"] = FakeUser(role=False)
    res = ctx.client.get(
        "/google-ads/campaign-daily?date_from=2026-10-01&date_to=2026-10-02",
        headers=ctx.headers,
    )
    assert res.status_code == 403
    assert ctx.calls == []


def test_m2_disabled_independently_of_m1(ctx, monkeypatch):
    monkeypatch.delenv("GOOGLE_ADS_READONLY_ENABLED")
    res = ctx.client.get("/google-ads/account-check", headers=ctx.headers)
    assert res.status_code == 503
    assert res.json["code"] == "GOOGLE_ADS_READONLY_DISABLED"
    assert ctx.calls == []


def test_live_account_verification_allows_child_managed_by_mcc(ctx):
    res = ctx.client.get("/google-ads/account-check", headers=ctx.headers)
    assert res.status_code == 200
    assert res.json["account_access_verified"] is True
    assert res.json["target_directly_accessible"] is False
    assert res.json["account"]["customer_id"] == "2739125201"
    assert res.json["account"]["currency_code"] == "MXN"
    assert res.json["directly_accessible_customer_ids"] == ["1234567890"]
    assert res.json["api_version"] == "v25"
    assert "fake-access-token" not in res.text
    assert "fake-refresh-token" not in res.text
    assert "qa-developer-token" not in res.text
    assert res.headers["Cache-Control"] == "no-store"
    assert [x[0] for x in ctx.calls] == ["POST", "GET", "POST"]


def test_campaign_daily_returns_exact_cost_and_google_conversions_not_sales(ctx):
    res = ctx.client.get(
        "/google-ads/campaign-daily?date_from=2026-10-01&date_to=2026-10-02",
        headers=ctx.headers,
    )
    assert res.status_code == 200
    assert res.json["source"] == "GOOGLE_ADS_API_LIVE"
    assert res.json["snapshot_persisted"] is False
    assert res.json["totals"] == {
        "impressions": 920,
        "clicks": 25,
        "cost_micros": 11250000,
        "cost": "11.25",
        "conversions": "1.75",
    }
    assert len(res.json["rows"]) == 2
    assert res.json["rows"][1]["cost"] == "1.25"
    assert res.json["account"]["timezone"] == "America/Tijuana"
    assert "no equivalen" in res.json["conversions_note"]
    queries = [x[2]["json"]["query"] for x in ctx.calls
               if x[0] == "POST" and x[1].endswith("searchStream")]
    assert len(queries) == 2
    assert "BETWEEN '2026-10-01' AND '2026-10-02'" in queries[1]
    assert "metrics.cost_micros" in queries[1]
    assert "segments.date" in queries[1]
    assert "UPDATE " not in queries[1]
    assert "MUTATE " not in queries[1]


@pytest.mark.parametrize("start,end", [
    (None, "2026-10-03"), ("2026-10-01", None),
    ("2026-10-04", "2026-10-01"),
    ("2026-09-01", "2026-10-09"),
    ("2026-10-01'; DELETE FROM campaign", "2026-10-02"),
    ("2026-10-31", "2026-11-31"),
])
def test_date_rejection_without_external_calls(ctx, start, end):
    query_string = {}
    if start is not None:
        query_string["date_from"] = start
    if end is not None:
        query_string["date_to"] = end
    res = ctx.client.get(
        "/google-ads/campaign-daily",
        headers=ctx.headers,
        query_string=query_string,
    )
    assert res.status_code == 400
    assert res.json["code"] == "GOOGLE_ADS_DATE_RANGE_INVALID"
    assert ctx.calls == []


def test_missing_or_mismatched_grant_never_calls_google(ctx):
    ctx.store.row = None
    res = ctx.client.get("/google-ads/account-check", headers=ctx.headers)
    assert res.status_code == 409
    assert res.json["code"] == "GOOGLE_ADS_NOT_CONNECTED"
    assert ctx.calls == []
    ctx.store.row = GoogleAdsOAuthCredentialORM(
        id=1, customer_id="9999999999",
        encrypted_refresh_token="fake", authorized_by_user_id=7,
    )
    res = ctx.client.get("/google-ads/account-check", headers=ctx.headers)
    assert res.status_code == 409
    assert res.json["code"] == "GOOGLE_ADS_CUSTOMER_BINDING_MISMATCH"
    assert ctx.calls == []


def test_token_encryption_key_mismatch_is_safe(ctx):
    ctx.store.row.encrypted_refresh_token = "not-fernet"
    res = ctx.client.get("/google-ads/account-check", headers=ctx.headers)
    assert res.status_code == 503
    assert res.json["code"] == "GOOGLE_ADS_REFRESH_TOKEN_UNREADABLE"
    assert ctx.calls == []


def test_manager_header_only_when_configured(ctx, monkeypatch):
    monkeypatch.setenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "123-456-7890")
    res = ctx.client.get("/google-ads/account-check", headers=ctx.headers)
    assert res.status_code == 200
    get_headers = [x[2]["headers"] for x in ctx.calls if x[0] == "GET"]
    search_headers = [x[2]["headers"] for x in ctx.calls
                      if x[0] == "POST" and x[1].endswith("searchStream")]
    assert "login-customer-id" not in get_headers[0]
    assert search_headers[0]["login-customer-id"] == "1234567890"


def test_invalid_manager_id_fails_closed(ctx, monkeypatch):
    monkeypatch.setenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "evil: header")
    res = ctx.client.get("/google-ads/account-check", headers=ctx.headers)
    assert res.status_code == 503
    assert res.json["code"] == "GOOGLE_ADS_LOGIN_CUSTOMER_ID_INVALID"
    assert ctx.calls == []


def test_invalid_version_fails_closed(ctx, monkeypatch):
    monkeypatch.setenv("GOOGLE_ADS_API_VERSION", "https://evil.invalid/")
    res = ctx.client.get("/google-ads/account-check", headers=ctx.headers)
    assert res.status_code == 503
    assert res.json["code"] == "GOOGLE_ADS_API_VERSION_INVALID"
    assert ctx.calls == []


def test_provider_rate_limit_is_not_hidden(ctx, monkeypatch):
    monkeypatch.setattr(service.requests, "get", lambda *args, **kwargs: Reply({}, 429))
    res = ctx.client.get("/google-ads/account-check", headers=ctx.headers)
    assert res.status_code == 503
    assert res.json["code"] == "GOOGLE_ADS_API_QUOTA_OR_RATE_LIMIT"
    assert "qa-developer-token" not in res.text


def test_expired_refresh_requires_reauthorization(ctx, monkeypatch):
    monkeypatch.setattr(service.requests, "post", lambda *args, **kwargs: Reply(
        {"error": "invalid_grant", "debug": "must not echo"}, status=400
    ))
    res = ctx.client.get("/google-ads/account-check", headers=ctx.headers)
    assert res.status_code == 409
    assert res.json["code"] == "GOOGLE_ADS_REAUTHORIZATION_REQUIRED"
    assert "invalid_grant" not in res.text
    assert "must not echo" not in res.text


def test_account_response_other_customer_does_not_pass(ctx, monkeypatch):
    original = service._search_stream

    def wrong_account(settings, token, query):
        if "FROM customer" in query:
            return [{"customer": {
                "id": "1234567890", "currencyCode": "MXN",
                "timeZone": "America/Tijuana", "manager": False
            }}]
        return original(settings, token, query)

    monkeypatch.setattr(service, "_search_stream", wrong_account)
    res = ctx.client.get("/google-ads/account-check", headers=ctx.headers)
    assert res.status_code == 502
    assert res.json["code"] == "GOOGLE_ADS_CUSTOMER_ID_UNEXPECTED"


def test_report_is_rejected_for_manager_account(ctx, monkeypatch):
    original = service._search_stream

    def manager_account(settings, token, query):
        if "FROM customer" in query:
            return [{"customer": {
                "id": "2739125201", "currencyCode": "MXN",
                "timeZone": "America/Tijuana", "manager": True
            }}]
        return original(settings, token, query)

    monkeypatch.setattr(service, "_search_stream", manager_account)
    res = ctx.client.get(
        "/google-ads/campaign-daily?date_from=2026-10-01&date_to=2026-10-02",
        headers=ctx.headers,
    )
    assert res.status_code == 409
    assert res.json["code"] == "GOOGLE_ADS_TARGET_IS_MANAGER"


def test_response_over_limit_fails_instead_of_truncating(ctx, monkeypatch):
    monkeypatch.setattr(
        service, "_search_stream",
        lambda settings, token, query: (
            [{"customer": {"id": "2739125201", "currencyCode": "MXN",
                           "timeZone": "America/Tijuana", "manager": False}}]
            if "FROM customer" in query else [{}] * (service.MAX_REPORT_ROWS + 1)
        ),
    )
    res = ctx.client.get(
        "/google-ads/campaign-daily?date_from=2026-10-01&date_to=2026-10-02",
        headers=ctx.headers,
    )
    assert res.status_code == 502
    assert res.json["code"] == "GOOGLE_ADS_INVALID_PROVIDER_RESPONSE"


def test_search_stream_refuses_oversized_google_batch(ctx, monkeypatch):
    monkeypatch.setattr(
        service.requests, "post",
        lambda url, **kwargs: (
            Reply({"access_token": "temporary"})
            if url == service.TOKEN_ENDPOINT else
            Reply([{"results": [{}] * (service.MAX_REPORT_ROWS + 1)}])
        ),
    )
    res = ctx.client.get("/google-ads/account-check", headers=ctx.headers)
    assert res.status_code == 502
    assert res.json["code"] == "GOOGLE_ADS_RESPONSE_TOO_LARGE"
