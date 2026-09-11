from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.warehouse.services.track_operational_universe_service as service


def test_load_operational_track_branch_canons_uses_operational_rules(
    monkeypatch: pytest.MonkeyPatch,
):
    query = MagicMock()

    rows = [
        (
            SimpleNamespace(
                sucursal_canon="ACTIVA_1",
                display_order=1,
            ),
            SimpleNamespace(sucursal_id=1),
        ),
        (
            SimpleNamespace(
                sucursal_canon="LA_VIGA",
                display_order=26,
            ),
            SimpleNamespace(sucursal_id=2),
        ),
        (
            SimpleNamespace(
                sucursal_canon="SIN_COHORTE",
                display_order=None,
            ),
            SimpleNamespace(sucursal_id=3),
        ),
    ]

    query.join.return_value.filter.return_value.all.return_value = rows

    monkeypatch.setattr(
        service.db.session,
        "query",
        MagicMock(return_value=query),
    )

    result = service.load_operational_track_branch_canons()

    assert result == {"ACTIVA_1"}

    query.join.assert_called_once()

    filter_call = query.join.return_value.filter.call_args
    assert filter_call is not None

    filter_expressions = filter_call.args

    assert {
        getattr(getattr(expression, "left", None), "key", None)
        for expression in filter_expressions
    } == {
        "is_track_active",
        "operational_status",
    }