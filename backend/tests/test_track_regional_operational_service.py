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


def test_priorities_include_domiciliados_with_linear_pace():
    from datetime import date
    from decimal import Decimal

    from app.track_alerts.services import (
        track_regional_operational_service as service,
    )

    cutoff = date(2026, 8, 18)

    branch = {
        "sucursal_canon": "TEST_BRANCH",
        "sucursal_name": "Test Branch",
        "metrics": {
            "clientes_nuevos": service.build_clientes_nuevos_metric(
                actual_mtd=100,
                monthly_target=100,
                cutoff_date=cutoff,
            ).to_dict(),
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
    assert Decimal(domiciliados[0]["expected_mtd"]) == Decimal("180")
    assert domiciliados[0]["status"] == "DEBAJO_RITMO"
