"""P26.9 — contrato de inventario de Marketing en Flask (sin mutaciones).

El registro HTTP real, no los archivos V1 desregistrados ni el seed historico,
define el alcance. La evidencia AST prueba presencia de verificaciones
estructurales, NO su efectividad ni la autorizacion de servicios/filas SQL.
"""
import ast
from collections import Counter
import inspect
import textwrap
from unittest.mock import patch

from app import create_app
from app.config import Config


BLUEPRINTS = {
    "marketing": (7, 1),
    "marketing_campaign_v2": (76, 43),
    "marketing_sales_funnel": (3, 0),
}
HTTP = {"GET", "POST", "PUT", "PATCH", "DELETE"}
MUTATIONS = HTTP - {"GET"}
V2_REQUEST_GATES = {
    "_resolve_campaign_v2_request",
    "_resolve_campaign_v2_preflight_request",
    "_resolve_campaign_v2_dispatch_config_request",
    "_resolve_campaign_v2_reconciliation_request",
    "_resolve_campaign_v2_send_request",
}


def _active_routes():
    # The route census initializes Flask without opening a database connection.
    # CI has no production DATABASE_URI; an isolated SQLite URI is sufficient.
    with patch.object(Config, "SQLALCHEMY_DATABASE_URI", "sqlite://"):
        app = create_app()
    result = []
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api/marketing/"):
            continue
        blueprint = rule.endpoint.split(".", 1)[0]
        for method in sorted(set(rule.methods) & HTTP):
            result.append((
                blueprint,
                method,
                rule.rule,
                inspect.unwrap(app.view_functions[rule.endpoint]),
            ))
    return sorted(result, key=lambda row: (row[0], row[1], row[2]))


def _source_tree(function):
    source = textwrap.dedent(inspect.getsource(function))
    tree = ast.parse(source)
    return next(
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def _calls(tree):
    result = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            result.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            result.add(node.func.attr)
    return result


def _has_jwt_decorator(tree):
    return any(
        isinstance(
            decorator.func if isinstance(decorator, ast.Call) else decorator,
            ast.Name,
        )
        and (
            decorator.func if isinstance(decorator, ast.Call) else decorator
        ).id == "jwt_required"
        for decorator in tree.decorator_list
    )


def test_p26_9_active_blueprints_have_exact_reviewed_route_counts():
    routes = _active_routes()
    counts = Counter(row[0] for row in routes)
    mutations = Counter(row[0] for row in routes if row[1] in MUTATIONS)
    assert set(counts) == set(BLUEPRINTS)
    for blueprint, (expected_total, expected_mutations) in BLUEPRINTS.items():
        assert counts[blueprint] == expected_total, blueprint
        assert mutations[blueprint] == expected_mutations, blueprint
    assert len(routes) == 86
    assert sum(mutations.values()) == 44
    # Every new endpoint is explicitly accounted for in this reviewed census.
    route_methods = {(method, path) for _, method, path, _ in routes}
    assert {
        ("POST", "/api/marketing/campaigns-v2/<int:campaign_id>/dispatch/jobs"),
        ("GET", "/api/marketing/campaigns-v2/<int:campaign_id>/dispatch/jobs/<int:job_id>"),
        ("GET", "/api/marketing/campaigns-v2/dispatch/jobs/mine"),
        ("POST", "/api/marketing/campaigns-v2/<int:campaign_id>/dispatch/jobs/<int:job_id>/stop"),
    } <= route_methods


def test_p26_9_v1_blueprints_remain_unregistered():
    routes = _active_routes()
    assert not [
        (method, path) for _, method, path, _ in routes
        if path.startswith("/api/marketing/reactivation/")
    ]


def test_p26_9_all_active_marketing_handlers_require_jwt():
    routes = _active_routes()
    missing = [
        (method, path, function.__name__)
        for _, method, path, function in routes
        if not _has_jwt_decorator(_source_tree(function))
    ]
    assert missing == []


def test_p26_9_all_active_mutation_handlers_reach_backend_access_resolution():
    missing = []
    for blueprint, method, path, function in _active_routes():
        if method not in MUTATIONS:
            continue
        tree = _source_tree(function)
        calls = _calls(tree)
        if blueprint == "marketing_campaign_v2":
            if not (calls & V2_REQUEST_GATES):
                missing.append((method, path, function.__name__, "V2 gate"))
        elif blueprint == "marketing":
            if not {"_resolve_request_access", "load_visible_marketing_branches"} <= calls:
                missing.append((method, path, function.__name__, "branch scope"))
            attrs = {
                node.attr for node in ast.walk(tree)
                if isinstance(node, ast.Attribute)
            }
            if "can_edit_inputs" not in attrs:
                missing.append((method, path, function.__name__, "edit capability"))
        else:
            missing.append((method, path, function.__name__, "unreviewed blueprint"))
    assert missing == []
