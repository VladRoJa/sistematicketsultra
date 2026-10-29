"""Guard inventory: read-only prioritization, NEVER authorization certification."""
from scripts.audit_permission_endpoints import (
    action_coverage_from_seed,
    review_priority_routes,
)


def _route(method, route, classification, hints=""):
    return {
        "method": method,
        "route": route,
        "endpoint": "test_endpoint",
        "family": "tickets",
        "source_file": "app/routes/ticket_routes.py",
        "classification": classification,
        "seed_guard_annotation": "",
        "jwt_decorator_visible": True,
        "guard_call_hints": hints,
        "enforcement_certified": False,
    }


def test_action_coverage_never_certifies_from_route_mapping():
    seed = [{
        "method": "GET", "route": "/api/test",
        "action_full_key": "track.read", "is_active": True,
    }]
    actions = [
        ("track", "read", "track.read", "Consultar Track", "", "low"),
        ("pm", "validate", "pm.validate", "Validar PM", "", "high"),
    ]
    routes = [_route("GET", "/api/test", "exact", "_require_track_read_role")]
    coverage = action_coverage_from_seed(actions, seed, routes)
    assert len(coverage) == 2
    assert coverage[0]["seed_mapped_routes"] == 1
    assert coverage[0]["authorization_status"] == "NOT_CERTIFIED"
    assert coverage[0]["guard_hints"] == "_require_track_read_role"
    assert coverage[1]["seed_mapped_routes"] == 0
    assert coverage[1]["authorization_status"] == "NOT_CERTIFIED"


def test_mutating_routes_unmapped_are_prioritized_but_not_called_public():
    routes = [
        _route("GET", "/api/tickets/list", "not_cataloged"),
        _route("POST", "/api/tickets/create", "not_cataloged"),
        _route("GET", "/api/tickets/safe", "exact"),
    ]
    sorted_routes = review_priority_routes(routes)
    assert [row["review_priority"] for row in sorted_routes] == [
        "P0_UNMAPPED_MUTATION", "P1_UNMAPPED_READ", "P2_CATALOG_REVIEW",
    ]
    assert all(row["enforcement_certified"] is False for row in sorted_routes)


def test_inactive_seed_route_is_not_certified():
    actions = [("track", "read", "track.read", "Consultar Track", "", "low")]
    seed = [{
        "method": "GET", "route": "/api/track/legacy",
        "action_full_key": "track.read", "is_active": False,
    }]
    result = action_coverage_from_seed(actions, seed, [])
    assert result[0]["seed_mapped_routes"] == 0
    assert result[0]["authorization_status"] == "NOT_CERTIFIED"
