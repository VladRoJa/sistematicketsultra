"""Fase A: contrato de inversion de la MISMA matriz diagnostica.

Los endpoints inversos aun NO existen. Este fixture no los simula como rutas
productivas: proyecta un unico conjunto de decisiones de
_serialize_effective_action hacia tres indices in-memory y coteja que
todas conservan la misma tupla (usuario, accion, sucursal, objeto).

No toca PostgreSQL, grants, HTTP ni el resolvedor global.
"""
from collections import defaultdict
from types import SimpleNamespace

import pytest

from app.routes import permissions_catalog_routes as catalog


USERS = [
    (1, "ADMINISTRADOR", [7], False, False),
    (2, "SISTEMAS", [7], True, True),
    (3, "GERENTE", [9], False, False),
    (4, "LECTOR_GLOBAL", [7, 9], False, False),
    (5, "RECEPCIONISTA", [8], False, False),
]
ACTION_KEYS = [
    "track.read",
    "track.run_daily_pipeline",
    "warehouse.view",
    "warehouse.upload",
    "planning.read",
    "planning.edit",
    "internal_documents.view",
    "internal_documents.manage",
    "inventory.read",
    "inventory.movement_write",
    "pm.read",
    "tickets.close",
]


def _operator(view):
    return SimpleNamespace(can_view=view, can_upload=False, can_archive=False)


def _planning(view):
    return SimpleNamespace(
        can_view=view, can_edit=False, can_submit=False,
        can_approve=False, can_publish=False, can_configure_model=False,
        is_active=True,
    )


def _action(full_key, identifier):
    module_key, key = full_key.split(".", 1)
    return SimpleNamespace(
        id=identifier,
        module=SimpleNamespace(key=module_key),
        key=key,
        full_key=full_key,
        name=full_key,
        risk_level="low",
        is_active=True,
    )


def _matrix():
    # Construida una sola vez a partir de la funcion serializadora REAL
    # usada por GET /users/<id>/effective; NO representa views inversas
    # expuestas por la API.
    result = []
    for user_id, role, branches, wh_view, pl_view in USERS:
        user = SimpleNamespace(id=user_id, rol=role)
        ctx = {
            "role": role,
            "sucursal_ids": branches,
            "warehouse_operator": _operator(wh_view) if wh_view else None,
            "planning_operator": _planning(pl_view) if pl_view else None,
            "allow_ticket_delete_all": False,
        }
        for i, key in enumerate(ACTION_KEYS, start=1):
            decision = catalog._serialize_effective_action(
                _action(key, i), user, ctx
            )
            result.append({
                "user_id": user_id,
                "requested_sucursal_id": None,  # No hay contexto de request.
                "object_type": None,
                "object_id": None,
                **decision,
            })
    return result


def _project(rows):
    by_user = defaultdict(list)
    by_action = defaultdict(list)
    by_module = defaultdict(list)
    for row in rows:
        # Importante: solo indices de las MISMAS filas, sin recalcular
        # decision ni asignar "allowed" a otra accion por su nombre.
        by_user[row["user_id"]].append(row)
        by_action[row["full_key"]].append(row)
        by_module[row["module_key"]].append(row)
    return by_user, by_action, by_module


def _fingerprint(row):
    return (
        row["user_id"], row["action_id"], row["full_key"],
        row["module_key"], row["requested_sucursal_id"],
        row["object_type"], row["object_id"], row["allowed"],
        row["source"], row["reason"], row["scope_type"],
        tuple(row["scope_values"]),
    )


@pytest.mark.parametrize("user_id", [item[0] for item in USERS])
def test_p20_user_projection_preserves_action_rows(user_id):
    matrix = _matrix()
    by_user, by_action, by_module = _project(matrix)
    assert len(by_user[user_id]) == len(ACTION_KEYS)
    for row in by_user[user_id]:
        assert any(
            _fingerprint(candidate) == _fingerprint(row)
            for candidate in by_action[row["full_key"]]
        )
        assert any(
            _fingerprint(candidate) == _fingerprint(row)
            for candidate in by_module[row["module_key"]]
        )


@pytest.mark.parametrize("action_key", ACTION_KEYS)
def test_p20_action_projection_preserves_users_and_provenance(action_key):
    matrix = _matrix()
    by_user, by_action, by_module = _project(matrix)
    assert len(by_action[action_key]) == len(USERS)
    for row in by_action[action_key]:
        assert len([
            item for item in by_user[row["user_id"]]
            if item["full_key"] == action_key
        ]) == 1
        expected = next(
            item for item in by_user[row["user_id"]]
            if item["full_key"] == action_key
        )
        assert _fingerprint(expected) == _fingerprint(row)
        assert row in by_module[row["module_key"]]


@pytest.mark.parametrize(
    "module_key",
    sorted({key.split(".")[0] for key in ACTION_KEYS}),
)
def test_p20_module_projection_preserves_all_distinct_actions(module_key):
    matrix = _matrix()
    by_user, by_action, by_module = _project(matrix)
    keys = {key for key in ACTION_KEYS if key.startswith(module_key + ".")}
    assert {row["full_key"] for row in by_module[module_key]} == keys
    assert len(by_module[module_key]) == len(keys) * len(USERS)
    # No sumar permisos por modulo: cada fila conserva SU accion exacta.
    for row in by_module[module_key]:
        assert _fingerprint(row) in {
            _fingerprint(item) for item in by_user[row["user_id"]]
        }
        assert _fingerprint(row) in {
            _fingerprint(item) for item in by_action[row["full_key"]]
        }


@pytest.mark.parametrize("role,full_key,expected", [
    ("GERENTE", "track.read", True),
    ("LECTOR_GLOBAL", "track.read", True),
    ("SISTEMAS", "warehouse.view", True),
    ("GERENTE", "warehouse.view", False),
    ("SISTEMAS", "planning.read", True),
    ("ADMINISTRADOR", "internal_documents.manage", True),
    ("GERENTE", "internal_documents.manage", False),
])
def test_p20_inversion_preserves_diagnostic_decisions(
    role, full_key, expected
):
    rows = _matrix()
    user_id = next(item[0] for item in USERS if item[1] == role)
    by_user, by_action, by_module = _project(rows)
    first = next(
        row for row in by_user[user_id] if row["full_key"] == full_key
    )
    assert first["allowed"] is expected
    assert _fingerprint(first) in {
        _fingerprint(row) for row in by_action[full_key]
    }
    assert _fingerprint(first) in {
        _fingerprint(row) for row in by_module[first["module_key"]]
    }
    # Inversion coherente del DIAGNOSTICO no prueba que el guard coincida.
