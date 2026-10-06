from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, Column, Integer, MetaData, String, Table, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.purchase_requisition import (
    PurchaseRequisitionEventORM,
    PurchaseRequisitionFinanceApproverORM,
    PurchaseRequisitionItemORM,
    PurchaseRequisitionORM,
)
from app.services.purchase_requisition_service import (
    PurchaseRequisitionAuthorizationError,
    PurchaseRequisitionValidationError,
    _temporary_public_id,
    create_purchase_requisition,
    get_purchase_requisition,
    list_purchase_requisitions,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_as_integer(_type, compiler, **kw):
    return "INTEGER"


@pytest.fixture()
def engine():
    value = create_engine("sqlite://")
    metadata = MetaData()
    Table(
        "users",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("username", String(100)),
        Column("rol", String(50)),
    )
    Table(
        "sucursales",
        metadata,
        Column("sucursal_id", Integer, primary_key=True),
    )
    PurchaseRequisitionORM.__table__.to_metadata(metadata)
    PurchaseRequisitionItemORM.__table__.to_metadata(metadata)
    PurchaseRequisitionEventORM.__table__.to_metadata(metadata)
    PurchaseRequisitionFinanceApproverORM.__table__.to_metadata(metadata)
    with value.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        metadata.create_all(connection)
        connection.exec_driver_sql(
            "INSERT INTO users (id, username, rol) VALUES "
            "(1, 'branch-user', 'RECEPCIONISTA'), "
            "(2, 'sports', 'GERENCIA DEPORTIVA'), "
            "(3, 'maintenance', 'MANTENIMIENTO'), "
            "(4, 'other-branch', 'RECEPCIONISTA'), "
            "(5, 'finance', 'RECEPCIONISTA')"
        )
        connection.exec_driver_sql(
            "INSERT INTO sucursales (sucursal_id) VALUES (10), (20)"
        )
    try:
        yield value
    finally:
        value.dispose()


def _user(
    user_id: int,
    role: str,
    branch_id: int,
    *,
    branch_ids=(),
):
    return SimpleNamespace(
        id=user_id,
        username=f"user-{user_id}",
        rol=role,
        sucursal_id=branch_id,
        sucursales_ids=list(branch_ids),
    )


def _payload(**overrides):
    values = {
        "sucursal_id": 10,
        "category": "GYM_EQUIPMENT",
        "reason": "REPLACEMENT",
        "priority": "HIGH",
        "justification": "Equipo fuera de servicio.",
        "items": [
            {
                "item_description": "Caminadora",
                "quantity": 2,
                "notes": "Modelo equivalente.",
            }
        ],
    }
    values.update(overrides)
    return values


def test_create_persists_header_items_and_created_event(engine):
    actor = _user(1, "RECEPCIONISTA", 10)
    with Session(engine) as session:
        row = create_purchase_requisition(
            _payload(),
            actor,
            session=session,
        )
        session.commit()

        assert row.id == 1
        assert row.public_id.startswith("RQ-")
        assert row.public_id.endswith("-000001")
        assert row.status == "PENDING_REVIEW"
        assert row.sucursal_id == 10
        assert row.created_by_user_id == 1
        assert len(row.items) == 1
        assert row.items[0].item_description == "Caminadora"
        assert row.items[0].quantity == 2
        assert len(row.events) == 1
        assert row.events[0].event_type == "CREATED"
        assert row.events[0].from_status is None
        assert row.events[0].to_status == "PENDING_REVIEW"


def test_create_requires_at_least_one_item(engine):
    actor = _user(1, "RECEPCIONISTA", 10)
    with Session(engine) as session:
        with pytest.raises(
            PurchaseRequisitionValidationError,
            match="al menos una partida",
        ):
            create_purchase_requisition(
                _payload(items=[]),
                actor,
                session=session,
            )


def test_create_rejects_non_positive_quantity(engine):
    actor = _user(1, "RECEPCIONISTA", 10)
    with Session(engine) as session:
        with pytest.raises(
            PurchaseRequisitionValidationError,
            match="mayor que cero",
        ):
            create_purchase_requisition(
                _payload(
                    items=[{
                        "item_description": "Bicicleta",
                        "quantity": 0,
                    }]
                ),
                actor,
                session=session,
            )


def test_create_enforces_branch_scope(engine):
    actor = _user(1, "RECEPCIONISTA", 10)
    with Session(engine) as session:
        with pytest.raises(
            PurchaseRequisitionAuthorizationError,
            match="esa sucursal",
        ):
            create_purchase_requisition(
                _payload(sucursal_id=20),
                actor,
                session=session,
            )


def test_gerencia_can_list_pending_but_maintenance_cannot(engine):
    creator = _user(1, "RECEPCIONISTA", 10)
    sports = _user(2, "GERENCIA DEPORTIVA", 1000)
    maintenance = _user(3, "MANTENIMIENTO", 1000)

    with Session(engine) as session:
        create_purchase_requisition(
            _payload(),
            creator,
            session=session,
        )
        session.commit()

        sports_rows = list_purchase_requisitions(
            sports,
            session=session,
        )
        maintenance_rows = list_purchase_requisitions(
            maintenance,
            session=session,
        )

        assert len(sports_rows) == 1
        assert sports_rows[0].status == "PENDING_REVIEW"
        assert maintenance_rows == []


def test_same_branch_can_view_and_other_branch_cannot(engine):
    creator = _user(1, "RECEPCIONISTA", 10)
    same_branch = _user(4, "RECEPCIONISTA", 10)
    other_branch = _user(4, "RECEPCIONISTA", 20)

    with Session(engine) as session:
        row = create_purchase_requisition(
            _payload(),
            creator,
            session=session,
        )
        session.commit()

        assert get_purchase_requisition(
            row.id,
            same_branch,
            session=session,
        ).id == row.id

        with pytest.raises(PurchaseRequisitionAuthorizationError):
            get_purchase_requisition(
                row.id,
                other_branch,
                session=session,
            )


def test_creator_can_read_own_requisition(engine):
    creator = _user(1, "RECEPCIONISTA", 10)
    with Session(engine) as session:
        row = create_purchase_requisition(
            _payload(),
            creator,
            session=session,
        )
        session.commit()

        loaded = get_purchase_requisition(
            row.id,
            creator,
            session=session,
        )
        assert loaded.id == row.id


def test_list_filters_status_priority_branch(engine):
    creator = _user(1, "RECEPCIONISTA", 10)
    sports = _user(2, "GERENCIA DEPORTIVA", 1000)

    with Session(engine) as session:
        create_purchase_requisition(
            _payload(priority="HIGH"),
            creator,
            session=session,
        )
        session.commit()

        assert len(list_purchase_requisitions(
            sports,
            status="PENDING_REVIEW",
            priority="HIGH",
            branch_id=10,
            session=session,
        )) == 1
        assert list_purchase_requisitions(
            sports,
            status="IN_QUOTATION",
            session=session,
        ) == []


def test_temporary_public_id_fits_database_column():
    temporary = _temporary_public_id()
    assert temporary.startswith("TMP-")
    assert len(temporary) <= 32

def test_maintenance_lists_all_post_approval_states(engine):
    creator = _user(1, "RECEPCIONISTA", 10)
    maintenance = _user(3, "MANTENIMIENTO", 1000)
    visible_statuses = (
        "IN_QUOTATION",
        "QUOTE_PENDING_FINANCE_APPROVAL",
        "PAYMENT_REQUESTED",
        "SHIPPING_IN_PROGRESS",
        "IMPORT_IN_PROGRESS",
        "FINAL_DESTINATION_SHIPMENT",
        "RECEIPT_ISSUE",
        "CLOSED",
    )

    with Session(engine) as session:
        row = create_purchase_requisition(
            _payload(),
            creator,
            session=session,
        )
        session.commit()

        for status in visible_statuses:
            row.status = status
            session.commit()

            listed = list_purchase_requisitions(
                maintenance,
                session=session,
            )
            assert [item.id for item in listed] == [row.id]
            assert get_purchase_requisition(
                row.id,
                maintenance,
                session=session,
            ).id == row.id


def test_finance_approver_sees_only_pending_finance_outside_branch(engine):
    creator = _user(1, "RECEPCIONISTA", 10)
    finance = _user(5, "RECEPCIONISTA", 20)

    with Session(engine) as session:
        row = create_purchase_requisition(
            _payload(),
            creator,
            session=session,
        )
        row.status = "QUOTE_PENDING_FINANCE_APPROVAL"
        session.add(
            PurchaseRequisitionFinanceApproverORM(
                user_id=5,
                is_active=True,
                added_by_user_id=2,
            )
        )
        session.commit()

        listed = list_purchase_requisitions(
            finance,
            session=session,
        )
        assert [item.id for item in listed] == [row.id]
        assert get_purchase_requisition(
            row.id,
            finance,
            session=session,
        ).id == row.id

        row.status = "IN_QUOTATION"
        session.commit()

        assert list_purchase_requisitions(
            finance,
            session=session,
        ) == []
        with pytest.raises(PurchaseRequisitionAuthorizationError):
            get_purchase_requisition(
                row.id,
                finance,
                session=session,
            )
