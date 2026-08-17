from __future__ import annotations

from datetime import date, datetime, timezone
import json

import pytest

from app.models import (
    MarketingMetaAdInsightORM,
    MarketingMetaRawPageORM,
    MarketingMetaSyncRunORM,
)
from app.services.marketing_meta_persistence_service import (
    MarketingMetaPersistenceError,
    MarketingMetaRunCounters,
    apply_meta_raw_page_parse_metadata,
    create_meta_sync_run_running,
    finalize_meta_sync_run,
    persist_meta_raw_page_pre_parse,
    persist_meta_structured_page,
)
from app.services.marketing_meta_service import (
    MarketingMetaParseError,
    MarketingMetaRawPageResponse,
    parse_meta_raw_page,
)


class _FakeQuery:
    def __init__(self, session, model):
        self.session = session
        self.model = model
        self.filters = {}

    def filter_by(self, **kwargs):
        self.filters.update(kwargs)
        return self

    def _matches(self, row) -> bool:
        return all(
            getattr(row, field_name) == value
            for field_name, value in self.filters.items()
        )

    def first(self):
        return next(
            (
                row
                for row in self.session.rows.get(self.model, [])
                if self._matches(row)
            ),
            None,
        )

    def all(self):
        return [
            row
            for row in self.session.rows.get(self.model, [])
            if self._matches(row)
        ]


class _FakeSession:
    def __init__(self):
        self.rows = {}
        self.next_id = 1
        self.commit_calls = 0
        self.rollback_calls = 0
        self.flush_calls = 0

    def add(self, row):
        if row.id is None:
            row.id = self.next_id
            self.next_id += 1
        self.rows.setdefault(type(row), []).append(row)

    def query(self, model):
        return _FakeQuery(self, model)

    def get(self, model, object_id):
        return next(
            (
                row
                for row in self.rows.get(model, [])
                if int(row.id) == int(object_id)
            ),
            None,
        )

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1

    def flush(self):
        self.flush_calls += 1


def _raw_response() -> MarketingMetaRawPageResponse:
    return MarketingMetaRawPageResponse(
        http_status=200,
        request_cursor=None,
        raw_payload=json.dumps(
            {
                "data": [
                    {
                        "account_id": "123",
                        "account_name": "Cuenta Norte",
                        "campaign_id": "200",
                        "campaign_name": "Campaña Agosto",
                        "adset_id": "300",
                        "adset_name": "Prospección",
                        "ad_id": "400",
                        "ad_name": "Video A",
                        "date_start": "2026-08-01",
                        "date_stop": "2026-08-31",
                        "spend": "125.75",
                        "reach": "1000",
                        "impressions": "1500",
                        "clicks": "75",
                        "actions": [
                            {
                                "action_type": "lead",
                                "value": "30",
                                "1d_click": "25",
                            },
                            {
                                "action_type": "link_click",
                                "value": "70",
                            },
                        ],
                    }
                ],
                "paging": {},
            },
            separators=(",", ":"),
        ),
    )


def test_parser_preserves_complete_actions_and_stable_hash():
    first = parse_meta_raw_page(_raw_response())
    second = parse_meta_raw_page(_raw_response())

    assert len(first.insights) == 1
    insight = first.insights[0]
    assert insight.account_id == "123"
    assert insight.ad_id == "400"
    assert insight.actions == (
        {
            "action_type": "lead",
            "value": "30",
            "1d_click": "25",
        },
        {
            "action_type": "link_click",
            "value": "70",
        },
    )
    assert insight.row_hash == second.insights[0].row_hash


def test_parser_does_not_truncate_meta_names():
    payload = json.loads(_raw_response().raw_payload)
    long_name = "Campaña " + ("X" * 400)
    payload["data"][0]["campaign_name"] = long_name
    parsed = parse_meta_raw_page(
        MarketingMetaRawPageResponse(
            http_status=200,
            request_cursor=None,
            raw_payload=json.dumps(payload),
        )
    )
    assert parsed.insights[0].campaign_name == long_name


def test_parser_rejects_missing_metrics_instead_of_inventing_zero():
    payload = json.loads(_raw_response().raw_payload)
    del payload["data"][0]["spend"]
    with pytest.raises(
        MarketingMetaParseError,
        match="spend es obligatorio",
    ):
        parse_meta_raw_page(
            MarketingMetaRawPageResponse(
                http_status=200,
                request_cursor=None,
                raw_payload=json.dumps(payload),
            )
        )


def test_raw_is_committed_before_structured_and_retry_is_idempotent():
    session = _FakeSession()
    started_at = datetime(2026, 8, 17, tzinfo=timezone.utc)
    run = create_meta_sync_run_running(
        period_key="META-2026-08",
        date_from=date(2026, 8, 1),
        date_to=date(2026, 8, 31),
        accounts_requested=1,
        started_at=started_at,
        session=session,
    )
    assert session.commit_calls == 1

    raw_response = _raw_response()
    raw_page = persist_meta_raw_page_pre_parse(
        sync_run_id=int(run.id),
        account_id="act_123",
        page_number=1,
        raw_response=raw_response,
        received_at=started_at,
        session=session,
    )
    assert session.commit_calls == 2
    assert raw_page.payload_json == raw_response.raw_payload
    assert raw_page.rows_count is None

    page = parse_meta_raw_page(raw_response)
    apply_meta_raw_page_parse_metadata(
        raw_page_id=int(raw_page.id),
        page=page,
        session=session,
    )
    assert session.commit_calls == 3
    assert raw_page.rows_count == 1

    first_result = persist_meta_structured_page(
        sync_run_id=int(run.id),
        raw_page_id=int(raw_page.id),
        insights=page.insights,
        session=session,
    )
    assert first_result.insights_created == 1
    assert session.commit_calls == 4
    stored = session.rows[MarketingMetaAdInsightORM][0]
    assert stored.raw_page_id == raw_page.id
    assert stored.actions_json[0]["1d_click"] == "25"

    retry_result = persist_meta_structured_page(
        sync_run_id=int(run.id),
        raw_page_id=int(raw_page.id),
        insights=page.insights,
        session=session,
    )
    assert retry_result.insights_created == 0
    assert retry_result.insights_existing == 1
    assert session.commit_calls == 4


def test_same_raw_identity_cannot_be_overwritten():
    session = _FakeSession()
    run = create_meta_sync_run_running(
        period_key="META-2026-08",
        date_from=date(2026, 8, 1),
        date_to=date(2026, 8, 31),
        accounts_requested=1,
        started_at=datetime(2026, 8, 17, tzinfo=timezone.utc),
        session=session,
    )
    persist_meta_raw_page_pre_parse(
        sync_run_id=int(run.id),
        account_id="123",
        page_number=1,
        raw_response=_raw_response(),
        session=session,
    )

    with pytest.raises(
        MarketingMetaPersistenceError,
        match="contenido HTTP diferente",
    ):
        persist_meta_raw_page_pre_parse(
            sync_run_id=int(run.id),
            account_id="123",
            page_number=1,
            raw_response=MarketingMetaRawPageResponse(
                http_status=200,
                request_cursor=None,
                raw_payload='{"data":[]}',
            ),
            session=session,
        )


def test_canonical_finalize_replaces_previous_and_is_idempotent():
    session = _FakeSession()
    started_at = datetime(2026, 8, 17, tzinfo=timezone.utc)
    previous = MarketingMetaSyncRunORM(
        period_key="META-2026-08",
        date_from=date(2026, 8, 1),
        date_to=date(2026, 8, 31),
        started_at=started_at,
        finished_at=started_at,
        status="COMPLETED",
        accounts_requested=1,
        accounts_completed=1,
        accounts_failed=0,
        pages_received=1,
        insights_received=1,
        insights_unique=1,
        is_canonical=True,
    )
    session.add(previous)
    current = create_meta_sync_run_running(
        period_key="META-2026-08",
        date_from=date(2026, 8, 1),
        date_to=date(2026, 8, 31),
        accounts_requested=1,
        started_at=started_at,
        session=session,
    )
    counters = MarketingMetaRunCounters(
        accounts_completed=1,
        accounts_failed=0,
        pages_received=2,
        insights_received=4,
        insights_unique=4,
    )

    first = finalize_meta_sync_run(
        sync_run_id=int(current.id),
        status="COMPLETED",
        counters=counters,
        make_canonical=True,
        finished_at=started_at,
        session=session,
    )
    assert previous.is_canonical is False
    assert current.is_canonical is True
    assert first.replaced_canonical_run_id == previous.id
    assert session.flush_calls == 1

    second = finalize_meta_sync_run(
        sync_run_id=int(current.id),
        status="COMPLETED",
        counters=counters,
        make_canonical=True,
        finished_at=started_at,
        session=session,
    )
    assert second.was_already_finalized is True
    assert second.replaced_canonical_run_id is None


def test_meta_models_do_not_duplicate_iventas_contacts():
    table_names = {
        MarketingMetaSyncRunORM.__tablename__,
        MarketingMetaRawPageORM.__tablename__,
        MarketingMetaAdInsightORM.__tablename__,
    }
    assert table_names == {
        "marketing_meta_sync_runs",
        "marketing_meta_raw_pages",
        "marketing_meta_ad_insights",
    }
    assert "contact_id" not in MarketingMetaAdInsightORM.__table__.c
    assert "phone" not in MarketingMetaAdInsightORM.__table__.c
