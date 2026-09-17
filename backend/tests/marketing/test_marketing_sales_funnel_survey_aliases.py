import app.services.marketing_sales_funnel_service as marketing_sales_funnel_service
from app.services.marketing_sales_funnel_service import _classify_survey


def test_plaza_comercial_accepts_provider_vista_label():
    assert (
        _classify_survey("Vista a Plaza Comercial")
        == marketing_sales_funnel_service.ORIGIN_PLAZA
    )


def test_plaza_comercial_keeps_visita_alias_compatible():
    assert (
        _classify_survey("Visita a Plaza Comercial")
        == marketing_sales_funnel_service.ORIGIN_PLAZA
    )
