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


def test_postgres16_reads_real_synthetic_warehouse_without_writes(tmp_path):
    """Integration gate: actual SQLAlchemy ORM, audit rows and stored Excel bytes."""
    import os
    import uuid
    from datetime import datetime, timezone
    import sqlalchemy as sa
    from app.extensions import db

    url = os.getenv("M3B_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Requires isolated PostgreSQL 16 CI database")

    schema = "m3b_provenance_" + uuid.uuid4().hex[:16]
    admin = sa.create_engine(url)
    app_root = tmp_path / "runtime" / "api" / "app"
    app_root.mkdir(parents=True)
    with admin.begin() as conn:
        assert int(conn.exec_driver_sql("SHOW server_version_num").scalar()) // 10000 == 16
        conn.exec_driver_sql(f"CREATE SCHEMA {schema}")

    app = Flask("m3b_provenance_pg_" + schema, root_path=str(app_root))
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=url,
        SQLALCHEMY_ENGINE_OPTIONS={
            "connect_args": {"options": f"-csearch_path={schema}"},
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    create_sql = (
        """CREATE TABLE warehouse_report_types (
          id integer PRIMARY KEY, key varchar(80) NOT NULL,
          label varchar(150), family_id integer,
          default_source_id integer, default_operational_role_id integer,
          default_period_type varchar(20), active boolean
        )""",
        """CREATE TABLE warehouse_uploads (
          id integer PRIMARY KEY, original_filename varchar(255) NOT NULL,
          stored_filename varchar(255) NOT NULL, stored_path text NOT NULL,
          file_size_bytes bigint NOT NULL, file_hash_sha256 varchar(64) NOT NULL,
          mime_type varchar(100), extension varchar(10) NOT NULL,
          source_id integer NOT NULL, family_id integer NOT NULL,
          operational_role_id integer NOT NULL, report_type_id integer NOT NULL,
          period_type varchar(20) NOT NULL, cutoff_date date,
          date_from date, date_to date, status varchar(20),
          notes text, uploaded_by_user_id integer NOT NULL,
          track_daily_version_id bigint, created_at timestamptz,
          updated_at timestamptz, source_file_deleted_at timestamptz
        )""",
        """CREATE TABLE warehouse_audit_logs (
          id integer PRIMARY KEY, upload_id integer,
          action varchar(30) NOT NULL, performed_by_user_id integer NOT NULL,
          details json, created_at timestamptz
        )""",
        """CREATE TABLE kpi_desempeno_snapshots (
          id integer PRIMARY KEY, warehouse_upload_id integer NOT NULL UNIQUE,
          report_type_key varchar(100) NOT NULL, business_date date NOT NULL,
          captured_at timestamptz NOT NULL, snapshot_kind varchar(50) NOT NULL,
          is_canonical boolean NOT NULL,
          row_count_detected integer NOT NULL, row_count_valid integer NOT NULL,
          row_count_rejected integer NOT NULL,
          created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL
        )""",
        """CREATE TABLE kpi_desempeno_snapshot_rows (
          id integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
          snapshot_id integer NOT NULL, row_index integer NOT NULL,
          sucursal varchar(255) NOT NULL,
          socios_activos_inicio_mes integer NOT NULL,
          clientes_nuevo_real integer NOT NULL,
          reactivaciones integer NOT NULL, renovaciones integer NOT NULL,
          bajas integer NOT NULL, socios_activos_del_mes integer NOT NULL,
          meta_socios_activos_del_mes integer NOT NULL,
          alcance_meta numeric(12,2) NOT NULL,
          created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL
        )""",
    )
    try:
        with app.app_context():
            for ddl in create_sql:
                db.session.execute(sa.text(ddl))
            db.session.execute(sa.text(
                """INSERT INTO warehouse_report_types
                (id,key,label,default_period_type,active)
                VALUES (1,'kpi_desempeno','Synthetic KPI','diario',TRUE)"""
            ))
            now = datetime.now(timezone.utc)
            for day_idx, day in enumerate((FIRST, FIRST + timedelta(days=1))):
                for canonical, bajas, prefix in (
                    (True, 7 + day_idx, 100),
                    (False, 7 - 2 * day_idx, 200),
                ):
                    upload_id = prefix + day_idx + 1
                    snapshot_id = (1 if canonical else 11) + day_idx
                    payload = _synthetic_excel_bytes(bajas=bajas)
                    stored = f"kpi_{upload_id}.xlsx"
                    folder = tmp_path / "runtime" / "uploads" / "synthetic"
                    folder.mkdir(parents=True, exist_ok=True)
                    (folder / stored).write_bytes(payload)
                    db.session.execute(sa.text(
                        """INSERT INTO warehouse_uploads (
                         id,original_filename,stored_filename,stored_path,
                         file_size_bytes,file_hash_sha256,mime_type,extension,
                         source_id,family_id,operational_role_id,report_type_id,
                         period_type,cutoff_date,status,uploaded_by_user_id,created_at
                        ) VALUES (
                         :id,:name,:name,'uploads/synthetic',:size,:digest,
                         'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         'xlsx',1,1,1,1,'diario',:day,'ACTIVE',999,:now
                        )"""
                    ), {
                        "id": upload_id, "name": stored, "size": len(payload),
                        "digest": sha256(payload).hexdigest(), "day": day, "now": now,
                    })
                    db.session.execute(sa.text(
                        """INSERT INTO warehouse_audit_logs
                         (id,upload_id,action,performed_by_user_id,created_at)
                         VALUES (:id,:id,'UPLOAD',999,:now)"""
                    ), {"id": upload_id, "now": now})
                    db.session.execute(sa.text(
                        """INSERT INTO kpi_desempeno_snapshots (
                         id,warehouse_upload_id,report_type_key,business_date,
                         captured_at,snapshot_kind,is_canonical,
                         row_count_detected,row_count_valid,row_count_rejected,
                         created_at,updated_at
                        ) VALUES (
                         :id,:upload,'kpi_desempeno',:day,:now,'daily',
                         :canonical,2,2,0,:now,:now
                        )"""
                    ), {
                        "id": snapshot_id, "upload": upload_id, "day": day,
                        "now": now, "canonical": canonical,
                    })
                    for row_idx, (branch, react, bajas_value, active) in enumerate(
                        (("Centro", 20, bajas, 133), ("Norte", 25, 8, 155)),
                    ):
                        db.session.execute(sa.text(
                            """INSERT INTO kpi_desempeno_snapshot_rows (
                             snapshot_id,row_index,sucursal,socios_activos_inicio_mes,
                             clientes_nuevo_real,reactivaciones,renovaciones,bajas,
                             socios_activos_del_mes,meta_socios_activos_del_mes,
                             alcance_meta,created_at,updated_at
                            ) VALUES (
                             :sid,:ix,:branch,110,15,:react,12,:bajas,:active,150,
                             0.89,:now,:now
                            )"""
                        ), {
                            "sid": snapshot_id, "ix": row_idx, "branch": branch,
                            "react": react, "bajas": bajas_value, "active": active,
                            "now": now,
                        })
            db.session.commit()
            before = [
                db.session.execute(sa.text(f"SELECT COUNT(*) FROM {name}")).scalar_one()
                for name in (
                    "warehouse_uploads", "warehouse_audit_logs",
                    "kpi_desempeno_snapshots", "kpi_desempeno_snapshot_rows",
                )
            ]
            report = audit.audit_kpi_desempeno_m3b_provenance(
                candidate_snapshot_ids={FIRST: 11, FIRST + timedelta(days=1): 12},
                canonical_snapshot_ids={FIRST: 1, FIRST + timedelta(days=1): 2},
                expected_branch_count=2,
            )
            after = [
                db.session.execute(sa.text(f"SELECT COUNT(*) FROM {name}")).scalar_one()
                for name in (
                    "warehouse_uploads", "warehouse_audit_logs",
                    "kpi_desempeno_snapshots", "kpi_desempeno_snapshot_rows",
                )
            ]
            assert before == after == [4, 4, 4, 8]
            assert report.status == "BLOCKED_APPROVAL_REQUIRED"
            assert report.publication_authorized is False
            assert len(report.declines) == 1
            assert report.new_declines == 1
            assert report.shared_declines == 0
            assert not sa.inspect(db.engine).has_table("track_daily_mart")
            db.session.remove()
    finally:
        with admin.begin() as conn:
            conn.exec_driver_sql(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        admin.dispose()
