from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine
from sqlalchemy.orm import Session

from app.models.purchase_requisition import (
    PurchaseRequisitionFinanceApproverORM,
)
from app.services.purchase_requisition_finance_approver_service import (
    create_purchase_requisition_finance_approver,
    list_purchase_requisition_finance_approvers,
    serialize_purchase_requisition_finance_approver,
    update_purchase_requisition_finance_approver,
)
from app.services.purchase_requisition_service import (
    PurchaseRequisitionNotFoundError,
    PurchaseRequisitionValidationError,
)
from app.utils.purchase_requisition_permissions import (
    PurchaseRequisitionAuthorizationError,
)


@pytest.fixture()
def engine():
    value = create_engine("sqlite://")
    metadata = MetaData()
    Table(
        "users",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("username", String(100), nullable=False),
        Column("email", String(255), nullable=True),
        Column("rol", String(50), nullable=False),
    )
    PurchaseRequisitionFinanceApproverORM.__table__.to_metadata(metadata)

    with value.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        metadata.create_all(connection)
        connection.exec_driver_sql(
            "INSERT INTO users (id, username, email, rol) VALUES "
            "(50, 'finance-one', 'finance1@example.com', 'RECEPCIONISTA'), "
            "(51, 'finance-two', 'finance2@example.com', 'GERENTE'), "
            "(90, 'admin', 'admin@example.com', 'ADMINISTRADOR')"
        )

    try:
        yield value
    finally:
        value.dispose()


def _actor(user_id=90, role="ADMINISTRADOR"):
    return SimpleNamespace(
        id=user_id,
        username=f"user-{user_id}",
        rol=role,
    )


def test_admin_creates_lists_deactivates_and_reactivates_approver(engine):
    with Session(engine) as session:
        row = create_purchase_requisition_finance_approver(
            {
                "user_id": 50,
                "notes": "Responsable financiero inicial.",
            },
            _actor(),
            session=session,
        )
        session.commit()

        first_id = row.id
        assert row.user_id == 50
        assert row.is_active is True
        assert row.added_by_user_id == 90

        payload = list_purchase_requisition_finance_approvers(
            _actor(),
            session=session,
        )
        assert payload["count"] == 1
        assert payload["active_count"] == 1
        assert payload["rows"][0]["user"] == {
            "id": 50,
            "username": "finance-one",
            "email": "finance1@example.com",
            "role": "RECEPCIONISTA",
        }

        updated = update_purchase_requisition_finance_approver(
            50,
            {
                "is_active": False,
                "notes": "Temporalmente desactivado.",
            },
            _actor(),
            session=session,
        )
        session.commit()

        assert updated.id == first_id
        assert updated.is_active is False
        assert updated.notes == "Temporalmente desactivado."

        payload = list_purchase_requisition_finance_approvers(
            _actor(),
            session=session,
        )
        assert payload["count"] == 1
        assert payload["active_count"] == 0

        reactivated = update_purchase_requisition_finance_approver(
            50,
            {"is_active": True},
            _actor(),
            session=session,
        )
        session.commit()

        assert reactivated.id == first_id
        assert reactivated.is_active is True
        assert serialize_purchase_requisition_finance_approver(
            reactivated,
            session=session,
        )["user"]["id"] == 50


def test_duplicate_create_is_rejected_even_if_existing_row_is_inactive(engine):
    with Session(engine) as session:
        create_purchase_requisition_finance_approver(
            {"user_id": 50},
            _actor(),
            session=session,
        )
        session.commit()

        update_purchase_requisition_finance_approver(
            50,
            {"is_active": False},
            _actor(),
            session=session,
        )
        session.commit()

        with pytest.raises(
            PurchaseRequisitionValidationError,
            match="ya existe",
        ):
            create_purchase_requisition_finance_approver(
                {"user_id": 50},
                _actor(),
                session=session,
            )


def test_create_requires_existing_user_and_admin_actor(engine):
    with Session(engine) as session:
        with pytest.raises(
            PurchaseRequisitionValidationError,
            match="no existe",
        ):
            create_purchase_requisition_finance_approver(
                {"user_id": 999},
                _actor(),
                session=session,
            )

        with pytest.raises(PurchaseRequisitionAuthorizationError):
            create_purchase_requisition_finance_approver(
                {"user_id": 50},
                _actor(user_id=51, role="GERENTE"),
                session=session,
            )

        with pytest.raises(PurchaseRequisitionAuthorizationError):
            list_purchase_requisition_finance_approvers(
                _actor(user_id=51, role="GERENTE"),
                session=session,
            )


def test_update_requires_existing_assignment_and_explicit_change(engine):
    with Session(engine) as session:
        with pytest.raises(PurchaseRequisitionNotFoundError):
            update_purchase_requisition_finance_approver(
                50,
                {"is_active": True},
                _actor(),
                session=session,
            )

        create_purchase_requisition_finance_approver(
            {"user_id": 50},
            _actor(),
            session=session,
        )
        session.commit()

        with pytest.raises(
            PurchaseRequisitionValidationError,
            match="is_active o notes",
        ):
            update_purchase_requisition_finance_approver(
                50,
                {},
                _actor(),
                session=session,
            )

        with pytest.raises(
            PurchaseRequisitionValidationError,
            match="booleano",
        ):
            update_purchase_requisition_finance_approver(
                50,
                {"is_active": "false"},
                _actor(),
                session=session,
            )
