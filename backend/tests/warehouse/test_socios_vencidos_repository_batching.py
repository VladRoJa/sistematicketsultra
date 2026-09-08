from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import app.warehouse.services.socios_vencidos_repository as repository


class _TupleExpression:
    def in_(self, keys):
        return tuple(keys)


class _FakeQuery:
    def __init__(self, store, batches):
        self.store = store
        self.batches = batches
        self.batch_keys = ()

    def filter(self, batch_keys):
        self.batch_keys = tuple(batch_keys)
        self.batches.append(self.batch_keys)
        return self

    def all(self):
        return [
            self.store[key]
            for key in self.batch_keys
            if key in self.store
        ]


class _FakeSession:
    def __init__(self, store):
        self.store = store
        self.batches = []

    def query(self, _model):
        return _FakeQuery(self.store, self.batches)


def _row(index):
    return {
        "sucursal_key": f"SUCURSAL-{index % 17:02d}",
        "pin": f"{index:07d}",
        "fecha_vencimiento_date": date(
            2026,
            1 + (index % 8),
            1 + (index % 27),
        ),
    }


def _install_fake_sql(monkeypatch):
    fake_model = SimpleNamespace(
        sucursal_key=object(),
        pin=object(),
        fecha_vencimiento_date=object(),
    )
    monkeypatch.setattr(repository, "SociosVencidosCarteraORM", fake_model)
    monkeypatch.setattr(
        repository,
        "tuple_",
        lambda *_columns: _TupleExpression(),
    )


def test_read_existing_cartera_rows_batches_large_lookup(monkeypatch):
    _install_fake_sql(monkeypatch)

    rows = [_row(index) for index in range(1201)]
    keys = {
        repository._cartera_episode_key(row)
        for row in rows
    }
    store = {
        key: SimpleNamespace(
            sucursal_key=key[0],
            pin=key[1],
            fecha_vencimiento_date=key[2],
        )
        for key in keys
    }
    session = _FakeSession(store)

    result = repository._read_existing_cartera_rows(
        rows=rows,
        session=session,
    )

    assert [len(batch) for batch in session.batches] == [500, 500, 201]
    assert set(result) == keys
    assert len(result) == 1201


def test_read_existing_cartera_rows_deduplicates_before_batching(monkeypatch):
    _install_fake_sql(monkeypatch)

    unique_rows = [_row(index) for index in range(501)]
    rows = unique_rows + unique_rows[:25]
    keys = {
        repository._cartera_episode_key(row)
        for row in unique_rows
    }
    store = {
        key: SimpleNamespace(
            sucursal_key=key[0],
            pin=key[1],
            fecha_vencimiento_date=key[2],
        )
        for key in keys
    }
    session = _FakeSession(store)

    result = repository._read_existing_cartera_rows(
        rows=rows,
        session=session,
    )

    assert [len(batch) for batch in session.batches] == [500, 1]
    assert set(result) == keys


def test_read_existing_cartera_rows_empty_input_does_not_query():
    session = _FakeSession({})

    result = repository._read_existing_cartera_rows(
        rows=[],
        session=session,
    )

    assert result == {}
    assert session.batches == []
