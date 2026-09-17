from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.control_center.sales_composition import _build_analysis


def _row(
    index,
    kind,
    mode,
    group,
    branch,
    current_flow,
    comparison_flow,
    current_qty,
    comparison_qty,
):
    return SimpleNamespace(
        row_index=index,
        row_kind=kind,
        sales_mode=mode,
        family=group if mode == "NO_CONTRACT" else None,
        contract_type=group if mode == "CONTRACT" else None,
        plan_type="MES" if mode == "NO_CONTRACT" else None,
        tariff_name=f"Tarifa {index}",
        source_cost=Decimal("500"),
        monthly_equivalent=(
            Decimal("500")
            if mode == "NO_CONTRACT"
            else None
        ),
        free_months_raw=None,
        branch_raw=branch,
        current_quantity=Decimal(str(current_qty)),
        comparison_quantity=Decimal(str(comparison_qty)),
        current_flow=Decimal(str(current_flow)),
        comparison_flow=Decimal(str(comparison_flow)),
    )


def test_analysis_explains_mix_drivers_and_branch_movement():
    snapshot = SimpleNamespace(
        id=7,
        warehouse_upload_id=99,
        business_date=date(2026, 9, 16),
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 16),
        captured_at=datetime(2026, 9, 17, tzinfo=timezone.utc),
        is_canonical=True,
        current_label="01 al 16 septiembre",
        comparison_label="01 al 16 agosto",
        row_count_valid=6,
        data_quality={"reconciliation_status": "ok"},
    )
    rows = [
        _row(
            0,
            "TARIFF",
            "CONTRACT",
            "Contrato no forzoso",
            None,
            600,
            500,
            6,
            5,
        ),
        _row(
            1,
            "TARIFF",
            "NO_CONTRACT",
            "Convenio",
            None,
            300,
            200,
            3,
            2,
        ),
        _row(
            2,
            "TARIFF",
            "NO_CONTRACT",
            "Multi mes regular",
            None,
            100,
            200,
            1,
            2,
        ),
        _row(
            3,
            "BRANCH",
            "CONTRACT",
            "Contrato no forzoso",
            "A",
            400,
            300,
            4,
            3,
        ),
        _row(
            4,
            "BRANCH",
            "NO_CONTRACT",
            "Convenio",
            "A",
            200,
            100,
            2,
            1,
        ),
        _row(
            5,
            "BRANCH",
            "NO_CONTRACT",
            "Multi mes regular",
            "B",
            100,
            200,
            1,
            2,
        ),
    ]

    result = _build_analysis(snapshot=snapshot, rows=rows)

    assert result["summary"]["current_flow"] == 1000.0
    assert result["summary"]["comparison_flow"] == 900.0
    assert round(
        result["summary"]["contract_mix_delta_pp"],
        4,
    ) == round(60 - (500 / 900 * 100), 4)
    assert result["drivers"]["positive"][0]["label"] in {
        "Contrato no forzoso",
        "Convenio",
    }
    assert (
        result["drivers"]["negative"][0]["label"]
        == "Multi mes regular"
    )
    assert result["branches"][0]["branch"] == "A"
    assert result["data_quality"]["reconciliation_status"] == "ok"
