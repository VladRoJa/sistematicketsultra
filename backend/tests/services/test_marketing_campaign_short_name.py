from app.services import marketing_campaign_export_service as export_service


def test_short_name_keeps_regular_first_name():
    assert export_service._short_name("  MARÍA   DE JESÚS  ") == "María"
    assert export_service._short_name("MARIA FERNANDA PEREZ") == "Maria"
    assert export_service._short_name(None) == ""


def test_short_name_skips_ma_abbreviation_and_connectors():
    assert export_service._short_name("MA HUMBERTA MARTINEZ VARGAS") == "Humberta"
    assert export_service._short_name("MA DEL CARMEN LOPEZ") == "Carmen"
    assert export_service._short_name("MA. DE LOS ANGELES PEREZ") == "Angeles"
