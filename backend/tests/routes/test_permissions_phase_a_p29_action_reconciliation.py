"""Fase A P29: candidates are diagnostics, NEVER authorization.

Read the historical action seed and the P28/P29 manifests. Inspect Flask's
registered handlers without invoking any endpoint, DB query, or service.
Neither a JWT decorator nor an action name proves object/branch permission.
"""
import ast
import csv
from collections import Counter
import inspect
from pathlib import Path
import re
import textwrap

import pytest

from app import create_app
from app.utils.permission_route_inventory import flask_registry

ROOT = Path(__file__).resolve().parents[3]
P28 = ROOT / "docs/security/permissions_phase_a_p28_live_mutations_20261026.csv"
P29 = ROOT / "docs/security/permissions_phase_a_p29_action_reconciliation_20261026.csv"
SEEDS = (
    "backend/migrations/versions/3d4f6a8b9c10_seed_global_permissions_catalog.py",
    "backend/migrations/versions/7b8c9d0e1f2a_seed_permission_route_map_high_risk.py",
    "backend/migrations/versions/8f1e2d3c4b5a_add_permission_module_assignable_metadata.py",
)

CANDIDATES = {
    "coordinate_maintenance_ticket": "tickets.update",
    "reassign_maintenance_ticket": "tickets.update",
    "maintenance_return_work_to_technician": "tickets.update_status",
    "maintenance_mark_work_completed": "tickets.update_status",
    "cambiar_recepcion_aparato": "tickets.update",
    "cambiar_recepciones_lote_tapizado": "tickets.update",
    "corregir_codigo_interno": "inventory.master_write",
    "anular_movimiento": "inventory.movement_write",
    "mark_opening_opened": "openings.manage",
    "update_user_module_access": "users.manage",
}
MUTATIONS = {"POST", "PUT", "PATCH", "DELETE"}


def _read_csv(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def app():
    return create_app()


def _handler_ast(fn):
    source = inspect.getsource(inspect.unwrap(fn))
    syntax = ast.parse(textwrap.dedent(source))
    return next(
        x for x in syntax.body if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def _direct_calls(node):
    calls = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if isinstance(child.func, ast.Name):
            calls.add(child.func.id)
        elif isinstance(child.func, ast.Attribute):
            calls.add(child.func.attr)
    return calls


def _jwt_present(node):
    for deco in node.decorator_list:
        fn = deco.func if isinstance(deco, ast.Call) else deco
        if isinstance(fn, ast.Name) and fn.id == "jwt_required":
            return True
    return False


def test_p29_all_112_decisions_remain_a_one_to_one_projection_of_p28():
    p28 = _read_csv(P28)
    p29 = _read_csv(P29)
    idcols = ("family", "method", "route", "handler", "review_group", "risk_triage")
    assert len(p28) == len(p29) == 112
    assert [{k: row[k] for k in idcols} for row in p29] == [
        {k: row[k] for k in idcols} for row in p28
    ]
    assert Counter(row["proposal_state"] for row in p29) == {
        "candidate_requires_guard_parity": 10,
        "requires_operational_action_decision": 102,
    }
    assert all(row["runtime_permission_proven"] == "NO" for row in p29)
    assert all(row["catalog_state_at_cut"] == "not_cataloged" for row in p29)
    assert all(row["backend_gate_to_verify"] and row["boundary_to_verify"] for row in p29)


def test_p29_only_explicit_tentative_candidates_exist_in_historical_migrations():
    p29 = _read_csv(P29)
    seed_text = "\n".join((ROOT / file).read_text(encoding="utf-8") for file in SEEDS)
    present = {
        match.group(1) for match in re.finditer(
            r"""["']([a-z][a-z_]*\.[a-z][a-z_]*)["']""", seed_text
        )
    }
    actual = {row["handler"]: row["historical_seed_action_candidate"]
              for row in p29 if row["historical_seed_action_candidate"]}
    assert actual == CANDIDATES
    assert set(actual.values()) <= present
    assert all(
        row["proposal_state"] == (
            "candidate_requires_guard_parity"
            if row["historical_seed_action_candidate"]
            else "requires_operational_action_decision"
        ) for row in p29
    )


def test_p29_flask_methods_have_direct_jwt_except_the_three_session_protocol_routes(app):
    # Structural observation only. Login/refresh/logout intentionally use
    # credential/cookie contracts and must not require access JWT.
    views = {
        (method, rule.rule): inspect.unwrap(app.view_functions[rule.endpoint])
        for rule in app.url_map.iter_rules()
        for method in set(rule.methods) & MUTATIONS
        if rule.rule.startswith("/api/")
    }
    missing = []
    for row in _read_csv(P29):
        key = row["method"], row["route"]
        handler = views.get(key)
        if handler is None or handler.__name__ != row["handler"]:
            missing.append((key, "missing_or_renamed"))
            continue
        if row["family"] != "auth" and not _jwt_present(_handler_ast(handler)):
            missing.append((key, "jwt_decorator_absent"))
    assert missing == []


def test_p29_high_risk_handler_gate_signals_are_still_present(app):
    views = {
        rule.endpoint.rsplit(".", 1)[-1]:
            inspect.unwrap(app.view_functions[rule.endpoint])
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith("/api/")
    }
    expectations = {
        "update_user_module_access": "_current_admin_user_or_error",
        "request_track_canonical_close_endpoint": "_require_track_admin_role",
        "create_gasca_sms_request_route": "_require_module_access",
        "campaign_v2_governed_execute_endpoint":
            "_resolve_campaign_v2_dispatch_config_request",
        "post_purchase_requisition_finance_approve_quote": "_current_user",
        "post_purchase_requisition_finance_reject_quote": "_current_user",
        "post_verify_purchase": "_assert_appointment_access",
        "bi_rollout": "_require_bi_access",
        "publish_google_ads_m6_manual_day": "require_current_admicorp",
    }
    absent = []
    for handler, signal in expectations.items():
        if handler not in views or signal not in _direct_calls(_handler_ast(views[handler])):
            absent.append((handler, signal))
    assert absent == []
