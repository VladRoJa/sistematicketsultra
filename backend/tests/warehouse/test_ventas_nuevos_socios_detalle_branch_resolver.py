from __future__ import annotations

from unittest.mock import sentinel

from app.warehouse.services import (
    ventas_nuevos_socios_detalle_branch_resolver
    as branch_resolver,
)


def test_delegates_to_existing_gasca_resolver_with_injected_session(
    monkeypatch,
):
    calls: list[dict[str, object]] = []

    def fake_resolver(
        source_branch_name,
        *,
        session,
    ):
        calls.append(
            {
                "source_branch_name": source_branch_name,
                "session": session,
            }
        )
        return 7

    monkeypatch.setattr(
        branch_resolver,
        "resolve_gasca_branch_id",
        fake_resolver,
    )

    result = (
        branch_resolver
        .resolve_ventas_nuevos_socios_detalle_branch_id(
            "  VILLAS DEL REY  ",
            session=sentinel.session,
        )
    )

    assert result == 7

    assert calls == [
        {
            "source_branch_name": (
                "  VILLAS DEL REY  "
            ),
            "session": sentinel.session,
        }
    ]
