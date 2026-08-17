from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

import app.services.marketing_inputs_service as service


class _FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.commit_calls = 0
        self.rollback_calls = 0

    def add(self, row) -> None:
        if row.id is None:
            row.id = 91
        self.added.append(row)

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1


def test_monthly_input_upsert_updates_existing_row(
    monkeypatch: pytest.MonkeyPatch,
):
    fake_session = _FakeSession()
    stored = {"row": None}

    monkeypatch.setattr(
        service,
        "db",
        SimpleNamespace(session=fake_session),
    )
    monkeypatch.setattr(
        service,
        "_branch_exists",
        lambda _: True,
    )
    monkeypatch.setattr(
        service,
        "_find_monthly_input",
        lambda **_: stored["row"],
    )

    validated = service.validate_input_payload(
        {
            "month": "2026-07",
            "investment": "100.00",
            "notes": "Primera carga",
        }
    )
    created_row, created = service.upsert_marketing_input(
        sucursal_id=7,
        user_id=3,
        **validated,
    )
    stored["row"] = created_row
    created_row.leads = 77

    updated_values = service.validate_input_payload(
        {
            "month": "2026-07",
            "investment": "125.50",
            "notes": "Actualizada",
        }
    )
    updated_row, updated_created = (
        service.upsert_marketing_input(
            sucursal_id=7,
            user_id=4,
            **updated_values,
        )
    )

    assert created is True
    assert updated_created is False
    assert updated_row.id == 91
    assert updated_row.investment == Decimal("125.50")
    assert updated_row.leads == 77
    assert updated_row.updated_by_user_id == 4
    assert fake_session.commit_calls == 2
    assert len(fake_session.added) == 1


def test_negative_investment_is_rejected():
    payload = {
        "month": "2026-07",
        "investment": -1,
    }

    with pytest.raises(
        service.MarketingInputValidationError
    ):
        service.validate_input_payload(payload)


def test_unknown_payload_field_is_rejected():
    with pytest.raises(
        service.MarketingInputValidationError,
        match="Campos no permitidos",
    ):
        service.validate_input_payload(
            {
                "month": "2026-07",
                "investment": 100,
                "campaigns": 5,
            }
        )


def test_deprecated_leads_field_is_rejected():
    with pytest.raises(
        service.MarketingInputValidationError,
        match="Campos no permitidos: leads",
    ):
        service.validate_input_payload(
            {
                "month": "2026-07",
                "investment": 100,
                "leads": 10,
            }
        )
