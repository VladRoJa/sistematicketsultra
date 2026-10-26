"""P30 permissions catalogue snapshot: privacy-preserving, PostgreSQL READ ONLY.

Manual invocation only: python -m app.utils.permission_live_action_snapshot
No HTTP handler, scheduler, grant mutation, personal principal identifiers or
grant reasons are read or emitted. Does not evaluate effective authorization.
"""

from collections import Counter
from datetime import datetime, timezone
import json

from sqlalchemy import select

from app.utils.permission_route_inventory import (
    compare_route_maps, flask_registry,
)


def summarize_live_actions(*, module_rows, action_rows, route_rows, grant_rows, comparison):
    """Pure renderer with aggregate grants only, never users or grant reasons."""
    modules = {row["id"]: row for row in module_rows}
    map_counter = Counter(
        row["action_id"] for row in route_rows
        if row["is_active"] and row["action_id"] is not None
    )
    now = datetime.now(timezone.utc)
    grant_active_flag = Counter()
    grant_current_window = Counter()
    grant_groups = Counter()

    for row in grant_rows:
        group = (
            row["effect"], row["principal_type"], row["scope_type"],
            bool(row["is_active"]),
        )
        grant_groups[group] += 1
        if not row["is_active"] or row["deleted_at"] is not None:
            continue

        # 'active_flag' is NOT authorization: service-level hard stops,
        # role, branch, principal and object policies remain authoritative.
        grant_active_flag[row["action_id"]] += 1
        starts_at = row["starts_at"]
        expires_at = row["expires_at"]
        if starts_at is not None and starts_at.tzinfo is None:
            raise ValueError("PostgreSQL returned a naive starts_at timestamp")
        if expires_at is not None and expires_at.tzinfo is None:
            raise ValueError("PostgreSQL returned a naive expires_at timestamp")
        if (starts_at is None or starts_at <= now) and (
            expires_at is None or expires_at > now
        ):
            grant_current_window[row["action_id"]] += 1

    actions = []
    for action in sorted(action_rows, key=lambda x: x["full_key"]):
        module = modules.get(action["module_id"], {})
        actions.append({
            "full_key": action["full_key"],
            "module_key": module.get("key"),
            "action_active": bool(action["is_active"]),
            "module_active": bool(module.get("is_active", False)),
            "module_assignable": bool(module.get("is_assignable", False)),
            "mapped_active_routes": map_counter[action["id"]],
            "grants_active_flag_rows": grant_active_flag[action["id"]],
            "grants_current_window_rows": grant_current_window[action["id"]],
        })

    return {
        "read_only": True,
        "principal_identifiers_exported": False,
        "actual_permission_enforcement_evaluated": False,
        "generated_at_utc": now.isoformat(),
        "module_count": len(module_rows),
        "action_count": len(action_rows),
        "active_route_map_rows": sum(row["is_active"] for row in route_rows),
        "flask_route_classification": comparison["by_classification"],
        "uncataloged_mutations": len(comparison["unreviewed_mutations"]),
        "uncataloged_get": sum(
            row["method"] == "GET" and row["classification"] == "not_cataloged"
            for row in comparison["route_rows"]
        ),
        "action_summary": actions,
        "grants_grouped": [
            {
                "effect": effect, "principal_type": kind,
                "scope_type": scope, "is_active": active, "count": count,
            }
            for (effect, kind, scope, active), count in sorted(grant_groups.items())
        ],
    }


def read_live_snapshot(app, engine):
    from app.models.permissions import (
        PermissionActionORM as A,
        PermissionGrantORM as G,
        PermissionModuleORM as M,
        PermissionRouteMapORM as R,
    )
    if engine.dialect.name != "postgresql":
        raise RuntimeError("P30 requiere PostgreSQL para SET TRANSACTION READ ONLY")
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            modules = [dict(x) for x in connection.execute(select(
                M.id, M.key, M.is_active, M.is_assignable,
            )).mappings()]
            actions = [dict(x) for x in connection.execute(select(
                A.id, A.module_id, A.full_key, A.is_active,
            )).mappings()]
            routes = [dict(x) for x in connection.execute(select(
                R.method, R.route, R.endpoint_function, R.is_active,
                R.action_id, R.module_id, R.current_guard, R.current_scope,
                R.review_status,
            )).mappings()]
            grants = [dict(x) for x in connection.execute(select(
                G.action_id, G.effect, G.principal_type, G.scope_type,
                G.is_active, G.deleted_at, G.starts_at, G.expires_at,
            )).mappings()]
        finally:
            transaction.rollback()

    return summarize_live_actions(
        module_rows=modules, action_rows=actions, route_rows=routes,
        grant_rows=grants,
        comparison=compare_route_maps(flask_registry(app), routes),
    )


def main():
    from app import create_app
    from app.extensions import db

    app = create_app()
    with app.app_context():
        result = read_live_snapshot(app, db.engine)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
