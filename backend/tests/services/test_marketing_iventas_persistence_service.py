from datetime import (
    date,
    datetime,
    timezone,
)

import pytest

from app.integrations.iventas import (
    IventasPage,
    IventasRawPageResponse,
)
from app.models import (
    MarketingIventasRawPageORM,
    MarketingIventasSyncRunORM,
)
from app.services.marketing_iventas_persistence_service import (
    MarketingIventasPersistenceError,
    SYNC_STATUS_RUNNING,
    apply_iventas_raw_page_parse_metadata,
    create_iventas_sync_run_running,
    persist_iventas_raw_page_pre_parse,
)


class FakeQuery:
    def __init__(
        self,
        result=None,
    ):
        self.result = result
        self.filters = None

    def filter_by(
        self,
        **kwargs,
    ):
        self.filters = kwargs
        return self

    def first(self):
        return self.result


class FakeSession:
    def __init__(
        self,
        *,
        query_result=None,
        get_result=None,
    ):
        self.query_result = query_result
        self.get_result = get_result

        self.added = []
        self.commit_count = 0
        self.query_model = None
        self.get_calls = []

    def add(
        self,
        obj,
    ):
        self.added.append(obj)

    def commit(self):
        self.commit_count += 1

    def query(
        self,
        model,
    ):
        self.query_model = model

        return FakeQuery(
            self.query_result
        )

    def get(
        self,
        model,
        object_id,
    ):
        self.get_calls.append(
            (
                model,
                object_id,
            )
        )

        return self.get_result


def _raw_response():
    return IventasRawPageResponse(
        request_cursor=None,
        http_status=200,
        raw_payload='{"contacts":[]}',
        _response=object(),
    )


def _parsed_page():
    return IventasPage(
        request_cursor=None,
        http_status=200,
        raw_payload='{"contacts":[]}',
        payload={
            "contacts": [],
            "pagination": {
                "hasMore": True,
                "nextCursor": "cursor-2",
            },
        },
        contacts=[],
        has_more=True,
        next_cursor="cursor-2",
        provider_branch_code="papalote",
        provider_branch_label="Papalote",
    )


def test_create_running_sync_run_commits_boundary(
) -> None:
    session = FakeSession()

    started_at = datetime(
        2026,
        8,
        9,
        3,
        0,
        tzinfo=timezone.utc,
    )

    run = create_iventas_sync_run_running(
        period_key="2026-08",
        date_from=date(2026, 8, 1),
        date_to=date(2026, 8, 8),
        branches_requested=26,
        started_at=started_at,
        session=session,
    )

    assert isinstance(
        run,
        MarketingIventasSyncRunORM,
    )

    assert run.status == SYNC_STATUS_RUNNING
    assert run.started_at == started_at
    assert run.branches_requested == 26
    assert run.branches_completed == 0
    assert run.branches_failed == 0
    assert run.aliases_resolved == 0
    assert run.aliases_unresolved == 0
    assert run.is_canonical is False

    assert session.added == [run]
    assert session.commit_count == 1


def test_raw_pre_parse_commits_null_parse_metadata(
) -> None:
    session = FakeSession()

    raw = _raw_response()

    received_at = datetime(
        2026,
        8,
        9,
        3,
        1,
        tzinfo=timezone.utc,
    )

    row = persist_iventas_raw_page_pre_parse(
        sync_run_id=7,
        branch_code="papalote",
        page_number=1,
        raw_response=raw,
        received_at=received_at,
        session=session,
    )

    assert isinstance(
        row,
        MarketingIventasRawPageORM,
    )

    assert row.sync_run_id == 7
    assert row.branch_code == "papalote"
    assert row.page_number == 1
    assert row.request_cursor is None
    assert row.has_more is None
    assert row.next_cursor is None
    assert row.http_status == 200
    assert (
        row.payload_json
        == '{"contacts":[]}'
    )
    assert row.received_at == received_at

    assert session.added == [row]
    assert session.commit_count == 1


def test_same_raw_page_is_idempotent(
) -> None:
    existing = MarketingIventasRawPageORM(
        sync_run_id=7,
        branch_code="papalote",
        page_number=1,
        request_cursor=None,
        next_cursor=None,
        has_more=None,
        http_status=200,
        payload_json='{"contacts":[]}',
        received_at=datetime(
            2026,
            8,
            9,
            3,
            1,
            tzinfo=timezone.utc,
        ),
    )

    session = FakeSession(
        query_result=existing,
    )

    result = persist_iventas_raw_page_pre_parse(
        sync_run_id=7,
        branch_code="papalote",
        page_number=1,
        raw_response=_raw_response(),
        session=session,
    )

    assert result is existing
    assert session.added == []
    assert session.commit_count == 0


def test_same_page_key_with_different_raw_fails(
) -> None:
    existing = MarketingIventasRawPageORM(
        sync_run_id=7,
        branch_code="papalote",
        page_number=1,
        request_cursor=None,
        next_cursor=None,
        has_more=None,
        http_status=200,
        payload_json='{"version":1}',
        received_at=datetime(
            2026,
            8,
            9,
            3,
            1,
            tzinfo=timezone.utc,
        ),
    )

    session = FakeSession(
        query_result=existing,
    )

    with pytest.raises(
        MarketingIventasPersistenceError,
        match="contenido HTTP diferente",
    ):
        persist_iventas_raw_page_pre_parse(
            sync_run_id=7,
            branch_code="papalote",
            page_number=1,
            raw_response=_raw_response(),
            session=session,
        )

    assert session.commit_count == 0


def test_apply_parse_metadata_commits_without_touching_raw(
) -> None:
    raw_row = MarketingIventasRawPageORM(
        sync_run_id=7,
        branch_code="papalote",
        page_number=1,
        request_cursor=None,
        next_cursor=None,
        has_more=None,
        http_status=200,
        payload_json='{"contacts":[]}',
        received_at=datetime(
            2026,
            8,
            9,
            3,
            1,
            tzinfo=timezone.utc,
        ),
    )

    session = FakeSession(
        get_result=raw_row,
    )

    page = _parsed_page()

    result = apply_iventas_raw_page_parse_metadata(
        raw_page_id=11,
        page=page,
        session=session,
    )

    assert result is raw_row
    assert raw_row.has_more is True
    assert raw_row.next_cursor == "cursor-2"

    assert (
        raw_row.payload_json
        == '{"contacts":[]}'
    )

    assert session.commit_count == 1

    assert session.get_calls == [
        (
            MarketingIventasRawPageORM,
            11,
        )
    ]


def test_apply_same_parse_metadata_is_idempotent(
) -> None:
    raw_row = MarketingIventasRawPageORM(
        sync_run_id=7,
        branch_code="papalote",
        page_number=1,
        request_cursor=None,
        next_cursor="cursor-2",
        has_more=True,
        contacts_count=len(
            _parsed_page().contacts
        ),
        http_status=200,
        payload_json='{"contacts":[]}',
        received_at=datetime(
            2026,
            8,
            9,
            3,
            1,
            tzinfo=timezone.utc,
        ),
    )

    session = FakeSession(
        get_result=raw_row,
    )

    result = apply_iventas_raw_page_parse_metadata(
        raw_page_id=11,
        page=_parsed_page(),
        session=session,
    )

    assert result is raw_row
    assert session.commit_count == 0


def test_parse_metadata_must_match_persisted_raw(
) -> None:
    raw_row = MarketingIventasRawPageORM(
        sync_run_id=7,
        branch_code="papalote",
        page_number=1,
        request_cursor=None,
        next_cursor=None,
        has_more=None,
        http_status=200,
        payload_json='{"different":true}',
        received_at=datetime(
            2026,
            8,
            9,
            3,
            1,
            tzinfo=timezone.utc,
        ),
    )

    session = FakeSession(
        get_result=raw_row,
    )

    with pytest.raises(
        MarketingIventasPersistenceError,
        match="no corresponde",
    ):
        apply_iventas_raw_page_parse_metadata(
            raw_page_id=11,
            page=_parsed_page(),
            session=session,
        )

    assert session.commit_count == 0


def test_missing_raw_page_fails(
) -> None:
    session = FakeSession(
        get_result=None,
    )

    with pytest.raises(
        MarketingIventasPersistenceError,
        match="No existe",
    ):
        apply_iventas_raw_page_parse_metadata(
            raw_page_id=999,
            page=_parsed_page(),
            session=session,
        )

    assert session.commit_count == 0
