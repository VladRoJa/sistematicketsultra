"""M3-B contract checks: synthetic branch-level MTD and selective F3 impacts.

No real KPI uploads, no Track operations, no canonicality or reporting writes.
PostgreSQL is used solely as synthetic input/evidence of read-only behavior.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
import os
import uuid

import pytest
import sqlalchemy as sa

from app.warehouse.services.kpi_desempeno_semantic_diff import (
    DIFFERENCES_DETECTED,
    KpiDesempenoSemanticDiffResult,
    KpiDesempenoBranchDifference,
    KpiDesempenoFieldChange,
)
from app.warehouse.services.kpi_desempeno_m3b_continuity_plan import (
    BLOCKED,
    READY_FOR_REVIEW,
    plan_kpi_desempeno_mtd_impact,
)

DAY = date(2026, 8, 20)
CENTRO = "sucursal_sintetica_a"
NORTE = "sucursal_sintetica_b"


def _diff(*, day=DAY, branch=CENTRO, fields=None):
    if fields is None:
        fields = [("reactivaciones", 150, 140)]
    return KpiDesempenoSemanticDiffResult(
        status=DIFFERENCES_DETECTED, business_date=day.isoformat(),
        previous_row_count=2, current_row_count=2,
        differences=(KpiDesempenoBranchDifference(
            branch_key=branch, kind="CHANGED",
            previous_branch_name=branch, current_branch_name=branch,
            fields=tuple(KpiDesempenoFieldChange(
                field=field, previous=old, current=new, delta=new-old,
            ) for field, old, new in fields),
        ),),
    )


def _series(day=DAY, branch=CENTRO, *, prior=(110, 20),
            original=(150, 25), following=(170, 29), included_next=True,
            other_fields=False):
    def values(items):
        out = {
            "reactivaciones_real_mtd": items[0],
            "bajas_reales_mtd": items[1],
        }
        if other_fields:
            out.update({
                "ingreso_real_base_mtd": 1234.56,
                "ingreso_real_agregadora_mtd": 150.34,
                "ingreso_real_total_mtd": 1384.90,
                "nuevos_domiciliados_real_mtd": 17,
                "venta_tienda_real_mtd": 89,
                "clientes_nuevos_real_mtd": 30,
                "meta_reactivaciones_mes": 99,
            })
        return out
    rows = {
        day - timedelta(days=1): {branch: values(prior)},
        day: {branch: values(original)},
    }
    if included_next:
        rows[day + timedelta(days=1)] = {branch: values(following)}
    return rows


def test_select_only_changed_F3_cells_and_explicit_derived_days():
    observed = _series(other_fields=True)
    before = deepcopy(observed)
    diff = _diff(fields=[
        ("reactivaciones", 150, 140),
        ("bajas", 25, 27),
        ("socios_activos_del_mes", 800, 805),
        ("renovaciones", 45, 41),
    ])
    plan = plan_kpi_desempeno_mtd_impact(
        business_date=DAY, diff=diff, observed_mtd=observed,
    )
    assert plan.status == READY_FOR_REVIEW
    assert plan.blocking_issues == ()
    assert len(plan.changed_snapshot_fields) == 4
    assert {
        (c.business_date, c.branch_key, c.track_field, c.previous, c.current)
        for c in plan.track_field_changes
    } == {
        (DAY, CENTRO, "reactivaciones_real_mtd", 150, 140),
        (DAY, CENTRO, "bajas_reales_mtd", 25, 27),
        (DAY, CENTRO, "usuarios_activos_actual", 800, 805),
    }
    assert plan.continuity_days == (
        DAY - timedelta(days=1), DAY, DAY + timedelta(days=1)
    )
    assert {
        (x.business_date, x.track_mtd_field)
        for x in plan.derived_delta_impacts
    } == {
        (DAY, "reactivaciones_real_mtd"),
        (DAY + timedelta(days=1), "reactivaciones_real_mtd"),
        (DAY, "bajas_reales_mtd"),
        (DAY + timedelta(days=1), "bajas_reales_mtd"),
    }
    assert observed == before
    assert not ({x.track_field for x in plan.track_field_changes} & {
        "ingreso_real_base_mtd", "ingreso_real_agregadora_mtd",
        "ingreso_real_total_mtd", "nuevos_domiciliados_real_mtd",
        "venta_tienda_real_mtd", "clientes_nuevos_real_mtd",
        "meta_reactivaciones_mes", "renovaciones",
    })


def test_mandatory_october_6_to_7_regression_blocks_without_real_branch_data():
    """User-mandated aggregate invariant, NOT imported production branch rows."""
    d = date(2026, 10, 7)
    synthetic = "total_agregado_sintetico"
    observed = _series(day=d, branch=synthetic,
                       prior=(1253, 30), original=(1372, 40),
                       following=(1450, 50))
    plan = plan_kpi_desempeno_mtd_impact(
        business_date=d,
        diff=_diff(day=d, branch=synthetic, fields=[
            ("reactivaciones", 1372, 963)
        ]),
        observed_mtd=observed,
    )
    assert plan.status == BLOCKED
    issues = [x for x in plan.blocking_issues if x.code == "MTD_DECREASE"]
    assert [(x.earlier_date, x.later_date, x.delta, x.track_mtd_field)
            for x in issues] == [
        (date(2026, 10, 6), date(2026, 10, 7), -290,
         "reactivaciones_real_mtd")
    ]
    assert len(plan.track_field_changes) == 1
    assert {x.business_date for x in plan.derived_delta_impacts} == {
        date(2026, 10, 7), date(2026, 10, 8),
    }


def test_decreasing_bajas_mtd_blocks_specific_branch_and_field():
    plan = plan_kpi_desempeno_mtd_impact(
        business_date=DAY,
        diff=_diff(fields=[("bajas", 25, 19)]),
        observed_mtd=_series(),
    )
    assert plan.status == BLOCKED
    assert [(x.code, x.track_mtd_field, x.delta)
            for x in plan.blocking_issues] == [
        ("MTD_DECREASE", "bajas_reales_mtd", -1),
    ]  # previous day bajas=20


def test_next_day_reactivaciones_negative_is_incompatible():
    plan = plan_kpi_desempeno_mtd_impact(
        business_date=DAY,
        diff=_diff(fields=[("reactivaciones", 150, 200)]),
        observed_mtd=_series(following=(170, 29)),
    )
    assert plan.status == BLOCKED
    assert [(x.earlier_date, x.later_date, x.delta)
            for x in plan.blocking_issues] == [
        (DAY, DAY + timedelta(days=1), -30)
    ]


@pytest.mark.parametrize("missing", ["previous", "current", "following", "branch"])
def test_missing_neighbor_or_branch_blocks(missing):
    observed = _series()
    if missing == "previous":
        del observed[DAY-timedelta(days=1)]
    elif missing == "current":
        del observed[DAY]
    elif missing == "following":
        del observed[DAY+timedelta(days=1)]
    else:
        observed[DAY+timedelta(days=1)] = {NORTE: {
            "reactivaciones_real_mtd": 170, "bajas_reales_mtd": 29,
        }}
    plan = plan_kpi_desempeno_mtd_impact(
        business_date=DAY, diff=_diff(), observed_mtd=observed,
    )
    assert plan.status == BLOCKED
    assert {"MISSING_DAY", "MISSING_BRANCH"} & {
        x.code for x in plan.blocking_issues
    }


def test_original_mtd_lineage_must_match_semantic_previous():
    plan = plan_kpi_desempeno_mtd_impact(
        business_date=DAY,
        diff=_diff(fields=[("reactivaciones", 151, 140)]),
        observed_mtd=_series(),
    )
    assert plan.status == BLOCKED
    assert any(x.code == "BASELINE_MISMATCH" for x in plan.blocking_issues)


@pytest.mark.parametrize("value", [-1, None, 10.5, True])
def test_invalid_mtd_rejects_noninteger_negative_missing_or_bool(value):
    observed = _series()
    observed[DAY + timedelta(days=1)][CENTRO]["reactivaciones_real_mtd"] = value
    plan = plan_kpi_desempeno_mtd_impact(
        business_date=DAY, diff=_diff(), observed_mtd=observed,
    )
    assert plan.status == BLOCKED
    assert any(x.code == "INVALID_MTD" for x in plan.blocking_issues)


def test_only_document_metric_does_not_touch_track():
    plan = plan_kpi_desempeno_mtd_impact(
        business_date=DAY,
        diff=_diff(fields=[("renovaciones", 45, 41)]),
        observed_mtd={},
    )
    assert plan.status == READY_FOR_REVIEW
    assert [x.kpi_field for x in plan.changed_snapshot_fields] == ["renovaciones"]
    assert plan.track_field_changes == ()
    assert plan.derived_delta_impacts == ()
    assert plan.continuity_days == ()


def test_month_boundary_does_not_cross_mtd_reset():
    first = date(2026, 9, 1)
    observed = {
        first: {CENTRO: {"reactivaciones_real_mtd": 5, "bajas_reales_mtd": 1}},
        first + timedelta(days=1): {CENTRO: {
            "reactivaciones_real_mtd": 7, "bajas_reales_mtd": 2,
        }},
    }
    plan = plan_kpi_desempeno_mtd_impact(
        business_date=first,
        diff=_diff(day=first, fields=[("reactivaciones", 5, 4)]),
        observed_mtd=observed,
    )
    assert plan.status == READY_FOR_REVIEW
    assert plan.continuity_days == (first, first + timedelta(days=1))
    assert all(x.business_date >= first for x in plan.derived_delta_impacts)


def test_bad_M1_date_or_identity_cannot_produce_ready_plan():
    wrong = plan_kpi_desempeno_mtd_impact(
        business_date=DAY + timedelta(days=1),
        diff=_diff(), observed_mtd=_series(),
    )
    assert wrong.status == BLOCKED
    assert wrong.track_field_changes == ()
    assert any(x.code == "INVALID_M1_DIFF" for x in wrong.blocking_issues)
    added = _diff()
    altered = KpiDesempenoSemanticDiffResult(
        status=added.status, business_date=added.business_date,
        previous_row_count=added.previous_row_count,
        current_row_count=added.current_row_count,
        differences=(KpiDesempenoBranchDifference(
            branch_key=CENTRO, kind="ADDED",
            previous_branch_name=None, current_branch_name=CENTRO,
            fields=added.differences[0].fields,
        ),),
    )
    assert plan_kpi_desempeno_mtd_impact(
        business_date=DAY, diff=altered, observed_mtd=_series(),
    ).status == BLOCKED


@pytest.mark.parametrize(
    ("old", "new"), [(150, 149), (150, 180)]
)
def test_selective_plan_always_mentions_changed_mtd_day_and_next(old, new):
    obs = _series(original=(old, 25), following=(200, 29))
    plan = plan_kpi_desempeno_mtd_impact(
        business_date=DAY,
        diff=_diff(fields=[("reactivaciones", old, new)]),
        observed_mtd=obs,
    )
    assert [x.business_date for x in plan.derived_delta_impacts] == [
        DAY, DAY + timedelta(days=1),
    ]


def test_postgres16_synthetic_snapshot_is_not_mutated():
    url = os.getenv("M3B_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Requires isolated PostgreSQL 16 CI service")
    schema = "kpi_m3b_" + uuid.uuid4().hex[:16]
    engine = sa.create_engine(url)
    try:
        with engine.begin() as conn:
            assert int(conn.exec_driver_sql("SHOW server_version_num").scalar()) // 10000 == 16
            conn.exec_driver_sql(f"CREATE SCHEMA {schema}")
            conn.exec_driver_sql(f"""
                CREATE TABLE {schema}.synthetic_mtd (
                  business_date DATE NOT NULL,
                  branch_key TEXT NOT NULL,
                  reactivaciones_real_mtd INT NOT NULL,
                  bajas_reales_mtd INT NOT NULL,
                  ingreso_real_base_mtd NUMERIC(14,2) NOT NULL,
                  ingreso_real_agregadora_mtd NUMERIC(14,2) NOT NULL,
                  nuevos_domiciliados_real_mtd INT NOT NULL,
                  venta_tienda_real_mtd INT NOT NULL,
                  meta_reactivaciones_mes INT NOT NULL,
                  PRIMARY KEY (business_date, branch_key)
                )
            """)
            for offset, react, bajas in [(-1, 110, 20), (0, 150, 25), (1, 170, 29)]:
                conn.execute(sa.text(f"""
                    INSERT INTO {schema}.synthetic_mtd VALUES
                    (:day, :branch, :react, :bajas, 1234.56, 150.34, 17, 89, 99)
                """), {
                    "day": DAY + timedelta(days=offset),
                    "branch": CENTRO, "react": react, "bajas": bajas,
                })

        with engine.connect() as conn:
            rows_before = conn.execute(sa.text(f"""
                SELECT * FROM {schema}.synthetic_mtd ORDER BY business_date, branch_key
            """)).mappings().all()
            observed = {
                row["business_date"]: {
                    row["branch_key"]: {
                        "reactivaciones_real_mtd": row["reactivaciones_real_mtd"],
                        "bajas_reales_mtd": row["bajas_reales_mtd"],
                        "ingreso_real_base_mtd": row["ingreso_real_base_mtd"],
                        "ingreso_real_agregadora_mtd": row["ingreso_real_agregadora_mtd"],
                        "nuevos_domiciliados_real_mtd": row["nuevos_domiciliados_real_mtd"],
                        "venta_tienda_real_mtd": row["venta_tienda_real_mtd"],
                        "meta_reactivaciones_mes": row["meta_reactivaciones_mes"],
                    }
                } for row in rows_before
            }
            plan = plan_kpi_desempeno_mtd_impact(
                business_date=DAY,
                diff=_diff(fields=[
                    ("reactivaciones", 150, 140),
                    ("bajas", 25, 27),
                ]),
                observed_mtd=observed,
            )
            rows_after = conn.execute(sa.text(f"""
                SELECT * FROM {schema}.synthetic_mtd ORDER BY business_date, branch_key
            """)).mappings().all()

            assert plan.status == READY_FOR_REVIEW
            assert rows_before == rows_after
            assert len(plan.track_field_changes) == 2
            assert {x.track_field for x in plan.track_field_changes} == {
                "reactivaciones_real_mtd", "bajas_reales_mtd",
            }
            assert conn.execute(sa.text(f"""
                SELECT COUNT(*) FROM {schema}.synthetic_mtd
            """)).scalar_one() == 3
    finally:
        with engine.begin() as conn:
            conn.exec_driver_sql(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        engine.dispose()
