from types import SimpleNamespace

import pytest

import app.services.marketing_iventas_branch_service as service
from app.services.marketing_iventas_branch_service import (
    IVENTAS_ALIAS_SOURCE_FAMILY,
    MarketingIventasBranchResolutionError,
    resolve_iventas_branch,
)


def _catalog(
    *,
    sucursal_id=13,
    is_track_active=True,
):
    return SimpleNamespace(
        sucursal_id=sucursal_id,
        is_track_active=is_track_active,
    )


def test_resolve_iventas_branch_returns_canonical_result(
    monkeypatch,
) -> None:
    captured = {}

    def fake_alias_resolver(
        *,
        source_family,
        raw_branch_name,
    ):
        captured["source_family"] = source_family
        captured["raw_branch_name"] = (
            raw_branch_name
        )
        return "PAPALOTE_TJ"

    monkeypatch.setattr(
        service,
        "resolve_track_branch_alias",
        fake_alias_resolver,
    )

    monkeypatch.setattr(
        service,
        "_load_track_catalog_branch",
        lambda sucursal_canon: _catalog(),
    )

    result = resolve_iventas_branch(
        "  papalote  "
    )

    assert result is not None

    assert result.branch_code == "papalote"
    assert (
        result.sucursal_canon
        == "PAPALOTE_TJ"
    )
    assert result.sucursal_id == 13

    assert (
        captured["source_family"]
        == IVENTAS_ALIAS_SOURCE_FAMILY
    )

    assert (
        captured["raw_branch_name"]
        == "papalote"
    )


def test_unresolved_alias_returns_none(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        service,
        "resolve_track_branch_alias",
        lambda **kwargs: None,
    )

    def should_not_load_catalog(
        sucursal_canon,
    ):
        raise AssertionError(
            "No debe consultar catálogo "
            "si el alias no resolvió."
        )

    monkeypatch.setattr(
        service,
        "_load_track_catalog_branch",
        should_not_load_catalog,
    )

    assert (
        resolve_iventas_branch(
            "codigo-inexistente"
        )
        is None
    )


def test_blank_branch_code_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="branch_code",
    ):
        resolve_iventas_branch("   ")


def test_missing_track_catalog_is_structural_error(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        service,
        "resolve_track_branch_alias",
        lambda **kwargs: "PAPALOTE_TJ",
    )

    monkeypatch.setattr(
        service,
        "_load_track_catalog_branch",
        lambda sucursal_canon: None,
    )

    with pytest.raises(
        MarketingIventasBranchResolutionError,
        match="track_branch_catalog",
    ):
        resolve_iventas_branch(
            "papalote"
        )


def test_catalog_without_sucursal_id_is_error(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        service,
        "resolve_track_branch_alias",
        lambda **kwargs: "PAPALOTE_TJ",
    )

    monkeypatch.setattr(
        service,
        "_load_track_catalog_branch",
        lambda sucursal_canon: _catalog(
            sucursal_id=None
        ),
    )

    with pytest.raises(
        MarketingIventasBranchResolutionError,
        match="sucursal_id",
    ):
        resolve_iventas_branch(
            "papalote"
        )


def test_inactive_track_destination_is_error(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        service,
        "resolve_track_branch_alias",
        lambda **kwargs: "PAPALOTE_TJ",
    )

    monkeypatch.setattr(
        service,
        "_load_track_catalog_branch",
        lambda sucursal_canon: _catalog(
            is_track_active=False
        ),
    )

    with pytest.raises(
        MarketingIventasBranchResolutionError,
        match="inactivo",
    ):
        resolve_iventas_branch(
            "papalote"
        )


def test_non_positive_sucursal_id_is_error(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        service,
        "resolve_track_branch_alias",
        lambda **kwargs: "PAPALOTE_TJ",
    )

    monkeypatch.setattr(
        service,
        "_load_track_catalog_branch",
        lambda sucursal_canon: _catalog(
            sucursal_id=0
        ),
    )

    with pytest.raises(
        MarketingIventasBranchResolutionError,
        match="inválido",
    ):
        resolve_iventas_branch(
            "papalote"
        )
