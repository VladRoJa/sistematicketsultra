"""P28: regresión reproducible del corte P25, SIN consultar PostgreSQL.

El CSV es una fotografía entregada por un operador; no es catálogo oficial,
permiso vigente ni evidencia de rutas públicas. El test exige revisión expresa
si alguno de los 112 handlers cambia de método/ruta/nombre Python.
"""
from collections import Counter
import csv
from pathlib import Path

from app import create_app
from app.utils.permission_route_inventory import flask_registry

BASE = Path(__file__).resolve().parents[3]
SNAPSHOT = BASE / "docs/security/permissions_phase_a_p28_live_mutations_20261026.csv"
EXPECTED = {
    "auth": 3,
    "contact-center": 10,
    "integrations": 11,
    "inventario": 3,
    "maintenance-planner": 1,
    "mantenimiento-equipos": 1,
    "marketing": 42,
    "openings": 1,
    "permissions": 1,
    "purchase-requisitions": 19,
    "routine-control": 2,
    "rpa": 1,
    "system-daily-checks": 3,
    "tickets": 6,
    "track": 1,
    "track-alerts": 5,
    "warehouse": 2,
}
RETIRED_RRHH = {
    ("POST", "/api/tickets/rrhh/aprobar/<int:ticket_id>"),
    ("POST", "/api/tickets/rrhh/rechazar/<int:ticket_id>"),
    ("POST", "/api/tickets/rrhh/solicitar/<int:ticket_id>"),
}


def _rows():
    with SNAPSHOT.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def test_p28_live_catalog_snapshot_is_complete_and_not_an_authorization_grant():
    rows = _rows()
    assert len(rows) == 112
    assert Counter(row["family"] for row in rows) == EXPECTED
    assert all(row["method"] in {"POST", "PUT", "PATCH", "DELETE"} for row in rows)
    assert all(row["catalog_classification"] == "not_cataloged" for row in rows)
    assert all(row["risk_triage"] in {"critical", "high", "medium"} for row in rows)
    assert all(row["review_group"] and row["handler"] for row in rows)
    assert len({(row["method"], row["route"]) for row in rows}) == 112
    assert len({(row["method"], row["route"], row["handler"]) for row in rows}) == 112


def test_p28_all_112_snapshot_identifiers_still_exist_in_flask_without_executing_routes():
    app = create_app()
    current = flask_registry(app)
    by_method_route = {
        (route["method"], route["route"]): route for route in current
    }
    missing = []
    handler_drift = []
    for row in _rows():
        identity = (row["method"], row["route"])
        actual = by_method_route.get(identity)
        if actual is None:
            missing.append(identity)
        elif actual["function_name"] != row["handler"]:
            handler_drift.append((identity, row["handler"], actual["function_name"]))
    assert missing == []
    assert handler_drift == []
    assert not RETIRED_RRHH.intersection(by_method_route)
