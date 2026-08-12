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
from app.services.marketing_iventas_persistence_service import (
    MarketingIventasPersistenceError,
    apply_iventas_raw_page_parse_metadata,
    persist_iventas_raw_page_pre_parse,
)


RECEIVED_AT = datetime(
    2026,
    8,
    10,
    17,
    0,
    tzinfo=timezone.utc,
)


class FakeQuery:
    def __init__(
        self,
        existing=None,
    ):
        self.existing = existing

    def filter_by(
        self,
        **kwargs,
    ):
        return self

    def first(self):
        return self.existing


class FakeSession:
    def __init__(
        self,
        *,
        existing_query=None,
        row_by_id=None,
    ):
        self.existing_query = (
            existing_query
        )
        self.row_by_id = row_by_id
        self.added = []
        self.commit_count = 0

    def query(
        self,
        model,
    ):
        return FakeQuery(
            self.existing_query
        )

    def get(
        self,
        model,
        object_id,
    ):
        if (
            self.row_by_id is not None
            and self.row_by_id.id
            == object_id
        ):
            return self.row_by_id

        return None

    def add(
        self,
        row,
    ):
        self.added.append(
            row
        )

    def commit(self):
        self.commit_count += 1


def _raw_response():
    return IventasRawPageResponse(
        request_cursor=None,
        http_status=200,
        raw_payload='{"ok":true}',
        _response=object(),
    )


def _page(
    *,
    contacts,
    has_more=True,
    next_cursor="cursor-2",
):
    return IventasPage(
        request_cursor=None,
        http_status=200,
        raw_payload='{"ok":true}',
        payload={},
        contacts=list(
            contacts
        ),
        has_more=has_more,
        next_cursor=next_cursor,
        provider_branch_code="papalote",
        provider_branch_label="Papalote",
    )


def _existing_raw(
    *,
    has_more=None,
    next_cursor=None,
    contacts_count=None,
):
    return SimpleNamespace(
        id=11,
        request_cursor=None,
        http_status=200,
        payload_json='{"ok":true}',
        has_more=has_more,
        next_cursor=next_cursor,
        contacts_count=contacts_count,
    )


def test_pre_parse_contacts_count_stays_null():
    session = FakeSession()

    row = persist_iventas_raw_page_pre_parse(
        sync_run_id=7,
        branch_code="papalote",
        page_number=1,
        raw_response=_raw_response(),
        received_at=RECEIVED_AT,
        session=session,
    )

    assert row.has_more is None
    assert row.next_cursor is None
    assert row.contacts_count is None
    assert session.commit_count == 1


def test_parse_metadata_persists_contacts_count():
    raw_row = _existing_raw()

    session = FakeSession(
        row_by_id=raw_row
    )

    result = apply_iventas_raw_page_parse_metadata(
        raw_page_id=11,
        page=_page(
            contacts=[
                {"id": "a"},
                {"id": "b"},
            ]
        ),
        session=session,
    )

    assert result.has_more is True
    assert result.next_cursor == "cursor-2"
    assert result.contacts_count == 2
    assert session.commit_count == 1


def test_same_parse_metadata_is_idempotent():
    raw_row = _existing_raw(
        has_more=True,
        next_cursor="cursor-2",
        contacts_count=2,
    )

    session = FakeSession(
        row_by_id=raw_row
    )

    result = apply_iventas_raw_page_parse_metadata(
        raw_page_id=11,
        page=_page(
            contacts=[
                {"id": "a"},
                {"id": "b"},
            ]
        ),
        session=session,
    )

    assert result is raw_row
    assert result.contacts_count == 2
    assert session.commit_count == 0


def test_legacy_parsed_row_can_backfill_contacts_count():
    raw_row = _existing_raw(
        has_more=True,
        next_cursor="cursor-2",
        contacts_count=None,
    )

    session = FakeSession(
        row_by_id=raw_row
    )

    result = apply_iventas_raw_page_parse_metadata(
        raw_page_id=11,
        page=_page(
            contacts=[
                {"id": "a"},
                {"id": "b"},
                {"id": "c"},
            ]
        ),
        session=session,
    )

    assert result.contacts_count == 3
    assert session.commit_count == 1


def test_existing_different_contacts_count_is_rejected():
    raw_row = _existing_raw(
        has_more=True,
        next_cursor="cursor-2",
        contacts_count=99,
    )

    session = FakeSession(
        row_by_id=raw_row
    )

    with pytest.raises(
        MarketingIventasPersistenceError,
        match="contacts_count diferente",
    ):
        apply_iventas_raw_page_parse_metadata(
            raw_page_id=11,
            page=_page(
                contacts=[
                    {"id": "a"},
                    {"id": "b"},
                ]
            ),
            session=session,
        )

    assert raw_row.contacts_count == 99
    assert session.commit_count == 0
