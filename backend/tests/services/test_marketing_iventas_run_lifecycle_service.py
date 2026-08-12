from datetime import (
    datetime,
    timedelta,
    timezone,
)

import pytest

from app.models import MarketingIventasSyncRunORM
from app.services.marketing_iventas_run_lifecycle_service import (
    MarketingIventasRunCounters,
    MarketingIventasRunLifecycleError,
    SYNC_STATUS_COMPLETED,
    SYNC_STATUS_FAILED,
    SYNC_STATUS_PARTIAL,
    SYNC_STATUS_RUNNING,
    finalize_iventas_sync_run,
)


class FakeQuery:
    def __init__(
        self,
        session,
    ):
        self.session = session
        self.filters = {}

    def filter_by(
        self,
        **kwargs,
    ):
        self.filters = kwargs
        return self

    def all(self):
        result = []

        for row in self.session.canonical_rows:
            matches = True

            for key, value in self.filters.items():
                if getattr(
                    row,
                    key,
                ) != value:
                    matches = False
                    break

            if matches:
                result.append(
                    row
                )

        return result


class FakeSession:
    def __init__(
        self,
        *,
        run=None,
        canonical_rows=None,
    ):
        self.run = run
        self.canonical_rows = list(
            canonical_rows or []
        )

        self.events = []
        self.rollback_count = 0
        self.query_count = 0

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
            is MarketingIventasSyncRunORM
        )

        self.query_count += 1

        return FakeQuery(
            self
        )

    def flush(self):
        self.events.append(
            "flush"
        )

    def commit(self):
        self.events.append(
            "commit"
        )

    def rollback(self):
        self.rollback_count += 1
        self.events.append(
            "rollback"
        )


def _started():
    return datetime(
        2026,
        8,
        10,
        14,
        0,
        tzinfo=timezone.utc,
    )


def _finished():
    return datetime(
        2026,
        8,
        10,
        14,
        30,
        tzinfo=timezone.utc,
    )


def _run(
    *,
    run_id=2,
    period_key="2026-08",
    status=SYNC_STATUS_RUNNING,
    canonical=False,
):
    finished_at = (
        None
        if status == SYNC_STATUS_RUNNING
        else _finished()
    )

    return MarketingIventasSyncRunORM(
        id=run_id,
        period_key=period_key,
        started_at=_started(),
        finished_at=finished_at,
        status=status,
        branches_requested=26,
        branches_completed=0,
        branches_failed=0,
        contacts_received=0,
        contacts_unique=0,
        contacts_with_phone=0,
        contacts_mx10_matchable=0,
        contacts_non_mx_or_unresolved=0,
        contacts_with_first_message=0,
        contacts_with_any_tag=0,
        contacts_with_meta_ad_tag=0,
        contacts_with_multiple_meta_ad_tags=0,
        aliases_resolved=0,
        aliases_unresolved=0,
        is_canonical=canonical,
    )


def _completed_counters():
    return MarketingIventasRunCounters(
        branches_completed=26,
        branches_failed=0,
        contacts_received=2500,
        contacts_unique=2490,
        contacts_with_phone=2400,
        contacts_mx10_matchable=2300,
        contacts_non_mx_or_unresolved=90,
        contacts_with_first_message=2100,
        contacts_with_any_tag=500,
        contacts_with_meta_ad_tag=120,
        contacts_with_multiple_meta_ad_tags=2,
        aliases_resolved=26,
        aliases_unresolved=0,
    )


def _partial_counters():
    return MarketingIventasRunCounters(
        branches_completed=20,
        branches_failed=2,
        contacts_received=1800,
        contacts_unique=1790,
        contacts_with_phone=1700,
        contacts_mx10_matchable=1600,
        contacts_non_mx_or_unresolved=80,
        contacts_with_first_message=1500,
        contacts_with_any_tag=300,
        contacts_with_meta_ad_tag=75,
        contacts_with_multiple_meta_ad_tags=1,
        aliases_resolved=22,
        aliases_unresolved=4,
    )


def test_completed_canonical_replaces_previous_in_same_transaction(
) -> None:
    current = _run(
        run_id=2,
    )

    previous = _run(
        run_id=1,
        status=SYNC_STATUS_COMPLETED,
        canonical=True,
    )

    previous.branches_completed = 26
    previous.aliases_resolved = 26

    session = FakeSession(
        run=current,
        canonical_rows=[
            previous,
        ],
    )

    result = finalize_iventas_sync_run(
        sync_run_id=2,
        status=SYNC_STATUS_COMPLETED,
        counters=_completed_counters(),
        make_canonical=True,
        finished_at=_finished(),
        session=session,
    )

    assert previous.is_canonical is False

    assert current.status == SYNC_STATUS_COMPLETED
    assert current.is_canonical is True
    assert current.finished_at == _finished()

    assert current.branches_completed == 26
    assert current.branches_failed == 0
    assert current.aliases_resolved == 26
    assert current.aliases_unresolved == 0

    assert session.events == [
        "flush",
        "commit",
    ]

    assert result.replaced_canonical_run_id == 1
    assert result.is_canonical is True
    assert result.was_already_finalized is False


def test_completed_noncanonical_does_not_touch_previous_canonical(
) -> None:
    current = _run(
        run_id=2,
    )

    previous = _run(
        run_id=1,
        status=SYNC_STATUS_COMPLETED,
        canonical=True,
    )

    session = FakeSession(
        run=current,
        canonical_rows=[
            previous,
        ],
    )

    result = finalize_iventas_sync_run(
        sync_run_id=2,
        status=SYNC_STATUS_COMPLETED,
        counters=_completed_counters(),
        make_canonical=False,
        finished_at=_finished(),
        session=session,
    )

    assert previous.is_canonical is True
    assert current.is_canonical is False

    assert session.query_count == 0
    assert session.events == [
        "commit",
    ]

    assert result.replaced_canonical_run_id is None


def test_partial_noncanonical_is_allowed(
) -> None:
    current = _run()

    session = FakeSession(
        run=current,
    )

    result = finalize_iventas_sync_run(
        sync_run_id=2,
        status=SYNC_STATUS_PARTIAL,
        counters=_partial_counters(),
        make_canonical=False,
        finished_at=_finished(),
        session=session,
    )

    assert current.status == SYNC_STATUS_PARTIAL
    assert current.is_canonical is False
    assert current.branches_completed == 20
    assert current.branches_failed == 2
    assert current.aliases_unresolved == 4

    assert session.events == [
        "commit",
    ]

    assert result.status == SYNC_STATUS_PARTIAL


def test_partial_cannot_be_canonical(
) -> None:
    current = _run()

    session = FakeSession(
        run=current,
    )

    with pytest.raises(
        MarketingIventasRunLifecycleError,
        match="Solo un run COMPLETED",
    ):
        finalize_iventas_sync_run(
            sync_run_id=2,
            status=SYNC_STATUS_PARTIAL,
            counters=_partial_counters(),
            make_canonical=True,
            finished_at=_finished(),
            session=session,
        )

    assert current.status == SYNC_STATUS_RUNNING
    assert session.events == [
        "rollback",
    ]


def test_completed_requires_all_requested_branches(
) -> None:
    current = _run()

    counters = _partial_counters()

    session = FakeSession(
        run=current,
    )

    with pytest.raises(
        MarketingIventasRunLifecycleError,
        match="todas las sucursales",
    ):
        finalize_iventas_sync_run(
            sync_run_id=2,
            status=SYNC_STATUS_COMPLETED,
            counters=counters,
            finished_at=_finished(),
            session=session,
        )

    assert current.status == SYNC_STATUS_RUNNING
    assert session.events == [
        "rollback",
    ]


def test_exact_terminal_retry_is_idempotent(
) -> None:
    current = _run(
        status=SYNC_STATUS_COMPLETED,
        canonical=True,
    )

    counters = _completed_counters()

    for field_name, value in vars(
        counters
    ).items():
        setattr(
            current,
            field_name,
            value,
        )

    session = FakeSession(
        run=current,
        canonical_rows=[
            current,
        ],
    )

    result = finalize_iventas_sync_run(
        sync_run_id=2,
        status=SYNC_STATUS_COMPLETED,
        counters=counters,
        make_canonical=True,
        finished_at=(
            _finished()
            + timedelta(minutes=10)
        ),
        session=session,
    )

    assert result.was_already_finalized is True
    assert result.is_canonical is True

    assert session.query_count == 0
    assert session.events == []


def test_terminal_retry_with_different_state_fails(
) -> None:
    current = _run(
        status=SYNC_STATUS_FAILED,
        canonical=False,
    )

    session = FakeSession(
        run=current,
    )

    with pytest.raises(
        MarketingIventasRunLifecycleError,
        match="estado diferente",
    ):
        finalize_iventas_sync_run(
            sync_run_id=2,
            status=SYNC_STATUS_PARTIAL,
            counters=_partial_counters(),
            make_canonical=False,
            finished_at=_finished(),
            session=session,
        )

    assert session.events == [
        "rollback",
    ]


def test_invalid_contact_counter_hierarchy_fails(
) -> None:
    current = _run()

    counters = MarketingIventasRunCounters(
        branches_completed=20,
        branches_failed=0,
        contacts_received=10,
        contacts_unique=11,
        contacts_with_phone=5,
        contacts_mx10_matchable=4,
        contacts_non_mx_or_unresolved=1,
        contacts_with_first_message=3,
        contacts_with_any_tag=2,
        contacts_with_meta_ad_tag=1,
        contacts_with_multiple_meta_ad_tags=0,
        aliases_resolved=20,
        aliases_unresolved=0,
    )

    session = FakeSession(
        run=current,
    )

    with pytest.raises(
        ValueError,
        match="contacts_unique",
    ):
        finalize_iventas_sync_run(
            sync_run_id=2,
            status=SYNC_STATUS_PARTIAL,
            counters=counters,
            finished_at=_finished(),
            session=session,
        )

    assert session.events == [
        "rollback",
    ]


def test_multiple_previous_canonicals_are_treated_as_corruption(
) -> None:
    current = _run(
        run_id=3,
    )

    previous_1 = _run(
        run_id=1,
        status=SYNC_STATUS_COMPLETED,
        canonical=True,
    )

    previous_2 = _run(
        run_id=2,
        status=SYNC_STATUS_COMPLETED,
        canonical=True,
    )

    session = FakeSession(
        run=current,
        canonical_rows=[
            previous_1,
            previous_2,
        ],
    )

    with pytest.raises(
        MarketingIventasRunLifecycleError,
        match="más de un canónico",
    ):
        finalize_iventas_sync_run(
            sync_run_id=3,
            status=SYNC_STATUS_COMPLETED,
            counters=_completed_counters(),
            make_canonical=True,
            finished_at=_finished(),
            session=session,
        )

    assert previous_1.is_canonical is True
    assert previous_2.is_canonical is True

    assert session.events == [
        "rollback",
    ]


def test_missing_run_fails(
) -> None:
    session = FakeSession(
        run=None,
    )

    with pytest.raises(
        MarketingIventasRunLifecycleError,
        match="No existe",
    ):
        finalize_iventas_sync_run(
            sync_run_id=999,
            status=SYNC_STATUS_FAILED,
            counters=_partial_counters(),
            finished_at=_finished(),
            session=session,
        )

    assert session.events == [
        "rollback",
    ]


def test_finished_at_cannot_precede_started_at(
) -> None:
    current = _run()

    session = FakeSession(
        run=current,
    )

    with pytest.raises(
        ValueError,
        match="anterior a started_at",
    ):
        finalize_iventas_sync_run(
            sync_run_id=2,
            status=SYNC_STATUS_PARTIAL,
            counters=_partial_counters(),
            finished_at=(
                _started()
                - timedelta(seconds=1)
            ),
            session=session,
        )

    assert session.events == [
        "rollback",
    ]
