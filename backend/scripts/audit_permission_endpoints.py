"""Inventario READ-ONLY de endpoints Flask para la matriz existente.

Compara las rutas realmente registradas por create_app con el seed de rutas
high-risk. Un match NO certifica que un checkbox conceda/revoque acceso:
el guard sigue siendo la fuente de autorización hasta su integración probada.
No toca BD, grants, permisos ni ejecuta peticiones HTTP.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import inspect
import json
from collections import Counter
from pathlib import Path

from app import create_app


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SEED = BACKEND_ROOT / "migrations" / "versions" / (
    "7b8c9d0e1f2a_seed_permission_route_map_high_risk.py"
)
METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def load_initial_high_risk_map() -> list[dict]:
    """Carga las entradas declarativas del seed sin ejecutar upgrade()."""
    spec = importlib.util.spec_from_file_location("permissions_high_risk_seed", SEED)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"No se puede leer {SEED}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return list(module.ROUTE_MAP_ROWS)


def registered_routes(app) -> list[dict]:
    rows = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static" or not rule.rule.startswith("/api/"):
            continue
        view = app.view_functions[rule.endpoint]
        original = inspect.unwrap(view)
        source = inspect.getsourcefile(original) or inspect.getsourcefile(view) or ""
        try:
            source = str(Path(source).resolve().relative_to(BACKEND_ROOT.parent))
        except (ValueError, OSError):
            source = str(source)
        for method in sorted(set(rule.methods) & METHODS):
            rows.append({
                "method": method,
                "route": rule.rule,
                "endpoint_function": original.__name__,
                "blueprint": rule.endpoint.split(".")[0] if "." in rule.endpoint else "",
                "source_file": source,
                "flask_endpoint": rule.endpoint,
            })
    return sorted(rows, key=lambda row: (row["route"], row["method"], row["flask_endpoint"]))


def classify(rows: list[dict], seed: list[dict]) -> list[dict]:
    by_route_method = {}
    by_exact = {}
    for item in seed:
        key = (item["method"].upper(), item["route"])
        by_route_method.setdefault(key, []).append(item)
        by_exact[(key, item["endpoint_function"])] = item

    output = []
    for row in rows:
        key = (row["method"], row["route"])
        matched = by_exact.get((key, row["endpoint_function"]))
        candidates = by_route_method.get(key, [])
        if matched is not None:
            coverage = "seed_exact_match_not_enforcement"
        elif candidates:
            # Route exists, but endpoint was renamed or declaration is out of date.
            coverage = "seed_route_method_function_mismatch"
        else:
            coverage = "not_in_initial_high_risk_map"
        output.append({
            **row,
            "coverage": coverage,
            "catalog_action": matched.get("action_full_key", "") if matched else "",
            "documented_guard": matched.get("current_guard", "") if matched else "",
            "review_status": matched.get("review_status", "") if matched else "",
            "enforcement_certified": False,
        })
    return output


def generate_report(output_dir: Path | None = None) -> dict:
    # El inventario no requiere una conexión a PostgreSQL ni schema migrado.
    app = create_app()
    live = registered_routes(app)
    seed = load_initial_high_risk_map()
    rows = classify(live, seed)
    coverage = Counter(row["coverage"] for row in rows)
    modules = Counter(row["blueprint"] for row in rows)
    report = {
        "mode": "read_only_route_inventory",
        "runtime_route_method_count": len(rows),
        "initial_high_risk_seed_entries": len(seed),
        "classification": dict(sorted(coverage.items())),
        "blueprints": dict(sorted(modules.items())),
        "warning": (
            "Los mappings son parciales; rutas no mapeadas requieren análisis "
            "de guard. Mapeado != permiso HTTP certificado. "
            "No habilitar checks editables a partir de este inventario."
        ),
    }
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        with (output_dir / "permissions_endpoint_inventory.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            fields = [
                "method", "route", "flask_endpoint", "endpoint_function",
                "blueprint", "source_file", "coverage", "catalog_action",
                "documented_guard", "review_status", "enforcement_certified",
            ]
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        (output_dir / "permissions_endpoint_summary.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(generate_report(args.output_dir), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
