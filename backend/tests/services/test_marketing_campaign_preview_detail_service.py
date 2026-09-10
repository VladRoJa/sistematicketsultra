from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from app.services import marketing_campaign_audience_service as audience
from app.services import marketing_campaign_preview_detail_service as detail
from app.services import marketing_reactivation_service as reactivation


def _row(
    row_id,
    *,
    category="Domiciliado",
    group="DOMICILIATED_FLOW",
    eligibility="EXCLUDED_TARIFF",
    reason="TARIFF_DOMICILIATED_FLOW",
    phone=None,
    debt="100.00",
    operational="AVAILABLE",
    branch="MISION ENS",
    tariff=None,
):
    return {
        "vencido_row_id": row_id,
        "pin": f"PIN-{row_id}",
        "nombre": f"Socio {row_id}",
        "phone_mx10": phone or f"686100{row_id:04d}",
        "sucursal": branch,
        "fecha_vencimiento": "2026-08-01",
        "tarifa": tariff or f"Tarifa {row_id}",
        "tarifa_categoria": category,
        "tarifa_group": group,
        "adeudo": debt,
        "operational_status": operational,
        "campaign_eligibility": eligibility,
        "eligibility_reason": reason,
        "iventas_contact_id": None,
        "latest_outbound_at_utc": None,
    }


def _plan(rows, **summary):
    base_summary = {
        "total_candidates": len(rows),
        "eligible": 0,
        "excluded_active": 0,
        "excluded_invalid_phone": 0,
        "review_identity": 0,
        "duplicate_phone": 0,
        "excluded_tariff": 0,
        "excluded_tariff_general": 0,
        "domiciliated_flow": 0,
        "borron_cuenta_nueva": 0,
        "review_tariff": 0,
        "excluded_recent_campaign": 0,
        "review": 0,
    }
    base_summary.update(summary)
    return {
        "sources": {
            "date_from": "2026-08-01",
            "date_to": "2026-08-31",
            "iventas_sync_run_id": 87,
        },
        "filters": {"campaign_type": "WINBACK"},
        "summary": base_summary,
        "decision_rows": rows,
        "eligible_rows": [
            row for row in rows if row.get("campaign_eligibility") == "ELIGIBLE"
        ],
    }


def _run(
    monkeypatch,
    plan,
    bucket,
    *,
    page=1,
    page_size=50,
    explorer_filters=None,
):
    monkeypatch.setattr(
        reactivation,
        "_prepare_campaign_plan",
        lambda **kwargs: plan,
    )
    monkeypatch.setattr(
        detail,
        "_enrich_page_rows",
        lambda *, rows, sources, session: list(rows),
    )
    return detail.build_marketing_campaign_preview_detail(
        filters={"campaign_type": "WINBACK", "segment": "WINBACK_30"},
        bucket=bucket,
        page=page,
        page_size=page_size,
        explorer_filters=explorer_filters,
        allowed_sucursal_keys=None,
        session=NS(),
    )


def test_domiciliated_bucket_matches_preview_count_and_composition(monkeypatch):
    rows = [
        _row(1, category="Domiciliado"),
        _row(2, category="Domiciliado"),
        _row(3, category="Recurrente"),
        _row(
            4,
            category="Mensualidad",
            group="REACTIVATE",
            eligibility="ELIGIBLE",
            reason=None,
        ),
    ]
    plan = _plan(rows, domiciliated_flow=3, eligible=1)

    result = _run(monkeypatch, plan, detail.BUCKET_DOMICILIATED_FLOW)

    assert result["total"] == 3
    assert result["filtered_total"] == 3
    assert [row["vencido_row_id"] for row in result["rows"]] == [1, 2, 3]
    assert result["composition"] == [
        {"label": "Domiciliado", "count": 2, "percentage": 66.67},
        {"label": "Recurrente", "count": 1, "percentage": 33.33},
    ]
    assert result["operational_counts"] == {"AVAILABLE": 3}


def test_bcn_bucket_uses_same_positive_debt_rule(monkeypatch):
    rows = [
        _row(1, debt="500.00"),
        _row(2, debt="0.00"),
        _row(3, debt="-1.00"),
        _row(
            4,
            group="REACTIVATE",
            eligibility="ELIGIBLE",
            reason=None,
            debt="900.00",
        ),
    ]
    plan = _plan(rows, domiciliated_flow=3, borron_cuenta_nueva=1, eligible=1)

    result = _run(monkeypatch, plan, detail.BUCKET_BCN_CANDIDATES)

    assert result["total"] == 1
    assert result["rows"][0]["vencido_row_id"] == 1
    assert audience._is_bcn_base_candidate(rows[0]) is True


def test_duplicate_bucket_reproduces_preview_phone_dedupe(monkeypatch):
    rows = [
        _row(
            1,
            group="REACTIVATE",
            eligibility="ELIGIBLE",
            reason=None,
            phone="6861000001",
        ),
        _row(
            2,
            group="REACTIVATE",
            eligibility="ELIGIBLE",
            reason=None,
            phone="6861000001",
        ),
        _row(
            3,
            group="REACTIVATE",
            eligibility="ELIGIBLE",
            reason=None,
            phone="6861000002",
        ),
    ]
    plan = _plan(rows, eligible=2, duplicate_phone=1)
    plan["eligible_rows"] = [rows[0], rows[2]]

    result = _run(monkeypatch, plan, detail.BUCKET_DUPLICATE_PHONE)

    assert result["total"] == 1
    assert result["rows"][0]["vencido_row_id"] == 2


def test_eligible_bucket_supports_sources_without_decision_rows(monkeypatch):
    eligible = [
        {
            "vencido_row_id": None,
            "nombre": "Socio activo",
            "phone_mx10": "6861000001",
            "sucursal": "MISION ENS",
            "fecha_vencimiento": "2026-09-12",
            "tarifa": "MENSUALIDAD",
            "operational_status": "ACTIVE",
            "reason": "ACTIVE_CONFIRMED",
        }
    ]
    plan = {
        "sources": {"date_from": "2026-09-10", "date_to": "2026-09-10"},
        "filters": {"campaign_type": "BASCULA_RETENCION"},
        "summary": {"eligible": 1},
        "eligible_rows": eligible,
    }

    result = _run(monkeypatch, plan, detail.BUCKET_ELIGIBLE)

    assert result["total"] == 1
    assert result["filtered_total"] == 1
    assert result["rows"] == eligible


def test_stage_bucket_rejects_source_without_decision_rows(monkeypatch):
    plan = {
        "sources": {"date_from": "2026-09-10", "date_to": "2026-09-10"},
        "filters": {"campaign_type": "BASCULA_RETENCION"},
        "summary": {"total_candidates": 1},
        "eligible_rows": [],
    }

    with pytest.raises(
        reactivation.MarketingReactivationValidationError,
        match="universo de vencidos",
    ):
        _run(monkeypatch, plan, detail.BUCKET_TOTAL_CANDIDATES)


def test_detail_fails_closed_when_bucket_count_diverges_from_preview(monkeypatch):
    rows = [_row(1)]
    plan = _plan(rows, domiciliated_flow=2)

    with pytest.raises(RuntimeError, match="no coincide"):
        _run(monkeypatch, plan, detail.BUCKET_DOMICILIATED_FLOW)


def test_base_filters_keep_original_bucket_total_and_recalculate_result(monkeypatch):
    rows = [
        _row(1, debt="650", tariff="DOMICILIADO ANUAL"),
        _row(
            2,
            debt="300",
            operational="CONTACTED_THIS_MONTH",
            tariff="DOMICILIADO ANUAL",
        ),
        _row(
            3,
            category="Recurrente",
            debt="800",
            branch="SEND MXL",
            tariff="RECURRENTE 799",
        ),
    ]
    plan = _plan(rows, domiciliated_flow=3)

    result = _run(
        monkeypatch,
        plan,
        detail.BUCKET_DOMICILIATED_FLOW,
        explorer_filters={
            "sucursal": "MISION ENS",
            "tariff_category": "Domiciliado",
            "adeudo_min": 500,
            "operational_status": "AVAILABLE",
        },
    )

    assert result["total"] == 3
    assert result["filtered_total"] == 1
    assert result["pagination"]["total"] == 1
    assert [row["vencido_row_id"] for row in result["rows"]] == [1]
    assert result["composition"] == [
        {"label": "Domiciliado", "count": 1, "percentage": 100.0}
    ]
    assert result["filter_options"]["branches"] == ["MISION ENS", "SEND MXL"]
    assert result["filter_options"]["tariff_categories"] == [
        "Domiciliado",
        "Recurrente",
    ]


def test_suite_history_and_iventas_filters_apply_to_enriched_bucket(monkeypatch):
    rows = [_row(1), _row(2), _row(3)]
    rows[0].update(
        suite_campaigns_total=0,
        iventas_last_message_status="failed",
    )
    rows[1].update(
        suite_campaigns_total=1,
        iventas_last_message_status="viewed",
    )
    rows[2].update(
        suite_campaigns_total=2,
        iventas_last_message_status="viewed",
    )
    plan = _plan(rows, domiciliated_flow=3)

    result = _run(
        monkeypatch,
        plan,
        detail.BUCKET_DOMICILIATED_FLOW,
        explorer_filters={
            "suite_history": "TWO_PLUS",
            "iventas_status": "VIEWED",
        },
    )

    assert result["total"] == 3
    assert result["filtered_total"] == 1
    assert result["rows"][0]["vencido_row_id"] == 3
    assert result["explorer_filters"] == {
        "suite_history": "TWO_PLUS",
        "iventas_status": "VIEWED",
    }


def test_debt_filter_rejects_inverted_range(monkeypatch):
    plan = _plan([_row(1)], domiciliated_flow=1)

    with pytest.raises(
        reactivation.MarketingReactivationValidationError,
        match="mínimo no puede ser mayor",
    ):
        _run(
            monkeypatch,
            plan,
            detail.BUCKET_DOMICILIATED_FLOW,
            explorer_filters={"adeudo_min": 1000, "adeudo_max": 500},
        )
