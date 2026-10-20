"""Fail-closed preflight after a Warehouse provenance audit; synthetic only."""
from datetime import date, timedelta
from dataclasses import replace

import pytest

from app.warehouse.services import kpi_desempeno_m3b_provenance_audit as audit
from app.warehouse.services import kpi_desempeno_m3b_verified_plan as bridge
from app.warehouse.services.kpi_desempeno_m3b_continuity_plan import (
    BLOCKED, READY_FOR_PROCESSING,
)
from app.warehouse.services.kpi_desempeno_semantic_diff import (
    DIFFERENCES_DETECTED, KpiDesempenoSemanticDiffResult,
    KpiDesempenoBranchDifference, KpiDesempenoFieldChange,
)

DAY = date(2026, 8, 2)
DAY1 = DAY - timedelta(days=1)
DAY3 = DAY + timedelta(days=1)
BRANCH = "centro"
CANON = {DAY1: 11, DAY: 12, DAY3: 13}
PROPOSED = {DAY1: 11, DAY: 22, DAY3: 13}


def _diff(*, updated=19):
    return KpiDesempenoSemanticDiffResult(
        status=DIFFERENCES_DETECTED,
        business_date=DAY.isoformat(),
        previous_row_count=2,
        current_row_count=2,
        differences=(KpiDesempenoBranchDifference(
            branch_key=BRANCH, kind="CHANGED",
            previous_branch_name="Centro", current_branch_name="Centro",
            fields=(KpiDesempenoFieldChange(
                field="bajas", previous=25, current=updated, delta=updated - 25,
            ),),
        ),),
    )


def _source(day, snapid, *, canonical, bajas):
    return audit.VerifiedKpiSource(
        day=day, snapshot_id=snapid, upload_id=snapid + 100,
        file_hash_sha256="a" * 64, is_canonical=canonical,
        values={BRANCH: (100, bajas, 200), "norte": (90, 8, 150)},
    )


def _fake_verified_audit(monkeypatch, *, evidence=True, source_mismatch=False,
                         unauthorized=False):
    sources = {
        (DAY1, 11): _source(DAY1, 11, canonical=True, bajas=20),
        (DAY, 12): _source(DAY, 12, canonical=True, bajas=25),
        (DAY, 22): _source(
            DAY, 22, canonical=False, bajas=18 if source_mismatch else 19,
        ),
        (DAY3, 13): _source(DAY3, 13, canonical=True, bajas=22),
    }
    decline = audit.M3BSourceDecline(
        earlier_date=DAY1, later_date=DAY, branch_key=BRANCH,
        track_field="bajas_reales_mtd", earlier=20, later=19, delta=-1,
        earlier_snapshot_id=11, later_snapshot_id=22,
        earlier_upload_id=111, later_upload_id=122,
        earlier_sha256="a" * 64, later_sha256="b" * 64,
    )
    report = audit.M3BProvenanceReport(
        status="SOURCE_VERIFIED_WITH_MTD_REVISIONS" if evidence else "SOURCE_VERIFIED",
        days_verified=3, branches_per_day=2,
        declines=(decline,) if evidence else (),
        shared_declines=0, new_declines=1 if evidence else 0,
        removed_declines=0, publication_authorized=unauthorized,
    )
    state = {"audit_calls": 0, "load_calls": []}

    def audit_series(*, candidate_snapshot_ids, canonical_snapshot_ids, expected_branch_count):
        state["audit_calls"] += 1
        assert candidate_snapshot_ids == PROPOSED
        assert canonical_snapshot_ids == CANON
        assert expected_branch_count == 2
        return report

    def load(*, day, snapshot_id, expected_canonical, expected_count):
        state["load_calls"].append((day, snapshot_id))
        item = sources[(day, snapshot_id)]
        assert item.is_canonical is expected_canonical
        assert len(item.values) == expected_count
        return item

    monkeypatch.setattr(audit, "audit_kpi_desempeno_m3b_provenance", audit_series)
    monkeypatch.setattr(audit, "_load_verified_source", load)
    return state


def _plan():
    return bridge.plan_kpi_desempeno_verified_source_impact(
        business_date=DAY, diff=_diff(),
        candidate_snapshot_ids=PROPOSED, canonical_snapshot_ids=CANON,
        expected_branch_count=2,
    )


def test_verified_gasca_mtd_decrease_is_not_approval_block(monkeypatch):
    state = _fake_verified_audit(monkeypatch)
    plan = _plan()
    assert state["audit_calls"] == 1
    assert (DAY, 22) in state["load_calls"]
    assert plan.status == READY_FOR_PROCESSING
    assert plan.blocking_issues == ()
    assert [(x.code, x.delta, x.earlier_date, x.later_date)
            for x in plan.verified_source_revisions] == [
        ("MTD_VERIFIED_SOURCE_REVISION", -1, DAY1, DAY)
    ]
    assert [(x.previous, x.current) for x in plan.track_field_changes] == [
        (25, 19)
    ]


def test_unverified_decrease_remains_blocked_even_when_values_match(monkeypatch):
    _fake_verified_audit(monkeypatch, evidence=False)
    plan = _plan()
    assert plan.status == BLOCKED
    assert [x.code for x in plan.blocking_issues] == ["MTD_DECREASE"]
    assert plan.verified_source_revisions == ()


@pytest.mark.parametrize("wrong", ["diff", "file", "authorization"])
def test_no_forged_or_untrusted_override(monkeypatch, wrong):
    _fake_verified_audit(
        monkeypatch,
        source_mismatch=wrong == "file",
        unauthorized=wrong == "authorization",
    )
    kwargs = dict(
        business_date=DAY,
        diff=_diff(updated=18) if wrong == "diff" else _diff(),
        candidate_snapshot_ids=PROPOSED, canonical_snapshot_ids=CANON,
        expected_branch_count=2,
    )
    with pytest.raises(audit.M3BProvenanceError):
        bridge.plan_kpi_desempeno_verified_source_impact(**kwargs)



def _two_day_audit():
    return audit.M3BProvenanceReport(
        status="SOURCE_VERIFIED_WITH_MTD_REVISIONS",
        days_verified=2, branches_per_day=2,
        declines=(audit.M3BSourceDecline(
            earlier_date=DAY1, later_date=DAY, branch_key=BRANCH,
            track_field="bajas_reales_mtd", earlier=20, later=19,
            delta=-1, earlier_snapshot_id=11, later_snapshot_id=22,
            earlier_upload_id=111, later_upload_id=122,
            earlier_sha256="a"*64, later_sha256="b"*64,
        ),),
        shared_declines=0, new_declines=1, removed_declines=0,
    )


def test_last_day_of_verified_cutoff_does_not_require_tomorrow(monkeypatch):
    _fake_verified_audit(monkeypatch)
    monkeypatch.setattr(audit, "audit_kpi_desempeno_m3b_provenance",
                        lambda **kwargs: _two_day_audit())
    plan = bridge.plan_kpi_desempeno_verified_source_impact(
        business_date=DAY, diff=_diff(),
        candidate_snapshot_ids={DAY1: 11, DAY: 22},
        canonical_snapshot_ids={DAY1: 11, DAY: 12},
        expected_branch_count=2,
    )
    assert plan.status == READY_FOR_PROCESSING
    assert plan.blocking_issues == ()
    assert len(plan.verified_source_revisions) == 1
    assert plan.continuity_days == (DAY1, DAY)
    assert [x.business_date for x in plan.derived_delta_impacts] == [DAY]


def test_missing_previous_day_still_blocks_even_if_mock_audit_lies(monkeypatch):
    _fake_verified_audit(monkeypatch)
    monkeypatch.setattr(audit, "audit_kpi_desempeno_m3b_provenance",
                        lambda **kwargs: _two_day_audit())
    plan = bridge.plan_kpi_desempeno_verified_source_impact(
        business_date=DAY, diff=_diff(),
        candidate_snapshot_ids={DAY: 22, DAY3: 13},
        canonical_snapshot_ids={DAY: 12, DAY3: 13},
        expected_branch_count=2,
    )
    assert plan.status == BLOCKED
    assert any(x.code == "MISSING_DAY" for x in plan.blocking_issues)


def test_failed_provenance_audit_propagates_without_a_plan(monkeypatch):
    monkeypatch.setattr(
        audit, "audit_kpi_desempeno_m3b_provenance",
        lambda **kwargs: (_ for _ in ()).throw(
            audit.M3BProvenanceError("Warehouse SHA mismatch")
        ),
    )
    with pytest.raises(audit.M3BProvenanceError, match="SHA mismatch"):
        _plan()
