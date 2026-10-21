"""Pruebas del planificador de backfill Meta (sin red ni base de datos)."""
from datetime import date
from types import SimpleNamespace

from scripts.marketing.backfill_meta_history import (
    classify_runs,
    month_windows,
)


def _run(
    *,
    status="COMPLETED",
    canonical=False,
    start=date(2023, 9, 21),
    end=date(2023, 9, 30),
    count=5,
    failed=0,
):
    return SimpleNamespace(
        status=status,
        is_canonical=canonical,
        date_from=start,
        date_to=end,
        accounts_requested=count,
        accounts_completed=count - failed,
        accounts_failed=failed,
    )


def test_month_windows_with_partial_edges_and_year_change():
    assert list(month_windows(date(2023, 12, 21), date(2024, 2, 8))) == [
        ("META-2023-12", date(2023, 12, 21), date(2023, 12, 31)),
        ("META-2024-01", date(2024, 1, 1), date(2024, 1, 31)),
        ("META-2024-02", date(2024, 2, 1), date(2024, 2, 8)),
    ]


def test_rerun_skips_completed_noncanonical_exact_range():
    assert classify_runs(
        [_run()],
        start=date(2023, 9, 21),
        end=date(2023, 9, 30),
        account_count=5,
    ) == "SKIP_COMPLETED"


def test_partial_or_different_accounts_retries():
    for run in (_run(status="PARTIAL", failed=1), _run(count=4)):
        assert classify_runs(
            [run],
            start=date(2023, 9, 21),
            end=date(2023, 9, 30),
            account_count=5,
        ) == "PENDING"


def test_canonical_same_range_skips_without_replacement():
    assert classify_runs(
        [_run(canonical=True)],
        start=date(2023, 9, 21),
        end=date(2023, 9, 30),
        account_count=5,
    ) == "SKIP_CANONICAL"


def test_canonical_shorter_range_blocks_for_review():
    assert classify_runs(
        [_run(canonical=True, start=date(2023, 9, 1))],
        start=date(2023, 9, 21),
        end=date(2023, 9, 30),
        account_count=5,
    ) == "BLOCK_CANONICAL_RANGE"


def test_running_run_blocks_duplicate_concurrent_month():
    assert classify_runs(
        [_run(status="RUNNING")],
        start=date(2023, 9, 21),
        end=date(2023, 9, 30),
        account_count=5,
    ) == "BLOCK_RUNNING"
