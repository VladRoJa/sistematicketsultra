"""Conciliación de rutas Flask vs permission_route_map VIGENTE (P25).

Consulta de solo lectura, manual, nunca llamada por requests ni schedulers.
Una ruta sin fila en catálogo NO significa pública o sin guard.
No autoriza, no modifica catálogo ni crea grants.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from typing import Any


HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
MUTATIONS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
CATEGORIES = (
    "exact", "handler_alias", "handler_mismatch",
    "catalog_inactive", "not_cataloged",
)
REVIEW_FAMILIES = (
    "purchase-requisitions", "marketing", "contact-center",
    "system-daily-checks", "tickets", "inventario", "pm",
    "internal-documents",
)


def flask_registry(app) -> list[dict[str, Any]]:
    """Censa métodos HTTP existentes sin ejecutar ningún handler."""
    found = []
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api/"):
            continue
        endpoint = rule.endpoint.rsplit(".", 1)[-1]
        function_name = app.view_functions[rule.endpoint].__name__
        for method in sorted(set(rule.methods) & HTTP_METHODS):
            found.append({
                "method": method,
                "route": rule.rule,
                "endpoint": endpoint,
                "function_name": function_name,
                "family": rule.rule.split("/")[2],
            })
    return sorted(found, key=lambda row: (
        row["route"], row["method"], row["endpoint"],
    ))


def _catalog_row(row: dict[str, Any]) -> dict[str, Any]:
    # No conservar datos personales en el reporte: son metadatos de rutas.
    return {
        "method": str(row["method"]).upper(),
        "route": str(row["route"]),
        "endpoint_function": str(row["endpoint_function"]),
        "is_active": bool(row["is_active"]),
        "current_guard": row.get("current_guard"),
        "current_scope": row.get("current_scope"),
        "review_status": row.get("review_status"),
        "action_id": row.get("action_id"),
        "module_id": row.get("module_id"),
    }


def compare_route_maps(
    flask_rows: list[dict[str, Any]],
    current_catalog_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compara identidades por método+ruta+endpoint con alias explícitos.

    No usa grants ni interpreta current_guard como un guard ejecutado.
    """
    catalog = [_catalog_row(row) for row in current_catalog_rows]
    by_pair = defaultdict(list)
    for row in catalog:
        by_pair[(row["method"], row["route"])].append(row)

    observed_pairs = set()
    report_rows = []
    seen = set()
    for route in flask_rows:
        identity = (route["method"], route["route"], route["endpoint"])
        if identity in seen:
            raise ValueError("Identidad duplicada en el registro Flask: " + repr(identity))
        seen.add(identity)
        pair = identity[:2]
        observed_pairs.add(pair)
        same_pair = by_pair.get(pair, [])
        active = [row for row in same_pair if row["is_active"]]
        exact = [row for row in active if row["endpoint_function"] == route["endpoint"]]
        alias = [
            row for row in active
            if row["endpoint_function"] == route["function_name"]
        ]
        if exact:
            kind, matched = "exact", exact
        elif alias:
            kind, matched = "handler_alias", alias
        elif active:
            kind, matched = "handler_mismatch", active
        elif same_pair:
            kind, matched = "catalog_inactive", same_pair
        else:
            kind, matched = "not_cataloged", []

        review = sorted({
            str(row.get("review_status") or "") for row in matched
        })
        report_rows.append({
            **route,
            "classification": kind,
            "catalog_action_ids": sorted({
                int(row["action_id"]) for row in matched
                if row.get("action_id") is not None
            }),
            "catalog_review_statuses": review,
            "catalog_guard_annotations": sorted({
                str(row["current_guard"]) for row in matched
                if row.get("current_guard")
            }),
            "guard_evaluated": False,
        })

    # Registros activos/inactivos sin método+ruta en Flask; no confundir
    # alias de endpoint con una ruta desaparecida.
    catalog_only = sorted(
        [
            {
                "method": row["method"],
                "route": row["route"],
                "endpoint_function": row["endpoint_function"],
                "is_active": row["is_active"],
                "review_status": row["review_status"],
            }
            for row in catalog
            if (row["method"], row["route"]) not in observed_pairs
        ],
        key=lambda row: (
            row["route"], row["method"], row["endpoint_function"],
        ),
    )
    by_kind = Counter(row["classification"] for row in report_rows)
    by_method = Counter(row["method"] for row in report_rows)
    by_family = defaultdict(lambda: {
        "total": 0, "exact": 0, "handler_alias": 0,
        "handler_mismatch": 0, "catalog_inactive": 0,
        "not_cataloged": 0, "mutation_unreviewed": 0,
    })
    for row in report_rows:
        counts = by_family[row["family"]]
        counts["total"] += 1
        counts[row["classification"]] += 1
        if row["method"] in MUTATIONS and row["classification"] not in {"exact", "handler_alias"}:
            counts["mutation_unreviewed"] += 1

    unreviewed_mutations = [
        row for row in report_rows
        if row["method"] in MUTATIONS
        and row["classification"] not in {"exact", "handler_alias"}
    ]
    family_rank = {family: n for n, family in enumerate(REVIEW_FAMILIES)}
    unreviewed_mutations.sort(key=lambda row: (
        family_rank.get(row["family"], len(family_rank)),
        row["family"], row["route"], row["method"],
    ))

    active_catalog = [row for row in catalog if row["is_active"]]
    return {
        "basis": "Flask url_map vs permission_route_map ACTUAL en PostgreSQL",
        "interpretation": (
            "Diferencias son inventario de cobertura, NO vulnerabilidades "
            "ni evidencia de accesos sin autenticacion."
        ),
        "read_only": True,
        "guards_executed": False,
        "endpoints_called": False,
        "catalog_rows_all": len(catalog),
        "catalog_rows_active": len(active_catalog),
        "flask_method_handlers": len(report_rows),
        "by_method": dict(sorted(by_method.items())),
        "by_classification": {
            k: by_kind[k] for k in CATEGORIES
        },
        "by_family": dict(sorted(by_family.items())),
        "unreviewed_mutations": unreviewed_mutations,
        "catalog_only_method_routes": catalog_only,
        "route_rows": report_rows,
    }


def read_current_route_map(engine) -> list[dict[str, Any]]:
    """PostgreSQL con transacción explícitamente READ ONLY. Sin sesión ORM."""
    from sqlalchemy import select
    from app.models.permissions import PermissionRouteMapORM

    if engine.dialect.name != "postgresql":
        raise RuntimeError(
            "La lectura del catálogo vigente requiere PostgreSQL "
            "para forzar una transacción READ ONLY."
        )

    cols = (
        PermissionRouteMapORM.method,
        PermissionRouteMapORM.route,
        PermissionRouteMapORM.endpoint_function,
        PermissionRouteMapORM.is_active,
        PermissionRouteMapORM.current_guard,
        PermissionRouteMapORM.current_scope,
        PermissionRouteMapORM.review_status,
        PermissionRouteMapORM.action_id,
        PermissionRouteMapORM.module_id,
    )
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            # La primera instrucción en esta transacción impide escrituras
            # incluso si el proceso reutilizase credenciales privilegiadas.
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            result = connection.execute(select(*cols)).mappings().all()
            return [dict(item) for item in result]
        finally:
            transaction.rollback()


def main() -> None:
    """Usar SOLO por invocación manual: python -m app.utils.permission_route_inventory."""
    from app import create_app
    from app.extensions import db

    app = create_app()
    with app.app_context():
        rows = read_current_route_map(db.engine)
        report = compare_route_maps(flask_registry(app), rows)
    report["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
