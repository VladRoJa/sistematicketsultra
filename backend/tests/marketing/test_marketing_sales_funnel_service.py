from datetime import date

from app.services.marketing_sales_funnel_service import (
    ORIGIN_IVENTAS_META,
    ORIGIN_IVENTAS_OTHER,
    ORIGIN_OFFLINE,
    ORIGIN_PROXIMITY,
    ORIGIN_REFERRAL,
    ORIGIN_SOCIAL_UNTRACED,
    ORIGIN_UNKNOWN,
    _IventasEvidence,
    _classify_survey,
    _is_new_flag,
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


def test_new_flag_accepts_expected_variants():
    assert _is_new_flag("SI") is True
    assert _is_new_flag("Sí") is True
    assert _is_new_flag("1") is True
    assert _is_new_flag("NO") is False


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
