import pytest

from app.utils.sucursal_audience import (
    SUCURSAL_AUDIENCE_ANALYTICAL,
    SUCURSAL_AUDIENCE_OPERATIONAL,
    normalize_sucursal_audience,
)


def test_audience_defaults_to_analytical():
    assert normalize_sucursal_audience(None) == SUCURSAL_AUDIENCE_ANALYTICAL


def test_audience_accepts_analytical():
    assert (
        normalize_sucursal_audience(" ANALYTICAL ")
        == SUCURSAL_AUDIENCE_ANALYTICAL
    )


def test_audience_accepts_operational():
    assert (
        normalize_sucursal_audience(" OPERATIONAL ")
        == SUCURSAL_AUDIENCE_OPERATIONAL
    )


def test_audience_rejects_unknown_value():
    with pytest.raises(ValueError):
        normalize_sucursal_audience("demo-only")
