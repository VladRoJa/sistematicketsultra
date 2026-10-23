"""P22 Fase A: mutaciones ausentes del SEED historico, no de permisos vigentes.

Inspecciona el url_map Flask y los nombres de funciones/llamadas AST; no
realiza HTTP, no consulta PostgreSQL, no ejecuta mutations ni usa grants.
La presencia de un helper no prueba su cobertura completa ni autoriza acceso.
"""
import ast
from collections import Counter, defaultdict
import inspect
import json
from pathlib import Path
import runpy
import textwrap

import pytest

from app import create_app

SEED = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/7b8c9d0e1f2a_seed_permission_route_map_high_risk.py"
)
HTTP = {"GET", "POST", "PUT", "PATCH", "DELETE"}
MUTATIONS = {"POST", "PUT", "PATCH", "DELETE"}
PRIORITIES = (
    "marketing", "contact-center", "purchase-requisitions",
    "system-daily-checks", "automation-control",
)


@pytest.fixture(scope="module")
def registry():
    app = create_app()
    seed_rows = runpy.run_path(str(SEED))["ROUTE_MAP_ROWS"]
    mapped = {
        (item["method"], item["route"])
        for item in seed_rows if item.get("is_active", True)
    }
    rows = []
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api/"):
            continue
        for method in sorted(set(rule.methods) & HTTP):
            rows.append({
                "method": method,
                "route": rule.rule,
                "endpoint": rule.endpoint,
                "handler": app.view_functions[rule.endpoint],
                "family": rule.rule.split("/")[2],
                "in_historical_seed": (method, rule.rule) in mapped,
            })
    return rows


def _unmapped(registry):
    return [row for row in registry if not row["in_historical_seed"]]


def _func_ast(fn):
    # Unwrap the @jwt_required wrapper to analyze the SOURCE body/decorators,
    # not to invoke the decorated function or bypass JWT in HTTP.
    source = textwrap.dedent(inspect.getsource(inspect.unwrap(fn)))
    tree = ast.parse(source)
    return next(node for node in tree.body if isinstance(
        node, (ast.FunctionDef, ast.AsyncFunctionDef)
    ))


def _called_functions(tree):
    return {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))
    }


def _attributes(tree):
    return {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}


def _jwt_decorator(tree):
    for decorator in tree.decorator_list:
        fn = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(fn, ast.Name) and fn.id == "jwt_required":
            return True
    return False


def test_p22_classify_unmapped_http_methods_by_family(registry):
    unmapped = _unmapped(registry)
    by_method = Counter(row["method"] for row in unmapped)
    per_family = defaultdict(Counter)
    for row in unmapped:
        per_family[row["family"]][row["method"]] += 1
    by_family = {
        family: {
            "read_method_get": count["GET"],
            "mutation_methods": sum(count[m] for m in MUTATIONS),
            "by_method": dict(sorted(count.items())),
        }
        for family, count in sorted(per_family.items())
    }
    print(
        "FASE_A_P22_METHOD_SPLIT=" + json.dumps({
            "basis": "Flask code current vs historical route-map seed ONLY",
            "seed_is_not_live_db": True,
            "http_requests_executed": False,
            "total_flask_http_method_handlers": len(registry),
            "unmapped_historical_seed": len(unmapped),
            "unmapped_get": by_method["GET"],
            "unmapped_mutations": sum(by_method[method] for method in MUTATIONS),
            "unmapped_by_http_method": dict(sorted(by_method.items())),
            "by_family": by_family,
        }, ensure_ascii=False, sort_keys=True)
    )
    assert by_method["GET"] > 0
    assert sum(by_method[m] for m in MUTATIONS) > 0
    assert by_method["GET"] + sum(by_method[m] for m in MUTATIONS) == len(unmapped)
    # GET describe el metodo HTTP, no certifica ausencia de efectos secundarios.


@pytest.mark.parametrize("family", PRIORITIES)
def test_p22_priority_families_classify_methods_without_claiming_bypass(
    registry, family
):
    rows = [item for item in _unmapped(registry) if item["family"] == family]
    assert rows, family
    read = [item for item in rows if item["method"] == "GET"]
    mutations = [item for item in rows if item["method"] in MUTATIONS]
    print(
        "P22_PRIORITY=" + json.dumps({
            "family": family,
            "get_count": len(read),
            "mutation_count": len(mutations),
            "mutation_handlers": sorted(
                (item["method"], item["route"], item["endpoint"])
                for item in mutations
            ),
        }, ensure_ascii=False, sort_keys=True)
    )
    assert len(read) + len(mutations) == len(rows)
    if family != "automation-control":
        assert mutations  # Comprueba que el alcance de auditoria incluye escrituras.


# (HTTP method, actual Python function name, direct call dependencies,
#  direct attr checks, authorization evidence classification)
# service_delegated: a ROUTE calls a service with actor; service's policy
# must be audited separately before claiming parity or enforcement.
SELECTED_MUTATIONS = [
    ("PUT", "put_marketing_input_endpoint",
     ("_resolve_request_access", "load_visible_marketing_branches",
      "upsert_marketing_input"), ("can_edit_inputs",), "inline_branch_capability"),
    ("POST", "campaign_v2_submit_endpoint",
     ("_resolve_campaign_v2_send_request",),
     (), "campaign_send_access_and_kill_switch"),
    ("POST", "campaign_v2_governed_execute_endpoint",
     ("_resolve_campaign_v2_dispatch_config_request",
      "_require_campaign_v2_send", "_valid_governed_dispatch_password"),
     (), "send_step_up_and_dispatch_config"),
    ("POST", "campaign_v2_blacklist_import_endpoint",
     ("_resolve_campaign_v2_request", "_require_campaign_v2_global_management"),
     (), "global_campaign_management"),
    ("POST", "post_contact",
     ("_context", "create_contact_with_case"),
     (), "contact_service_delegated"),
    ("POST", "post_merge_contacts",
     ("_context", "_assert_operator_access", "merge_contacts"),
     ("is_supervisor",), "contact_supervisor"),
    ("POST", "post_close_appointment",
     ("_context", "_assert_appointment_access", "close_appointment"),
     (), "appointment_scope_guard"),
    ("POST", "post_verify_purchase",
     ("_context", "_assert_operator_access", "_assert_appointment_access"),
     (), "operator_and_appointment_scope"),
    ("POST", "post_purchase_requisition",
     ("_current_user", "create_purchase_requisition"),
     (), "requisition_service_delegated"),
    ("POST", "post_purchase_requisition_finance_approve_quote",
     ("_current_user", "approve_purchase_requisition_quote_by_finance"),
     (), "requisition_finance_service_delegated"),
    ("POST", "post_purchase_requisition_approve",
     ("_current_user", "approve_purchase_requisition"),
     (), "requisition_approval_service_delegated"),
    ("POST", "post_purchase_requisition_finance_approver",
     ("_current_user", "create_purchase_requisition_finance_approver"),
     (), "requisition_admin_service_delegated"),
    ("POST", "today_submit",
     ("_current_user", "submit_today", "_requested_branch_id"),
     (), "daily_check_service_branch_delegated"),
    ("POST", "today_postpone",
     ("_current_user", "postpone_today", "_requested_branch_id"),
     (), "daily_check_service_branch_delegated"),
]


@pytest.mark.parametrize(
    "method,handler_name,required_calls,required_attrs,evidence",
    SELECTED_MUTATIONS, ids=[x[1] for x in SELECTED_MUTATIONS]
)
def test_p22_priority_mutation_guard_evidence_is_traced_not_inferred(
    registry, method, handler_name, required_calls, required_attrs, evidence
):
    rows = [
        row for row in _unmapped(registry)
        if row["method"] == method
        and row["handler"].__name__ == handler_name
    ]
    assert len(rows) == 1, (method, handler_name, rows)
    row = rows[0]
    tree = _func_ast(row["handler"])
    calls, attributes = _called_functions(tree), _attributes(tree)
    assert _jwt_decorator(tree), (handler_name, "JWT decorator missing")
    for required in required_calls:
        assert required in calls, (handler_name, required)
    for required in required_attrs:
        assert required in attributes, (handler_name, required)
    if handler_name == "put_marketing_input_endpoint":
        assert any(
            isinstance(node, ast.Compare)
            and isinstance(node.left, ast.Name)
            and node.left.id == "sucursal_id"
            and any(isinstance(op, ast.NotIn) for op in node.ops)
            for node in ast.walk(tree)
        ), "Marketing input must check requested sucursal against allowed scope"
    print(
        "P22_GUARD_EVIDENCE=" + json.dumps({
            "method": method,
            "route": row["route"],
            "handler": handler_name,
            "jwt_decorator_in_source": True,
            "direct_calls_observed": sorted(required_calls),
            "access_attributes_observed": sorted(required_attrs),
            "guard_evidence_kind": evidence,
            "authorization_parity_http_tested": False,
        }, ensure_ascii=False, sort_keys=True)
    )


def test_p22_automation_control_is_get_only_in_historical_unmapped_set(registry):
    rows = [
        item for item in _unmapped(registry)
        if item["family"] == "automation-control"
    ]
    assert rows
    assert {item["method"] for item in rows} == {"GET"}
    # Un GET no certifica que no haya efectos secundarios en helpers.


def test_p22_no_catalog_keys_generated_or_enforcement_installed(registry):
    assert any(item["family"] == "marketing" for item in _unmapped(registry))
    # P22 intencionalmente se limita a observacion; ausencia en seed !=
    # ausencia en DB vigente, ni es evidencia de bypass de endpoints.
