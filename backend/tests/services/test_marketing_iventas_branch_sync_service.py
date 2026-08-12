from datetime import (
    datetime,
    timezone,
)
from types import SimpleNamespace

import pytest

from app.integrations.iventas import (
    IventasPage,
    IventasRawPageResponse,
)
from app.models import (
    MarketingIventasRawPageORM,
    MarketingIventasSyncRunORM,
)
from app.services.marketing_iventas_branch_service import (
    MarketingIventasBranchResolution,
)
from app.services.marketing_iventas_branch_sync_service import (
    MarketingIventasBranchSyncError,
    sync_iventas_branch_pages,
)
from app.services.marketing_iventas_structured_persistence_service import (
    MarketingIventasStructuredPageResult,
)

import app.services.marketing_iventas_branch_sync_service as service


OBSERVED_AT = datetime(
    2026,
    8,
    10,
    16,
    0,
    tzinfo=timezone.utc,
)


class FakeRawQuery:
    def __init__(
        self,
        existing_raw,
    ):
        self.existing_raw = (
            existing_raw
        )
        self.filters = {}

    def filter_by(
        self,
        **kwargs,
    ):
        self.filters = kwargs
        return self

    def first(self):
        return self.existing_raw


class FakeSession:
    def __init__(
        self,
        *,
        run=None,
        existing_raw=None,
    ):
        self.run = run
        self.existing_raw = (
            existing_raw
        )

    def get(
        self,
        model,
        object_id,
    ):
        assert (
            model
            is MarketingIventasSyncRunORM
        )

        if (
            self.run is not None
            and self.run.id == object_id
        ):
            return self.run

        return None

    def query(
        self,
        model,
    ):
        assert (
            model
            is MarketingIventasRawPageORM
        )

        return FakeRawQuery(
            self.existing_raw
        )


class FakeClient:
    def __init__(
        self,
        *,
        raw_responses,
        pages,
        events,
    ):
        self.raw_responses = list(
            raw_responses
        )
        self.pages = list(
            pages
        )
        self.events = events
        self.request_calls = []

    def request_page_raw(
        self,
        *,
        branch,
        from_utc,
        to_utc,
        limit,
        cursor,
    ):
        self.events.append(
            f"request:{cursor}"
        )

        self.request_calls.append(
            {
                "branch": branch,
                "from_utc": from_utc,
                "to_utc": to_utc,
                "limit": limit,
                "cursor": cursor,
            }
        )

        if not self.raw_responses:
            raise AssertionError(
                "Request HTTP inesperado."
            )

        return self.raw_responses.pop(
            0
        )

    def parse_page(
        self,
        raw_response,
    ):
        self.events.append(
            f"parse:{raw_response.request_cursor}"
        )

        if not self.pages:
            raise AssertionError(
                "Parse inesperado."
            )

        return self.pages.pop(
            0
        )


def _run(
    *,
    status="RUNNING",
):
    return SimpleNamespace(
        id=7,
        status=status,
    )


def _resolution():
    return MarketingIventasBranchResolution(
        branch_code="papalote",
        sucursal_canon="PAPALOTE_TJ",
        sucursal_id=13,
    )


def _raw(
    *,
    cursor=None,
    payload="{}",
):
    return IventasRawPageResponse(
        request_cursor=cursor,
        http_status=200,
        raw_payload=payload,
        _response=object(),
    )


def _page(
    *,
    cursor=None,
    contacts=None,
    has_more=False,
    next_cursor=None,
    payload="{}",
):
    return IventasPage(
        request_cursor=cursor,
        http_status=200,
        raw_payload=payload,
        payload={},
        contacts=list(
            contacts or []
        ),
        has_more=has_more,
        next_cursor=next_cursor,
        provider_branch_code="papalote",
        provider_branch_label="Papalote",
    )


def _install_persistence_mocks(
    monkeypatch,
    *,
    events,
    structured_results,
):
    raw_ids = iter(
        range(
            100,
            1000,
        )
    )

    structured_queue = list(
        structured_results
    )

    def persist_raw(
        *,
        sync_run_id,
        branch_code,
        page_number,
        raw_response,
        received_at,
        session,
    ):
        events.append(
            f"raw_commit:{page_number}"
        )

        assert sync_run_id == 7
        assert branch_code == "papalote"
        assert received_at.tzinfo is not None

        return SimpleNamespace(
            id=next(raw_ids),
            received_at=OBSERVED_AT,
        )

    def apply_metadata(
        *,
        raw_page_id,
        page,
        session,
    ):
        events.append(
            f"metadata_commit:{raw_page_id}"
        )

        return SimpleNamespace(
            id=raw_page_id
        )

    def normalize(
        *,
        contact,
        branch_code,
        sucursal_id,
    ):
        events.append(
            f"normalize:{contact['id']}"
        )

        assert branch_code == "papalote"
        assert sucursal_id == 13

        return SimpleNamespace(
            contact_id=contact["id"]
        )

    def persist_structured(
        *,
        sync_run_id,
        contacts,
        observed_at,
        session,
    ):
        events.append(
            "structured_commit"
        )

        assert sync_run_id == 7
        assert observed_at == OBSERVED_AT

        if not structured_queue:
            raise AssertionError(
                "Persistencia estructurada inesperada."
            )

        return structured_queue.pop(
            0
        )

    monkeypatch.setattr(
        service,
        "persist_iventas_raw_page_pre_parse",
        persist_raw,
    )

    monkeypatch.setattr(
        service,
        "apply_iventas_raw_page_parse_metadata",
        apply_metadata,
    )

    monkeypatch.setattr(
        service,
        "normalize_iventas_contact",
        normalize,
    )

    monkeypatch.setattr(
        service,
        "persist_iventas_normalized_page",
        persist_structured,
    )

    monkeypatch.setattr(
        service,
        "resolve_iventas_branch",
        lambda branch: _resolution(),
    )


def _structured_result(
    *,
    received,
    created,
    existing=0,
    tags=0,
):
    return MarketingIventasStructuredPageResult(
        contacts_received=received,
        contacts_created=created,
        contacts_existing=existing,
        tags_created=tags,
        contact_row_ids=tuple(
            range(
                1,
                created + existing + 1,
            )
        ),
    )


def test_two_pages_follow_exact_raw_first_sequence(
    monkeypatch,
) -> None:
    events = []

    client = FakeClient(
        raw_responses=[
            _raw(
                cursor=None,
                payload='{"page":1}',
            ),
            _raw(
                cursor="cursor-2",
                payload='{"page":2}',
            ),
        ],
        pages=[
            _page(
                cursor=None,
                contacts=[
                    {"id": "a"},
                    {"id": "b"},
                ],
                has_more=True,
                next_cursor="cursor-2",
                payload='{"page":1}',
            ),
            _page(
                cursor="cursor-2",
                contacts=[
                    {"id": "c"},
                ],
                has_more=False,
                next_cursor=None,
                payload='{"page":2}',
            ),
        ],
        events=events,
    )

    _install_persistence_mocks(
        monkeypatch,
        events=events,
        structured_results=[
            _structured_result(
                received=2,
                created=2,
                tags=3,
            ),
            _structured_result(
                received=1,
                created=1,
                tags=1,
            ),
        ],
    )

    result = sync_iventas_branch_pages(
        sync_run_id=7,
        branch_code="papalote",
        from_utc=(
            "2026-08-01T07:00:00.000Z"
        ),
        to_utc=(
            "2026-08-11T06:59:59.999Z"
        ),
        client=client,
        page_limit=100,
        session=FakeSession(
            run=_run()
        ),
    )

    assert events == [
        "request:None",
        "raw_commit:1",
        "parse:None",
        "metadata_commit:100",
        "normalize:a",
        "normalize:b",
        "structured_commit",
        "request:cursor-2",
        "raw_commit:2",
        "parse:cursor-2",
        "metadata_commit:101",
        "normalize:c",
        "structured_commit",
    ]

    assert [
        call["cursor"]
        for call
        in client.request_calls
    ] == [
        None,
        "cursor-2",
    ]

    assert result.pages_processed == 2
    assert result.contacts_received == 3
    assert result.contacts_created == 3
    assert result.contacts_existing == 0
    assert result.tags_created == 4

    assert result.branch_code == "papalote"
    assert result.sucursal_canon == "PAPALOTE_TJ"
    assert result.sucursal_id == 13


def test_structured_existing_counts_are_aggregated(
    monkeypatch,
) -> None:
    events = []

    client = FakeClient(
        raw_responses=[
            _raw(),
        ],
        pages=[
            _page(
                contacts=[
                    {"id": "a"},
                    {"id": "b"},
                ],
            ),
        ],
        events=events,
    )

    _install_persistence_mocks(
        monkeypatch,
        events=events,
        structured_results=[
            _structured_result(
                received=2,
                created=1,
                existing=1,
                tags=1,
            ),
        ],
    )

    result = sync_iventas_branch_pages(
        sync_run_id=7,
        branch_code="papalote",
        from_utc="from",
        to_utc="to",
        client=client,
        session=FakeSession(
            run=_run()
        ),
    )

    assert result.contacts_received == 2
    assert result.contacts_created == 1
    assert result.contacts_existing == 1
    assert result.tags_created == 1


def test_unresolved_branch_stops_before_http(
    monkeypatch,
) -> None:
    events = []

    client = FakeClient(
        raw_responses=[],
        pages=[],
        events=events,
    )

    monkeypatch.setattr(
        service,
        "resolve_iventas_branch",
        lambda branch: None,
    )

    with pytest.raises(
        MarketingIventasBranchSyncError,
        match="no resolvió",
    ):
        sync_iventas_branch_pages(
            sync_run_id=7,
            branch_code="desconocida",
            from_utc="from",
            to_utc="to",
            client=client,
            session=FakeSession(
                run=_run()
            ),
        )

    assert events == []


def test_missing_run_stops_before_branch_resolution_and_http(
    monkeypatch,
) -> None:
    events = []

    client = FakeClient(
        raw_responses=[],
        pages=[],
        events=events,
    )

    called = {
        "resolver": False,
    }

    def resolver(branch):
        called["resolver"] = True
        return _resolution()

    monkeypatch.setattr(
        service,
        "resolve_iventas_branch",
        resolver,
    )

    with pytest.raises(
        MarketingIventasBranchSyncError,
        match="No existe",
    ):
        sync_iventas_branch_pages(
            sync_run_id=7,
            branch_code="papalote",
            from_utc="from",
            to_utc="to",
            client=client,
            session=FakeSession(
                run=None
            ),
        )

    assert called["resolver"] is False
    assert events == []


def test_terminal_run_stops_before_http(
    monkeypatch,
) -> None:
    events = []

    client = FakeClient(
        raw_responses=[],
        pages=[],
        events=events,
    )

    called = {
        "resolver": False,
    }

    def resolver(branch):
        called["resolver"] = True
        return _resolution()

    monkeypatch.setattr(
        service,
        "resolve_iventas_branch",
        resolver,
    )

    with pytest.raises(
        MarketingIventasBranchSyncError,
        match="RUNNING",
    ):
        sync_iventas_branch_pages(
            sync_run_id=7,
            branch_code="papalote",
            from_utc="from",
            to_utc="to",
            client=client,
            session=FakeSession(
                run=_run(
                    status="COMPLETED"
                )
            ),
        )

    assert called["resolver"] is False
    assert events == []


def test_existing_raw_page_blocks_ambiguous_resume(
    monkeypatch,
) -> None:
    events = []

    client = FakeClient(
        raw_responses=[],
        pages=[],
        events=events,
    )

    monkeypatch.setattr(
        service,
        "resolve_iventas_branch",
        lambda branch: _resolution(),
    )

    with pytest.raises(
        MarketingIventasBranchSyncError,
        match="Resume/retry",
    ):
        sync_iventas_branch_pages(
            sync_run_id=7,
            branch_code="papalote",
            from_utc="from",
            to_utc="to",
            client=client,
            session=FakeSession(
                run=_run(),
                existing_raw=SimpleNamespace(
                    id=99
                ),
            ),
        )

    assert events == []


def test_has_more_without_next_cursor_fails_after_page_is_preserved(
    monkeypatch,
) -> None:
    events = []

    client = FakeClient(
        raw_responses=[
            _raw(),
        ],
        pages=[
            _page(
                contacts=[
                    {"id": "a"},
                ],
                has_more=True,
                next_cursor=None,
            ),
        ],
        events=events,
    )

    _install_persistence_mocks(
        monkeypatch,
        events=events,
        structured_results=[
            _structured_result(
                received=1,
                created=1,
            ),
        ],
    )

    with pytest.raises(
        MarketingIventasBranchSyncError,
        match="sin next_cursor",
    ):
        sync_iventas_branch_pages(
            sync_run_id=7,
            branch_code="papalote",
            from_utc="from",
            to_utc="to",
            client=client,
            session=FakeSession(
                run=_run()
            ),
        )

    assert events == [
        "request:None",
        "raw_commit:1",
        "parse:None",
        "metadata_commit:100",
        "normalize:a",
        "structured_commit",
    ]


def test_repeated_cursor_is_detected_before_next_http(
    monkeypatch,
) -> None:
    events = []

    client = FakeClient(
        raw_responses=[
            _raw(
                cursor=None,
            ),
            _raw(
                cursor="cursor-2",
            ),
        ],
        pages=[
            _page(
                contacts=[],
                has_more=True,
                next_cursor="cursor-2",
            ),
            _page(
                cursor="cursor-2",
                contacts=[],
                has_more=True,
                next_cursor="cursor-2",
            ),
        ],
        events=events,
    )

    _install_persistence_mocks(
        monkeypatch,
        events=events,
        structured_results=[
            _structured_result(
                received=0,
                created=0,
            ),
            _structured_result(
                received=0,
                created=0,
            ),
        ],
    )

    with pytest.raises(
        MarketingIventasBranchSyncError,
        match="mismo cursor",
    ):
        sync_iventas_branch_pages(
            sync_run_id=7,
            branch_code="papalote",
            from_utc="from",
            to_utc="to",
            client=client,
            session=FakeSession(
                run=_run()
            ),
        )

    assert len(
        client.request_calls
    ) == 2


def test_max_pages_stops_before_requesting_extra_page(
    monkeypatch,
) -> None:
    events = []

    client = FakeClient(
        raw_responses=[
            _raw(),
        ],
        pages=[
            _page(
                contacts=[],
                has_more=True,
                next_cursor="cursor-2",
            ),
        ],
        events=events,
    )

    _install_persistence_mocks(
        monkeypatch,
        events=events,
        structured_results=[
            _structured_result(
                received=0,
                created=0,
            ),
        ],
    )

    with pytest.raises(
        MarketingIventasBranchSyncError,
        match="max_pages",
    ):
        sync_iventas_branch_pages(
            sync_run_id=7,
            branch_code="papalote",
            from_utc="from",
            to_utc="to",
            client=client,
            max_pages=1,
            session=FakeSession(
                run=_run()
            ),
        )

    assert len(
        client.request_calls
    ) == 1


def test_invalid_page_limit_fails_before_any_dependency(
    monkeypatch,
) -> None:
    events = []

    client = FakeClient(
        raw_responses=[],
        pages=[],
        events=events,
    )

    called = {
        "resolver": False,
    }

    def resolver(branch):
        called["resolver"] = True
        return _resolution()

    monkeypatch.setattr(
        service,
        "resolve_iventas_branch",
        resolver,
    )

    with pytest.raises(
        ValueError,
        match="page_limit",
    ):
        sync_iventas_branch_pages(
            sync_run_id=7,
            branch_code="papalote",
            from_utc="from",
            to_utc="to",
            client=client,
            page_limit=0,
            session=FakeSession(
                run=_run()
            ),
        )

    assert called["resolver"] is False
    assert events == []
