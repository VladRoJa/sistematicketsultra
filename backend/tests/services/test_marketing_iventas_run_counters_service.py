from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.models import (
    MarketingIventasSyncRunORM,
)
from app.services.marketing_iventas_run_counters_service import (
    MarketingIventasRunCountersReadError,
    read_iventas_stored_run_counters,
)


class FakeMappings:
    def __init__(
        self,
        row,
    ):
        self.row = row

    def one(self):
        return self.row


class FakeExecuteResult:
    def __init__(
        self,
        row,
    ):
        self.row = row

    def mappings(self):
        return FakeMappings(
            self.row
        )


class FakeSession:
    def __init__(
        self,
        *,
        run=None,
        row=None,
    ):
        self.run = run
        self.row = row
        self.executed_statement = None

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
            and self.run.id
            == object_id
        ):
            return self.run

        return None

    def execute(
        self,
        statement,
    ):
        self.executed_statement = (
            statement
        )

        return FakeExecuteResult(
            self.row
        )


def _run():
    return SimpleNamespace(
        id=7
    )


def _valid_row():
    return {
        "contacts_received": 120,
        "contacts_unique": 100,
        "contacts_with_phone": 95,
        "contacts_mx10_matchable": 90,
        "contacts_non_mx_or_unresolved": 5,
        "contacts_with_first_message": 80,
        "contacts_with_any_tag": 30,
        "contacts_with_meta_ad_tag": 20,
        "contacts_with_multiple_meta_ad_tags": 3,
    }


def test_reads_all_persisted_counters():
    session = FakeSession(
        run=_run(),
        row=_valid_row(),
    )

    result = read_iventas_stored_run_counters(
        sync_run_id=7,
        session=session,
    )

    assert result.contacts_received == 120
    assert result.contacts_unique == 100
    assert result.contacts_with_phone == 95
    assert result.contacts_mx10_matchable == 90
    assert (
        result.contacts_non_mx_or_unresolved
        == 5
    )
    assert result.contacts_with_first_message == 80
    assert result.contacts_with_any_tag == 30
    assert result.contacts_with_meta_ad_tag == 20
    assert (
        result.contacts_with_multiple_meta_ad_tags
        == 3
    )

    assert session.executed_statement is not None


def test_query_contains_expected_persisted_sources():
    session = FakeSession(
        run=_run(),
        row=_valid_row(),
    )

    read_iventas_stored_run_counters(
        sync_run_id=7,
        session=session,
    )

    sql = str(
        session
        .executed_statement
        .compile(
            dialect=postgresql.dialect(),
            compile_kwargs={
                "literal_binds": True,
            },
        )
    ).lower()

    assert (
        "marketing_iventas_raw_pages"
        in sql
    )

    assert (
        "contacts_count"
        in sql
    )

    assert (
        "marketing_iventas_contacts"
        in sql
    )

    assert (
        "phone_match_status"
        in sql
    )

    assert (
        "first_message_at_utc"
        in sql
    )

    assert (
        "marketing_iventas_contact_tags"
        in sql
    )

    assert (
        "meta_ad"
        in sql
    )

    assert (
        "count(distinct"
        in sql
    )

    assert (
        "having count("
        in sql
    )


@pytest.mark.parametrize(
    "sync_run_id",
    [
        0,
        -1,
        True,
        "7",
    ],
)
def test_invalid_sync_run_id_fails(
    sync_run_id,
):
    with pytest.raises(
        ValueError,
        match="sync_run_id",
    ):
        read_iventas_stored_run_counters(
            sync_run_id=sync_run_id,
            session=FakeSession(),
        )


def test_missing_run_fails_before_query():
    session = FakeSession(
        run=None,
        row=_valid_row(),
    )

    with pytest.raises(
        MarketingIventasRunCountersReadError,
        match="No existe",
    ):
        read_iventas_stored_run_counters(
            sync_run_id=7,
            session=session,
        )

    assert (
        session.executed_statement
        is None
    )


def test_unique_cannot_exceed_received():
    row = _valid_row()

    row[
        "contacts_received"
    ] = 50

    with pytest.raises(
        MarketingIventasRunCountersReadError,
        match="contacts_unique",
    ):
        read_iventas_stored_run_counters(
            sync_run_id=7,
            session=FakeSession(
                run=_run(),
                row=row,
            ),
        )


def test_tag_hierarchy_is_validated():
    row = _valid_row()

    row[
        "contacts_with_meta_ad_tag"
    ] = 40

    row[
        "contacts_with_any_tag"
    ] = 30

    with pytest.raises(
        MarketingIventasRunCountersReadError,
        match="contacts_with_meta_ad_tag",
    ):
        read_iventas_stored_run_counters(
            sync_run_id=7,
            session=FakeSession(
                run=_run(),
                row=row,
            ),
        )
