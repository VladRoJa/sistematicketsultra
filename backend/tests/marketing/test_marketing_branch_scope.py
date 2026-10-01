from __future__ import annotations

from types import SimpleNamespace

from app.services import marketing_campaign_audience_service as legacy_audience
from app.services import marketing_branch_scope as shared_scope


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args):
        return self

    def all(self):
        return list(self.rows)


class _Session:
    def __init__(self, rows):
        self.rows = rows

    def query(self, _model):
        return _Query(self.rows)


def test_shared_branch_mapper_uses_track_label_and_active_catalog_contract():
    session = _Session(
        [
            SimpleNamespace(sucursal_id=2, track_label=" branch   b "),
            SimpleNamespace(sucursal_id=1, track_label="Branch A"),
            SimpleNamespace(sucursal_id=None, track_label="Ignored"),
        ]
    )
    result = shared_scope.marketing_branch_keys_by_sucursal_ids(
        sucursal_ids=(2, 1, 2),
        session=session,
    )
    assert result == {1: "BRANCH A", 2: "BRANCH B"}


def test_legacy_reactivation_mapper_delegates_to_shared_helper(monkeypatch):
    calls = []

    def shared(**kwargs):
        calls.append(kwargs)
        return {7: "CENTRO"}

    monkeypatch.setattr(
        legacy_audience,
        "marketing_branch_keys_by_sucursal_ids",
        shared,
    )
    session = object()
    result = legacy_audience.reactivation_branch_keys_by_sucursal_ids(
        sucursal_ids=[7],
        session=session,
    )
    assert result == {7: "CENTRO"}
    assert calls == [{"sucursal_ids": [7], "session": session}]
