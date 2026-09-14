from collections import Counter
from types import SimpleNamespace

from app.services import marketing_reactivation_service as service


class _FakeQuery:
    def __init__(self, rows):
        self.rows = list(rows)
        self.iterations = 0

    def yield_per(self, _batch_size):
        self.iterations += 1
        if self.iterations > 1:
            raise AssertionError("La consulta base no debe recorrerse dos veces")
        yield from self.rows


class _FakeSession:
    pass


def test_collect_segment_batches_reuses_single_base_query_pass(monkeypatch):
    rows = [
        SimpleNamespace(id=1),
        SimpleNamespace(id=2),
        SimpleNamespace(id=3),
    ]
    query = _FakeQuery(rows)
    observed_batches = []

    def fake_count(*, vencidos_rows, context, session):
        observed_batches.append([row.id for row in vencidos_rows])
        return Counter({str(vencidos_rows[0].id): len(vencidos_rows)})

    monkeypatch.setattr(
        service,
        "count_socios_vencidos_not_found_phones",
        fake_count,
    )

    phone_counts, batches = (
        service._collect_complete_segment_batches_and_phone_counts(
            base_query=query,
            context=object(),
            session=_FakeSession(),
            batch_size=2,
        )
    )

    assert query.iterations == 1
    assert observed_batches == [[1, 2], [3]]
    assert [[row.id for row in batch] for batch in batches] == [[1, 2], [3]]
    assert phone_counts == Counter({"1": 2, "3": 1})
