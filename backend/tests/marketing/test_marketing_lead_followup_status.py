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
            branch_id=1,
            phone="6861111111",
            sale_date=date(2026, 9, 8),
        ),
    ]

    enriched = _enrich_lead_followup_rows(
        rows,
        visits=visits,
        sales=sales,
    )

    assert enriched[0]["visit_status"] == "Sí"
    assert enriched[0]["visit_date"] == "2026-09-04"
    assert enriched[0]["purchase_status"] == "Sí"
    assert enriched[0]["sale_date"] == "2026-09-08"
    assert enriched[0]["followup_status"] == "Ya compró"

    assert enriched[1]["visit_status"] == "Sí"
    assert enriched[1]["purchase_status"] == "No"
    assert enriched[1]["followup_status"] == "Visita sin compra"

    assert enriched[2]["visit_status"] == "No"
    assert enriched[2]["purchase_status"] == "No"
    assert enriched[2]["followup_status"] == "Sin visita / sin compra"


def test_enrich_lead_followup_rows_respects_cutoff_and_match_window():
    rows = [
        _lead(branch_id=1, phone="6864444444", lead_date="2026-09-01"),
        _lead(branch_id=1, phone="6865555555", lead_date="2026-09-01"),
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
            branch_id=1,
            phone="6864444444",
            sale_date=date(2026, 9, 12),
        ),
        _sale(
            branch_id=1,
            phone="6865555555",
            sale_date=date(2026, 10, 3),
        ),
    ]

    cutoff_rows = _enrich_lead_followup_rows(
        rows,
        visits=visits,
        sales=sales,
        cutoff_date=date(2026, 9, 8),
    )

    assert cutoff_rows[0]["followup_status"] == "Sin visita / sin compra"
    assert cutoff_rows[1]["followup_status"] == "Sin visita / sin compra"

    full_rows = _enrich_lead_followup_rows(
        rows,
        visits=visits,
        sales=sales,
    )

    assert full_rows[0]["followup_status"] == "Ya compró"
    assert full_rows[1]["followup_status"] == "Sin visita / sin compra"
