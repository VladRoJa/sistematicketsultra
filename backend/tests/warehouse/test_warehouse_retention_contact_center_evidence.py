"""Contract regression for Contact Center evidence during Venta Total retention.

The SQL predicate is checked in both dry-run and purge queries. PostgreSQL
integration coverage is still required before deploying this retention change.
"""

from types import SimpleNamespace

import pytest

from app.warehouse.services import warehouse_retention_service as retention


class _Result:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return self

    def one(self):
        return self._row


class _FakeSession:
    def __init__(self, *, dry_run):
        self.dry_run = dry_run
        self.queries = []
        self.commits = 0

    def execute(self, statement, params):
        self.queries.append((str(statement), params))
        if self.dry_run:
            return _Result({"target_snapshots": 0, "target_rows": 0})
        return _Result({
            "target_snapshots": 0,
            "target_rows": 0,
            "deleted_snapshots": 0,
        })

    def commit(self):
        self.commits += 1

    def rollback(self):
        raise AssertionError("Unexpected rollback")


@pytest.mark.parametrize("dry_run", [True, False])
def test_retention_excludes_contact_center_evidence_before_deletion(
    monkeypatch, dry_run
):
    session = _FakeSession(dry_run=dry_run)
    monkeypatch.setattr(retention, "db", SimpleNamespace(session=session))

    result = retention.purge_venta_total_non_canonical_snapshots(
        dry_run=dry_run,
    )

    assert result["dry_run"] is dry_run
    assert len(session.queries) == 1
    statement, parameters = session.queries[0]
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
        assert session.commits == 0
        assert "COUNT(DISTINCT s.id)" in statement
    else:
        assert session.commits == 1
        assert "DELETE FROM public.venta_total_snapshots s" in statement
        assert statement.index("WHERE p.snapshot_id = s.id") < statement.index(
            "LIMIT :batch_limit"
        )
