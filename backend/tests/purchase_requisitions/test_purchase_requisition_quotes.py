from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, Column, Integer, MetaData, Table, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.purchase_requisition import (
    PurchaseRequisitionAttachmentORM,
    PurchaseRequisitionEventORM,
    PurchaseRequisitionORM,
    PurchaseRequisitionQuoteFinanceStatus,
    PurchaseRequisitionQuoteORM,
)
from app.services.purchase_requisition_quote_service import (
    create_purchase_requisition_quote,
    select_purchase_requisition_quote,
)
from app.services.purchase_requisition_service import (
    PurchaseRequisitionValidationError,
)
from app.services.purchase_requisition_workflow_service import (
    PurchaseRequisitionConflictError,
)
from app.utils.purchase_requisition_permissions import (
    PurchaseRequisitionAuthorizationError,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_as_integer(_type, compiler, **kw):
    return "INTEGER"


@pytest.fixture()
def engine():
    value = create_engine("sqlite://")
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    Table(
        "sucursales",
        metadata,
        Column("sucursal_id", Integer, primary_key=True),
    )
    PurchaseRequisitionORM.__table__.to_metadata(metadata)
    PurchaseRequisitionEventORM.__table__.to_metadata(metadata)
    PurchaseRequisitionAttachmentORM.__table__.to_metadata(metadata)
    PurchaseRequisitionQuoteORM.__table__.to_metadata(metadata)

    with value.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        metadata.create_all(connection)
        connection.exec_driver_sql(
            "INSERT INTO users (id) VALUES (1), (2), (3)"
        )
        connection.exec_driver_sql(
            "INSERT INTO sucursales (sucursal_id) VALUES (10)"
        )

    try:
        yield value
    finally:
        value.dispose()


def _actor(user_id=2, role="MANTENIMIENTO"):
    return SimpleNamespace(
        id=user_id,
        username=f"user-{user_id}",
        rol=role,
        sucursal_id=1000,
        sucursales_ids=[],
    )


def _seed_requisition(session, *, status="IN_QUOTATION"):
    row = PurchaseRequisitionORM(
        id=1,
        public_id="RQ-2026-000001",
        sucursal_id=10,
        created_by_user_id=1,
        category="GYM_EQUIPMENT",
        reason="REPLACEMENT",
        justification="Equipo desgastado.",
        priority="NORMAL",
        status=status,
    )
    session.add(row)
    session.flush()
    return row


def _attachment(
    attachment_id: int,
    *,
    attachment_type="QUOTE",
    requisition_id=1,
):
    return PurchaseRequisitionAttachmentORM(
        id=attachment_id,
        requisition_id=requisition_id,
        attachment_type=attachment_type,
        original_filename=f"quote-{attachment_id}.pdf",
        storage_key=f"purchase-requisitions/1/{attachment_id}.pdf",
        mime_type="application/pdf",
        size_bytes=100,
        sha256=str(attachment_id) * 64,
        uploaded_by_user_id=2,
    )


def _payload(attachment_id: int, supplier="Proveedor Uno"):
    return {
        "supplier_name": supplier,
        "amount": "12500.50",
        "currency": "mxn",
        "quote_date": "2026-10-06",
        "attachment_id": attachment_id,
        "notes": "Entrega estimada según disponibilidad.",
    }


def test_maintenance_creates_structured_quote_and_event(engine):
    with Session(engine) as session:
        _seed_requisition(session)
        session.add(_attachment(1))
        session.flush()

        quote = create_purchase_requisition_quote(
            1,
            _payload(1),
            _actor(),
            session=session,
        )
        session.commit()

        assert quote.id == 1
        assert quote.supplier_name == "Proveedor Uno"
        assert str(quote.amount) == "12500.50"
        assert quote.currency == "MXN"
        assert quote.finance_status == "DRAFT"
        assert quote.is_selected is False

        event = session.query(PurchaseRequisitionEventORM).one()
        assert event.event_type == "QUOTE_ADDED"
        assert event.from_status == "IN_QUOTATION"
        assert event.to_status == "IN_QUOTATION"
        assert event.metadata_json["quote_id"] == quote.id
        assert event.metadata_json["attachment_id"] == 1


def test_quote_requires_in_quotation_owner_and_quote_attachment(engine):
    with Session(engine) as session:
        _seed_requisition(session)
        session.add(_attachment(1, attachment_type="OTHER"))
        session.flush()

        with pytest.raises(
            PurchaseRequisitionValidationError,
            match="adjunto QUOTE",
        ):
            create_purchase_requisition_quote(
                1,
                _payload(1),
                _actor(),
                session=session,
            )

        with pytest.raises(PurchaseRequisitionAuthorizationError):
            create_purchase_requisition_quote(
                1,
                _payload(1),
                _actor(user_id=3, role="GERENTE"),
                session=session,
            )

        requisition = session.get(PurchaseRequisitionORM, 1)
        requisition.status = "PAYMENT_REQUESTED"
        session.flush()

        with pytest.raises(PurchaseRequisitionConflictError):
            create_purchase_requisition_quote(
                1,
                _payload(1),
                _actor(),
                session=session,
            )


def test_same_attachment_cannot_back_two_quotes(engine):
    with Session(engine) as session:
        _seed_requisition(session)
        session.add(_attachment(1))
        session.flush()

        create_purchase_requisition_quote(
            1,
            _payload(1),
            _actor(),
            session=session,
        )
        session.flush()

        with pytest.raises(
            PurchaseRequisitionValidationError,
            match="ya está asociado",
        ):
            create_purchase_requisition_quote(
                1,
                _payload(1, supplier="Proveedor Dos"),
                _actor(),
                session=session,
            )


def test_select_quote_keeps_exactly_one_selected(engine):
    with Session(engine) as session:
        _seed_requisition(session)
        session.add_all([_attachment(1), _attachment(2)])
        session.flush()

        quote_one = create_purchase_requisition_quote(
            1,
            _payload(1, supplier="Proveedor Uno"),
            _actor(),
            session=session,
        )
        quote_two = create_purchase_requisition_quote(
            1,
            _payload(2, supplier="Proveedor Dos"),
            _actor(),
            session=session,
        )
        session.flush()

        selected_one = select_purchase_requisition_quote(
            1,
            quote_one.id,
            _actor(),
            session=session,
        )
        session.flush()
        assert selected_one.is_selected is True

        selected_two = select_purchase_requisition_quote(
            1,
            quote_two.id,
            _actor(),
            session=session,
        )
        session.commit()

        session.refresh(quote_one)
        session.refresh(quote_two)
        assert quote_one.is_selected is False
        assert quote_one.selected_by_user_id is None
        assert quote_two.is_selected is True
        assert quote_two.selected_by_user_id == 2
        assert quote_two.selected_at is not None

        selected = (
            session.query(PurchaseRequisitionQuoteORM)
            .filter(PurchaseRequisitionQuoteORM.is_selected.is_(True))
            .all()
        )
        assert [row.id for row in selected] == [quote_two.id]

        select_events = (
            session.query(PurchaseRequisitionEventORM)
            .filter(
                PurchaseRequisitionEventORM.event_type
                == "QUOTE_SELECTED"
            )
            .order_by(PurchaseRequisitionEventORM.id)
            .all()
        )
        assert len(select_events) == 2
        assert select_events[-1].metadata_json["previous_quote_ids"] == [
            quote_one.id
        ]


def test_rejected_quote_cannot_be_selected_again(engine):
    with Session(engine) as session:
        _seed_requisition(session)
        session.add(_attachment(1))
        session.flush()

        quote = create_purchase_requisition_quote(
            1,
            _payload(1),
            _actor(),
            session=session,
        )
        quote.finance_status = PurchaseRequisitionQuoteFinanceStatus.REJECTED
        session.flush()

        with pytest.raises(
            PurchaseRequisitionConflictError,
            match="borrador",
        ):
            select_purchase_requisition_quote(
                1,
                quote.id,
                _actor(),
                session=session,
            )
