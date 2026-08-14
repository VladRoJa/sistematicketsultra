from datetime import (
    date,
    datetime,
    timezone,
)
from types import SimpleNamespace

import pytest

import app.services.marketing_iventas_run_sync_service as service
from app.services.marketing_iventas_branch_service import (
    MarketingIventasBranchResolution,
)
from app.services.marketing_iventas_branch_sync_service import (
    MarketingIventasBranchSyncError,
)
from app.services.marketing_iventas_run_counters_service import (
    MarketingIventasStoredRunCounters,
)


STARTED_AT = datetime(
    2026,
    8,
    11,
    15,
    0,
    tzinfo=timezone.utc,
)

FINISHED_AT = datetime(
    2026,
    8,
    11,
    15,
    5,
    tzinfo=timezone.utc,
)


class FakeSession:
    def __init__(self):
        self.rollback_count = 0

    def rollback(self):
        self.rollback_count += 1


def _stored_counters():
    return MarketingIventasStoredRunCounters(
        contacts_received=30,
        contacts_unique=25,
        contacts_with_phone=20,
        contacts_mx10_matchable=18,
        contacts_non_mx_or_unresolved=2,
        contacts_with_first_message=15,
        contacts_with_any_tag=10,
        contacts_with_meta_ad_tag=8,
        contacts_with_multiple_meta_ad_tags=2,
    )


def _resolution(
    branch_code,
    sucursal_id,
):
    return MarketingIventasBranchResolution(
        branch_code=branch_code,
        sucursal_canon=(
            f"CANON_{sucursal_id}"
        ),
        sucursal_id=sucursal_id,
    )


def _install_common_mocks(
    monkeypatch,
    *,
    branch_codes=(
        "branch-a",
        "branch-b",
        "branch-c",
    ),
    resolutions=None,
    alias_failures=(),
):
    if resolutions is None:
        resolutions = tuple(
            _resolution(
                branch_code,
                index,
            )
            for index, branch_code
            in enumerate(
                branch_codes,
                start=1,
            )
        )

    monkeypatch.setattr(
        service,
        "_load_active_iventas_branch_codes",
        lambda **kwargs: tuple(
            branch_codes
        ),
    )

    monkeypatch.setattr(
        service,
        "_pre_resolve_branches",
        lambda branch_codes_value: (
            tuple(resolutions),
            tuple(alias_failures),
        ),
    )

    monkeypatch.setattr(
        service,
        "create_iventas_sync_run_running",
        lambda **kwargs: SimpleNamespace(
            id=101,
        ),
    )

    monkeypatch.setattr(
        service,
        "read_iventas_stored_run_counters",
        lambda **kwargs: _stored_counters(),
    )


def _capture_finalize(
    monkeypatch,
):
    calls = []

    def fake_finalize(**kwargs):
        calls.append(kwargs)

        return SimpleNamespace(
            status=kwargs["status"],
            is_canonical=kwargs[
                "make_canonical"
            ],
            replaced_canonical_run_id=None,
        )

    monkeypatch.setattr(
        service,
        "finalize_iventas_sync_run",
        fake_finalize,
    )

    return calls


def test_completed_run_canonicalizes(
    monkeypatch,
):
    session = FakeSession()

    _install_common_mocks(
        monkeypatch
    )

    finalize_calls = _capture_finalize(
        monkeypatch
    )

    branch_calls = []

    def fake_branch_sync(**kwargs):
        branch_calls.append(kwargs)

        return SimpleNamespace(
            branch_code=kwargs[
                "branch_code"
            ]
        )

    monkeypatch.setattr(
        service,
        "sync_iventas_branch_pages",
        fake_branch_sync,
    )

    result = service.sync_iventas_full_run(
        period_key="2026-08",
        date_from=date(
            2026,
            8,
            1,
        ),
        date_to=date(
            2026,
            8,
            11,
        ),
        client=object(),
        started_at=STARTED_AT,
        finished_at=FINISHED_AT,
        session=session,
    )

    assert result.status == "COMPLETED"
    assert result.is_canonical is True

    assert result.branches_requested == 3
    assert result.branches_completed == 3
    assert result.branches_failed == 0

    assert result.aliases_resolved == 3
    assert result.aliases_unresolved == 0

    assert result.failed_branches == ()

    assert len(branch_calls) == 3
    assert len(finalize_calls) == 1

    finalize = finalize_calls[0]

    assert finalize[
        "status"
    ] == "COMPLETED"

    assert finalize[
        "make_canonical"
    ] is True

    counters = finalize[
        "counters"
    ]

    assert counters.branches_completed == 3
    assert counters.branches_failed == 0
    assert counters.aliases_resolved == 3
    assert counters.aliases_unresolved == 0

    assert counters.contacts_received == 30
    assert counters.contacts_unique == 25

    assert session.rollback_count == 0


def test_completed_can_disable_canonicalization(
    monkeypatch,
):
    session = FakeSession()

    _install_common_mocks(
        monkeypatch
    )

    finalize_calls = _capture_finalize(
        monkeypatch
    )

    monkeypatch.setattr(
        service,
        "sync_iventas_branch_pages",
        lambda **kwargs: None,
    )

    result = service.sync_iventas_full_run(
        period_key="2026-08",
        date_from=date(
            2026,
            8,
            1,
        ),
        date_to=date(
            2026,
            8,
            11,
        ),
        client=object(),
        make_canonical_on_completed=False,
        session=session,
    )

    assert result.status == "COMPLETED"
    assert result.is_canonical is False

    assert finalize_calls[0][
        "make_canonical"
    ] is False


def test_partial_continues_after_operational_failure(
    monkeypatch,
):
    session = FakeSession()

    _install_common_mocks(
        monkeypatch
    )

    finalize_calls = _capture_finalize(
        monkeypatch
    )

    attempted = []

    def fake_branch_sync(**kwargs):
        branch = kwargs[
            "branch_code"
        ]

        attempted.append(branch)

        if branch == "branch-b":
            raise MarketingIventasBranchSyncError(
                "fallo esperado"
            )

        return None

    monkeypatch.setattr(
        service,
        "sync_iventas_branch_pages",
        fake_branch_sync,
    )

    result = service.sync_iventas_full_run(
        period_key="2026-08",
        date_from=date(
            2026,
            8,
            1,
        ),
        date_to=date(
            2026,
            8,
            11,
        ),
        client=object(),
        session=session,
    )

    assert attempted == [
        "branch-a",
        "branch-b",
        "branch-c",
    ]

    assert result.status == "PARTIAL"
    assert result.is_canonical is False

    assert result.branches_completed == 2
    assert result.branches_failed == 1

    assert session.rollback_count == 1

    assert len(
        result.failed_branches
    ) == 1

    failure = result.failed_branches[0]

    assert failure.branch_code == "branch-b"
    assert (
        failure.error_type
        == "MarketingIventasBranchSyncError"
    )

    assert finalize_calls[0][
        "status"
    ] == "PARTIAL"

    assert finalize_calls[0][
        "make_canonical"
    ] is False


def test_all_operational_failures_become_failed(
    monkeypatch,
):
    session = FakeSession()

    _install_common_mocks(
        monkeypatch
    )

    finalize_calls = _capture_finalize(
        monkeypatch
    )

    def fake_branch_sync(**kwargs):
        raise MarketingIventasBranchSyncError(
            "fallo branch"
        )

    monkeypatch.setattr(
        service,
        "sync_iventas_branch_pages",
        fake_branch_sync,
    )

    result = service.sync_iventas_full_run(
        period_key="2026-08",
        date_from=date(
            2026,
            8,
            1,
        ),
        date_to=date(
            2026,
            8,
            11,
        ),
        client=object(),
        session=session,
    )

    assert result.status == "FAILED"
    assert result.is_canonical is False

    assert result.branches_completed == 0
    assert result.branches_failed == 3

    assert len(
        result.failed_branches
    ) == 3

    assert session.rollback_count == 3

    assert finalize_calls[0][
        "status"
    ] == "FAILED"

    assert finalize_calls[0][
        "make_canonical"
    ] is False


def test_alias_incomplete_fails_before_http(
    monkeypatch,
):
    session = FakeSession()

    branch_codes = (
        "branch-a",
        "branch-b",
        "branch-c",
    )

    resolutions = (
        _resolution(
            "branch-a",
            1,
        ),
        _resolution(
            "branch-b",
            2,
        ),
    )

    alias_failure = (
        service
        .MarketingIventasRunBranchFailure(
            branch_code="branch-c",
            error_type="ALIAS_UNRESOLVED",
        )
    )

    _install_common_mocks(
        monkeypatch,
        branch_codes=branch_codes,
        resolutions=resolutions,
        alias_failures=(
            alias_failure,
        ),
    )

    finalize_calls = _capture_finalize(
        monkeypatch
    )

    branch_calls = []

    monkeypatch.setattr(
        service,
        "sync_iventas_branch_pages",
        lambda **kwargs: branch_calls.append(
            kwargs
        ),
    )

    client_created = []

    monkeypatch.setattr(
        service,
        "IventasClient",
        lambda: client_created.append(
            True
        ),
    )

    result = service.sync_iventas_full_run(
        period_key="2026-08",
        date_from=date(
            2026,
            8,
            1,
        ),
        date_to=date(
            2026,
            8,
            11,
        ),
        client=None,
        session=session,
    )

    assert result.status == "FAILED"
    assert result.is_canonical is False

    assert result.branches_requested == 3
    assert result.branches_completed == 0
    assert result.branches_failed == 3

    assert result.aliases_resolved == 2
    assert result.aliases_unresolved == 1

    assert branch_calls == []
    assert client_created == []

    assert result.failed_branches == (
        alias_failure,
    )

    assert finalize_calls[0][
        "status"
    ] == "FAILED"

    assert finalize_calls[0][
        "make_canonical"
    ] is False


def test_unexpected_exception_is_not_masked(
    monkeypatch,
):
    session = FakeSession()

    _install_common_mocks(
        monkeypatch
    )

    finalize_calls = _capture_finalize(
        monkeypatch
    )

    def fake_branch_sync(**kwargs):
        raise RuntimeError(
            "bug inesperado"
        )

    monkeypatch.setattr(
        service,
        "sync_iventas_branch_pages",
        fake_branch_sync,
    )

    with pytest.raises(
        RuntimeError,
        match="bug inesperado",
    ):
        service.sync_iventas_full_run(
            period_key="2026-08",
            date_from=date(
                2026,
                8,
                1,
            ),
            date_to=date(
                2026,
                8,
                11,
            ),
            client=object(),
            session=session,
        )

    assert session.rollback_count == 1

    assert len(finalize_calls) == 1

    finalize_call = finalize_calls[0]

    assert finalize_call[
        "sync_run_id"
    ] == 101

    assert finalize_call[
        "status"
    ] == "FAILED"

    assert finalize_call[
        "make_canonical"
    ] is False

    counters = finalize_call[
        "counters"
    ]

    assert counters.branches_completed == 0
    assert counters.branches_failed == 3

    assert counters.aliases_resolved == 3
    assert counters.aliases_unresolved == 0


def test_passes_commercial_utc_period_to_each_branch(
    monkeypatch,
):
    session = FakeSession()

    _install_common_mocks(
        monkeypatch
    )

    _capture_finalize(
        monkeypatch
    )

    calls = []

    def fake_branch_sync(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(
        service,
        "sync_iventas_branch_pages",
        fake_branch_sync,
    )

    service.sync_iventas_full_run(
        period_key="2026-08",
        date_from=date(
            2026,
            8,
            1,
        ),
        date_to=date(
            2026,
            8,
            2,
        ),
        client=object(),
        session=session,
    )

    assert len(calls) == 3

    for call in calls:
        assert (
            call["from_utc"]
            == "2026-08-01T07:00:00.000Z"
        )

        assert (
            call["to_utc"]
            == "2026-08-03T06:59:59.999Z"
        )

        assert call[
            "page_limit"
        ] == 100

        assert call[
            "max_pages"
        ] == 10000


def test_partial_uses_stored_postgres_counters(
    monkeypatch,
):
    session = FakeSession()

    _install_common_mocks(
        monkeypatch
    )

    finalize_calls = _capture_finalize(
        monkeypatch
    )

    def fake_branch_sync(**kwargs):
        if (
            kwargs["branch_code"]
            == "branch-c"
        ):
            raise MarketingIventasBranchSyncError(
                "fallo tardio"
            )

    monkeypatch.setattr(
        service,
        "sync_iventas_branch_pages",
        fake_branch_sync,
    )

    result = service.sync_iventas_full_run(
        period_key="2026-08",
        date_from=date(
            2026,
            8,
            1,
        ),
        date_to=date(
            2026,
            8,
            11,
        ),
        client=object(),
        session=session,
    )

    assert result.status == "PARTIAL"

    counters = finalize_calls[0][
        "counters"
    ]

    assert counters.contacts_received == 30
    assert counters.contacts_unique == 25
    assert counters.contacts_with_phone == 20
    assert counters.contacts_mx10_matchable == 18
    assert (
        counters.contacts_non_mx_or_unresolved
        == 2
    )
    assert (
        counters.contacts_with_first_message
        == 15
    )
    assert counters.contacts_with_any_tag == 10
    assert counters.contacts_with_meta_ad_tag == 8
    assert (
        counters
        .contacts_with_multiple_meta_ad_tags
        == 2
    )

def test_requires_exactly_26_active_iventas_aliases():
    rows = tuple(
        SimpleNamespace(
            raw_branch_name=f"branch-{index:02d}"
        )
        for index in range(1, 26)
    )

    class FakeAliasQuery:
        def filter(self, *args):
            return self

        def order_by(self, *args):
            return self

        def all(self):
            return rows

    class FakeAliasSession:
        def query(self, *args):
            return FakeAliasQuery()

    with pytest.raises(
        service.MarketingIventasRunSyncError,
        match=(
            "requiere 26 aliases activos "
            "iventas_family; se encontraron 25"
        ),
    ):
        service._load_active_iventas_branch_codes(
            session=FakeAliasSession(),
        )
