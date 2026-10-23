"""Sucursal de origen para SMS que Gasca no pudo resolver.

No abre Chrome ni ejecuta consultas: valida el contrato público del ORM.
"""
from app.models.rpa import GascaSmsRequestORM
from app.models.sucursal_model import Sucursal


def _request(*, status: str, gasca_sucursal: str | None = None, with_origin: bool = True):
    request = GascaSmsRequestORM(
        pin_raw="00000",
        pin_normalized="00000",
        requested_phone_raw="0000000000",
        requested_phone_masked="******0000",
        motivo="SMS_NO_LLEGA",
        status=status,
        sucursal_id=26 if with_origin else None,
        gasca_sucursal=gasca_sucursal,
        attempt_count=0,
    )
    if with_origin:
        request.sucursal = Sucursal(
            sucursal_id=26,
            sucursal="SUCURSAL DE PRUEBA",
            serie="ZZZ",
            estado="Baja California",
            municipio="Prueba",
            direccion="Dirección de prueba",
        )
    return request


def test_phone_mismatch_exposes_suite_origin_without_gasca_club():
    data = _request(status="phone_not_found_for_pin").to_public_dict()
    assert data["sucursal_id"] == 26
    assert data["gasca_sucursal"] is None
    assert data["sucursal_origen_nombre"] == "SUCURSAL DE PRUEBA"


def test_duplicate_rejection_exposes_suite_origin_without_attempt():
    data = _request(status="failed").to_public_dict()
    assert data["attempt_count"] == 0
    assert data["sucursal_origen_nombre"] == "SUCURSAL DE PRUEBA"


def test_sent_request_keeps_gasca_club_as_primary():
    data = _request(status="sent", gasca_sucursal="PAPALOTE TJ").to_public_dict()
    assert data["gasca_sucursal"] == "PAPALOTE TJ"
    assert data["sucursal_origen_nombre"] == "SUCURSAL DE PRUEBA"


def test_missing_source_remains_unknown_not_guessed():
    data = _request(status="failed", with_origin=False).to_public_dict()
    assert data["gasca_sucursal"] is None
    assert data["sucursal_origen_nombre"] is None
