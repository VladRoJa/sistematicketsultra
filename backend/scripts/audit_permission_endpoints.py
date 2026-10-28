"""Exportador CI de cobertura de permisos. Reutiliza permission_route_inventory.

Solo inspección: nunca ejecuta handlers, accede a PostgreSQL ni muta grants.
Un mapeo no certifica autorización HTTP. El catálogo productivo puede
contener más entradas que el seed inicial high-risk utilizado por CI.
"""
from __future__ import annotations

import argparse
import ast
import csv
import importlib.util
import inspect
import json
import textwrap
from collections import Counter
from pathlib import Path

from app import create_app
from app.utils.permission_route_inventory import compare_route_maps, flask_registry

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "migrations/versions/7b8c9d0e1f2a_seed_permission_route_map_high_risk.py"


def initial_catalog():
    spec = importlib.util.spec_from_file_location("permissions_high_risk_seed", SEED)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"No es posible cargar {SEED}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return [
        {
            "method": row["method"], "route": row["route"],
            "endpoint_function": row["endpoint_function"],
            "is_active": row["is_active"],
            "current_guard": row.get("current_guard"),
            "current_scope": row.get("current_scope"),
            "review_status": row.get("review_status"),
            "action_id": None,
            "module_id": None,
            "action_full_key": row.get("action_full_key"),
        }
        for row in module.ROUTE_MAP_ROWS
    ]


def static_guard_hints(func):
    """Heurística de fuente para auditoría; no ejecuta ni certifica guards."""
    original = inspect.unwrap(func)
    try:
        source = textwrap.dedent(inspect.getsource(original))
        tree = ast.parse(source)
    except (OSError, TypeError, SyntaxError):
        return False, "", ""
    outer = next(
        (item for item in tree.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))),
        None,
    )
    if outer is None:
        return False, "", ""
    has_jwt = any("jwt_required" in ast.unparse(d) for d in outer.decorator_list)
    hints = set()
    for node in ast.walk(outer):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        name = (
            callee.id if isinstance(callee, ast.Name)
            else callee.attr if isinstance(callee, ast.Attribute)
            else ""
        )
        if name.startswith((
            "require_", "_require_", "_validar_", "can_", "has_",
            "check_", "_check_", "assert_", "_get_current_user_admin",
        )):
            hints.add(name)
    source_file = inspect.getsourcefile(original) or ""
    try:
        source_file = str(Path(source_file).resolve().relative_to(ROOT.parent))
    except (ValueError, OSError):
        source_file = str(source_file)
    return has_jwt, ";".join(sorted(hints)), source_file


def generate_report(output_dir=None):
    app = create_app()
    current = flask_registry(app)
    seed = initial_catalog()
    comparison = compare_route_maps(current, seed)
    # Extiende el inventario existente con pistas de fuente sin cambiar
    # su clasificación ni usar el resultado como permiso efectivo.
    functions = {}
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api/"):
            continue
        functions[(rule.rule, rule.endpoint.rsplit(".", 1)[-1])] = (
            app.view_functions[rule.endpoint]
        )

    output = []
    for row in comparison["route_rows"]:
        func = functions.get((row["route"], row["endpoint"]))
        jwt, hints, source = static_guard_hints(func) if func else (False, "", "")
        output.append({
            "method": row["method"],
            "route": row["route"],
            "endpoint": row["endpoint"],
            "family": row["family"],
            "source_file": source,
            "classification": row["classification"],
            "seed_guard_annotation": ";".join(row["catalog_guard_annotations"]),
            "jwt_decorator_visible": jwt,
            "guard_call_hints": hints,
            "enforcement_certified": False,
        })

    report = {
        "mode": "read_only_route_inventory",
        "basis": "Flask url_map vs initial high-risk seed (not live DB catalog)",
        "flask_route_methods": comparison["flask_method_handlers"],
        "seed_total": comparison["catalog_rows_all"],
        "seed_active": comparison["catalog_rows_active"],
        "classification": comparison["by_classification"],
        "methods": comparison["by_method"],
        "uncataloged_mutations": len(comparison["unreviewed_mutations"]),
        "jwt_decorator_visible": sum(bool(x["jwt_decorator_visible"]) for x in output),
        "guard_call_hints": sum(bool(x["guard_call_hints"]) for x in output),
        "seed_only": comparison["catalog_only_method_routes"],
        "families": comparison["by_family"],
        "caution": "Mapeado NO significa guard evaluado; el escáner no activa permisos.",
    }
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        with (output_dir / "permissions_endpoint_inventory.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=list(output[0]) if output else [])
            writer.writeheader()
            writer.writerows(output)
        (output_dir / "permissions_endpoint_summary.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(generate_report(args.output_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
