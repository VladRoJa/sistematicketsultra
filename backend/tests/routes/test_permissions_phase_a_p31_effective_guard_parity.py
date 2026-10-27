"""Fase A P31: efectivo = guard backend; accion catalogada = observabilidad.

Synthetic, deny-before-side-effects regression for ten P30 candidates.
No production HTTP/DB, grants, inventory mutation, SMTP or scheduler.
"""
import csv
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app import create_app
from app.routes import (
    inventarios as inventory,
    openings_lifecycle_routes as lifecycle,
    openings_routes as openings,
    permissions_catalog_routes as catalog,
)
from app.services import (
    ticket_maintenance_coordination_service as maintenance,
    ticket_tapizado_recepcion_service as tapizado,
)

ROOT = Path(__file__).resolve().parents[3]
P30 = ROOT / "docs/security/permissions_phase_a_p30_live_action_reconciliation_20261026.csv"
P31 = ROOT / "docs/security/permissions_phase_a_p31_effective_guards_20261027.csv"
HANDLERS = {
    "coordinate_maintenance_ticket": ("tickets.maintenance.coordinate", "specialized_guard_aligned"),
    "reassign_maintenance_ticket": ("tickets.maintenance.coordinate", "specialized_guard_aligned"),
    "maintenance_return_work_to_technician": (
        "tickets.maintenance.coordinate", "specialized_guard_aligned",
    ),
    "maintenance_mark_work_completed": ("", "generic_action_not_equivalent"),
    "cambiar_recepcion_aparato": ("", "generic_action_not_equivalent"),
    "cambiar_recepciones_lote_tapizado": ("", "generic_action_not_equivalent"),
    "corregir_codigo_interno": ("inventory.master_write", "candidate_guard_scoped"),
    "anular_movimiento": ("inventory.movement_write", "candidate_guard_scoped"),
    "mark_opening_opened": ("openings.manage", "observability_projection_corrected"),
    "update_user_module_access": ("users.manage", "candidate_guard_scoped"),
}


def _rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def test_p31_all_112_preserved_and_only_ten_reclassified():
    earlier, current = _rows(P30), _rows(P31)
    identity = ("family", "method", "route", "handler", "review_group", "risk_triage")
    assert len(earlier) == len(current) == 112
    assert [{key: row[key] for key in identity} for row in current] == [
        {key: row[key] for key in identity} for row in earlier
    ]
    assert all(row["effective_permission_proven_by_runtime"] == "NO" for row in current)
    present = {}
    for row in current:
        found = HANDLERS.get(row["handler"])
        if not found:
            assert row["p31_guard_parity_class"] == "out_of_scope_p31"
            assert row["p31_diagnostic_action"] == ""
            continue
        present[row["handler"]] = (row["p31_diagnostic_action"], row["p31_guard_parity_class"])
        assert row["p31_effective_gate"] and row["p31_resource_or_state_condition"]
    assert present == HANDLERS


@pytest.fixture(scope="module")
def deployed_registry_app():
    # Registry only; no handler is invoked unless JWT is verified first.
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.mark.parametrize("row", [row for row in _rows(P31) if row["handler"] in HANDLERS],
                         ids=lambda row: row["handler"])
def test_p31_all_ten_reject_anonymous_before_any_side_effect(deployed_registry_app, row):
    # Methods, Flask rule and test URL are tied to the P31 evidence manifest.
    import re
    path = re.sub(r"<int:[^>]+>", "908070", row["route"])
    result = deployed_registry_app.test_client().open(
        path, method=row["method"], json={},
    )
    assert result.status_code == 401


def _test_client(bp, prefix):
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="synthetic-p31-only")
    JWTManager(app)
    app.register_blueprint(bp, url_prefix=prefix)
    with app.app_context():
        token = create_access_token(identity="881")
    return app.test_client(), {"Authorization": "Bearer " + token}


@pytest.mark.parametrize("role,should_allow", [
    ("GERENTE", False),
    ("LECTOR_GLOBAL", False),
    ("SISTEMAS", True),
    ("APERTURAS_ADMIN", True),
    ("ADMINISTRADOR", True),
])
def test_openings_projection_equals_actual_http_guard_before_database(role, should_allow):
    # The catalog preview must not silently report DENY for an actual admin.
    action = SimpleNamespace(full_key="openings.manage")
    context = {"role": role, "sucursal_ids": [], "warehouse_operator": None,
               "planning_operator": None}
    preview = catalog._effective_action_decision(action, None, context)
    assert bool(preview["allowed"]) == should_allow
    assert should_allow == (role in openings.OPENINGS_ADMIN_ROLES)

    client, auth = _test_client(lifecycle.openings_lifecycle_bp, "/api/openings")
    session = Mock()
    session.get.return_value = None  # authorized lookup, never mutates an opening
    with patch.object(openings, "_current_role", return_value=role), \
         patch.object(lifecycle, "db", SimpleNamespace(session=session)):
        response = client.post("/api/openings/317/mark-opened", json={}, headers=auth)
    assert response.status_code == (404 if should_allow else 403)
    if should_allow:
        session.get.assert_called_once()
    else:
        session.get.assert_not_called()
    session.commit.assert_not_called()
    session.add.assert_not_called()


def test_user_module_grant_mutation_rejects_non_admin_before_db_lookup_or_write():
    client, auth = _test_client(catalog.permissions_catalog_bp, "/api/permissions/catalog")
    session = Mock()
    with patch.object(
        catalog.UserORM, "get_by_id",
        return_value=SimpleNamespace(id=881, rol="GERENTE"),
    ), patch.object(catalog, "db", SimpleNamespace(session=session)):
        response = client.put(
            "/api/permissions/catalog/users/55/module-access",
            headers=auth,
            json={"changes": [{"module_key": "tickets", "override": "allow"}]},
        )
    assert response.status_code == 403
    session.add.assert_not_called()
    session.flush.assert_not_called()
    session.commit.assert_not_called()


def test_master_code_change_requires_global_inventory_writer_before_lock():
    client, auth = _test_client(inventory.inventario_bp, "/api/inventario")
    with patch.object(
        inventory, "_get_current_inventory_user",
        return_value=SimpleNamespace(rol="GERENTE", id=881),
    ), patch.object(inventory, "_bloquear_escritura_codigos") as lock:
        response = client.post(
            "/api/inventario/443/corregir-codigo",
            headers=auth,
            json={"codigo_anterior": "ABC", "codigo_nuevo": "DEF",
                  "motivo": "Una razón válida"},
        )
    assert response.status_code == 403
    lock.assert_not_called()


@pytest.mark.parametrize("role,branch,allowed", [
    ("AUX_MANTENIMIENTO", 8, True),
    ("AUX_MANTENIMIENTO", 9, False),
    ("SR_MANTENIMIENTO", 8, True),
    ("SR_MANTENIMIENTO", 9, False),
    ("GERENTE", 8, False),
])
def test_inventory_annulment_guard_is_branch_specific(role, branch, allowed):
    user = SimpleNamespace(id=881, rol=role, sucursal_id=8, sucursales_ids=[8])
    app = Flask(__name__)
    with app.test_request_context("/api/inventario/movimientos/10/anular", method="POST"):
        with patch.object(inventory, "_get_current_inventory_user", return_value=user):
            result = inventory._require_inventory_movement_write(branch)
    assert (result is None) == allowed
    if not allowed:
        assert result[1] == 403


@pytest.mark.parametrize("role,department,branch,username,assigned,state,expected", [
    ("GERENTE", 2, 8, "GERENTE_C", "TECNICO_A", "en progreso", False),
    ("GERENTE", 2, 7, "GERENTE_B", "TECNICO_A", "en progreso", True),
    ("TECNICO", 1, 7, "TECNICO_B", "TECNICO_A", "en progreso", False),
    ("TECNICO", 1, 7, "TECNICO_A", "TECNICO_A", "en progreso", True),
    ("TECNICO", 1, 7, "TECNICO_A", "TECNICO_A", "abierto", False),
    ("ADMINISTRADOR", 1, 7, "ADMICORP", "TECNICO_A", "cerrado", False),
])
def test_tapizado_generic_ticket_update_is_not_reception_authority(
    role, department, branch, username, assigned, state, expected
):
    user = SimpleNamespace(rol=role, department_id=department,
                           sucursal_id=branch, username=username)
    ticket = SimpleNamespace(
        tipo_trabajo="TAPIZADO", estado=state,
        sucursal_id_destino=7, sucursal_id=3, asignado_a=assigned,
    )
    assert tapizado.puede_editar_recepcion_tapizado(user, ticket) is expected


@pytest.mark.parametrize("handler,role", [
    ("prepare_maintenance_work_completion", "GERENTE"),
    ("prepare_maintenance_work_return", "TECNICO"),
])
def test_maintenance_completion_and_return_are_distinct_policies_before_lookup(
    handler, role
):
    user = SimpleNamespace(id=881, rol=role, department_id=1, username="USUARIO_QA")
    with patch.object(maintenance, "has_maintenance_coordination_permission",
                      return_value=False), \
         patch.object(maintenance.Ticket, "query") as lookup:
        with pytest.raises(maintenance.TicketCoordinationForbidden):
            getattr(maintenance, handler)(42, user, {})
    lookup.filter.assert_not_called()
