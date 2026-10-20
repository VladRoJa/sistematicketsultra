"""Read-only KPI M3-C diagnostics; no updates, ingestion or Track rebuild."""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.models.warehouse import KpiDesempenoSnapshotORM, WarehouseUploadORM
from app.warehouse.services import kpi_desempeno_m3b_provenance_audit as provenance
from app.warehouse.services import kpi_desempeno_m3c_preflight_service as preflight


FIRST = date(2026, 8, 1)
SECOND = FIRST + timedelta(days=1)
CANON = {FIRST: 11, SECOND: 12}
HASH = {FIRST: "a" * 64, SECOND: "b" * 64}


def _fixture(monkeypatch, *, changed=False, wrong_canonical=False, audit_failure=False):
    selected = {FIRST: 11, SECOND: 22 if changed else 12}
    hashes = {FIRST: "a" * 64, SECOND: ("c" if changed else "b") * 64}
    canonical = CANON.copy()
    uploads = {
        101: SimpleNamespace(id=101, file_hash_sha256="a" * 64),
        102: SimpleNamespace(id=102, file_hash_sha256="b" * 64),
        202: SimpleNamespace(id=202, file_hash_sha256="c" * 64),
    }
    snapshots = {
        11: SimpleNamespace(id=11, business_date=FIRST, warehouse_upload_id=101),
        12: SimpleNamespace(id=12, business_date=SECOND, warehouse_upload_id=102),
        22: SimpleNamespace(id=22, business_date=SECOND, warehouse_upload_id=202),
    }
    state = {"audit_calls": 0, "db_reads": 0}

    def audit(*, candidate_snapshot_ids, canonical_snapshot_ids, expected_branch_count):
        state["audit_calls"] += 1
        assert candidate_snapshot_ids == selected
        assert canonical_snapshot_ids == canonical
        assert expected_branch_count == 2
        if audit_failure:
            raise provenance.M3BProvenanceError("source XLSX SHA mismatch")
        return provenance.M3BProvenanceReport(
            status="SOURCE_VERIFIED_WITH_MTD_REVISIONS" if changed else "SOURCE_VERIFIED",
            days_verified=2, branches_per_day=2, declines=(),
            shared_declines=0, new_declines=0, removed_declines=0,
        )

    def get(model, key):
        state["db_reads"] += 1
        return snapshots.get(key) if model is KpiDesempenoSnapshotORM else uploads.get(key)

    monkeypatch.setattr(provenance, "audit_kpi_desempeno_m3b_provenance", audit)
    monkeypatch.setattr(provenance, "_canonical_ids", lambda day: (
        99 if wrong_canonical and day == SECOND else canonical[day],
    ))
    monkeypatch.setattr(preflight.db.session, "get", get)

    return selected, canonical, hashes, state


def _run(selected, canonical, hashes):
    return preflight.preflight_kpi_desempeno_existing_batch(
        selected_snapshot_ids=selected,
        expected_canonical_snapshot_ids=canonical,
        expected_sha256_by_day=hashes,
        expected_branch_count=2,
    )


def test_exact_canonical_snapshots_and_hashes_are_no_op(monkeypatch):
    selected, canonical, hashes, state = _fixture(monkeypatch)
    result = _run(selected, canonical, hashes)
    assert result.status == preflight.ALREADY_CURRENT
    assert result.days_verified == 2
    assert result.changed_dates == ()
    assert [x.needs_update for x in result.days] == [False, False]
    assert [x.selected_upload_id for x in result.days] == [101, 102]
    assert result.external_origin_verified is False
    assert result.execution_allowed is False
    assert state["audit_calls"] == 1


def test_different_selected_snapshot_is_not_a_no_op(monkeypatch):
    selected, canonical, hashes, state = _fixture(monkeypatch, changed=True)
    result = _run(selected, canonical, hashes)
    assert result.status == preflight.CHANGES_DETECTED
    assert result.changed_dates == (SECOND,)
    assert [x.needs_update for x in result.days] == [False, True]
    assert result.days[-1].verified_sha256 == "c" * 64
    assert result.execution_allowed is False


def test_untrusted_or_stale_expected_sha_fails_closed(monkeypatch):
    selected, canonical, hashes, _ = _fixture(monkeypatch)
    hashes[SECOND] = "f" * 64
    with pytest.raises(preflight.M3CPreflightError, match="expected Gasca SHA"):
        _run(selected, canonical, hashes)


def test_canonical_moved_since_expected_baseline_fails_closed(monkeypatch):
    selected, canonical, hashes, _ = _fixture(monkeypatch, wrong_canonical=True)
    with pytest.raises(preflight.M3CPreflightError, match="canonical changed"):
        _run(selected, canonical, hashes)


def test_warehouse_source_audit_error_fails_closed(monkeypatch):
    selected, canonical, hashes, state = _fixture(monkeypatch, audit_failure=True)
    with pytest.raises(preflight.M3CPreflightError, match="SHA mismatch"):
        _run(selected, canonical, hashes)
    assert state["db_reads"] == 0


@pytest.mark.parametrize("case", (
    "missing_date", "missing_hash", "extra_hash", "not_first_day",
    "other_month", "bool_snapshot", "bad_sha", "wrong_type_sha",
))
def test_bad_manifest_fails_before_reading_warehouse(monkeypatch, case):
    selected, canonical, hashes, state = _fixture(monkeypatch)
    if case == "missing_date":
        del selected[SECOND]
    elif case == "missing_hash":
        del hashes[SECOND]
    elif case == "extra_hash":
        hashes[SECOND + timedelta(days=1)] = "a" * 64
    elif case == "not_first_day":
        canonical.pop(FIRST)
        selected.pop(FIRST)
        hashes.pop(FIRST)
        canonical[SECOND + timedelta(days=1)] = 13
        selected[SECOND + timedelta(days=1)] = 13
        hashes[SECOND + timedelta(days=1)] = "c" * 64
    elif case == "other_month":
        new_day = date(2026, 9, 1)
        canonical[new_day] = canonical.pop(SECOND)
        selected[new_day] = selected.pop(SECOND)
        hashes[new_day] = hashes.pop(SECOND)
    elif case == "bool_snapshot":
        selected[FIRST] = True
    elif case == "bad_sha":
        hashes[FIRST] = "not_a_sha"
    elif case == "wrong_type_sha":
        hashes[FIRST] = None
    with pytest.raises(preflight.M3CPreflightError):
        _run(selected, canonical, hashes)
    assert state["audit_calls"] == 0
    assert state["db_reads"] == 0
