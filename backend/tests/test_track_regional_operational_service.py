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
            operational_status="ACTIVA",
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
    ), patch.object(
        service,
        "_load_branch_operational_histories_bulk",
        return_value={},
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
    ), patch.object(
        service,
        "_load_branch_operational_histories_bulk",
        return_value={},
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
    ), patch.object(
        service,
        "_load_branch_operational_histories_bulk",
        return_value={},
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


def test_global_scope_summary_consolidates_all_authorized_regions():
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
                canon="NORTE_01",
                name="Norte 01",
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
                canon="NORTE_02",
                name="Norte 02",
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
                canon="SUR_01",
                name="Sur 01",
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
    ), patch.object(
        service,
        "_load_branch_operational_histories_bulk",
        return_value={},
    ):
        result = service.get_regional_operational_detail(
            user=SimpleNamespace(
                rol="ADMIN",
                sucursal_id=None,
            ),
            track_date=track_date,
            generation_mode="manual_preview",
        )

    scope_summary = result["scope_summary"]

    assert scope_summary["scope"] == "global"
    assert scope_summary["total_branches"] == 3

    metrics = scope_summary["metrics"]

    assert metrics["clientes_nuevos"]["actual_mtd"] == "60"
    assert metrics["clientes_nuevos"]["monthly_target"] == "300"

    assert metrics["reactivaciones"]["actual_mtd"] == "120"
    assert metrics["reactivaciones"]["monthly_target"] == "300"

    assert metrics["bajas"]["actual_mtd"] == "60"
    assert metrics["bajas"]["monthly_limit"] == "570"

    assert metrics["domiciliados"]["actual_mtd"] == "90"
    assert metrics["domiciliados"]["monthly_target"] == "300"

    assert metrics["ingreso"]["actual_mtd"] == "240000"
    assert metrics["ingreso"]["monthly_target"] == "300000"

    assert metrics["tienda"]["actual_mtd"] == "60000"
    assert metrics["tienda"]["monthly_target"] == "90000"

    assert metrics["usuarios"]["current_users"] == "3000"
    assert metrics["usuarios"]["projected_close_users"] == "3300"
    assert metrics["usuarios"]["users_gap"] == "-300"


def test_operational_view_excludes_non_active_branches_from_summary_and_priorities():
    track_date = date(2026, 8, 17)

    region = SimpleNamespace(
        region_key="REGION_NORTE",
        region_label="Región Norte",
    )

    active_branch = _branch(
        branch_id=1,
        canon="ACTIVA_1",
        name="Activa 1",
        order=1,
    )
    active_branch.sucursal.operational_status = "ACTIVA"

    opening_branch = _branch(
        branch_id=2,
        canon="EN_APERTURA_1",
        name="En apertura 1",
        order=2,
    )
    opening_branch.sucursal.operational_status = "EN_APERTURA"

    rows = [
        (
            _mart_row(
                clientes_actual=Decimal("10"),
                bajas_actual=10,
            ),
            active_branch,
            region,
        ),
        (
            _mart_row(
                clientes_actual=Decimal("20"),
                bajas_actual=20,
            ),
            opening_branch,
            region,
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
    ), patch.object(
        service,
        "_load_branch_operational_histories_bulk",
        return_value={},
    ):
        result = service.get_regional_operational_detail(
            user=SimpleNamespace(
                rol="ADMIN",
                sucursal_id=None,
            ),
            track_date=track_date,
            generation_mode="manual_preview",
        )

    assert len(result["regions"]) == 1

    result_region = result["regions"][0]

    assert result_region["summary"]["total_branches"] == 1
    assert [
        branch["sucursal_canon"]
        for branch in result_region["branches"]
    ] == ["ACTIVA_1"]

    for priority_group in result["priorities"]:
        assert all(
            item["sucursal_canon"] != "EN_APERTURA_1"
            for item in priority_group["items"]
        )

def test_region_operational_projection_sums_branch_forecasts():
    branch_items = [
        {
            "sucursal_canon": "BRANCH_A",
            "metrics": {
                "clientes_nuevos": {
                    "monthly_target": "100",
                    "projection": {
                        "status": "available",
                        "projected_close": "80",
                        "projected_compliance_pct": "80",
                    },
                },
            },
        },
        {
            "sucursal_canon": "BRANCH_B",
            "metrics": {
                "clientes_nuevos": {
                    "monthly_target": "100",
                    "projection": {
                        "status": "available",
                        "projected_close": "70",
                        "projected_compliance_pct": "70",
                    },
                },
            },
        },
    ]

    result = service._build_region_operational_projection_summary(
        branch_items=branch_items,
        metric_key="clientes_nuevos",
    )

    assert result["status"] == "available"
    assert result["method"] == "sum_branch_operational_projections"

    assert Decimal(result["projected_close"]) == Decimal("150")
    assert Decimal(result["benchmark"]) == Decimal("200")
    assert Decimal(result["projected_compliance_pct"]) == Decimal("75")

    assert result["total_branches"] == 2
    assert result["available_branches"] == 2
    assert result["unavailable_branches_count"] == 0

def test_region_operational_projection_rejects_partial_coverage():
    branch_items = [
        {
            "sucursal_canon": "BRANCH_A",
            "metrics": {
                "clientes_nuevos": {
                    "monthly_target": "100",
                    "projection": {
                        "status": "available",
                        "projected_close": "80",
                    },
                },
            },
        },
        {
            "sucursal_canon": "BRANCH_B",
            "metrics": {
                "clientes_nuevos": {
                    "monthly_target": "100",
                    "projection": {
                        "status": "insufficient_history",
                        "projected_close": None,
                    },
                },
            },
        },
    ]

    result = service._build_region_operational_projection_summary(
        branch_items=branch_items,
        metric_key="clientes_nuevos",
    )

    assert result["status"] == "insufficient_history"
    assert result["method"] == "sum_branch_operational_projections"

    assert result["projected_close"] is None
    assert result["benchmark"] is None
    assert result["projected_compliance_pct"] is None

    assert result["total_branches"] == 2
    assert result["available_branches"] == 1
    assert result["unavailable_branches_count"] == 1

def test_regional_branch_clientes_nuevos_uses_shared_operational_projection():
    track_date = date(2026, 8, 10)

    branch_item = {
        "sucursal_canon": "BRANCH_A",
        "metrics": {
            "clientes_nuevos": {
                "actual_mtd": "40",
                "monthly_target": "100",
            },
        },
    }

    history = [
        {
            "track_date": f"2026-08-{day:02d}",
            "previous_track_date": f"2026-08-{day - 1:02d}",
            "days_since_previous": 1,
            "is_consecutive_previous_date": True,
            "metrics": {
                "clientes_nuevos": {
                    "daily_delta": "4",
                },
            },
        }
        for day in range(4, 11)
    ]

    result = service._attach_branch_operational_projection(
        branch_item=branch_item,
        history=history,
        metric_key="clientes_nuevos",
        cutoff_date=track_date,
    )

    projection = result["metrics"]["clientes_nuevos"]["projection"]

    assert projection["status"] == "available"
    assert (
        projection["method"]
        == "recent_valid_daily_average_7_calendar_days"
    )
    assert Decimal(projection["recent_daily_average"]) == Decimal("4")
    assert Decimal(projection["projected_close"]) == Decimal("124")
    assert (
        Decimal(projection["projected_compliance_pct"])
        == Decimal("124")
    )

def test_bulk_loader_queries_all_branches_and_versions_once():
    rows = [
        SimpleNamespace(
            sucursal_canon="BRANCH_A",
            track_daily_version_id=901,
        ),
        SimpleNamespace(
            sucursal_canon="BRANCH_B",
            track_daily_version_id=902,
        ),
    ]

    with patch.object(service.db.session, "query") as query:
        query.return_value.filter.return_value.all.return_value = rows

        result = service._load_branch_rows_for_versions_bulk(
            sucursal_canons=[
                "BRANCH_B",
                "BRANCH_A",
                "BRANCH_A",
            ],
            version_ids=[
                902,
                901,
                901,
            ],
        )

    query.assert_called_once_with(service.TrackDailyMartORM)
    query.return_value.filter.assert_called_once()

    assert set(result) == {
        ("BRANCH_A", 901),
        ("BRANCH_B", 902),
    }

    assert result[("BRANCH_A", 901)] is rows[0]
    assert result[("BRANCH_B", 902)] is rows[1]

def test_bulk_loader_rejects_duplicate_branch_version_rows():
    rows = [
        SimpleNamespace(
            sucursal_canon="BRANCH_A",
            track_daily_version_id=901,
        ),
        SimpleNamespace(
            sucursal_canon="BRANCH_A",
            track_daily_version_id=901,
        ),
    ]

    with patch.object(service.db.session, "query") as query:
        query.return_value.filter.return_value.all.return_value = rows

        with pytest.raises(
            service.TrackRegionalOperationalDataError,
            match="más de una fila",
        ):
            service._load_branch_rows_for_versions_bulk(
                sucursal_canons=["BRANCH_A"],
                version_ids=[901],
            )

def test_build_branch_operational_history_calculates_consecutive_daily_deltas():
    calendar_dates = [
        date(2026, 8, 8),
        date(2026, 8, 9),
        date(2026, 8, 10),
    ]
    resolved_versions = {
        date(2026, 8, 8): SimpleNamespace(id=908),
        date(2026, 8, 9): SimpleNamespace(id=909),
        date(2026, 8, 10): SimpleNamespace(id=910),
    }

    rows_by_branch_version = {}

    for calendar_date, version_id, actual in [
        (date(2026, 8, 8), 908, Decimal("30")),
        (date(2026, 8, 9), 909, Decimal("34")),
        (date(2026, 8, 10), 910, Decimal("40")),
    ]:
        row = _mart_row(
            clientes_actual=actual,
            bajas_actual=Decimal("10"),
        )
        row.track_date = calendar_date
        row.track_daily_version_id = version_id

        rows_by_branch_version[
            ("BRANCH_A", version_id)
        ] = row

    history, missing_dates = (
        service._build_branch_operational_history(
            sucursal_canon="BRANCH_A",
            calendar_dates=calendar_dates,
            resolved_versions=resolved_versions,
            rows_by_branch_version=rows_by_branch_version,
            target_month=date(2026, 8, 1),
        )
    )

    assert missing_dates == []
    assert [point["track_date"] for point in history] == [
        "2026-08-08",
        "2026-08-09",
        "2026-08-10",
    ]

    assert history[0]["previous_track_date"] is None
    assert history[0]["days_since_previous"] is None
    assert history[0]["is_consecutive_previous_date"] is False
    assert (
        history[0]["metrics"]["clientes_nuevos"]["daily_delta"]
        is None
    )

    assert history[1]["previous_track_date"] == "2026-08-08"
    assert history[1]["days_since_previous"] == 1
    assert history[1]["is_consecutive_previous_date"] is True
    assert Decimal(
        history[1]["metrics"]["clientes_nuevos"]["daily_delta"]
    ) == Decimal("4")

    assert history[2]["previous_track_date"] == "2026-08-09"
    assert history[2]["days_since_previous"] == 1
    assert history[2]["is_consecutive_previous_date"] is True
    assert Decimal(
        history[2]["metrics"]["clientes_nuevos"]["daily_delta"]
    ) == Decimal("6")

def test_build_branch_operational_history_marks_gap_as_non_consecutive():
    calendar_dates = [
        date(2026, 8, 8),
        date(2026, 8, 9),
        date(2026, 8, 10),
    ]
    resolved_versions = {
        date(2026, 8, 8): SimpleNamespace(id=908),
        date(2026, 8, 9): SimpleNamespace(id=909),
        date(2026, 8, 10): SimpleNamespace(id=910),
    }

    row_08 = _mart_row(
        clientes_actual=Decimal("30"),
        bajas_actual=Decimal("10"),
    )
    row_08.track_date = date(2026, 8, 8)
    row_08.track_daily_version_id = 908

    row_10 = _mart_row(
        clientes_actual=Decimal("40"),
        bajas_actual=Decimal("10"),
    )
    row_10.track_date = date(2026, 8, 10)
    row_10.track_daily_version_id = 910

    rows_by_branch_version = {
        ("BRANCH_A", 908): row_08,
        ("BRANCH_A", 910): row_10,
    }

    history, missing_dates = (
        service._build_branch_operational_history(
            sucursal_canon="BRANCH_A",
            calendar_dates=calendar_dates,
            resolved_versions=resolved_versions,
            rows_by_branch_version=rows_by_branch_version,
            target_month=date(2026, 8, 1),
        )
    )

    assert missing_dates == ["2026-08-09"]
    assert len(history) == 2

    point = history[1]

    assert point["track_date"] == "2026-08-10"
    assert point["previous_track_date"] == "2026-08-08"
    assert point["days_since_previous"] == 2
    assert point["is_consecutive_previous_date"] is False

    assert Decimal(
        point["metrics"]["clientes_nuevos"]["daily_delta"]
    ) == Decimal("10")

def test_regional_projection_ignores_non_consecutive_daily_delta():
    calendar_dates = [
        date(2026, 8, day)
        for day in range(4, 11)
    ]

    resolved_versions = {
        calendar_date: SimpleNamespace(
            id=900 + calendar_date.day
        )
        for calendar_date in calendar_dates
    }

    actual_by_day = {
        4: Decimal("10"),
        5: Decimal("12"),
        6: Decimal("14"),
        8: Decimal("30"),
        9: Decimal("32"),
        10: Decimal("34"),
    }

    rows_by_branch_version = {}

    for day, actual in actual_by_day.items():
        calendar_date = date(2026, 8, day)
        version_id = 900 + day

        row = _mart_row(
            clientes_actual=actual,
            bajas_actual=Decimal("10"),
        )
        row.track_date = calendar_date
        row.track_daily_version_id = version_id

        rows_by_branch_version[
            ("BRANCH_A", version_id)
        ] = row

    history, missing_dates = (
        service._build_branch_operational_history(
            sucursal_canon="BRANCH_A",
            calendar_dates=calendar_dates,
            resolved_versions=resolved_versions,
            rows_by_branch_version=rows_by_branch_version,
            target_month=date(2026, 8, 1),
        )
    )

    assert missing_dates == ["2026-08-07"]

    gap_point = next(
        point
        for point in history
        if point["track_date"] == "2026-08-08"
    )

    assert gap_point["days_since_previous"] == 2
    assert gap_point["is_consecutive_previous_date"] is False
    assert Decimal(
        gap_point["metrics"]["clientes_nuevos"]["daily_delta"]
    ) == Decimal("16")

    branch_item = {
        "sucursal_canon": "BRANCH_A",
        "metrics": {
            "clientes_nuevos": {
                "actual_mtd": "34",
                "monthly_target": "100",
            },
        },
    }

    result = service._attach_branch_operational_projection(
        branch_item=branch_item,
        history=history,
        metric_key="clientes_nuevos",
        cutoff_date=date(2026, 8, 10),
    )

    projection = result["metrics"]["clientes_nuevos"]["projection"]

    assert projection["status"] == "available"
    assert projection["valid_daily_deltas"] == 4
    assert Decimal(
        projection["recent_daily_average"]
    ) == Decimal("2")
    assert Decimal(
        projection["projected_close"]
    ) == Decimal("76")

def test_load_branch_operational_histories_bulk_uses_current_resolved_version_for_cutoff():
    track_date = date(2026, 8, 3)
    current_version = SimpleNamespace(id=903)

    historical_versions = {
        date(2026, 8, 1): SimpleNamespace(id=901),
        date(2026, 8, 2): SimpleNamespace(id=902),
    }

    def resolve_history_version(*, track_date):
        assert track_date != date(2026, 8, 3)
        return historical_versions.get(track_date)

    def build_history(**kwargs):
        assert kwargs["calendar_dates"] == [
            date(2026, 8, 1),
            date(2026, 8, 2),
            date(2026, 8, 3),
        ]
        assert kwargs["resolved_versions"][date(2026, 8, 1)].id == 901
        assert kwargs["resolved_versions"][date(2026, 8, 2)].id == 902
        assert (
            kwargs["resolved_versions"][date(2026, 8, 3)]
            is current_version
        )
        assert kwargs["target_month"] == date(2026, 8, 1)

        return (
            [
                {
                    "track_date": "2026-08-03",
                    "metrics": {},
                }
            ],
            [],
        )

    fake_rows = {
        ("BRANCH_A", 901): object(),
        ("BRANCH_A", 902): object(),
        ("BRANCH_A", 903): object(),
    }

    with patch.object(
        service,
        "resolve_preferred_track_daily_version",
        side_effect=resolve_history_version,
        create=True,
    ) as resolve_history, patch.object(
        service,
        "_load_branch_rows_for_versions_bulk",
        return_value=fake_rows,
    ) as load_rows, patch.object(
        service,
        "_build_branch_operational_history",
        side_effect=build_history,
    ) as build_branch_history:
        result = service._load_branch_operational_histories_bulk(
            track_date=track_date,
            current_version=current_version,
            sucursal_canons=[
                "BRANCH_B",
                "BRANCH_A",
                "BRANCH_A",
            ],
        )

    assert resolve_history.call_count == 2
    assert [
        item.kwargs["track_date"]
        for item in resolve_history.call_args_list
    ] == [
        date(2026, 8, 1),
        date(2026, 8, 2),
    ]

    load_rows.assert_called_once()

    loader_kwargs = load_rows.call_args.kwargs

    assert loader_kwargs["sucursal_canons"] == [
        "BRANCH_A",
        "BRANCH_B",
    ]
    assert set(loader_kwargs["version_ids"]) == {
        901,
        902,
        903,
    }

    assert build_branch_history.call_count == 2
    assert set(result) == {
        "BRANCH_A",
        "BRANCH_B",
    }

    assert result["BRANCH_A"]["missing_dates"] == []
    assert result["BRANCH_B"]["missing_dates"] == []

def test_regional_detail_attaches_clientes_nuevos_projection_from_bulk_history():
    track_date = date(2026, 8, 10)
    resolved_version = SimpleNamespace(
        id=910,
        version_type="preview_operativo",
        status="success",
    )

    mart = _mart_row(
        clientes_actual=Decimal("40"),
        bajas_actual=Decimal("10"),
    )
    mart.track_date = track_date
    mart.track_daily_version_id = 910

    branch = _branch(
        branch_id=1,
        canon="BRANCH_A",
        name="Sucursal A",
        order=1,
    )
    branch.sucursal.operational_status = (
        service.SucursalOperationalStatus.ACTIVA
    )

    region = SimpleNamespace(
        region_key="REGION_TEST",
        region_label="Región Test",
    )

    history = [
        {
            "track_date": f"2026-08-{day:02d}",
            "previous_track_date": f"2026-08-{day - 1:02d}",
            "days_since_previous": 1,
            "is_consecutive_previous_date": True,
            "metrics": {
                "clientes_nuevos": {
                    "daily_delta": "4",
                },
            },
        }
        for day in range(4, 11)
    ]

    with patch.object(
        service,
        "resolve_effective_track_daily_version",
        return_value=resolved_version,
    ), patch.object(
        service,
        "_load_track_rows_with_region",
        return_value=[
            (
                mart,
                branch,
                region,
            ),
        ],
    ), patch.object(
        service,
        "build_branch_income_projection_summary",
        return_value={
            "status": "insufficient_history",
            "projected_close": None,
        },
    ), patch.object(
        service,
        "_load_branch_operational_histories_bulk",
        return_value={
            "BRANCH_A": {
                "history": history,
                "missing_dates": [],
            },
        },
    ) as load_histories:
        result = service.get_regional_operational_detail(
            user=SimpleNamespace(
                rol="ADMIN",
                sucursal_id=None,
            ),
            track_date=track_date,
            generation_mode="manual_preview",
        )

    load_histories.assert_called_once_with(
        track_date=track_date,
        current_version=resolved_version,
        sucursal_canons=["BRANCH_A"],
    )

    branch_metric = (
        result["regions"][0]
        ["branches"][0]
        ["metrics"]["clientes_nuevos"]
    )

    assert branch_metric["projection"]["status"] == "available"
    assert Decimal(
        branch_metric["projection"]["projected_close"]
    ) == Decimal("124")
    assert Decimal(
        branch_metric["projection"]["projected_compliance_pct"]
    ) == Decimal("124")

    region_metric = (
        result["regions"][0]
        ["summary"]["metrics"]["clientes_nuevos"]
    )

    assert region_metric["projection"]["status"] == "available"
    assert Decimal(
        region_metric["projection"]["projected_close"]
    ) == Decimal("124")
    assert Decimal(
        region_metric["projection"]["benchmark"]
    ) == Decimal("100")
    assert Decimal(
        region_metric["projection"]["projected_compliance_pct"]
    ) == Decimal("124")

def test_regional_detail_attaches_reactivaciones_projection_from_bulk_history():
    track_date = date(2026, 8, 10)
    resolved_version = SimpleNamespace(
        id=910,
        version_type="preview_operativo",
        status="success",
    )

    mart = _mart_row(
        clientes_actual=Decimal("40"),
        bajas_actual=Decimal("10"),
    )
    mart.track_date = track_date
    mart.track_daily_version_id = 910
    mart.reactivaciones_real_mtd = Decimal("40")
    mart.meta_reactivaciones_mes = Decimal("100")

    branch = _branch(
        branch_id=1,
        canon="BRANCH_A",
        name="Sucursal A",
        order=1,
    )
    branch.sucursal.operational_status = (
        service.SucursalOperationalStatus.ACTIVA
    )

    region = SimpleNamespace(
        region_key="REGION_TEST",
        region_label="Región Test",
    )

    history = [
        {
            "track_date": f"2026-08-{day:02d}",
            "previous_track_date": f"2026-08-{day - 1:02d}",
            "days_since_previous": 1,
            "is_consecutive_previous_date": True,
            "metrics": {
                "clientes_nuevos": {
                    "daily_delta": "4",
                },
                "reactivaciones": {
                    "daily_delta": "3",
                },
            },
        }
        for day in range(4, 11)
    ]

    with patch.object(
        service,
        "resolve_effective_track_daily_version",
        return_value=resolved_version,
    ), patch.object(
        service,
        "_load_track_rows_with_region",
        return_value=[
            (
                mart,
                branch,
                region,
            ),
        ],
    ), patch.object(
        service,
        "build_branch_income_projection_summary",
        return_value={
            "status": "insufficient_history",
            "projected_close": None,
        },
    ), patch.object(
        service,
        "_load_branch_operational_histories_bulk",
        return_value={
            "BRANCH_A": {
                "history": history,
                "missing_dates": [],
            },
        },
    ):
        result = service.get_regional_operational_detail(
            user=SimpleNamespace(
                rol="ADMIN",
                sucursal_id=None,
            ),
            track_date=track_date,
            generation_mode="manual_preview",
        )

    branch_metric = (
        result["regions"][0]
        ["branches"][0]
        ["metrics"]["reactivaciones"]
    )

    assert branch_metric["projection"]["status"] == "available"
    assert Decimal(
        branch_metric["projection"]["recent_daily_average"]
    ) == Decimal("3")
    assert Decimal(
        branch_metric["projection"]["projected_close"]
    ) == Decimal("103")
    assert Decimal(
        branch_metric["projection"]["projected_compliance_pct"]
    ) == Decimal("103")

    region_metric = (
        result["regions"][0]
        ["summary"]["metrics"]["reactivaciones"]
    )

    assert region_metric["projection"]["status"] == "available"
    assert Decimal(
        region_metric["projection"]["projected_close"]
    ) == Decimal("103")
    assert Decimal(
        region_metric["projection"]["benchmark"]
    ) == Decimal("100")
    assert Decimal(
        region_metric["projection"]["projected_compliance_pct"]
    ) == Decimal("103")

def test_regional_detail_attaches_domiciliados_projection_from_bulk_history():
    track_date = date(2026, 8, 10)
    resolved_version = SimpleNamespace(
        id=910,
        version_type="preview_operativo",
        status="success",
    )

    mart = _mart_row(
        clientes_actual=Decimal("40"),
        bajas_actual=Decimal("10"),
        domiciliados_actual=Decimal("50"),
        domiciliados_target=Decimal("100"),
    )
    mart.track_date = track_date
    mart.track_daily_version_id = 910

    branch = _branch(
        branch_id=1,
        canon="BRANCH_A",
        name="Sucursal A",
        order=1,
    )
    branch.sucursal.operational_status = (
        service.SucursalOperationalStatus.ACTIVA
    )

    region = SimpleNamespace(
        region_key="REGION_TEST",
        region_label="Región Test",
    )

    history = [
        {
            "track_date": f"2026-08-{day:02d}",
            "previous_track_date": f"2026-08-{day - 1:02d}",
            "days_since_previous": 1,
            "is_consecutive_previous_date": True,
            "metrics": {
                "clientes_nuevos": {
                    "daily_delta": "4",
                },
                "reactivaciones": {
                    "daily_delta": "3",
                },
                "domiciliados": {
                    "daily_delta": "2",
                },
            },
        }
        for day in range(4, 11)
    ]

    with patch.object(
        service,
        "resolve_effective_track_daily_version",
        return_value=resolved_version,
    ), patch.object(
        service,
        "_load_track_rows_with_region",
        return_value=[
            (
                mart,
                branch,
                region,
            ),
        ],
    ), patch.object(
        service,
        "build_branch_income_projection_summary",
        return_value={
            "status": "insufficient_history",
            "projected_close": None,
        },
    ), patch.object(
        service,
        "_load_branch_operational_histories_bulk",
        return_value={
            "BRANCH_A": {
                "history": history,
                "missing_dates": [],
            },
        },
    ):
        result = service.get_regional_operational_detail(
            user=SimpleNamespace(
                rol="ADMIN",
                sucursal_id=None,
            ),
            track_date=track_date,
            generation_mode="manual_preview",
        )

    branch_metric = (
        result["regions"][0]
        ["branches"][0]
        ["metrics"]["domiciliados"]
    )

    assert branch_metric["projection"]["status"] == "available"
    assert Decimal(
        branch_metric["projection"]["recent_daily_average"]
    ) == Decimal("2")
    assert Decimal(
        branch_metric["projection"]["projected_close"]
    ) == Decimal("92")
    assert Decimal(
        branch_metric["projection"]["projected_compliance_pct"]
    ) == Decimal("92")

    region_metric = (
        result["regions"][0]
        ["summary"]["metrics"]["domiciliados"]
    )

    assert region_metric["projection"]["status"] == "available"
    assert Decimal(
        region_metric["projection"]["projected_close"]
    ) == Decimal("92")
    assert Decimal(
        region_metric["projection"]["benchmark"]
    ) == Decimal("100")
    assert Decimal(
        region_metric["projection"]["projected_compliance_pct"]
    ) == Decimal("92")

def test_branch_bajas_projection_uses_monthly_limit_as_benchmark():
    history = [
        {
            "track_date": f"2026-08-{day:02d}",
            "previous_track_date": f"2026-08-{day - 1:02d}",
            "days_since_previous": 1,
            "is_consecutive_previous_date": True,
            "metrics": {
                "bajas": {
                    "daily_delta": "3",
                },
            },
        }
        for day in range(4, 11)
    ]

    branch_item = {
        "sucursal_canon": "BRANCH_A",
        "metrics": {
            "bajas": {
                "actual_mtd": "40",
                "monthly_limit": "100",
            },
        },
    }

    result = service._attach_branch_operational_projection(
        branch_item=branch_item,
        history=history,
        metric_key="bajas",
        cutoff_date=date(2026, 8, 10),
    )

    projection = result["metrics"]["bajas"]["projection"]

    assert projection["status"] == "available"
    assert Decimal(
        projection["recent_daily_average"]
    ) == Decimal("3")
    assert Decimal(
        projection["projected_close"]
    ) == Decimal("103")
    assert Decimal(
        projection["projected_limit_usage_pct"]
    ) == Decimal("103")
    assert Decimal(
        projection["projected_excess_units"]
    ) == Decimal("3")
    assert Decimal(
        projection["projected_remaining_margin"]
    ) == Decimal("0")

def test_region_bajas_projection_uses_limits_and_inverse_semantics():
    branch_items = [
        {
            "sucursal_canon": "BRANCH_A",
            "metrics": {
                "bajas": {
                    "actual_mtd": "40",
                    "monthly_limit": "100",
                    "projection": {
                        "status": "available",
                        "projected_close": "95",
                    },
                },
            },
        },
        {
            "sucursal_canon": "BRANCH_B",
            "metrics": {
                "bajas": {
                    "actual_mtd": "30",
                    "monthly_limit": "50",
                    "projection": {
                        "status": "available",
                        "projected_close": "70",
                    },
                },
            },
        },
    ]

    result = service._build_region_operational_projection_summary(
        branch_items=branch_items,
        metric_key="bajas",
    )

    assert result["status"] == "available"
    assert (
        result["method"]
        == "sum_branch_operational_projections"
    )
    assert Decimal(result["projected_close"]) == Decimal("165")
    assert Decimal(result["benchmark"]) == Decimal("150")
    assert Decimal(
        result["projected_limit_usage_pct"]
    ) == Decimal("110")
    assert Decimal(
        result["projected_excess_units"]
    ) == Decimal("15")
    assert Decimal(
        result["projected_remaining_margin"]
    ) == Decimal("0")

    assert "projected_compliance_pct" not in result

    assert result["total_branches"] == 2
    assert result["available_branches"] == 2
    assert result["unavailable_branches_count"] == 0

def test_regional_detail_attaches_bajas_projection_from_bulk_history():
    track_date = date(2026, 8, 10)

    resolved_version = SimpleNamespace(
        id=910,
        version_type="preview_operativo",
        status="success",
    )

    mart = _mart_row(
        clientes_actual=Decimal("40"),
        bajas_actual=Decimal("40"),
    )
    mart.track_date = track_date
    mart.track_daily_version_id = 910
    mart.meta_bajas_mes = Decimal("100")

    branch = _branch(
        branch_id=1,
        canon="BRANCH_A",
        name="Sucursal A",
        order=1,
    )
    branch.sucursal.operational_status = (
        service.SucursalOperationalStatus.ACTIVA
    )

    region = SimpleNamespace(
        region_key="REGION_TEST",
        region_label="Región Test",
    )

    history = [
        {
            "track_date": f"2026-08-{day:02d}",
            "previous_track_date": f"2026-08-{day - 1:02d}",
            "days_since_previous": 1,
            "is_consecutive_previous_date": True,
            "metrics": {
                "clientes_nuevos": {
                    "daily_delta": "4",
                },
                "reactivaciones": {
                    "daily_delta": "3",
                },
                "domiciliados": {
                    "daily_delta": "2",
                },
                "bajas": {
                    "daily_delta": "3",
                },
            },
        }
        for day in range(4, 11)
    ]

    with patch.object(
        service,
        "resolve_effective_track_daily_version",
        return_value=resolved_version,
    ), patch.object(
        service,
        "_load_track_rows_with_region",
        return_value=[
            (
                mart,
                branch,
                region,
            ),
        ],
    ), patch.object(
        service,
        "build_branch_income_projection_summary",
        return_value={
            "status": "insufficient_history",
            "projected_close": None,
        },
    ), patch.object(
        service,
        "_load_branch_operational_histories_bulk",
        return_value={
            "BRANCH_A": {
                "history": history,
                "missing_dates": [],
            },
        },
    ):
        result = service.get_regional_operational_detail(
            user=SimpleNamespace(
                rol="ADMIN",
                sucursal_id=None,
            ),
            track_date=track_date,
            generation_mode="manual_preview",
        )

    branch_metric = (
        result["regions"][0]
        ["branches"][0]
        ["metrics"]["bajas"]
    )

    assert branch_metric["projection"]["status"] == "available"
    assert Decimal(
        branch_metric["projection"]["recent_daily_average"]
    ) == Decimal("3")
    assert Decimal(
        branch_metric["projection"]["projected_close"]
    ) == Decimal("103")
    assert Decimal(
        branch_metric["projection"]["projected_limit_usage_pct"]
    ) == Decimal("103")
    assert Decimal(
        branch_metric["projection"]["projected_excess_units"]
    ) == Decimal("3")
    assert Decimal(
        branch_metric["projection"]["projected_remaining_margin"]
    ) == Decimal("0")

    region_metric = (
        result["regions"][0]
        ["summary"]["metrics"]["bajas"]
    )

    assert region_metric["projection"]["status"] == "available"
    assert Decimal(
        region_metric["projection"]["projected_close"]
    ) == Decimal("103")
    assert Decimal(
        region_metric["projection"]["benchmark"]
    ) == Decimal("100")
    assert Decimal(
        region_metric["projection"]["projected_limit_usage_pct"]
    ) == Decimal("103")
    assert Decimal(
        region_metric["projection"]["projected_excess_units"]
    ) == Decimal("3")
    assert Decimal(
        region_metric["projection"]["projected_remaining_margin"]
    ) == Decimal("0")

    assert (
        "projected_compliance_pct"
        not in region_metric["projection"]
    )

def test_region_income_projection_includes_goal_compliance():
    branch_items = [
        {
            "sucursal_canon": "BRANCH_A",
            "metrics": {
                "ingreso": {
                    "monthly_target": "100",
                    "projection": {
                        "status": "available",
                        "projected_close": "120",
                    },
                },
            },
        },
        {
            "sucursal_canon": "BRANCH_B",
            "metrics": {
                "ingreso": {
                    "monthly_target": "200",
                    "projection": {
                        "status": "available",
                        "projected_close": "180",
                    },
                },
            },
        },
    ]

    result = service._build_region_income_projection_summary(
        branch_items
    )

    assert result["status"] == "available"
    assert (
        result["method"]
        == "sum_branch_income_projections"
    )
    assert Decimal(
        result["projected_close"]
    ) == Decimal("300")
    assert Decimal(
        result["benchmark"]
    ) == Decimal("300")
    assert Decimal(
        result["projected_compliance_pct"]
    ) == Decimal("100")
    assert result["total_branches"] == 2
    assert result["available_branches"] == 2
    assert result["unavailable_branches_count"] == 0

def test_region_income_projection_survives_partial_goal_coverage():
    branch_items = [
        {
            "sucursal_canon": "BRANCH_A",
            "metrics": {
                "ingreso": {
                    "monthly_target": "100",
                    "projection": {
                        "status": "available",
                        "projected_close": "120",
                    },
                },
            },
        },
        {
            "sucursal_canon": "BRANCH_B",
            "metrics": {
                "ingreso": {
                    "monthly_target": None,
                    "projection": {
                        "status": "available",
                        "projected_close": "180",
                    },
                },
            },
        },
    ]

    result = service._build_region_income_projection_summary(
        branch_items
    )

    assert result["status"] == "available"
    assert Decimal(
        result["projected_close"]
    ) == Decimal("300")

    assert result["benchmark"] is None
    assert result["projected_compliance_pct"] is None

    assert result["total_branches"] == 2
    assert result["available_branches"] == 2
    assert result["unavailable_branches_count"] == 0
    assert result["quality_issue"] is None