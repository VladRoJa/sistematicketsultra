from __future__ import annotations

from datetime import date

import pytest

from sqlalchemy import BigInteger, Column, Integer, MetaData, String, Table, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    PurchaseRequisitionAttachmentORM,
    PurchaseRequisitionAttachmentType,
    PurchaseRequisitionCategory,
    PurchaseRequisitionEventORM,
    PurchaseRequisitionEventType,
    PurchaseRequisitionFinanceApproverORM,
    PurchaseRequisitionItemORM,
    PurchaseRequisitionORM,
    PurchaseRequisitionPriority,
    PurchaseRequisitionQuoteFinanceStatus,
    PurchaseRequisitionQuoteORM,
    PurchaseRequisitionReceiptIssueType,
    PurchaseRequisitionReason,
    PurchaseRequisitionStatus,
)


def _engine():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    Table(
        "sucursales",
        metadata,
        Column("sucursal_id", Integer, primary_key=True),
    )
    PurchaseRequisitionORM.__table__.to_metadata(metadata)
    PurchaseRequisitionItemORM.__table__.to_metadata(metadata)
    PurchaseRequisitionEventORM.__table__.to_metadata(metadata)
    PurchaseRequisitionAttachmentORM.__table__.to_metadata(metadata)
    PurchaseRequisitionQuoteORM.__table__.to_metadata(metadata)
    PurchaseRequisitionFinanceApproverORM.__table__.to_metadata(metadata)
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        metadata.create_all(connection)
        connection.exec_driver_sql(
            "INSERT INTO users (id) VALUES (1), (2)"
        )
        connection.exec_driver_sql(
            "INSERT INTO sucursales (sucursal_id) VALUES (10)"
        )
    return engine


def _requisition(**overrides):
    values = {
        "id": 1,
        "public_id": "RQ-2026-000001",
        "sucursal_id": 10,
        "created_by_user_id": 1,
        "reason": PurchaseRequisitionReason.REPLACEMENT,
        "justification": "Reemplazo por desgaste.",
    }
    values.update(overrides)
    return PurchaseRequisitionORM(**values)


def test_purchase_requisition_domain_is_independent_from_ticket_v1():
    tables = {
        PurchaseRequisitionORM.__tablename__,
        PurchaseRequisitionItemORM.__tablename__,
        PurchaseRequisitionEventORM.__tablename__,
        PurchaseRequisitionQuoteORM.__tablename__,
        PurchaseRequisitionFinanceApproverORM.__tablename__,
    }
    assert tables == {
        "purchase_requisitions",
        "purchase_requisition_items",
        "purchase_requisition_events",
        "purchase_requisition_quotes",
        "purchase_requisition_finance_approvers",
    }

    fk_targets = {
        fk.target_fullname
        for table in (
            PurchaseRequisitionORM.__table__,
            PurchaseRequisitionItemORM.__table__,
            PurchaseRequisitionEventORM.__table__,
            PurchaseRequisitionQuoteORM.__table__,
            PurchaseRequisitionFinanceApproverORM.__table__,
        )
        for fk in table.foreign_keys
    }
    assert all(not target.startswith("tickets.") for target in fk_targets)
    assert "users.id" in fk_targets
    assert "sucursales.sucursal_id" in fk_targets
    assert "purchase_requisitions.id" in fk_targets


def test_purchase_requisition_catalogs_match_contract():
    assert PurchaseRequisitionCategory.ALL == ("GYM_EQUIPMENT",)
    assert PurchaseRequisitionReason.ALL == (
        "REPLACEMENT",
        "NEW_EQUIPMENT",
        "DAMAGE",
        "EXPANSION",
        "OTHER",
    )
    assert PurchaseRequisitionPriority.ALL == (
        "NORMAL",
        "HIGH",
        "CRITICAL",
    )
    assert PurchaseRequisitionStatus.ALL == (
        "PENDING_REVIEW",
        "NEEDS_INFO",
        "REJECTED",
        "IN_QUOTATION",
        "QUOTE_PENDING_FINANCE_APPROVAL",
        "PAYMENT_REQUESTED",
        "SHIPPING_IN_PROGRESS",
        "IMPORT_IN_PROGRESS",
        "FINAL_DESTINATION_SHIPMENT",
        "RECEIPT_ISSUE",
        "CLOSED",
    )
    assert PurchaseRequisitionEventType.ALL == (
        "CREATED",
        "INFO_REQUESTED",
        "RESUBMITTED",
        "APPROVED",
        "REJECTED",
        "ROUTED_TO_MAINTENANCE",
        "ATTACHMENT_ADDED",
        "QUOTE_ADDED",
        "QUOTE_SELECTED",
        "QUOTE_SUBMITTED_FOR_FINANCE_APPROVAL",
        "QUOTE_APPROVED_BY_FINANCE",
        "QUOTE_REJECTED_BY_FINANCE",
        "PAYMENT_REQUESTED",
        "SHIPPING_STARTED",
        "IMPORT_STARTED",
        "IMPORT_NOT_APPLICABLE",
        "FINAL_DESTINATION_SHIPMENT_STARTED",
        "RECEIVED",
        "RECEIPT_ISSUE_REPORTED",
        "RECEIPT_ISSUE_RESOLUTION_STARTED",
        "ADMINISTRATIVE_CORRECTION",
    )
    assert PurchaseRequisitionAttachmentType.ALL == (
        "EVIDENCE",
        "QUOTE",
        "OTHER",
        "RECEIPT_EVIDENCE",
        "RECEIPT_ISSUE_EVIDENCE",
    )
    assert PurchaseRequisitionQuoteFinanceStatus.ALL == (
        "DRAFT",
        "PENDING",
        "APPROVED",
        "REJECTED",
    )
    assert PurchaseRequisitionReceiptIssueType.ALL == (
        "DAMAGED",
        "INCOMPLETE",
        "WRONG_ITEM",
        "OTHER",
    )


def test_defaults_and_serialization_contract():
    requisition = _requisition()
    assert requisition.category is None
    assert requisition.priority is None
    assert requisition.status is None

    columns = PurchaseRequisitionORM.__table__.c
    assert columns.category.default.arg == "GYM_EQUIPMENT"
    assert columns.priority.default.arg == "NORMAL"
    assert columns.status.default.arg == "PENDING_REVIEW"
    assert columns.public_id.nullable is False
    assert columns.justification.nullable is False

    payload = requisition.to_dict()
    assert payload["public_id"] == "RQ-2026-000001"
    assert payload["reason"] == "REPLACEMENT"
    assert payload["items"] if "items" in payload else True


def test_db_constraints_enforce_domain_and_positive_quantity():
    engine = _engine()
    try:
        with Session(engine) as session:
            requisition = _requisition()
            session.add(requisition)
            session.flush()

            item = PurchaseRequisitionItemORM(
                id=1,
                requisition_id=requisition.id,
                item_description="Caminadora",
                quantity=2,
            )
            session.add(item)
            session.commit()

            assert requisition.category == "GYM_EQUIPMENT"
            assert requisition.priority == "NORMAL"
            assert requisition.status == "PENDING_REVIEW"
            assert item.quantity == 2

        with Session(engine) as session:
            session.add(
                _requisition(
                    id=2,
                    public_id="RQ-2026-000002",
                    status="INVALID",
                )
            )
            try:
                session.commit()
                raise AssertionError("status inválido fue aceptado")
            except IntegrityError:
                session.rollback()

        with Session(engine) as session:
            session.add(
                _requisition(
                    id=3,
                    public_id="RQ-2026-000003",
                    justification="   ",
                )
            )
            try:
                session.commit()
                raise AssertionError("justificación vacía fue aceptada")
            except IntegrityError:
                session.rollback()

        with Session(engine) as session:
            session.add(
                _requisition(
                    id=4,
                    public_id="RQ-2026-000004",
                )
            )
            session.flush()
            session.add(
                PurchaseRequisitionItemORM(
                    id=2,
                    requisition_id=4,
                    item_description="Bicicleta",
                    quantity=0,
                )
            )
            try:
                session.commit()
                raise AssertionError("quantity=0 fue aceptado")
            except IntegrityError:
                session.rollback()
    finally:
        engine.dispose()


def test_event_statuses_and_event_types_are_constrained():
    engine = _engine()
    try:
        with Session(engine) as session:
            session.add(_requisition())
            session.flush()
            session.add(
                PurchaseRequisitionEventORM(
                    id=1,
                    requisition_id=1,
                    event_type=PurchaseRequisitionEventType.CREATED,
                    actor_user_id=1,
                    from_status=None,
                    to_status=PurchaseRequisitionStatus.PENDING_REVIEW,
                )
            )
            session.commit()

        with Session(engine) as session:
            session.add(
                PurchaseRequisitionEventORM(
                    id=2,
                    requisition_id=1,
                    event_type="INVALID",
                    actor_user_id=1,
                )
            )
            try:
                session.commit()
                raise AssertionError("event_type inválido fue aceptado")
            except IntegrityError:
                session.rollback()
    finally:
        engine.dispose()

def _quote_attachment(attachment_id: int, requisition_id: int = 1):
    return PurchaseRequisitionAttachmentORM(
        id=attachment_id,
        requisition_id=requisition_id,
        attachment_type=PurchaseRequisitionAttachmentType.QUOTE,
        original_filename=f"quote-{attachment_id}.pdf",
        storage_key=(
            f"purchase-requisitions/{requisition_id}/"
            f"quote-{attachment_id}.pdf"
        ),
        mime_type="application/pdf",
        size_bytes=100,
        sha256=str(attachment_id) * 64,
        uploaded_by_user_id=1,
    )


def test_e1_quote_and_finance_approver_constraints():
    engine = _engine()
    try:
        with Session(engine) as session:
            session.add(_requisition())
            session.flush()

            session.add_all([
                _quote_attachment(1),
                _quote_attachment(2),
            ])
            session.flush()

            quote = PurchaseRequisitionQuoteORM(
                id=1,
                requisition_id=1,
                supplier_name="Proveedor Uno",
                amount=12500,
                currency="MXN",
                quote_date=date(2026, 10, 6),
                attachment_id=1,
                created_by_user_id=1,
                is_selected=True,
                selected_by_user_id=1,
            )
            session.add(quote)
            session.add(
                PurchaseRequisitionFinanceApproverORM(
                    id=1,
                    user_id=2,
                    added_by_user_id=1,
                    notes="Aprobador financiero inicial.",
                )
            )
            session.commit()

            assert quote.finance_status == "DRAFT"
            assert quote.is_selected is True

        with Session(engine) as session:
            session.add(_quote_attachment(3))
            session.flush()
            session.add(
                PurchaseRequisitionQuoteORM(
                    id=2,
                    requisition_id=1,
                    supplier_name="Proveedor Dos",
                    amount=13000,
                    currency="MXN",
                    quote_date=date(2026, 10, 6),
                    attachment_id=3,
                    created_by_user_id=1,
                    is_selected=True,
                    selected_by_user_id=1,
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

        with Session(engine) as session:
            session.add(
                PurchaseRequisitionFinanceApproverORM(
                    id=2,
                    user_id=2,
                    added_by_user_id=1,
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

        with Session(engine) as session:
            session.add(_quote_attachment(4))
            session.flush()
            session.add(
                PurchaseRequisitionQuoteORM(
                    id=3,
                    requisition_id=1,
                    supplier_name="Proveedor Tres",
                    amount=0,
                    currency="MXN",
                    quote_date=date(2026, 10, 6),
                    attachment_id=4,
                    created_by_user_id=1,
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()
