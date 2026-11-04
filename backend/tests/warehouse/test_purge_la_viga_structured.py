from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts.ops import purge_la_viga_structured as purge


class _Session:
    def __init__(self):
        self.sql = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, statement):
        sql = str(statement)
        self.sql.append(sql)
        table = sql.split("DELETE FROM ", 1)[1].split(" ", 1)[0]
        return SimpleNamespace(rowcount=purge.EXPECTED_COUNTS[table])

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_preview_does_not_delete(monkeypatch):
    session = _Session()
    monkeypatch.setattr(purge, "db", SimpleNamespace(session=session))
    monkeypatch.setattr(
        purge, "_count_rows",
        lambda table: purge.EXPECTED_COUNTS[table],
    )
    monkeypatch.setattr(
        purge, "_reference_counts",
        lambda: {"contact_center_appointments": 0,
                 "contact_center_appointment_result_events": 0},
    )

    result = purge.purge(commit=False)

    assert result["mode"] == "DRY_RUN"
    assert result["before"] == purge.EXPECTED_COUNTS
    assert result["deleted"] == {}
    assert session.sql == []
    assert session.commits == 0
    assert session.rollbacks == 1


@pytest.mark.parametrize("condition", ["changed_count", "contact_reference"])
def test_commit_refuses_unreviewed_data_or_purchase_evidence(
    monkeypatch, condition,
):
    session = _Session()
    monkeypatch.setattr(purge, "db", SimpleNamespace(session=session))

    def count(table):
        if condition == "changed_count" and table == "venta_total_snapshot_rows":
            return 5
        return purge.EXPECTED_COUNTS[table]

    monkeypatch.setattr(purge, "_count_rows", count)
    monkeypatch.setattr(
        purge, "_reference_counts",
        lambda: {
            "contact_center_appointments": (
                1 if condition == "contact_reference" else 0
            ),
            "contact_center_appointment_result_events": 0,
        },
    )

    with pytest.raises(RuntimeError):
        purge.purge(commit=True)

    assert session.sql == []
    assert session.commits == 0


def test_commit_deletes_only_allowlisted_la_viga_rows(monkeypatch):
    session = _Session()
    monkeypatch.setattr(purge, "db", SimpleNamespace(session=session))

    calls = {}
    def count(table):
        calls[table] = calls.get(table, 0) + 1
        return purge.EXPECTED_COUNTS[table] if calls[table] == 1 else 0

    monkeypatch.setattr(purge, "_count_rows", count)
    monkeypatch.setattr(
        purge, "_reference_counts",
        lambda: {"contact_center_appointments": 0,
                 "contact_center_appointment_result_events": 0},
    )

    result = purge.purge(commit=True)

    assert result["deleted"] == purge.EXPECTED_COUNTS
    assert all(not amount for amount in result["remaining"].values())
    assert len(session.sql) == len(purge.EXPECTED_COUNTS)
    assert all("= 'LA_VIGA'" in sql for sql in session.sql)
    assert session.commits == 1
