import pytest

from app.utils.sucursal_audience import (
    SUCURSAL_AUDIENCE_ANALYTICAL,
    SUCURSAL_AUDIENCE_OPERATIONAL,
    normalize_sucursal_audience,
    parse_include_demo,
)


def test_audience_defaults_to_operational():
    assert normalize_sucursal_audience(None) == SUCURSAL_AUDIENCE_OPERATIONAL


def test_audience_accepts_analytical():
    assert (
        normalize_sucursal_audience(" ANALYTICAL ")
        == SUCURSAL_AUDIENCE_ANALYTICAL
    )


def test_audience_rejects_unknown_value():
    with pytest.raises(ValueError):
        normalize_sucursal_audience("demo-only")


@pytest.mark.parametrize("value", [True, "true", "1", "yes", "si", "sí"])
def test_parse_include_demo_true_values(value):
    assert parse_include_demo(value) is True


@pytest.mark.parametrize("value", [False, "false", "0", "no"])
def test_parse_include_demo_false_values(value):
    assert parse_include_demo(value) is False


def test_parse_include_demo_rejects_ambiguous_value():
    with pytest.raises(ValueError):
        parse_include_demo("tal vez")
