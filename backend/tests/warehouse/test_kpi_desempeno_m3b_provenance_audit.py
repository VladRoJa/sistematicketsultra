"""M3-B source provenance: synthetic Excel + in-memory repository doubles only."""
from __future__ import annotations

from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from flask import Flask

from app.models.warehouse import KpiDesempenoSnapshotORM, WarehouseUploadORM
from app.warehouse.services.kpi_desempeno_parser import EXPECTED_KPI_DESEMPENO_COLUMNS
from app.warehouse.services import kpi_desempeno_m3b_provenance_audit as audit


FIRST = date(2026, 8, 1)


def _src(day, snapshot_id, upload_id, *, canonical, bajas, react=10,
         branch_names=("centro", "norte")):
    values = {name: (react, bajas, 200) for name in branch_names}
    return audit.VerifiedKpiSource(
        day, snapshot_id, upload_id, "a" * 64, canonical, values,
    )


def _mock_series(monkeypatch, series, baselines, *, baseline_sources, candidate_sources):
    all_sources = {**baseline_sources, **candidate_sources}
    monkeypatch.setattr(audit, "_canonical_ids", lambda day: (baselines[day],))

    def load(*, day, snapshot_id, expected_canonical, expected_count):
        source = all_sources[(day, snapshot_id)]
        assert source.is_canonical is expected_canonical
        assert len(source.values) == expected_count
        return source

    monkeypatch.setattr(audit, "_load_verified_source", load)


def test_two_day_provenance_report_flags_new_and_removed_declines(monkeypatch):
    tomorrow = FIRST + timedelta(days=1)
    candidate = {FIRST: 11, tomorrow: 12}
    canon = {FIRST: 1, tomorrow: 2}
    b = {
        (FIRST, 1): _src(FIRST, 1, 101, canonical=True, bajas=20),
        (tomorrow, 2): _src(tomorrow, 2, 102, canonical=True, bajas=21),
    }
    c = {
        (FIRST, 11): _src(FIRST, 11, 111, canonical=False, bajas=20),
        (tomorrow, 12): _src(tomorrow, 12, 112, canonical=False, bajas=19),
    }
    _mock_series(monkeypatch, candidate, canon, baseline_sources=b, candidate_sources=c)
    report = audit.audit_kpi_desempeno_m3b_provenance(
        candidate_snapshot_ids=candidate,
        canonical_snapshot_ids=canon,
        expected_branch_count=2,
    )
    assert report.status == "BLOCKED_APPROVAL_REQUIRED"
    assert report.publication_authorized is False
    assert report.days_verified == 2
    assert len(report.declines) == 2
    assert report.new_declines == 2
    assert report.shared_declines == 0
    assert report.removed_declines == 0
    assert all(item.review_status == "REQUIRES_APROBACION_ORIGEN" for item in report.declines)
    assert {(item.earlier_upload_id, item.later_upload_id) for item in report.declines} == {
        (111, 112)
    }


def test_baseline_shared_drop_and_unchanged_terminal_canonical(monkeypatch):
    d2 = FIRST + timedelta(days=1)
    d3 = FIRST + timedelta(days=2)
    candidate = {FIRST: 11, d2: 12, d3: 3}
    canon = {FIRST: 1, d2: 2, d3: 3}
    b = {
        (FIRST, 1): _src(FIRST, 1, 101, canonical=True, bajas=20),
        (d2, 2): _src(d2, 2, 102, canonical=True, bajas=19),
        (d3, 3): _src(d3, 3, 103, canonical=True, bajas=19),
    }
    c = {
        (FIRST, 11): _src(FIRST, 11, 111, canonical=False, bajas=20),
        (d2, 12): _src(d2, 12, 112, canonical=False, bajas=19),
    }
    _mock_series(monkeypatch, candidate, canon, baseline_sources=b, candidate_sources=c)
    report = audit.audit_kpi_desempeno_m3b_provenance(
        candidate_snapshot_ids=candidate,
        canonical_snapshot_ids=canon, expected_branch_count=2,
    )
    assert report.days_verified == 3
    assert report.shared_declines == 2
    assert report.new_declines == 0
    assert report.removed_declines == 0
    assert report.publication_authorized is False


def test_baseline_drop_removed_by_new_series(monkeypatch):
    d2 = FIRST + timedelta(days=1)
    candidates = {FIRST: 11, d2: 12}
    originals = {FIRST: 1, d2: 2}
    _mock_series(
        monkeypatch, candidates, originals,
        baseline_sources={
            (FIRST, 1): _src(FIRST, 1, 101, canonical=True, bajas=20),
            (d2, 2): _src(d2, 2, 102, canonical=True, bajas=19),
        },
        candidate_sources={
            (FIRST, 11): _src(FIRST, 11, 111, canonical=False, bajas=20),
            (d2, 12): _src(d2, 12, 112, canonical=False, bajas=21),
        },
    )
    report = audit.audit_kpi_desempeno_m3b_provenance(
        candidate_snapshot_ids=candidates, canonical_snapshot_ids=originals,
        expected_branch_count=2,
    )
    assert report.status == "SOURCE_AUDIT_ONLY"
    assert report.removed_declines == 2
    assert report.declines == ()
    assert report.publication_authorized is False


@pytest.mark.parametrize("kind", [
    "missing_day", "cross_month", "wrong_first_day", "mismatched_days", "bool_id",
    "canonical_changed", "roster_changed",
])
def test_invalid_series_fails_closed(monkeypatch, kind):
    d2 = FIRST + timedelta(days=1)
    d3 = FIRST + timedelta(days=2)
    candidates = {FIRST: 11, d2: 12}
    originals = {FIRST: 1, d2: 2}
    b = {
        (FIRST, 1): _src(FIRST, 1, 101, canonical=True, bajas=20),
        (d2, 2): _src(d2, 2, 102, canonical=True, bajas=21),
    }
    c = {
        (FIRST, 11): _src(FIRST, 11, 111, canonical=False, bajas=20),
        (d2, 12): _src(d2, 12, 112, canonical=False, bajas=21),
    }
    if kind == "missing_day":
        candidates = {FIRST: 11, d3: 13}
        originals = {FIRST: 1, d3: 3}
    if kind == "cross_month":
        candidates = {FIRST: 11, date(2026, 9, 1): 12}
        originals = {FIRST: 1, date(2026, 9, 1): 2}
    if kind == "wrong_first_day":
        candidates = {d2: 11, d3: 12}
        originals = {d2: 1, d3: 2}
    if kind == "mismatched_days":
        del originals[d2]
    if kind == "bool_id":
        candidates[FIRST] = True
    if kind == "canonical_changed":
        monkeypatch.setattr(audit, "_canonical_ids", lambda day: (999,))
    if kind == "roster_changed":
        c[(d2, 12)] = _src(
            d2, 12, 112, canonical=False, bajas=21, branch_names=("centro", "sur"),
        )
    if kind not in {"canonical_changed"}:
        _mock_series(monkeypatch, candidates, originals, baseline_sources=b, candidate_sources=c)
    with pytest.raises(audit.M3BProvenanceError):
        audit.audit_kpi_desempeno_m3b_provenance(
            candidate_snapshot_ids=candidates,
            canonical_snapshot_ids=originals,
            expected_branch_count=2,
        )


def _synthetic_excel_bytes(*, bajas=7):
    data = pd.DataFrame(
        [
            ["Centro", 110, 15, 20, 12, bajas, 133, 150, .89],
            ["Norte", 120, 18, 25, 13, 8, 155, 170, .91],
        ],
        columns=EXPECTED_KPI_DESEMPENO_COLUMNS,
    )
    from io import BytesIO
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        data.to_excel(writer, sheet_name="data", index=False)
    return buffer.getvalue()


@pytest.fixture()
def synthetic_file_source(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    app_root = root / "api" / "app"
    app_root.mkdir(parents=True)
    app = Flask("m3b_provenance_synthetic", root_path=str(app_root))
    payload = _synthetic_excel_bytes()
    relative_path = Path("uploads/synthetic")
    dest = root / relative_path
    dest.mkdir(parents=True)
    (dest / "kpi.xlsx").write_bytes(payload)
    snap = SimpleNamespace(
        id=701,
        business_date=FIRST,
        snapshot_kind="daily",
        report_type_key="kpi_desempeno",
        is_canonical=False,
        row_count_valid=2,
        row_count_rejected=0,
        warehouse_upload_id=801,
    )
    upload = SimpleNamespace(
        id=801,
        uploaded_by_user_id=901,
        status="ACTIVE",
        period_type="diario",
        cutoff_date=FIRST,
        source_file_deleted_at=None,
        stored_filename="kpi.xlsx",
        stored_path=str(relative_path),
        file_size_bytes=len(payload),
        file_hash_sha256=sha256(payload).hexdigest(),
        report_type=SimpleNamespace(key="kpi_desempeno"),
    )
    rows = [
        SimpleNamespace(sucursal="Centro", reactivaciones=20, bajas=7,
                        socios_activos_del_mes=133),
        SimpleNamespace(sucursal="Norte", reactivaciones=25, bajas=8,
                        socios_activos_del_mes=155),
    ]
    def get(model, object_id):
        return (snap if object_id == 701 else upload if object_id == 801 else None)
    monkeypatch.setattr(audit, "_db_get", get)
    monkeypatch.setattr(audit, "_upload_has_audit", lambda source: True)
    monkeypatch.setattr(audit, "_stored_rows", lambda snapshot_id: rows)
    with app.app_context():
        yield snap, upload, rows, dest / "kpi.xlsx"


def test_verified_source_uses_real_xlsx_sha_and_compares_persisted_F3(synthetic_file_source):
    source = audit._load_verified_source(
        day=FIRST, snapshot_id=701, expected_canonical=False, expected_count=2,
    )
    assert source.file_hash_sha256 == synthetic_file_source[1].file_hash_sha256
    assert source.values == {"centro": (20, 7, 133), "norte": (25, 8, 155)}


def test_raw_file_tampering_fails_before_data_is_trusted(synthetic_file_source):
    path = synthetic_file_source[3]
    path.write_bytes(b"altered")
    with pytest.raises(Exception, match="size/SHA"):
        audit._load_verified_source(
            day=FIRST, snapshot_id=701, expected_canonical=False,
            expected_count=2,
        )


def test_missing_upload_audit_blocks(synthetic_file_source, monkeypatch):
    monkeypatch.setattr(audit, "_upload_has_audit", lambda source: False)
    with pytest.raises(audit.M3BProvenanceError, match="audit"):
        audit._load_verified_source(
            day=FIRST, snapshot_id=701, expected_canonical=False,
            expected_count=2,
        )


def test_database_row_drift_blocks(synthetic_file_source):
    synthetic_file_source[2][0].bajas = 999
    with pytest.raises(audit.M3BProvenanceError, match="differ"):
        audit._load_verified_source(
            day=FIRST, snapshot_id=701, expected_canonical=False,
            expected_count=2,
        )


def test_wrong_cutoff_or_canonicality_blocks(synthetic_file_source):
    snap, upload, rows, path = synthetic_file_source
    upload.cutoff_date = FIRST + timedelta(days=1)
    with pytest.raises(ValueError, match="cutoff_date"):
        audit._load_verified_source(
            day=FIRST, snapshot_id=701, expected_canonical=False,
            expected_count=2,
        )
    upload.cutoff_date = FIRST
    with pytest.raises(audit.M3BProvenanceError, match="canonicality"):
        audit._load_verified_source(
            day=FIRST, snapshot_id=701, expected_canonical=True,
            expected_count=2,
        )
