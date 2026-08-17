from datetime import date, datetime, timezone
from types import SimpleNamespace

import app.services.marketing_meta_run_sync_service as service
from app.services.marketing_meta_persistence_service import (
    MarketingMetaStructuredPageResult,
)
from app.services.marketing_meta_service import (
    MarketingMetaRawPageResponse,
)


class _FakeSession:
    def __init__(self):
        self.rollback_calls = 0

    def rollback(self):
        self.rollback_calls += 1


class _FakeClient:
    def __init__(self):
        self.account_ids = []

    def fetch_insights_page(self, **kwargs):
        self.account_ids.append(kwargs["account_id"])
        return MarketingMetaRawPageResponse(
            http_status=200,
            request_cursor=kwargs["after"],
            raw_payload='{"data":[],"paging":{}}',
        )


def test_full_run_keeps_multiple_accounts_in_one_canonical_snapshot(
    monkeypatch,
):
    call_order = []
    session = _FakeSession()
    client = _FakeClient()
    next_page_id = iter((101, 102))
    original_parse = service.parse_meta_raw_page

    monkeypatch.setattr(
        service,
        "create_meta_sync_run_running",
        lambda **_: SimpleNamespace(id=41),
    )

    def fake_persist_raw(**kwargs):
        call_order.append(f"raw:{kwargs['account_id']}")
        return SimpleNamespace(id=next(next_page_id))

    def traced_parse(raw_response):
        call_order.append("parse")
        return original_parse(raw_response)

    def fake_apply_metadata(**kwargs):
        call_order.append(f"metadata:{kwargs['raw_page_id']}")

    def fake_persist_structured(**kwargs):
        call_order.append(f"structured:{kwargs['raw_page_id']}")
        return MarketingMetaStructuredPageResult(
            insights_received=0,
            insights_created=0,
            insights_existing=0,
        )

    monkeypatch.setattr(
        service,
        "persist_meta_raw_page_pre_parse",
        fake_persist_raw,
    )
    monkeypatch.setattr(service, "parse_meta_raw_page", traced_parse)
    monkeypatch.setattr(
        service,
        "apply_meta_raw_page_parse_metadata",
        fake_apply_metadata,
    )
    monkeypatch.setattr(
        service,
        "persist_meta_structured_page",
        fake_persist_structured,
    )

    def fake_finalize(**kwargs):
        assert kwargs["status"] == "COMPLETED"
        assert kwargs["make_canonical"] is True
        assert kwargs["counters"].accounts_completed == 2
        assert kwargs["counters"].accounts_failed == 0
        assert kwargs["counters"].pages_received == 2
        return SimpleNamespace(
            period_key="META-2026-08",
            status="COMPLETED",
            is_canonical=True,
            replaced_canonical_run_id=9,
        )

    monkeypatch.setattr(
        service,
        "finalize_meta_sync_run",
        fake_finalize,
    )

    result = service.sync_meta_full_run(
        period_key="META-2026-08",
        date_from=date(2026, 8, 1),
        date_to=date(2026, 8, 31),
        accounts=(
            service.MarketingMetaAccount("act_123", "token-a"),
            service.MarketingMetaAccount("456", "token-b"),
        ),
        client=client,
        started_at=datetime(2026, 8, 17, tzinfo=timezone.utc),
        finished_at=datetime(2026, 8, 17, tzinfo=timezone.utc),
        session=session,
    )

    assert client.account_ids == ["123", "456"]
    assert call_order == [
        "raw:123",
        "parse",
        "metadata:101",
        "structured:101",
        "raw:456",
        "parse",
        "metadata:102",
        "structured:102",
    ]
    assert result.accounts_requested == 2
    assert result.accounts_completed == 2
    assert result.pages_received == 2
    assert result.is_canonical is True
    assert result.replaced_canonical_run_id == 9
    assert "token-a" not in repr(
        service.MarketingMetaAccount("123", "token-a")
    )
