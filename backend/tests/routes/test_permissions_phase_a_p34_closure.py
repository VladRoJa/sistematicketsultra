"""P34 — contrato de cierre A, sólo diagnóstico, sin efecto sobre grants.

La discrepancia de Nube se documenta como baseline de migración B1.
Ninguna prueba modifica las políticas ni consulta usuarios de producción.
"""

import csv
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import create_app
from app.routes.permissions_catalog_routes import _effective_action_decision
from app.utils.internal_documents_access import (
    InternalDocumentUserContext,
    can_manage_internal_documents,
)

ROOT = Path(__file__).resolve().parents[3]
MASTER = ROOT / "docs/security/permissions_phase_a_p34_compatibility_master_20261027.csv"
NUBE = ROOT / "docs/security/permissions_phase_a_p34_nube_pilot_p1_reads_20261027.csv"
P33 = ROOT / "docs/security/permissions_phase_a_p33_102_source_closure_20261027.csv"
DOC = ROOT / "docs/security/permissions_phase_a_p34_closure_20261027.md"

MODULE_KEYS = {
    "tickets", "inventory", "pm", "warehouse", "internal_documents",
    "track", "planning", "openings", "catalogs", "users", "reports",
}


def read_rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_p34_master_contract_is_eleven_modules_and_no_grants_or_enforcement():
    rows = read_rows(MASTER)
    assert len(rows) == 11
    assert {r["module_key"] for r in rows} == MODULE_KEYS
    assert all(r["real_authority_sources"] and r["hard_stops_to_preserve"]
               and r["phase_a_decision"] and r["next_gate"] for r in rows)
    first = next(r for r in rows if r["module_key"] == "internal_documents")
    assert first["pilot_priority"] == "priority_1_pilot"
    assert first["phase_a_decision"] == "retain_hard_stops;compare_only_first"
    for row in rows:
        if row["module_key"] != "internal_documents":
            assert row["pilot_priority"].startswith(("deferred_", "future_"))
    text = DOC.read_text(encoding="utf-8")
    for marker in ("247 GET", "112", "D1", "D2", "D3", "D4",
                   "compare_only", "ADMICORP", "SISTEMAS", "#1058"):
        assert marker in text
    assert len(read_rows(P33)) == 102


@pytest.mark.parametrize(
    "role,username,real,diagnostic",
    [
        ("SISTEMAS", "SISTEMAS_DEMO", True, True),
        ("ADMINISTRADOR", "ADMIN_DEMO", False, False),
        ("ADMINISTRADOR", "ADMICORP", True, True),
        ("GERENTE", "GERENTE_DEMO", False, False),
    ],
)
def test_p34_nube_guard_vs_observability_baseline(role, username, real, diagnostic):
    actor = InternalDocumentUserContext(
        user_id=99, username=username, role=role,
        sucursal_id=None, sucursales_ids=(), department_id=None,
    )
    assert can_manage_internal_documents(actor) is real
    action = SimpleNamespace(full_key="internal_documents.manage")
    context = {
        "role": role,
        "sucursal_ids": [],
        "warehouse_operator": None,
        "planning_operator": None,
    }
    # B1 resuelve identidad del usuario objetivo, no un rol aislado.
    projection = _effective_action_decision(action, actor, context)
    assert projection["allowed"] is diagnostic
    assert projection["details"]["mode"] == "compare_only"


def test_p34_p1_document_get_endpoints_exist_and_require_jwt():
    expected = read_rows(NUBE)
    assert len(expected) == 9
    assert all(r["method"] == "GET" and r["priority"] == "P1"
               and r["validation_status"] == "static_inspection_and_existing_regression"
               for r in expected)
    assert len({r["route"] for r in expected}) == 9

    app = create_app()
    app.config["TESTING"] = True
    registered = {(rule.rule, method) for rule in app.url_map.iter_rules()
                  for method in rule.methods}
    client = app.test_client()
    for entry in expected:
        route = entry["route"]
        assert (route, "GET") in registered
        concrete = route.replace("<int:document_id>", "99111")
        concrete = concrete.replace("<int:version_id>", "99222")
        response = client.get(concrete)
        assert response.status_code == 401, (route, response.status_code)


def test_p34_safety_requires_no_permission_migration():
    report = DOC.read_text(encoding="utf-8")
    assert "sin activar enforcement" in report
    assert "permission_grants" in report
    assert "Sin migración Alembic" in report
    assert "no concluyente" in report
