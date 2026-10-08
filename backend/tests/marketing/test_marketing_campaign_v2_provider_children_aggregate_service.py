from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services.marketing_campaign_v2_provider_children_aggregate_service import (
    build_campaign_v2_provider_children_aggregate as build,
)


BASE = datetime(2026, 10, 8, 18, tzinfo=timezone.utc)


def _child(identifier, *, status="SUBMITTED", count=3, campaign_id=7):
    return SimpleNamespace(
        id=identifier, campaign_v2_id=campaign_id, provider="IVENTAS",
        provider_campaign_id=f"external-{identifier}",
        status=status, sucursal_canon=f"BRANCH {identifier}", recipient_count=count,
    )


def _snapshot(identifier, child_id, *, raw=3, analytics_status="ok",
              timestamp=BASE, linked=True, campaign_id=7):
    return SimpleNamespace(
        id=identifier, campaign_v2_id=campaign_id,
        provider_campaign_child_id=child_id if linked else None,
        provider="IVENTAS", provider_campaign_id=f"external-{child_id}",
        fetched_at=timestamp, analytics_status=analytics_status,
        analytics_json={"cost": {"total": "15.25", "currency": "MXN"}},
        raw_successful=raw, raw_failed=0, raw_sent=0,
        raw_delivered=raw, raw_viewed=0, raw_answered=0,
        raw_interaction_groups=0, raw_interaction_items=0,
    )


def _obs(snapshot_id, recipient_id):
    return SimpleNamespace(snapshot_id=snapshot_id,
                           campaign_recipient_id=recipient_id)


def test_single_child_complete_stats_but_cost_unavailable_without_contract():
    report = build(
        campaign_id=7, children=[_child(1)],
        snapshots=[_snapshot(101, 1)],
        observations=[_obs(101, 10), _obs(101, 11)],
    )
    summary = report["summary"]
    assert summary["status"] == "SUBMITTED"
    assert summary["provider_raw_status"] == "complete"
    assert summary["provider_raw"]["successful"] == 3
    assert summary["recipient_exposures_accepted"] == 3
    assert summary["matched_frozen_recipients_unique"] == 2
    assert summary["cost"]["status"] == "unavailable"
    assert summary["cost"]["total"] is None


def test_two_children_latest_only_and_union_unique_recipient_count():
    report = build(
        campaign_id=7,
        children=[_child(2, count=2), _child(1, count=3)],
        snapshots=[
            _snapshot(100, 1, raw=1, timestamp=BASE - timedelta(minutes=2)),
            _snapshot(101, 1, raw=3),
            _snapshot(102, 2, raw=2),
        ],
        observations=[
            _obs(100, 99), _obs(101, 10), _obs(101, 11),
            _obs(102, 11), _obs(102, 12),
        ],
    )
    assert [child["id"] for child in report["children"]] == [1, 2]
    assert [child["snapshot_id"] for child in report["children"]] == [101, 102]
    assert report["summary"]["provider_raw"]["successful"] == 5
    assert report["summary"]["matched_frozen_recipients_unique"] == 3
    assert report["summary"]["recipient_exposures_accepted"] == 5
    assert report["summary"]["provider_raw_status"] == "complete"


def test_missing_and_not_synced_do_not_become_zero():
    report = build(
        campaign_id=7,
        children=[_child(1), _child(2), _child(3)],
        snapshots=[_snapshot(101, 1), _snapshot(102, 2, analytics_status="not_synced")],
    )
    assert report["summary"]["provider_raw"]["successful"] == 3
    assert report["summary"]["provider_raw_status"] == "partial"
    assert report["summary"]["batches_without_usable_stats"] == 2
    assert report["children"][1]["provider_raw"] is None
    assert report["children"][2]["provider_raw"] is None
    assert report["summary"]["cost"]["total"] is None


def test_no_snapshots_means_unavailable_not_zero():
    report = build(campaign_id=7, children=[_child(1)], snapshots=[])
    assert report["summary"]["provider_raw"] is None
    assert report["summary"]["provider_raw_status"] == "unavailable"
    assert report["children"][0]["snapshot_id"] is None


def test_reconciliation_and_partial_failure_do_not_erase_success():
    a = _child(1)
    b = _child(2, status="PROVIDER_ERROR")
    b.provider_campaign_id = None
    report = build(campaign_id=7, children=[a, b],
                   snapshots=[_snapshot(101, 1)])
    assert report["summary"]["status"] == "PARTIALLY_FAILED"
    assert report["summary"]["accepted_batches"] == 1
    assert report["summary"]["failed_batches"] == 1
    assert report["summary"]["recipient_exposures_accepted"] == 3

    b.status = "RECONCILIATION_REQUIRED"
    report = build(campaign_id=7, children=[a, b], snapshots=[])
    assert report["summary"]["status"] == "RECONCILIATION_REQUIRED"
    assert report["summary"]["reconciliation_required_batches"] == 1


def test_scheduled_is_accepted_not_sent():
    report = build(campaign_id=7, children=[_child(1, status="SCHEDULED")],
                   snapshots=[])
    assert report["summary"]["status"] == "SCHEDULED"
    assert report["summary"]["scheduled_batches"] == 1
    assert report["summary"]["provider_raw"] is None


def test_legacy_snapshot_without_fk_can_match_exact_external_identity():
    report = build(
        campaign_id=7, children=[_child(1)],
        snapshots=[_snapshot(101, 1, linked=False)],
    )
    assert report["children"][0]["snapshot_id"] == 101


def test_foreign_and_mismatched_snapshots_are_not_accepted():
    foreign_child = build(campaign_id=7, children=[_child(1)],
                          snapshots=[_snapshot(101, 2)])
    assert foreign_child["summary"]["provider_raw"] is None
    mismatched = _snapshot(102, 1)
    mismatched.provider_campaign_id = "external-elsewhere"
    with pytest.raises(ValueError, match="Identidad provider"):
        build(campaign_id=7, children=[_child(1)],
              snapshots=[mismatched])
    report = build(campaign_id=7, children=[_child(1)],
                   snapshots=[_snapshot(101, 1, campaign_id=8)])
    assert report["summary"]["provider_raw"] is None
    with pytest.raises(ValueError, match="fuera de la campaña"):
        build(campaign_id=7, children=[_child(1, campaign_id=8)], snapshots=[])


def test_cost_completeness_and_currency_safety_with_validated_projection():
    projection = lambda analytic: {
        "status": "available", "currency": analytic["cost"]["currency"],
        "total": analytic["cost"]["total"],
    }
    both = build(campaign_id=7, children=[_child(1), _child(2)],
                 snapshots=[_snapshot(101, 1), _snapshot(102, 2)],
                 cost_projector=projection)
    assert both["summary"]["cost"] == {
        "status": "complete", "currency": "MXN", "total": "30.50",
        "known_total": "30.50", "known_children": 2, "missing_children": 0,
    }
    partial = build(campaign_id=7, children=[_child(1), _child(2)],
                    snapshots=[_snapshot(101, 1)], cost_projector=projection)
    assert partial["summary"]["cost"]["status"] == "partial"
    assert partial["summary"]["cost"]["total"] is None
    assert partial["summary"]["cost"]["known_total"] == "15.25"
    assert partial["summary"]["cost"]["missing_children"] == 1

    another = _snapshot(102, 2)
    another.analytics_json = {"cost": {"currency": "USD", "total": "4.00"}}
    mixed = build(campaign_id=7, children=[_child(1), _child(2)],
                  snapshots=[_snapshot(101, 1), another],
                  cost_projector=projection)
    assert mixed["summary"]["cost"]["status"] == "unavailable"
    assert mixed["summary"]["cost"]["total"] is None
    assert mixed["summary"]["cost"]["currency"] is None
