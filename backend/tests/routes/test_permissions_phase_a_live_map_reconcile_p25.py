"""P25 — Contrato puro para comparar rutas actuales vs catalogo actual.

No conexión a producción, no HTTP, ninguna mutación. Los ejemplos de ruta
son inventados y las filas son fixtures, no grants ni decisiones de acceso.
"""
from types import SimpleNamespace

import pytest
from flask import Flask

from app.utils.permission_route_inventory import (
    compare_route_maps, flask_registry, read_current_route_map,
)


def _flask(method, route, endpoint="route_handler", function_name=None):
    return {
        "method": method,
        "route": route,
        "endpoint": endpoint,
        "function_name": function_name or endpoint,
        "family": route.split("/")[2],
    }


def _catalog(method, route, endpoint, active=True, action_id=9, guard="legacy_guard"):
    return {
        "method": method, "route": route,
        "endpoint_function": endpoint, "is_active": active,
        "action_id": action_id, "module_id": 2,
        "current_guard": guard, "current_scope": "branch",
        "review_status": "ok_hardened",
    }


def test_p25_classifies_exact_alias_handler_drift_inactive_and_unmapped():
    flask = [
        _flask("GET", "/api/demo/exact", "same"),
        _flask("PUT", "/api/demo/alias", "registered_alias", "actual_handler"),
        _flask("POST", "/api/demo/drift", "new_handler"),
        _flask("DELETE", "/api/demo/inactive", "retired"),
        _flask("POST", "/api/demo/unknown", "new_action"),
    ]
    db = [
        _catalog("GET", "/api/demo/exact", "same"),
        _catalog("PUT", "/api/demo/alias", "actual_handler"),
        _catalog("POST", "/api/demo/drift", "old_handler"),
        _catalog("DELETE", "/api/demo/inactive", "retired", active=False),
        _catalog("GET", "/api/demo/stale", "old_endpoint"),
    ]
    report = compare_route_maps(flask, db)
    assert report["by_classification"] == {
        "exact": 1, "handler_alias": 1, "handler_mismatch": 1,
        "catalog_inactive": 1, "not_cataloged": 1,
    }
    assert report["catalog_rows_active"] == 4
    assert report["catalog_rows_all"] == 5
    assert report["flask_method_handlers"] == 5
    assert [row["route"] for row in report["catalog_only_method_routes"]] == [
        "/api/demo/stale"
    ]
    assert [x["classification"] for x in report["unreviewed_mutations"]] == [
        "handler_mismatch", "catalog_inactive", "not_cataloged"
    ]
    assert all(x["guard_evaluated"] is False for x in report["route_rows"])
    assert report["by_family"]["demo"]["total"] == 5




def test_p25_admin_handler_alias_does_not_inflate_family_mutations():
    # El alias del endpoint de sucursales existe en Suite Ultra; NO es
    # una mutacion fuera del catalogo y no debe sumar en la familia admin.
    route = "/api/admin/usuarios/<int:user_id>/sucursales"
    flask = [
        _flask(
            "PUT", route,
            "admin_put_sucursales_usuario",
            "put_sucursales_usuario_admin",
        ),
        _flask("POST", "/api/marketing/submit", "send_campaign"),
    ]
    catalog = [
        _catalog("PUT", route, "put_sucursales_usuario_admin"),
    ]
    report = compare_route_maps(flask, catalog)

    assert report["by_classification"]["handler_alias"] == 1
    assert report["by_family"]["admin"]["handler_alias"] == 1
    assert report["by_family"]["admin"]["mutation_unreviewed"] == 0
    assert report["by_family"]["marketing"]["mutation_unreviewed"] == 1
    assert len(report["unreviewed_mutations"]) == 1
    assert (
        sum(stats["mutation_unreviewed"] for stats in report["by_family"].values())
        == len(report["unreviewed_mutations"])
    )

def test_p25_no_inferred_bypass_or_risk_from_missing_catalog_mapping():
    report = compare_route_maps(
        [_flask("POST", "/api/demo/unknown")],
        [],
    )
    assert report["by_classification"]["not_cataloged"] == 1
    assert report["guards_executed"] is False
    assert report["endpoints_called"] is False
    assert "NO vulnerabilidades" in report["interpretation"]
    assert report["unreviewed_mutations"][0]["catalog_guard_annotations"] == []


def test_p25_inactive_catalog_row_is_not_active_coverage():
    flask = [_flask("DELETE", "/api/demo/delete", "handler")]
    db = [_catalog("DELETE", "/api/demo/delete", "handler", active=False)]
    report = compare_route_maps(flask, db)
    assert report["by_classification"]["catalog_inactive"] == 1
    assert report["by_classification"]["exact"] == 0


def test_p25_handler_mismatch_does_not_mask_stale_function_as_exact():
    flask = [_flask("POST", "/api/demo/create", "handler_new")]
    db = [_catalog("POST", "/api/demo/create", "handler_old")]
    row = compare_route_maps(flask, db)["route_rows"][0]
    assert row["classification"] == "handler_mismatch"
    assert row["catalog_guard_annotations"] == ["legacy_guard"]


def test_p25_duplicate_runtime_identity_fails_closed():
    row = _flask("GET", "/api/demo/duplicate")
    with pytest.raises(ValueError, match="duplicada"):
        compare_route_maps([row, row], [])


def test_p25_flask_registry_only_reads_url_map_and_function_names():
    app = Flask(__name__)

    @app.get("/api/demo/example")
    def example():
        raise AssertionError("The endpoint must NEVER run during inventory")

    @app.post("/outside/api")
    def unrelated():
        raise AssertionError("not called either")

    rows = flask_registry(app)
    assert rows == [_flask("GET", "/api/demo/example", "example")]


def test_p25_requires_postgres_for_explicit_read_only_transaction():
    bad = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        read_current_route_map(bad)


def test_p25_postgres_transaction_is_read_only_and_rolled_back():
    actions = []

    class Result:
        def mappings(self):
            return self

        def all(self):
            return [{
                "method": "GET", "route": "/api/demo/a",
                "endpoint_function": "view_a", "is_active": True,
                "current_guard": "jwt_required", "current_scope": "role",
                "review_status": "pending", "action_id": None, "module_id": None,
            }]

    class Tx:
        def rollback(self):
            actions.append("rollback")

    class Conn:
        def __enter__(self):
            actions.append("connect")
            return self

        def __exit__(self, *args):
            actions.append("disconnect")

        def begin(self):
            actions.append("begin")
            return Tx()

        def exec_driver_sql(self, sql):
            actions.append(sql)
            assert sql == "SET TRANSACTION READ ONLY"

        def execute(self, statement):
            sql = str(statement).upper()
            actions.append("select")
            assert sql.startswith("SELECT ")
            return Result()

    class Engine:
        dialect = SimpleNamespace(name="postgresql")

        def connect(self):
            return Conn()

    result = read_current_route_map(Engine())
    assert len(result) == 1
    assert result[0]["endpoint_function"] == "view_a"
    assert actions == [
        "connect", "begin", "SET TRANSACTION READ ONLY",
        "select", "rollback", "disconnect",
    ]


def test_p25_db_failure_rolls_back_read_only_transaction():
    actions = []

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def begin(self):
            return SimpleNamespace(rollback=lambda: actions.append("rollback"))

        def exec_driver_sql(self, sql):
            assert sql == "SET TRANSACTION READ ONLY"
            raise RuntimeError("fixture connection error")

    engine = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql"),
        connect=lambda: Conn(),
    )
    with pytest.raises(RuntimeError, match="fixture connection error"):
        read_current_route_map(engine)
    assert actions == ["rollback"]
