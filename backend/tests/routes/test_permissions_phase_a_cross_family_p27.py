"""Fase A P27: censo y gates de entrada de cinco familias sensibles.

Contrato ESTATICO del registro Flask y AST. No invoca endpoints, servicios,
proveedores ni persistencia. El JWT/gate visible no certifica permiso efectivo
para una fila, sucursal o estado. La cobertura de servicio es independiente.
"""
from __future__ import annotations

import ast
from collections import Counter
import inspect
import textwrap

import pytest

from app import create_app


# Congelamos las mutaciones conocidas para exigir revisión explícita cuando
# se incorpore una ruta nueva (no se infiere riesgo solo por el método POST).
EXPECTED_WRITES = {
    "contact_center": {
        "post_contact", "post_merge_contacts", "post_assign_case",
        "post_interaction", "post_appointment", "post_close_appointment",
        "post_correct_appointment_result", "post_reschedule_appointment",
        "post_verify_purchase", "post_import_crm_candidate",
    },
    "purchase_requisition": {
        "post_purchase_requisition_finance_approver",
        "put_purchase_requisition_finance_approver",
        "post_purchase_requisition", "post_purchase_requisition_quote",
        "post_purchase_requisition_quote_select",
        "post_purchase_requisition_submit_quote_for_finance",
        "post_purchase_requisition_finance_approve_quote",
        "post_purchase_requisition_finance_reject_quote",
        "post_purchase_requisition_advance_logistics",
        "post_purchase_requisition_confirm_receipt",
        "post_purchase_requisition_report_receipt_issue",
        "post_purchase_requisition_resume_logistics",
        "post_purchase_requisition_administrative_correction",
        "put_purchase_requisition_requester_edit",
        "post_purchase_requisition_request_info",
        "post_purchase_requisition_resubmit",
        "post_purchase_requisition_approve",
        "post_purchase_requisition_reject",
        "post_purchase_requisition_attachment",
    },
    "system_daily_check": {"today_postpone", "today_submit"},
    "system_daily_check_bi": {"bi_rollout"},
    "automation_control": set(),
}
EXPECTED_COUNTS = {
    "contact_center": 18,
    "purchase_requisition": 24,
    "system_daily_check": 5,
    "system_daily_check_bi": 11,
    "automation_control": 14,
}
HTTP = {"GET", "POST", "PUT", "PATCH", "DELETE"}
WRITES = HTTP - {"GET"}
CONTACT_OPERATOR_ONLY = {
    "post_merge_contacts", "post_assign_case", "post_verify_purchase",
}
CONTACT_CASE_CHECK = {"post_interaction", "post_appointment"}
CONTACT_APPOINTMENT_CHECK = {
    "post_close_appointment", "post_correct_appointment_result",
    "post_reschedule_appointment", "post_verify_purchase",
}


@pytest.fixture(scope="module")
def registry():
    """Se inicializa la app, pero jamás se realiza consulta SQL/HTTP."""
    app = create_app()
    rows = []
    for rule in app.url_map.iter_rules():
        blueprint = rule.endpoint.split(".", 1)[0]
        if blueprint not in EXPECTED_WRITES:
            continue
        function = inspect.unwrap(app.view_functions[rule.endpoint])
        for method in sorted(set(rule.methods) & HTTP):
            rows.append((blueprint, method, rule.rule, function))
    return rows


def _tree(fn):
    source = textwrap.dedent(inspect.getsource(fn))
    parsed = ast.parse(source)
    return next(
        node for node in parsed.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def _calls(node):
    result = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if isinstance(child.func, ast.Name):
            result.add(child.func.id)
        elif isinstance(child.func, ast.Attribute):
            result.add(child.func.attr)
    return result


def _has_jwt(node):
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name) and target.id == "jwt_required":
            return True
    return False


def test_p27_registry_is_exactly_the_reviewed_five_families(registry):
    counts = Counter(blueprint for blueprint, _, _, _ in registry)
    assert counts == EXPECTED_COUNTS
    got = {
        blueprint: {
            fn.__name__ for bp, method, _, fn in registry
            if bp == blueprint and method in WRITES
        }
        for blueprint in EXPECTED_WRITES
    }
    assert got == EXPECTED_WRITES
    assert len(registry) == 72
    assert sum(len(v) for v in got.values()) == 32


def test_p27_every_registered_operation_has_direct_jwt(registry):
    missing = [
        (method, route, fn.__name__)
        for _, method, route, fn in registry if not _has_jwt(_tree(fn))
    ]
    assert missing == []


def test_p27_mutations_retain_identified_entry_guards(registry):
    missing = []
    for blueprint, method, route, fn in registry:
        if method not in WRITES:
            continue
        calls = _calls(_tree(fn))
        if blueprint == "contact_center":
            required = {"_context"}
            if fn.__name__ in CONTACT_OPERATOR_ONLY:
                required.add("_assert_operator_access")
            if fn.__name__ in CONTACT_CASE_CHECK:
                required.add("_assert_case_access")
            if fn.__name__ in CONTACT_APPOINTMENT_CHECK:
                required.add("_assert_appointment_access")
            if fn.__name__ in {"post_contact", "post_import_crm_candidate"}:
                required.add(
                    "create_contact_with_case"
                    if fn.__name__ == "post_contact"
                    else "import_crm_candidate"
                )
        elif blueprint == "purchase_requisition":
            # El control de actor existe en el handler; políticas finanzas,
            # estado y scope se deben comprobar dentro del servicio.
            required = {"_current_user"}
        elif blueprint == "system_daily_check":
            required = {"_current_user", "_requested_branch_id"}
            required.add("submit_today" if fn.__name__ == "today_submit"
                         else "postpone_today")
        elif blueprint == "system_daily_check_bi":
            required = {
                "_current_user", "_require_bi_access",
                "configure_system_daily_check_rollout_today",
            }
        else:
            required = set()  # automation_control no tiene mutaciones
        for call in required - calls:
            missing.append((method, route, fn.__name__, call))
    assert missing == []


def test_p27_delegated_finance_checks_are_not_mistaken_for_handler_checks(
    registry,
):
    """No se promueve _current_user a un permiso de aprobar/rechazar."""
    finance = {
        "post_purchase_requisition_finance_approve_quote":
            "approve_purchase_requisition_quote_by_finance",
        "post_purchase_requisition_finance_reject_quote":
            "reject_purchase_requisition_quote_by_finance",
    }
    functions = {
        fn.__name__: fn for bp, method, _, fn in registry
        if bp == "purchase_requisition" and method in WRITES
    }
    for name, service in finance.items():
        assert name in functions
        assert service in _calls(_tree(functions[name]))
        assert "_current_user" in _calls(_tree(functions[name]))
