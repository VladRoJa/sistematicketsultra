from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.track_alerts.services import track_regional_operational_service as service
from app.track_alerts.services.track_regional_pacing_service import (
    CLIENTES_NUEVOS_WEEKDAY_WEIGHTS,
    calculate_expected_progress_ratio,
)


def _mart_row(
    *,
    clientes_actual,
    bajas_actual,
    domiciliados_actual=Decimal("30"),
    domiciliados_target=Decimal("100"),
):
    return SimpleNamespace(
        target_month=date(2026, 8, 1),
        clientes_nuevos_real_mtd=clientes_actual,
        meta_clientes_nuevos_mes=Decimal("100"),
        reactivaciones_real_mtd=Decimal("40"),
        meta_reactivaciones_mes=Decimal("100"),
        bajas_reales_mtd=Decimal(str(bajas_actual)),
        meta_bajas_mes=Decimal("190"),
        nuevos_domiciliados_real_mtd=Decimal(str(domiciliados_actual)),
        meta_nuevos_domiciliados_mes=Decimal(str(domiciliados_target)),
        ingreso_real_total_mtd=Decimal("80000"),
        ingreso_real_mtd=Decimal("70000"),
        meta_faycgo_mes=Decimal("100000"),
        venta_tienda_real_mtd=Decimal("20000"),
        meta_venta_tienda_mes=Decimal("30000"),
        usuarios_activos_actual=Decimal("1000"),
        proyeccion_usuarios_cierre_mes=Decimal("1100"),
    )


def _branch(*, branch_id, canon, name, order):
    return SimpleNamespace(
        sucursal_id=branch_id,
        sucursal_canon=canon,
        track_label=name,
        sucursal=SimpleNamespace(
            sucursal=name,
            orden_apertura=order,
        ),
    )


def test_lagging_branch_remains_priority_when_region_is_ahead():
    track_date = date(2026, 8, 17)
    expected_ratio = calculate_expected_progress_ratio(
        cutoff_date=track_date,
        weekday_weights=CLIENTES_NUEVOS_WEEKDAY_WEIGHTS,
    )
    expected_each = Decimal("100") * expected_ratio
    region = SimpleNamespace(
        region_key="REGION_NORTE",
        region_label="Región Norte",
    )
    rows = [
        (
            _mart_row(
                clientes_actual=expected_each - Decimal("10"),
                bajas_actual=205,
            ),
            _branch(
                branch_id=1,
                canon="PAPALOTE_TJ",
                name="Papalote",
                order=1,
            ),
            region,
        ),
        (
            _mart_row(
                clientes_actual=expected_each + Decimal("30"),
                bajas_actual=100,
            ),
            _branch(
                branch_id=2,
                canon="SANTA_FE_TJ",
                name="Santa Fe",
                order=2,
            ),
            region,
        ),
    ]
    resolved_version = SimpleNamespace(
        id=901,
        version_type="preview_operativo",
        status="success",
    )
    insufficient_projection = {
        "status": "insufficient_history",
        "projected_close": None,
    }

    with patch.object(
        service,
        "resolve_effective_track_daily_version",
        return_value=resolved_version,
    ) as resolve_version, patch.object(
        service,
        "_load_track_rows_with_region",
        return_value=rows,
    ) as load_rows, patch.object(
        service,
        "build_branch_income_projection_summary",
        return_value=insufficient_projection,
    ):
        result = service.get_regional_operational_detail(
            user=SimpleNamespace(rol="ADMIN", sucursal_id=None),
            track_date=track_date,
            generation_mode="manual_preview",
        )

    resolve_version.assert_called_once_with(
        track_date=track_date,
        generation_mode="manual_preview",
    )
    load_rows.assert_called_once_with(track_daily_version_id=901)

    result_region = result["regions"][0]
    assert result_region["summary"]["metrics"]["clientes_nuevos"][
        "status"
    ] == "ADELANTADO"
    assert len(result_region["branches"]) == 2

    clientes_priorities = result["priorities"][0]["items"]
    assert [item["sucursal_canon"] for item in clientes_priorities] == [
        "PAPALOTE_TJ",
        "SANTA_FE_TJ",
    ]
    assert Decimal(clientes_priorities[0]["gap_pct_points"]) < 0
    assert clientes_priorities[0]["status"] == "DEBAJO_RITMO"
    assert clientes_priorities[1]["status"] in {
        "ADELANTADO",
        "META_SUPERADA",
    }

    bajas_priorities = result["priorities"][2]["items"]
    assert [item["sucursal_canon"] for item in bajas_priorities] == [
        "PAPALOTE_TJ",
        "SANTA_FE_TJ",
    ]
    assert bajas_priorities[0]["status"] == "LIMITE_EXCEDIDO"

    metrics = result_region["branches"][0]["metrics"]
    assert set(metrics) == {
        "clientes_nuevos",
        "reactivaciones",
        "bajas",
        "domiciliados",
        "ingreso",
        "tienda",
        "usuarios",
    }
    assert metrics["ingreso"]["actual_mtd"] == "80000"
    assert metrics["ingreso"]["projection"] == insufficient_projection
    assert metrics["usuarios"]["users_gap"] == "-100"


def test_regional_domiciliados_sums_actual_and_target_before_percentage():
    track_date = date(2026, 8, 17)
    domiciliados_values = [
        (52, 49),
        (40, 60),
        (130, 207),
        (94, 225),
        (104, 270),
    ]
    region = SimpleNamespace(
        region_key="REGION_TEST",
        region_label="Región de prueba",
    )
    rows = [
        (
            _mart_row(
                clientes_actual=Decimal("0"),
                bajas_actual=0,
                domiciliados_actual=actual,
                domiciliados_target=target,
            ),
            _branch(
                branch_id=index,
                canon=f"BRANCH_{index}",
                name=f"Sucursal {index}",
                order=index,
            ),
            region,
        )
        for index, (actual, target) in enumerate(
            domiciliados_values,
            start=1,
        )
    ]

    with patch.object(
        service,
        "resolve_effective_track_daily_version",
        return_value=SimpleNamespace(
            id=901,
            version_type="preview_operativo",
            status="success",
        ),
    ), patch.object(
        service,
        "_load_track_rows_with_region",
        return_value=rows,
    ), patch.object(
        service,
        "build_branch_income_projection_summary",
        return_value={
            "status": "insufficient_history",
            "projected_close": None,
        },
    ):
        result = service.get_regional_operational_detail(
            user=SimpleNamespace(rol="ADMIN", sucursal_id=None),
            track_date=track_date,
            generation_mode="manual_preview",
        )

    metric = result["regions"][0]["summary"]["metrics"]["domiciliados"]
    expected_pct = Decimal("420") / Decimal("811") * Decimal("100")
    branch_pct_average = sum(
        Decimal(actual) / Decimal(target) * Decimal("100")
        for actual, target in domiciliados_values
    ) / Decimal(len(domiciliados_values))

    assert metric["actual_mtd"] == "420"
    assert metric["monthly_target"] == "811"
    assert Decimal(metric["compliance_pct"]) == expected_pct
    assert Decimal(metric["compliance_pct"]) != branch_pct_average


def test_duplicate_current_region_assignment_is_rejected():
    mart = _mart_row(clientes_actual=10, bajas_actual=10)
    branch = _branch(
        branch_id=1,
        canon="PAPALOTE_TJ",
        name="Papalote",
        order=1,
    )
    rows = [
        (
            mart,
            branch,
            SimpleNamespace(region_key="R1", region_label="Región 1"),
        ),
        (
            mart,
            branch,
            SimpleNamespace(region_key="R2", region_label="Región 2"),
        ),
    ]

    with patch.object(
        service,
        "resolve_effective_track_daily_version",
        return_value=SimpleNamespace(
            id=901,
            version_type="preview_operativo",
            status="success",
        ),
    ), patch.object(
        service,
        "_load_track_rows_with_region",
        return_value=rows,
    ):
        with pytest.raises(
            service.TrackRegionalOperationalDataError,
            match="más de una región current",
        ):
            service.get_regional_operational_detail(
                user=SimpleNamespace(rol="ADMIN", sucursal_id=None),
                track_date=date(2026, 8, 17),
                generation_mode="manual_preview",
            )


def test_bajas_priorities_include_all_branches_ordered_by_limit_usage():
    from app.track_alerts.services import (
        track_regional_operational_service as service,
    )

    usages = [
        ("BRANCH_01", 130, 100, "LIMITE_EXCEDIDO"),
        ("BRANCH_02", 120, 100, "LIMITE_EXCEDIDO"),
        ("BRANCH_03", 99, 100, "EN_RITMO"),
        ("BRANCH_04", 98, 100, "EN_RITMO"),
        ("BRANCH_05", 97, 100, "EN_RITMO"),
        ("BRANCH_06", 96, 100, "EN_RITMO"),
        ("BRANCH_07", 95, 100, "EN_RITMO"),
        ("BRANCH_08", 94, 100, "EN_RITMO"),
        ("BRANCH_09", 93, 100, "EN_RITMO"),
        ("BRANCH_10", 92, 100, "EN_RITMO"),
        ("BRANCH_11", 91, 100, "EN_RITMO"),
        ("BRANCH_12", 80, 100, "EN_RITMO"),
    ]

    branches = []

    for branch_name, actual, limit, status in usages:
        branches.append(
            {
                "sucursal_canon": branch_name,
                "sucursal_name": branch_name,
                "metrics": {
                    "clientes_nuevos": {
                        "actual_mtd": "100",
                        "monthly_target": "100",
                        "actual_progress_pct": "100",
                        "expected_progress_pct": "100",
                        "expected_mtd": "100",
                        "gap_units": "0",
                        "gap_pct_points": "0",
                        "status": "EN_RITMO",
                    },
                    "reactivaciones": {
                        "actual_mtd": "100",
                        "monthly_target": "100",
                        "actual_progress_pct": "100",
                        "expected_progress_pct": "100",
                        "expected_mtd": "100",
                        "gap_units": "0",
                        "gap_pct_points": "0",
                        "status": "EN_RITMO",
                    },
                    "bajas": {
                        "actual_mtd": str(actual),
                        "monthly_limit": str(limit),
                        "limit_usage_pct": str(
                            actual / limit * 100
                        ),
                        "status": status,
                    },
                },
            }
        )

    priorities = service._build_priorities(
        [
            {
                "region_key": "TEST_REGION",
                "region_label": "Test region",
                "branches": branches,
            }
        ]
    )

    clientes_group = next(
        group
        for group in priorities
        if group["metric_key"] == "clientes_nuevos"
    )
    reactivaciones_group = next(
        group
        for group in priorities
        if group["metric_key"] == "reactivaciones"
    )
    bajas_group = next(
        group
        for group in priorities
        if group["metric_key"] == "bajas"
    )

    assert len(clientes_group["items"]) == 12
    assert len(reactivaciones_group["items"]) == 12
    assert len(bajas_group["items"]) == 12

    items = bajas_group["items"]

    assert items[0]["sucursal_canon"] == "BRANCH_01"
    assert items[0]["status"] == "LIMITE_EXCEDIDO"

    assert items[1]["sucursal_canon"] == "BRANCH_02"
    assert items[1]["status"] == "LIMITE_EXCEDIDO"

    assert items[2]["sucursal_canon"] == "BRANCH_03"
    assert items[2]["status"] == "DENTRO_LIMITE"
    assert items[2]["excess_units"] is None

    usage_values = [
        float(item["limit_usage_pct"])
        for item in items
    ]

    assert usage_values == sorted(
        usage_values,
        reverse=True,
    )

    assert {
        item["sucursal_canon"]
        for item in items
    } == {
        branch_name
        for branch_name, *_ in usages
    }


def test_priorities_domiciliados_reuse_clientes_nuevos_weekday_pace():
    cutoff = date(2026, 8, 18)

    clientes_metric = service.build_clientes_nuevos_metric(
        actual_mtd=100,
        monthly_target=100,
        cutoff_date=cutoff,
    ).to_dict()

    branch = {
        "sucursal_canon": "TEST_BRANCH",
        "sucursal_name": "Test Branch",
        "metrics": {
            "clientes_nuevos": clientes_metric,
            "reactivaciones": service.build_reactivaciones_metric(
                actual_mtd=100,
                monthly_target=100,
                cutoff_date=cutoff,
            ).to_dict(),
            "bajas": service.build_bajas_metric(
                actual_mtd=50,
                monthly_limit=100,
            ).to_dict(),
            "domiciliados": service.build_target_progress_metric(
                metric_key="domiciliados",
                actual_mtd=150,
                monthly_target=310,
            ).to_dict(),
        },
    }

    priorities = service._build_priorities(
        [
            {
                "region_key": "TEST_REGION",
                "region_label": "Test Region",
                "branches": [branch],
            }
        ],
        track_date=cutoff,
    )

    assert [
        group["metric_key"]
        for group in priorities
    ] == [
        "clientes_nuevos",
        "reactivaciones",
        "bajas",
        "domiciliados",
    ]

    domiciliados = priorities[3]["items"]

    assert len(domiciliados) == 1
    assert domiciliados[0]["sucursal_canon"] == "TEST_BRANCH"
    assert domiciliados[0]["actual_mtd"] == "150"
    assert domiciliados[0]["monthly_target"] == "310"

    assert (
        Decimal(domiciliados[0]["expected_progress_pct"])
        == Decimal(clientes_metric["expected_progress_pct"])
    )

    expected_mtd = (
        Decimal("310")
        * Decimal(clientes_metric["expected_progress_pct"])
        / Decimal("100")
    )

    assert Decimal(domiciliados[0]["expected_mtd"]) == expected_mtd
    assert domiciliados[0]["status"] == "DEBAJO_RITMO"

def test_gerente_sees_region_summary_but_only_own_branch_detail():
    track_date = date(2026, 8, 17)

    region_norte = SimpleNamespace(
        region_key="REGION_NORTE",
        region_label="Región Norte",
    )
    region_sur = SimpleNamespace(
        region_key="REGION_SUR",
        region_label="Región Sur",
    )

    rows = [
        (
            _mart_row(
                clientes_actual=Decimal("10"),
                bajas_actual=10,
            ),
            _branch(
                branch_id=101,
                canon="GERENTE_BRANCH",
                name="Sucursal gerente",
                order=1,
            ),
            region_norte,
        ),
        (
            _mart_row(
                clientes_actual=Decimal("20"),
                bajas_actual=20,
            ),
            _branch(
                branch_id=102,
                canon="OTHER_SAME_REGION",
                name="Otra misma región",
                order=2,
            ),
            region_norte,
        ),
        (
            _mart_row(
                clientes_actual=Decimal("30"),
                bajas_actual=30,
            ),
            _branch(
                branch_id=201,
                canon="OTHER_REGION",
                name="Otra región",
                order=3,
            ),
            region_sur,
        ),
    ]

    with patch.object(
        service,
        "resolve_effective_track_daily_version",
        return_value=SimpleNamespace(
            id=901,
            version_type="preview_operativo",
            status="success",
        ),
    ), patch.object(
        service,
        "_load_track_rows_with_region",
        return_value=rows,
    ), patch.object(
        service,
        "build_branch_income_projection_summary",
        return_value={
            "status": "insufficient_history",
            "projected_close": None,
        },
    ):
        result = service.get_regional_operational_detail(
            user=SimpleNamespace(
                rol="GERENTE",
                sucursal_id=101,
            ),
            track_date=track_date,
            generation_mode="manual_preview",
        )

    assert result["access"] == {
        "scope": "manager",
        "is_global": False,
    }

    assert len(result["regions"]) == 1

    region = result["regions"][0]

    assert region["region_key"] == "REGION_NORTE"

    # El consolidado sí representa toda su región.
    assert region["summary"]["total_branches"] == 2
    assert (
        region["summary"]["metrics"]["clientes_nuevos"]["actual_mtd"]
        == "30"
    )

    # El detalle sólo expone su propia sucursal.
    assert [
        branch["sucursal_canon"]
        for branch in region["branches"]
    ] == ["GERENTE_BRANCH"]

    # Las prioridades tampoco revelan otras sucursales.
    for priority_group in result["priorities"]:
        assert {
            item["sucursal_canon"]
            for item in priority_group["items"]
        } <= {"GERENTE_BRANCH"}


def test_region_income_projection_sums_all_available_branch_forecasts():
    projections = [
        (
            "VILLAS_DEL_REY",
            "791172.7181694691",
        ),
        (
            "VILLA_VERDE",
            "723497.8943661954",
        ),
        (
            "INDEPENDENCIA",
            "924048.9534239107",
        ),
        (
            "TEC_MXL",
            "887460.2043673072",
        ),
        (
            "SEND_MXL",
            "1387798.6921434574",
        ),
        (
            "SAN_LUIS",
            "727782.2716270635",
        ),
    ]

    branch_items = [
        {
            "sucursal_canon": sucursal_canon,
            "metrics": {
                "ingreso": {
                    "projection": {
                        "status": "available",
                        "projected_close": projected_close,
                    },
                },
            },
        }
        for sucursal_canon, projected_close in projections
    ]

    result = service._build_region_income_projection_summary(
        branch_items
    )

    assert result["status"] == "available"
    assert result["method"] == "sum_branch_income_projections"

    assert (
        Decimal(result["projected_close"])
        == Decimal("5441760.7340974033")
    )

    assert result["total_branches"] == 6
    assert result["available_branches"] == 6
    assert result["unavailable_branches_count"] == 0
    assert result["quality_issue"] is None


def test_region_income_projection_is_null_when_any_branch_is_unavailable():
    branch_items = [
        {
            "sucursal_canon": "VILLAS_DEL_REY",
            "metrics": {
                "ingreso": {
                    "projection": {
                        "status": "available",
                        "projected_close": "791172.7181694691",
                    },
                },
            },
        },
        {
            "sucursal_canon": "SERRANIA",
            "metrics": {
                "ingreso": {
                    "projection": {
                        "status": "insufficient_history",
                        "projected_close": None,
                    },
                },
            },
        },
    ]

    result = service._build_region_income_projection_summary(
        branch_items
    )

    assert result["status"] == "insufficient_history"
    assert result["method"] == "sum_branch_income_projections"
    assert result["projected_close"] is None

    assert result["total_branches"] == 2
    assert result["available_branches"] == 1
    assert result["unavailable_branches_count"] == 1

    assert result["quality_issue"]["code"] == (
        "incomplete_regional_projection"
    )
