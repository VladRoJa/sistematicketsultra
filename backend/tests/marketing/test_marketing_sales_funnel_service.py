from datetime import date
from types import SimpleNamespace

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
