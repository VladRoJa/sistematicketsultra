from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

import app.warehouse.services.track_venta_total_agg_service as service


class _FakeMappings:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeResult:
    def __init__(
        self,
        *,
        row=None,
        rowcount=0,
    ):
        self._row = row
        self.rowcount = rowcount

    def mappings(self):
        return _FakeMappings(self._row)


class _FakeSession:
    def __init__(self):
        self.calls = []
        self.insert_sql = None
        self.commit_calls = 0

    def execute(
        self,
        statement,
        params=None,
    ):
        sql = str(statement)

        self.calls.append(
            {
                "sql": sql,
                "params": params,
            }
        )

        if (
            "INSERT INTO "
            "track_venta_total_daily_branch_agg"
            in sql
        ):
            self.insert_sql = sql

            return _FakeResult(
                rowcount=1,
            )

        if "FROM venta_total_snapshots" in sql:
            return _FakeResult(
                row={
                    "id": 101,
                    "business_date": date(2026, 7, 31),
                    "business_month": date(2026, 7, 1),
                }
            )

        if (
            "DELETE FROM "
            "track_venta_total_daily_branch_agg"
            in sql
        ):
            return _FakeResult(
                rowcount=0,
            )

        raise AssertionError(
            f"SQL inesperado: {sql}"
        )

    def commit(self):
        self.commit_calls += 1


def test_aggregate_uses_official_statuses_and_keeps_negatives(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_session = _FakeSession()

    monkeypatch.setattr(
        service,
        "db",
        SimpleNamespace(
            session=fake_session,
        ),
    )

    result = service.aggregate_venta_total_snapshot(
        101,
        commit=True,
    )

    assert result == {
        "status": "ok",
        "snapshot_id": 101,
        "business_month": "2026-07-01",
        "business_date": "2026-07-31",
        "rows_deleted": 0,
        "rows_inserted": 1,
    }

    assert fake_session.insert_sql is not None

    normalized_sql = " ".join(
        fake_session.insert_sql.split()
    )

    assert (
        "upper(trim(r.estatus)) "
        "IN ('ACTIVO', 'FACTURADO')"
        in normalized_sql
    )

    assert "r.total > 0" not in normalized_sql

    assert fake_session.commit_calls == 1
