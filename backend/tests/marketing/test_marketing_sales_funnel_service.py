from datetime import date
from types import SimpleNamespace

import pytest

import app.services.marketing_sales_funnel_service as marketing_sales_funnel_service
from app.services.marketing_sales_funnel_detail_service import (
    MarketingSalesFunnelDetailValidationError,
    _normalize_pagination,
    _sale_matches_metric,
    _visit_matches_metric,
)
from app.services.marketing_sales_funnel_service import (
    ORIGIN_IVENTAS_META,
    ORIGIN_IVENTAS_OTHER,
    ORIGIN_OFFLINE,
    ORIGIN_PROXIMITY,
    ORIGIN_REFERRAL,
    ORIGIN_SOCIAL_UNTRACED,
    ORIGIN_UNKNOWN,
    _IventasEvidence,
    _build_venta_total_enrichment,
    _classify_survey,
    _find_venta_total_enrichment,
    _match_iventas,
)


def test_survey_fallback_categories_are_explicit():
    assert _classify_survey("Redes Sociales") == ORIGIN_SOCIAL_UNTRACED
    assert _classify_survey("Familiares o Amigos") == ORIGIN_REFERRAL
    assert (
        _classify_survey("Cerca de Domicilio/Trabajo")
        == ORIGIN_PROXIMITY
    )
    assert _classify_survey("Volantes") == ORIGIN_OFFLINE
    assert _classify_survey(None) == ORIGIN_UNKNOWN


def test_venta_total_enrichment_matches_by_folio_without_branch_requirement():
    rows = [
        SimpleNamespace(
            estatus="ACTIVO",
            fecha="07-09-26",
            folio="26020528335780010246",
            pin="24790",
            telefono="6861234567",
            encuesta="Familiares o Amigos",
            sucursal="VILLA VERDE",
        )
    ]

    by_folio, by_pin_date = _build_venta_total_enrichment(
        rows,
        date(2026, 9, 1),
    )
    match = _find_venta_total_enrichment(
        by_folio=by_folio,
        by_pin_date=by_pin_date,
        folio="26020528335780010246",
        pin="24790",
        payment_date=date(2026, 9, 7),
    )

    assert match is not None
    assert match.survey_raw == "Familiares o Amigos"
    assert match.phone == "6861234567"


def test_venta_total_enrichment_falls_back_to_pin_and_payment_date():
    rows = [
        SimpleNamespace(
            estatus="FACTURADO",
            fecha="07-09-26",
            folio="",
            pin="24790",
            telefono="6861234567",
            encuesta="Redes Sociales",
            sucursal="VILLA VERDE",
        )
    ]

    by_folio, by_pin_date = _build_venta_total_enrichment(
        rows,
        date(2026, 9, 1),
    )
    match = _find_venta_total_enrichment(
        by_folio=by_folio,
        by_pin_date=by_pin_date,
        folio=None,
        pin="24790",
        payment_date=date(2026, 9, 7),
    )

    assert match is not None
    assert match.survey_raw == "Redes Sociales"


def test_iventas_match_requires_prior_interaction_in_same_branch_and_window():
    evidence = {
        (4, "6861234567"): [
            _IventasEvidence(
                branch_id=4,
                phone="6861234567",
                interaction_date=date(2026, 8, 10),
                has_meta_ad=True,
            )
        ]
    }

    assert (
        _match_iventas(
            evidence,
            branch_id=4,
            phone="6861234567",
            target_date=date(2026, 8, 20),
        )
        == ORIGIN_IVENTAS_META
    )
    assert (
        _match_iventas(
            evidence,
            branch_id=5,
            phone="6861234567",
            target_date=date(2026, 8, 20),
        )
        is None
    )
    assert (
        _match_iventas(
            evidence,
            branch_id=4,
            phone="6861234567",
            target_date=date(2026, 8, 5),
        )
        is None
    )
    assert (
        _match_iventas(
            evidence,
            branch_id=4,
            phone="6861234567",
            target_date=date(2026, 9, 15),
        )
        is None
    )


def test_latest_iventas_interaction_controls_meta_classification():
    evidence = {
        (4, "6861234567"): [
            _IventasEvidence(
                branch_id=4,
                phone="6861234567",
                interaction_date=date(2026, 8, 1),
                has_meta_ad=True,
            ),
            _IventasEvidence(
                branch_id=4,
                phone="6861234567",
                interaction_date=date(2026, 8, 12),
                has_meta_ad=False,
            ),
        ]
    }

    assert (
        _match_iventas(
            evidence,
            branch_id=4,
            phone="6861234567",
            target_date=date(2026, 8, 20),
        )
        == ORIGIN_IVENTAS_OTHER
    )


def test_load_iventas_data_prefers_provider_ads_origin_and_uses_legacy_fallback(
    monkeypatch,
):
    runs = [
        SimpleNamespace(id=10, period_key="IVENTAS-2026-08"),
        SimpleNamespace(id=20, period_key="IVENTAS-2026-09"),
    ]
    projected_contacts = [
        SimpleNamespace(
            sync_run_id=10,
            sucursal_id=4,
            phone_mx10="6861111111",
            first_message_date_local=date(2026, 8, 20),
            is_from_ads=None,
            legacy_has_meta=True,
        ),
        SimpleNamespace(
            sync_run_id=20,
            sucursal_id=4,
            phone_mx10="6862222222",
            first_message_date_local=date(2026, 9, 5),
            is_from_ads=True,
            legacy_has_meta=False,
        ),
        SimpleNamespace(
            sync_run_id=20,
            sucursal_id=4,
            phone_mx10="6863333333",
            first_message_date_local=date(2026, 9, 6),
            is_from_ads=False,
            legacy_has_meta=True,
        ),
    ]

    class FakeExists:
        def label(self, _name):
            return self

    class FakeQuery:
        def __init__(self, *, rows=None, exists_value=None):
            self.rows = rows
            self.exists_value = exists_value

        def filter(self, *_args):
            return self

        def exists(self):
            return self.exists_value

        def all(self):
            return self.rows

    query_results = iter(
        (
            FakeQuery(exists_value=FakeExists()),
            FakeQuery(rows=projected_contacts),
        )
    )

    monkeypatch.setattr(
        marketing_sales_funnel_service,
        "_canonical_runs_for_window",
        lambda *_args: runs,
    )
    monkeypatch.setattr(
        marketing_sales_funnel_service,
        "_meta_contact_keys",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("_load_iventas_data no debe cargar tags aparte")
        ),
    )
    monkeypatch.setattr(
        marketing_sales_funnel_service,
        "db",
        SimpleNamespace(
            session=SimpleNamespace(
                query=lambda *_args: next(query_results)
            )
        ),
    )

    evidence, month_counts, run_ids = (
        marketing_sales_funnel_service._load_iventas_data(
            date(2026, 9, 1),
            (4,),
        )
    )

    assert run_ids == (10, 20)
    assert month_counts == {4: (2, 1)}
    assert evidence[(4, "6861111111")][0].has_meta_ad is True
    assert evidence[(4, "6862222222")][0].has_meta_ad is True
    assert evidence[(4, "6863333333")][0].has_meta_ad is False


def test_load_new_sales_uses_projected_rows(monkeypatch):
    projected_rows = [
        SimpleNamespace(
            id=101,
            sucursal_id=4,
            fecha_pago_at=date(2026, 9, 5),
            id_socio="5001",
            id_folio="F-5001",
            pin="",
            lada="686",
            telefono="1234567",
            total_pagado="499.00",
        )
    ]
    queried_columns: list[object] = []

    class FakeQuery:
        def filter(self, *_args):
            return self

        def order_by(self, *_args):
            return self

        def all(self):
            return projected_rows

    def fake_query(*columns):
        queried_columns.extend(columns)
        return FakeQuery()

    monkeypatch.setattr(
        marketing_sales_funnel_service,
        "db",
        SimpleNamespace(session=SimpleNamespace(query=fake_query)),
    )

    result = marketing_sales_funnel_service._load_new_sales(
        snapshot=SimpleNamespace(id=77),
        venta_total_rows=[],
        month_start=date(2026, 9, 1),
        branch_ids=(4,),
    )

    assert len(queried_columns) == 9
    assert len(result.sales) == 1
    assert result.enriched_with_venta_total == 0
    assert result.sales[0].sale_key == "id_socio:5001"
    assert result.sales[0].branch_id == 4
    assert result.sales[0].sale_date == date(2026, 9, 5)
    assert result.sales[0].phone == "6861234567"
    assert str(result.sales[0].revenue) == "499.00"


def test_drilldown_sale_filters_follow_same_attribution_hierarchy():
    assert _sale_matches_metric(
        "sales_total",
        None,
        phone="6861234567",
        origin=ORIGIN_IVENTAS_META,
    )
    assert _sale_matches_metric(
        "sales_with_phone",
        None,
        phone="6861234567",
        origin=ORIGIN_REFERRAL,
    )
    assert _sale_matches_metric(
        "sales_iventas",
        None,
        phone="6861234567",
        origin=ORIGIN_IVENTAS_OTHER,
    )
    assert not _sale_matches_metric(
        "sales_iventas",
        None,
        phone="6861234567",
        origin=ORIGIN_SOCIAL_UNTRACED,
    )
    assert _sale_matches_metric(
        "origin",
        ORIGIN_REFERRAL,
        phone=None,
        origin=ORIGIN_REFERRAL,
    )


def test_drilldown_visit_filters_do_not_treat_unmatched_as_iventas():
    assert _visit_matches_metric("visits_total", None)
    assert _visit_matches_metric("visits_iventas_meta", ORIGIN_IVENTAS_META)
    assert _visit_matches_metric("visits_iventas", ORIGIN_IVENTAS_OTHER)
    assert _visit_matches_metric("visits_not_iventas", None)
    assert not _visit_matches_metric("visits_iventas", None)


def test_drilldown_pagination_defaults_to_first_page_of_50():
    assert _normalize_pagination(None, None) == (1, 50)
    assert _normalize_pagination("2", "25") == (2, 25)


def test_drilldown_pagination_rejects_invalid_ranges():
    with pytest.raises(MarketingSalesFunnelDetailValidationError):
        _normalize_pagination("0", "50")

    with pytest.raises(MarketingSalesFunnelDetailValidationError):
        _normalize_pagination("1", "101")
