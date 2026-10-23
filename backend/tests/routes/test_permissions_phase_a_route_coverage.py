"""Fase A P21: censo runtime Flask vs seed historico de permission_route_map.

Solo diagnostico: create_app().url_map NO emite requests ni consulta PostgreSQL;
runpy carga declaraciones de migraciones sin invocar upgrade/downgrade.
No tratar faltantes de mapa como rutas publicas, ni mapa como enforcement.
"""
import json
import runpy
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from app import create_app


_BACKEND_DIR = Path(__file__).resolve().parents[2]
_MIGRATIONS = _BACKEND_DIR / "migrations" / "versions"
_SEED_ACTIONS = "3d4f6a8b9c10_seed_global_permissions_catalog.py"
_SEED_ROUTES = "7b8c9d0e1f2a_seed_permission_route_map_high_risk.py"
_HTTP = {"GET", "POST", "PUT", "PATCH", "DELETE"}


@pytest.fixture(scope="module")
def coverage():
    app = create_app()
    flask_rows = []
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api/"):
            continue
        for method in sorted(set(rule.methods) & _HTTP):
            flask_rows.append({
                "method": method,
                "route": rule.rule,
                "endpoint": rule.endpoint.rsplit(".", 1)[-1],
                "blueprint": rule.endpoint.split(".", 1)[0]
                if "." in rule.endpoint else "",
            })
    actions = runpy.run_path(str(_MIGRATIONS / _SEED_ACTIONS))
    seed = runpy.run_path(str(_MIGRATIONS / _SEED_ROUTES))
    mapped_rows = [
        row for row in seed["ROUTE_MAP_ROWS"] if row.get("is_active", True)
    ]
    action_keys = {
        full_key for _, _, full_key, _, _, _ in actions["ACTIONS"]
    } | {item["full_key"] for item in seed["EXTRA_ACTIONS"]}
    module_keys = {key for key, _, _ in actions["MODULES"]}

    flask_full = {
        (row["method"], row["route"], row["endpoint"])
        for row in flask_rows
    }
    mapped_full = {
        (row["method"], row["route"], row["endpoint_function"])
        for row in mapped_rows
    }
    flask_pairs = {(row["method"], row["route"]) for row in flask_rows}
    mapped_pairs = {(row["method"], row["route"]) for row in mapped_rows}

    return {
        "flask": flask_rows,
        "mapped": mapped_rows,
        "action_keys": action_keys,
        "module_keys": module_keys,
        "matched": flask_full & mapped_full,
        "flask_only": flask_full - mapped_full,
        "seed_only": mapped_full - flask_full,
        "method_route_overlap": flask_pairs & mapped_pairs,
        "flask_pairs": flask_pairs,
        "mapped_pairs": mapped_pairs,
    }


def test_p21_report_route_coverage_without_touching_database(coverage):
    flask_rows = coverage["flask"]
    mapped_rows = coverage["mapped"]
    matched = coverage["matched"]
    unmatched = coverage["flask_only"]
    seed_only = coverage["seed_only"]

    family_stats = defaultdict(lambda: {
        "flask_methods": 0, "seed_matched": 0, "unmapped_flask_methods": 0
    })
    for row in flask_rows:
        family = row["route"].split("/")[2]
        family_stats[family]["flask_methods"] += 1
        key = (row["method"], row["route"], row["endpoint"])
        family_stats[family][
            "seed_matched" if key in matched else "unmapped_flask_methods"
        ] += 1

    sample_unmapped = sorted(unmatched)[:30]
    sample_seed_only = sorted(seed_only)[:30]
    summary = {
        "source": "main Flask app.url_map vs historical migration 7b8c9d0e1f2a",
        "not_production_db": True,
        "runtime_flask_method_handler_rows": len(coverage["flask"]),
        "historical_active_seed_rows": len(mapped_rows),
        "seed_exact_matches": len(matched),
        "flask_unmapped_by_historical_seed": len(unmatched),
        "historical_seed_not_matching_flask": len(seed_only),
        "method_route_pair_overlap": len(coverage["method_route_overlap"]),
        "family_stats": dict(sorted(family_stats.items())),
        "sample_unmapped": sample_unmapped,
        "sample_seed_only": sample_seed_only,
    }
    print("\\nFASE_A_P21_COVERAGE=" + json.dumps(summary, ensure_ascii=False, sort_keys=True))
    assert len(flask_rows) > len(mapped_rows)
    assert len(mapped_rows) > 0
    assert len(unmatched) > 0   # seed de alto riesgo no era inventario exhaustivo
    assert len(matched) > 0     # confirma que ambas fuentes son comparables


def test_p21_no_duplicate_historical_seed_identity(coverage):
    identities = [
        (row["method"], row["route"], row["endpoint_function"])
        for row in coverage["mapped"]
    ]
    counts = Counter(identities)
    assert not [key for key, count in counts.items() if count > 1]


def test_p21_historical_actions_and_modules_reference_seeded_keys(coverage):
    invalid_actions = sorted({
        row["action_full_key"] for row in coverage["mapped"]
        if row.get("action_full_key")
        and row["action_full_key"] not in coverage["action_keys"]
    })
    invalid_modules = sorted({
        row["module_key"] for row in coverage["mapped"]
        if row["module_key"] not in coverage["module_keys"]
    })
    print("P21_UNRECOGNIZED_ACTIONS_IN_HISTORICAL_SEED=", invalid_actions)
    print("P21_UNRECOGNIZED_MODULES_IN_HISTORICAL_SEED=", invalid_modules)
    assert invalid_actions == []
    assert invalid_modules == []


def test_p21_cross_module_mapping_must_be_identified_not_reinterpreted(coverage):
    cross = [
        (row["module_key"], row.get("action_full_key"), row["method"], row["route"])
        for row in coverage["mapped"]
        if row.get("action_full_key")
        and row["module_key"] != row["action_full_key"].split(".", 1)[0]
    ]
    print("P21_CROSS_MODULE_MAP=", json.dumps(cross, ensure_ascii=False))
    # Estos cruces reflejan un proceso transversal y NO una autorización
    # otorgada por el modulo agrupador.
    assert len(cross) == 3
    assert ("internal_documents", "openings.manage") in {
        (module, action) for module, action, _, _ in cross
    }
    assert sum(1 for module, action, _, _ in cross
               if module == "reports" and action == "users.manage") == 2


def test_p21_nube_known_gap_remains_read_only(coverage):
    prefix = "/api/internal-documents"
    flask_rows = [
        row for row in coverage["flask"] if
        row["route"] == prefix or row["route"].startswith(prefix + "/")
    ]
    mapped = coverage["matched"]
    assert len(flask_rows) == 21
    mutations = [
        row for row in flask_rows if row["method"] != "GET"
    ]
    reads = [row for row in flask_rows if row["method"] == "GET"]
    assert len(mutations) == 10
    assert len(reads) == 11
    assert all(
        (row["method"], row["route"], row["endpoint"]) in mapped
        for row in mutations
    )
    assert all(
        (row["method"], row["route"], row["endpoint"]) not in mapped
        for row in reads
    )
    # Faltante del mapa NO implica endpoint anonimo ni ausencia de JWT.


def test_p21_family_coverage_identifies_later_modules_without_mappings(coverage):
    families = {
        route.split("/")[2] for _, route, _ in coverage["flask_only"]
    }
    for family in (
        "marketing", "contact-center", "automation-control",
        "purchase-requisitions", "system-daily-checks",
    ):
        assert family in families
    # Registro diagnóstico: no crear acciones basadas en el nombre de ruta.


def test_p21_seed_only_or_handler_drift_is_not_labeled_security_bug(coverage):
    pairs_only_in_seed = (
        coverage["mapped_pairs"] - coverage["flask_pairs"]
    )
    handler_drift = sorted(
        item for item in coverage["seed_only"]
        if (item[0], item[1]) in coverage["flask_pairs"]
    )
    print("P21_SEED_ROUTE_ABSENT_COUNT=", len(pairs_only_in_seed))
    print("P21_MATCHED_PATH_HANDLER_DRIFT=", json.dumps(handler_drift, ensure_ascii=False))
    assert len(coverage["seed_only"]) >= len(pairs_only_in_seed)
    # Sin inspeccionar el guard vivo de cada ruta no etiquetamos bypass.
