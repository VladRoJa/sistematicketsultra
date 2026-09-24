from app.routes.marketing_sales_funnel_routes import (
    _apply_unavailable_crm_visit_conversion,
)


def test_historical_visit_conversion_is_null_without_touching_totals():
    result = {
        "summary": {
            "visits_total": 3604,
            "sales_total": 2497,
            "revenue_total": 2105250.0,
            "visits_iventas_bought": 12,
            "visits_iventas_not_bought": 8,
            "visits_not_iventas_bought": 40,
            "visits_not_iventas_not_bought": 100,
            "iventas_visit_conversion_rate": 0.6,
            "not_iventas_visit_conversion_rate": 0.285,
        },
        "branches": [
            {
                "sucursal_id": 1,
                "visits_total": 100,
                "sales_total": 50,
                "visits_iventas_bought": 2,
                "visits_iventas_not_bought": 1,
                "visits_not_iventas_bought": 10,
                "visits_not_iventas_not_bought": 20,
                "iventas_visit_conversion_rate": 2 / 3,
                "not_iventas_visit_conversion_rate": 1 / 3,
            }
        ],
        "data_quality": {
            "crm_history_available": False,
            "visit_conversion_mode": "exact_phone_same_branch_30d",
            "visit_conversion_cohort_complete": True,
            "visit_conversion_sales_snapshot_ids": [1, 2],
        },
    }

    _apply_unavailable_crm_visit_conversion(result)

    for container in [result["summary"], *result["branches"]]:
        assert container["visits_iventas_bought"] is None
        assert container["visits_iventas_not_bought"] is None
        assert container["visits_not_iventas_bought"] is None
        assert container["visits_not_iventas_not_bought"] is None
        assert container["iventas_visit_conversion_rate"] is None
        assert container["not_iventas_visit_conversion_rate"] is None

    assert result["summary"]["visits_total"] == 3604
    assert result["summary"]["sales_total"] == 2497
    assert result["summary"]["revenue_total"] == 2105250.0
    assert result["branches"][0]["visits_total"] == 100
    assert result["branches"][0]["sales_total"] == 50

    quality = result["data_quality"]
    assert quality["visit_conversion_mode"] is None
    assert quality["visit_conversion_cohort_complete"] is None
    assert quality["visit_conversion_sales_snapshot_ids"] == []
