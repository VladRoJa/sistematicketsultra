"""SQL contract for snapshot and row-level Contact Center evidence retention.

The PostgreSQL integration tests cover actual FK locks and MVCC behavior.
"""
from types import SimpleNamespace

import pytest

from app.warehouse.services import warehouse_retention_service as retention


class _Result:
    def __init__(self, *, row=None, rows=None):
        self._row = row
        self._rows = rows or []

    def mappings(self):
        return self

    def one(self):
        return self._row

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, *, dry_run, locked_rows=2):
        self.dry_run = dry_run
        self.locked_rows = locked_rows
        self.queries = []
        self.commits = 0

    def execute(self, statement, params):
        sql = str(statement)
        self.queries.append((sql, params))
        if self.dry_run:
            return _Result(row={"target_snapshots": 0, "target_rows": 0})
        if "FOR UPDATE OF s SKIP LOCKED" in sql:
            return _Result(rows=[{"id": 42}])
        if "WITH locked_rows AS" in sql:
            return _Result(rows=[
                {"snapshot_id": 42, "locked_count": self.locked_rows},
            ])
        if "AS total_rows" in sql:
            return _Result(rows=[{"id": 42, "total_rows": 2}])
        if "DELETE FROM public.venta_total_snapshots s" in sql:
            return _Result(rows=[{"id": 42}])
        raise AssertionError("Unexpected SQL query")

    def commit(self):
        self.commits += 1

    def rollback(self):
        raise AssertionError("Unexpected rollback")


@pytest.mark.parametrize("dry_run", [True, False])
def test_retention_rechecks_both_reference_sources_after_row_locking(
    monkeypatch, dry_run
):
    session = _FakeSession(dry_run=dry_run)
    monkeypatch.setattr(retention, "db", SimpleNamespace(session=session))

    result = retention.purge_venta_total_non_canonical_snapshots(
        dry_run=dry_run, max_batches=1,
    )

    assert result["dry_run"] is dry_run
    assert session.commits == (0 if dry_run else 1)
    expected_queries = 1 if dry_run else 4
    assert len(session.queries) == expected_queries

    for query_index in ([0] if dry_run else [0, 2]):
        statement, parameters = session.queries[query_index]
        assert "WITH protected_snapshots AS" in statement
        assert "FROM public.contact_center_appointments a" in statement
        assert "FROM public.contact_center_appointment_result_events e" in statement
        assert "a.venta_total_snapshot_id AS snapshot_id" in statement
        assert "e.venta_total_snapshot_id AS snapshot_id" in statement
        assert "r.id = a.venta_total_snapshot_row_id" in statement
        assert "r.id = e.venta_total_snapshot_row_id" in statement
        assert "WHERE p.snapshot_id = s.id" in statement
        assert statement.count("UNION") == 3
        assert "cutoff_date" in parameters

    if dry_run:
        assert "COUNT(DISTINCT s.id)" in session.queries[0][0]
    else:
        assert "FOR UPDATE OF s SKIP LOCKED" in session.queries[0][0]
        assert "LIMIT :batch_limit" in session.queries[0][0]
        assert "FOR UPDATE OF r SKIP LOCKED" in session.queries[1][0]
        assert "ANY(:candidate_ids)" in session.queries[1][0]
        assert "AS total_rows" in session.queries[2][0]
        assert "DELETE FROM public.venta_total_snapshots s" in session.queries[3][0]
        assert session.queries[3][1]["eligible_ids"] == [42]
        assert result["deleted_snapshots"] == 1
        assert result["deleted_rows"] == 2


def test_retention_skips_snapshot_if_one_row_cannot_be_locked(monkeypatch):
    session = _FakeSession(dry_run=False, locked_rows=1)
    monkeypatch.setattr(retention, "db", SimpleNamespace(session=session))

    result = retention.purge_venta_total_non_canonical_snapshots(
        dry_run=False, max_batches=1,
    )

    assert result["deleted_snapshots"] == 0
    assert result["deleted_rows"] == 0
    assert len(session.queries) == 3
    assert session.commits == 1
