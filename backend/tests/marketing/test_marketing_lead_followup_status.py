from datetime import date
from types import SimpleNamespace

from app.services.marketing_sales_funnel_detail_service import (
    _enrich_lead_followup_rows,
)


def _lead(*, branch_id: int, phone: str, lead_date: str) -> dict:
    return {
        "branch_id": branch_id,
        "branch": f"Sucursal {branch_id}",
        "date": lead_date,
        "name": "Lead",
        "phone": phone,
    }


def _visit(*, branch_id: int, phone: str, visit_date: date):
    return SimpleNamespace(
        branch_id=branch_id,
        phone=phone,
        visit_date=visit_date,
    )


def _sale(*, branch_id: int, phone: str, sale_date: date):
    return SimpleNamespace(
        branch_id=branch_id,
        phone=phone,
        sale_date=sale_date,
    )


def test_enrich_lead_followup_rows_builds_call_center_segments():
    rows = [
        _lead(branch_id=1, phone="6861111111", lead_date="2026-09-01"),
        _lead(branch_id=1, phone="6862222222", lead_date="2026-09-01"),
        _lead(branch_id=1, phone="6863333333", lead_date="2026-09-01"),
    ]
    visits = [
        _visit(
            branch_id=1,
            phone="6861111111",
            visit_date=date(2026, 9, 4),
        ),
        _visit(
            branch_id=1,
            phone="6862222222",
            visit_date=date(2026, 9, 5),
        ),
    ]
    sales = [
        _sale(
            branch_id=2,
            phone="6861111111",
            sale_date=date(2026, 9, 8),
        ),
    ]

    enriched = _enrich_lead_followup_rows(
        rows,
        visits=visits,
        sales=sales,
        global_branch_names={
            1: "Villas del Rey",
            2: "Tecnológico",
        },
        visible_branch_ids=(1, 2),
    )

    assert enriched[0]["visit_status"] == "Sí"
    assert enriched[0]["visit_date"] == "2026-09-04"
    assert enriched[0]["purchase_status"] == "Sí"
    assert enriched[0]["sale_date"] == "2026-09-08"
    assert enriched[0]["purchase_branch"] == "Tecnológico"
    assert enriched[0]["followup_status"] == "Ya compró"

    assert enriched[1]["visit_status"] == "Sí"
    assert enriched[1]["purchase_status"] == "No"
    assert enriched[1]["purchase_branch"] is None
    assert enriched[1]["followup_status"] == "Visita sin compra"

    assert enriched[2]["visit_status"] == "No"
    assert enriched[2]["purchase_status"] == "No"
    assert enriched[2]["followup_status"] == "Sin visita / sin compra"


def test_global_purchase_window_is_60_days_and_cutoff_is_respected():
    rows = [
        _lead(branch_id=1, phone="6864444444", lead_date="2026-09-01"),
        _lead(branch_id=1, phone="6865555555", lead_date="2026-09-01"),
        _lead(branch_id=1, phone="6866666666", lead_date="2026-09-01"),
    ]
    visits = [
        _visit(
            branch_id=1,
            phone="6864444444",
            visit_date=date(2026, 9, 10),
        ),
        _visit(
            branch_id=1,
            phone="6865555555",
            visit_date=date(2026, 10, 2),
        ),
    ]
    sales = [
        _sale(
            branch_id=2,
            phone="6864444444",
            sale_date=date(2026, 9, 12),
        ),
        _sale(
            branch_id=2,
            phone="6865555555",
            sale_date=date(2026, 10, 3),
        ),
        _sale(
            branch_id=2,
            phone="6866666666",
            sale_date=date(2026, 11, 1),
        ),
    ]

    cutoff_rows = _enrich_lead_followup_rows(
        rows,
        visits=visits,
        sales=sales,
        global_branch_names={2: "Tecnológico"},
        visible_branch_ids=(1, 2),
        cutoff_date=date(2026, 9, 8),
    )

    assert cutoff_rows[0]["followup_status"] == "Sin visita / sin compra"
    assert cutoff_rows[1]["followup_status"] == "Sin visita / sin compra"
    assert cutoff_rows[2]["followup_status"] == "Sin visita / sin compra"

    full_rows = _enrich_lead_followup_rows(
        rows,
        visits=visits,
        sales=sales,
        global_branch_names={2: "Tecnológico"},
        visible_branch_ids=(1, 2),
    )

    assert full_rows[0]["followup_status"] == "Ya compró"
    assert full_rows[1]["purchase_status"] == "Sí"
    assert full_rows[1]["sale_date"] == "2026-10-03"
    assert full_rows[1]["followup_status"] == "Ya compró"
    assert full_rows[2]["purchase_status"] == "No"
    assert full_rows[2]["followup_status"] == "Sin visita / sin compra"


def test_purchase_branch_is_hidden_when_outside_visible_scope():
    enriched = _enrich_lead_followup_rows(
        [_lead(branch_id=1, phone="6867777777", lead_date="2026-09-01")],
        visits=[],
        sales=[
            _sale(
                branch_id=2,
                phone="6867777777",
                sale_date=date(2026, 9, 20),
            )
        ],
        global_branch_names={2: "Tecnológico"},
        visible_branch_ids=(1,),
    )

    assert enriched[0]["purchase_status"] == "Sí"
    assert enriched[0]["purchase_branch"] == "Otra sucursal Ultra"
    assert enriched[0]["followup_status"] == "Ya compró"
