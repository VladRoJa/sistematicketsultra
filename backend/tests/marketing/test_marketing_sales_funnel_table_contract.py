from types import SimpleNamespace

from app.services.marketing_sales_funnel_service import (
    ORIGIN_IVENTAS_META,
    ORIGIN_IVENTAS_OTHER,
    SALE_CATEGORY_BTL,
    SALE_CATEGORY_DIGITAL,
    SALE_CATEGORY_DIGITAL_ORGANIC,
    SALE_CATEGORY_WEB,
    _classify_sale_category,
    _merge_venta_total_enrichment,
)


def test_iventas_match_has_highest_priority():
    assert (
        _classify_sale_category(
            iventas_origin=ORIGIN_IVENTAS_META,
            api_raw="IVENTAS",
            survey_raw="Venta por web",
        )
        == SALE_CATEGORY_DIGITAL
    )
    assert (
        _classify_sale_category(
            iventas_origin=ORIGIN_IVENTAS_OTHER,
            api_raw=None,
            survey_raw="Redes sociales no trazadas",
        )
        == SALE_CATEGORY_DIGITAL
    )


def test_api_iventas_promotes_non_matched_sale_to_web():
    assert (
        _classify_sale_category(
            iventas_origin=None,
            api_raw="  iventas  ",
            survey_raw="Familiares o amigos",
        )
        == SALE_CATEGORY_WEB
    )


def test_untraced_social_sale_is_digital_organic():
    assert (
        _classify_sale_category(
            iventas_origin=None,
            api_raw=None,
            survey_raw="Redes sociales no trazadas",
        )
        == SALE_CATEGORY_DIGITAL_ORGANIC
    )


def test_legacy_social_label_remains_digital_organic():
    assert (
        _classify_sale_category(
            iventas_origin=None,
            api_raw=None,
            survey_raw="Redes sociales",
        )
        == SALE_CATEGORY_DIGITAL_ORGANIC
    )


def test_survey_web_sale_is_web_when_api_does_not_claim_it():
    assert (
        _classify_sale_category(
            iventas_origin=None,
            api_raw="OTRA",
            survey_raw="Venta por web",
        )
        == SALE_CATEGORY_WEB
    )


def test_remaining_surveys_and_missing_values_fall_back_to_btl():
    assert (
        _classify_sale_category(
            iventas_origin=None,
            api_raw=None,
            survey_raw="Familiares o amigos",
        )
        == SALE_CATEGORY_BTL
    )
    assert (
        _classify_sale_category(
            iventas_origin=None,
            api_raw=None,
            survey_raw=None,
        )
        == SALE_CATEGORY_BTL
    )


def test_venta_total_enrichment_preserves_api_origin():
    row = SimpleNamespace(
        telefono="6861234567",
        encuesta="Venta por web",
        api=" IVENTAS ",
    )

    enrichment = _merge_venta_total_enrichment(None, row)

    assert enrichment.phone == "6861234567"
    assert enrichment.survey_raw == "Venta por web"
    assert enrichment.api_raw == "IVENTAS"
