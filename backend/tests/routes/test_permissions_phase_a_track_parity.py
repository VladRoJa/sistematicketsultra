"""Paridad diagnóstica Track: verificar guard real contra catálogo actualizado.

No llama endpoints, usuarios reales, JWT, scheduler ni PostgreSQL.
Un falso negativo de catalogo NO concede ni revoca permisos.
"""
from types import SimpleNamespace

import pytest

from app.routes import permissions_catalog_routes as catalog
from app.routes import track_routes as track


def _catalog_action(full_key, role):
    user = SimpleNamespace(id=-50, rol=role)
    context = {
        "role": role,
        "sucursal_ids": [11],
        "warehouse_operator": None,
        "planning_operator": None,
        "allow_ticket_delete_all": False,
    }
    return catalog._effective_action_decision(
        SimpleNamespace(full_key=full_key), user, context
    )


@pytest.mark.parametrize(
    "role,legacy_allowed,catalog_allowed",
    [
        ("ADMIN", True, True),
        ("ADMINISTRADOR", True, True),
        ("SUPER_ADMIN", True, True),
        ("LECTOR_GLOBAL", True, True),
        ("GERENTE", True, True),
        ("GERENTE_REGIONAL", True, True),
        ("SISTEMAS", True, True),
        ("GERENCIA DEPORTIVA", True, True),
        ("MARKETING", True, True),
        ("TIENDA", True, True),
        ("RECEPCIONISTA", False, False),
        ("COMPRAS", False, False),
    ],
)
def test_p16_track_read_role_guard_vs_catalog(
    monkeypatch, role, legacy_allowed, catalog_allowed
):
    monkeypatch.setattr(track, "_get_current_role", lambda: role)

    if legacy_allowed:
        assert track._require_track_read_role() is None
    else:
        with pytest.raises(PermissionError, match="consultar el Track"):
            track._require_track_read_role()

    observed = _catalog_action("track.read", role)
    assert observed["allowed"] is catalog_allowed

    assert observed["allowed"] is legacy_allowed
    assert observed["reason"] == "track_read_role_matches_guard_v2"
    assert observed["source"] == "legacy_role"



@pytest.mark.parametrize(
    "role,expected",
    [
        ("ADMIN", True),
        ("ADMINISTRADOR", True),
        ("SUPER_ADMIN", True),
        ("GERENTE", False),
        ("SISTEMAS", False),
        ("LECTOR_GLOBAL", False),
    ],
)
def test_p17_track_pipeline_guard_and_catalog_agree(monkeypatch, role, expected):
    monkeypatch.setattr(track, "_get_current_role", lambda: role)

    if expected:
        assert track._require_track_admin_role() is None
    else:
        with pytest.raises(PermissionError, match="ejecutar procesos"):
            track._require_track_admin_role()

    for action in ("track.run_daily_pipeline", "track.run_agregadoras"):
        observed = _catalog_action(action, role)
        assert observed["allowed"] is expected
        assert observed["source"] == "legacy_role"
