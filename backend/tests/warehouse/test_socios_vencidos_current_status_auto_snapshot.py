from datetime import date
from types import SimpleNamespace

import pytest

from app.warehouse.services import (
    socios_vencidos_current_status_resolver
    as resolver,
)


def test_auto_mode_uses_latest_canonical_snapshot(
    monkeypatch,
):
    vencidos_snapshot = SimpleNamespace(
        date_to=date(2026, 8, 23),
    )

    expected_snapshot = SimpleNamespace(
        id=2,
        cutoff_date=date(2026, 8, 25),
    )

    fake_session = object()
    calls = {}

    def fake_resolve(
        *,
        minimum_cutoff_date,
        session,
    ):
        calls["minimum_cutoff_date"] = (
            minimum_cutoff_date
        )
        calls["session"] = session

        return expected_snapshot

    monkeypatch.setattr(
        resolver,
        "resolve_latest_canonical_socios_activos_snapshot",
        fake_resolve,
    )

    result = (
        resolver
        ._resolve_activos_snapshot_for_vencidos(
            vencidos_snapshot=vencidos_snapshot,
            activos_snapshot_id=None,
            active_session=fake_session,
        )
    )

    assert result is expected_snapshot
    assert calls[
        "minimum_cutoff_date"
    ] == date(2026, 8, 23)
    assert calls["session"] is fake_session


def test_auto_mode_fails_closed_without_canonical_snapshot(
    monkeypatch,
):
    vencidos_snapshot = SimpleNamespace(
        date_to=date(2026, 8, 23),
    )

    monkeypatch.setattr(
        resolver,
        "resolve_latest_canonical_socios_activos_snapshot",
        lambda **kwargs: None,
    )

    with pytest.raises(
        resolver.SociosVencidosCurrentStatusResolverError,
        match="No existe un snapshot canónico",
    ):
        resolver._resolve_activos_snapshot_for_vencidos(
            vencidos_snapshot=vencidos_snapshot,
            activos_snapshot_id=None,
            active_session=object(),
        )


def test_explicit_snapshot_id_preserves_manual_mode(
    monkeypatch,
):
    expected_snapshot = SimpleNamespace(
        id=2,
        cutoff_date=date(2026, 8, 25),
    )

    class FakeQuery:
        def filter(self, *args):
            return self

        def one_or_none(self):
            return expected_snapshot

    class FakeSession:
        def query(self, model):
            return FakeQuery()

    def fail_if_auto_resolver_is_called(
        **kwargs,
    ):
        raise AssertionError(
            "No debe resolver canonical automáticamente "
            "cuando activos_snapshot_id es explícito."
        )

    monkeypatch.setattr(
        resolver,
        "resolve_latest_canonical_socios_activos_snapshot",
        fail_if_auto_resolver_is_called,
    )

    result = (
        resolver
        ._resolve_activos_snapshot_for_vencidos(
            vencidos_snapshot=SimpleNamespace(
                date_to=date(2026, 8, 23),
            ),
            activos_snapshot_id=2,
            active_session=FakeSession(),
        )
    )

    assert result is expected_snapshot
