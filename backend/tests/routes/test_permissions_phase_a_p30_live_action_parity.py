"""P30: immutable 112-route reconciliation and sanitized live-catalog reader.

The 2026-10-26 prod aggregate is an evidence snapshot, not a permanent
required state. Tests never consult production Postgres, users or grants.
"""
import csv
from datetime import datetime, timedelta, timezone
import inspect
import json
from pathlib import Path

import pytest

from app.services import ticket_maintenance_coordination_service as coordination
from app.utils import tickets_maintenance_permissions as maintenance_permissions
from app.utils.permission_live_action_snapshot import summarize_live_actions

ROOT = Path(__file__).resolve().parents[3]
P29 = ROOT / "docs/security/permissions_phase_a_p29_action_reconciliation_20261026.csv"
P30 = ROOT / "docs/security/permissions_phase_a_p30_live_action_reconciliation_20261026.csv"
PROPOSED = {
    "coordinate_maintenance_ticket": "tickets.maintenance.coordinate",
    "reassign_maintenance_ticket": "tickets.maintenance.coordinate",
    "maintenance_return_work_to_technician": "tickets.update_status",
    "maintenance_mark_work_completed": "tickets.update_status",
    "cambiar_recepcion_aparato": "tickets.update",
    "cambiar_recepciones_lote_tapizado": "tickets.update",
    "corregir_codigo_interno": "inventory.master_write",
    "anular_movimiento": "inventory.movement_write",
    "mark_opening_opened": "openings.manage",
    "update_user_module_access": "users.manage",
}
MAP_COUNTS_AT_CUT = {
    "tickets.maintenance.coordinate": 0,
    "tickets.update_status": 1,
    "tickets.update": 2,
    "inventory.master_write": 4,
    "inventory.movement_write": 2,
    "openings.manage": 11,
    "users.manage": 6,
}


def _read(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_p30_source_preserved_and_ten_candidates_reconciled():
    p29, p30 = _read(P29), _read(P30)
    keys = ("family", "method", "route", "handler", "review_group", "risk_triage")
    assert len(p29) == len(p30) == 112
    assert [{k: row[k] for k in keys} for row in p30] == [
        {k: row[k] for k in keys} for row in p29
    ]
    decisions = {}
    for earlier, row in zip(p29, p30):
        assert row["p29_seed_candidate"] == earlier["historical_seed_action_candidate"]
        assert row["catalog_status_at_cut"] == "not_cataloged"
        candidate = row["p30_live_candidate"]
        if candidate:
            decisions[row["handler"]] = candidate
            assert row["live_candidate_status"] == "action_active_module_active_assignable"
            assert row["live_action_existing_route_mappings"] == str(MAP_COUNTS_AT_CUT[candidate])
        else:
            assert row["p30_evidence_class"] == "functional_action_design_pending"
            assert row["live_candidate_status"] == "not_assessed_no_candidate"
            assert row["live_action_existing_route_mappings"] == ""
    assert decisions == PROPOSED

    groups = {name: sum(
        row["p30_evidence_class"] == name for row in p30
    ) for name in {
        "service_guard_semantics_verified",
        "catalog_active_but_effective_parity_unverified",
        "functional_action_design_pending",
    }}
    assert groups == {
        "service_guard_semantics_verified": 2,
        "catalog_active_but_effective_parity_unverified": 8,
        "functional_action_design_pending": 102,
    }


def test_p30_specialized_action_is_real_effective_service_guard():
    assert maintenance_permissions.COORDINATE_ACTION == "tickets.maintenance.coordinate"
    assert maintenance_permissions.ASSIGNED_ONLY_ACTION == (
        "tickets.maintenance.read_assigned_only"
    )
    source = inspect.getsource(maintenance_permissions.has_maintenance_coordination_permission)
    assert "_has_active_user_grant(user, COORDINATE_ACTION)" in source
    assert "is_regional_maintenance_lead(user)" in source
    assert "can_pm_view(user)" in source

    for function in (
        coordination.prepare_maintenance_coordination,
        coordination.prepare_maintenance_reassignment,
    ):
        implementation = inspect.getsource(function)
        assert "has_maintenance_coordination_permission(user)" in implementation
        assert "_can_coordinate_branch(user, _ticket_branch_id(ticket))" in implementation
        assert "COORDINATABLE_STATES" in implementation


def test_p30_snapshot_only_aggregates_without_principal_ids_or_reasons():
    now = datetime.now(timezone.utc)
    report = summarize_live_actions(
        module_rows=[{
            "id": 23, "key": "tickets", "is_active": True, "is_assignable": True,
        }],
        action_rows=[{
            "id": 99, "module_id": 23, "full_key": "tickets.maintenance.coordinate",
            "is_active": True,
        }],
        route_rows=[{
            "method": "PUT", "route": "/api/tickets/maintenance/<int:ticket_id>/coordinate",
            "endpoint_function": "coordinate_maintenance_ticket",
            "is_active": False, "action_id": 99,
        }],
        grant_rows=[
            {
                "action_id": 99, "effect": "allow", "principal_type": "user",
                "scope_type": "global", "is_active": True, "deleted_at": None,
                "starts_at": now - timedelta(days=2),
                "expires_at": now + timedelta(days=2),
                "principal_user_id": 224, "reason": "private test-only note",
            },
            {
                "action_id": 99, "effect": "allow", "principal_type": "user",
                "scope_type": "global", "is_active": True, "deleted_at": None,
                "starts_at": None, "expires_at": now - timedelta(days=1),
            },
        ],
        comparison={
            "by_classification": {"not_cataloged": 1},
            "unreviewed_mutations": [{"method": "PUT"}],
            "route_rows": [{
                "method": "PUT", "classification": "not_cataloged",
            }],
        },
    )
    text = json.dumps(report, ensure_ascii=False)
    assert "224" not in text
    assert "private test-only note" not in text
    assert "principal_user_id" not in text
    assert "\"read_only\": true" in text
    assert report["action_summary"][0]["mapped_active_routes"] == 0
    assert report["action_summary"][0]["grants_active_flag_rows"] == 2
    assert report["action_summary"][0]["grants_current_window_rows"] == 1
    assert report["grants_grouped"][0]["count"] == 2
    assert report["actual_permission_enforcement_evaluated"] is False


def test_p30_rejects_unsafe_timestamp_silently_instead_of_guessing():
    with pytest.raises(ValueError, match="naive starts_at"):
        summarize_live_actions(
            module_rows=[], action_rows=[], route_rows=[],
            grant_rows=[{
                "action_id": None, "effect": "allow", "principal_type": "user",
                "scope_type": "global", "is_active": True, "deleted_at": None,
                "starts_at": datetime(2026, 10, 26), "expires_at": None,
            }],
            comparison={
                "by_classification": {},
                "unreviewed_mutations": [], "route_rows": [],
            },
        )
