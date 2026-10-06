from __future__ import annotations

from datetime import date

from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, Column, Integer, MetaData, String, Table, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.purchase_requisition import (
    PurchaseRequisitionAttachmentORM,
    PurchaseRequisitionEventORM,
    PurchaseRequisitionFinanceApproverORM,
    PurchaseRequisitionItemORM,
    PurchaseRequisitionORM,
    PurchaseRequisitionQuoteORM,
)
from app.services.purchase_requisition_service import (
    PurchaseRequisitionValidationError,
    create_purchase_requisition,
)
from app.services.purchase_requisition_workflow_service import (
    PurchaseRequisitionConflictError,
    administratively_correct_purchase_requisition,
    advance_purchase_requisition_logistics,
    approve_purchase_requisition,
    approve_purchase_requisition_quote_by_finance,
    confirm_purchase_requisition_receipt,
    reject_purchase_requisition,
    reject_purchase_requisition_quote_by_finance,
    report_purchase_requisition_receipt_issue,
    request_info_purchase_requisition,
    requester_edit_purchase_requisition,
    resume_purchase_requisition_logistics,
    resubmit_purchase_requisition,
    submit_purchase_requisition_quote_for_finance,
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
    PurchaseRequisitionAttachmentORM.__table__.to_metadata(metadata)
    PurchaseRequisitionQuoteORM.__table__.to_metadata(metadata)
    PurchaseRequisitionFinanceApproverORM.__table__.to_metadata(metadata)
    with value.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        metadata.create_all(connection)
        connection.exec_driver_sql(
            "INSERT INTO users (id, username, rol) VALUES "
            "(1, 'requester', 'RECEPCIONISTA'), "
            "(2, 'sports', 'GERENCIA DEPORTIVA'), "
            "(3, 'admin', 'ADMINISTRADOR'), "
            "(4, 'manager', 'GERENTE'), "
            "(5, 'maintenance', 'MANTENIMIENTO'), "
            "(6, 'finance', 'RECEPCIONISTA')"
        )
        connection.exec_driver_sql(
            "INSERT INTO sucursales (sucursal_id) VALUES (10)"
        )
    try:
        yield value
    finally:
        value.dispose()


def _user(user_id, role, branch_id=10):
    return SimpleNamespace(
        id=user_id,
        username=f"user-{user_id}",
        rol=role,
        sucursal_id=branch_id,
        sucursales_ids=[],
    )


def _payload():
    return {
        "sucursal_id": 10,
        "reason": "REPLACEMENT",
        "priority": "NORMAL",
        "justification": "Equipo desgastado.",
        "items": [{
            "item_description": "Caminadora",
            "quantity": 1,
        }],
    }


def _seed(session):
    row = create_purchase_requisition(
        _payload(),
        _user(1, "RECEPCIONISTA"),
        session=session,
    )
    session.commit()
    return row


def _seed_finance_ready(
    session,
    *,
    add_approver: bool = True,
    selected: bool = True,
):
    row = _seed(session)
    approve_purchase_requisition(
        row.id,
        _user(2, "GERENCIA DEPORTIVA"),
        session=session,
    )
    session.flush()

    attachment = PurchaseRequisitionAttachmentORM(
        id=1,
        requisition_id=row.id,
        attachment_type="QUOTE",
        original_filename="quote.pdf",
        storage_key="purchase-requisitions/1/quote.pdf",
        mime_type="application/pdf",
        size_bytes=100,
        sha256="a" * 64,
        uploaded_by_user_id=5,
    )
    session.add(attachment)
    session.flush()

    quote = PurchaseRequisitionQuoteORM(
        id=1,
        requisition_id=row.id,
        supplier_name="Proveedor Uno",
        amount=12500,
        currency="MXN",
        quote_date=date(2026, 10, 6),
        attachment_id=attachment.id,
        created_by_user_id=5,
        is_selected=selected,
        selected_by_user_id=5 if selected else None,
    )
    session.add(quote)

    if add_approver:
        session.add(
            PurchaseRequisitionFinanceApproverORM(
                user_id=6,
                is_active=True,
                added_by_user_id=3,
            )
        )

    session.flush()
    return row, quote


def _seed_logistics_ready(session):
    row, quote = _seed_finance_ready(session)
    submit_purchase_requisition_quote_for_finance(
        row.id,
        _user(5, "MANTENIMIENTO"),
        session=session,
    )
    approve_purchase_requisition_quote_by_finance(
        row.id,
        _user(6, "RECEPCIONISTA"),
        comment="Autorizada para pago.",
        session=session,
    )
    session.flush()
    return row, quote


def _seed_final_destination(session):
    row, quote = _seed_logistics_ready(session)
    advance_purchase_requisition_logistics(
        row.id,
        "SHIPPING_IN_PROGRESS",
        _user(5, "MANTENIMIENTO"),
        session=session,
    )
    advance_purchase_requisition_logistics(
        row.id,
        "FINAL_DESTINATION_SHIPMENT",
        _user(5, "MANTENIMIENTO"),
        session=session,
    )
    session.flush()
    return row, quote


def _receipt_attachment(
    attachment_id: int,
    attachment_type: str,
):
    return PurchaseRequisitionAttachmentORM(
        id=attachment_id,
        requisition_id=1,
        attachment_type=attachment_type,
        original_filename=f"evidence-{attachment_id}.pdf",
        storage_key=(
            f"purchase-requisitions/1/evidence-{attachment_id}.pdf"
        ),
        mime_type="application/pdf",
        size_bytes=100,
        sha256=(str(attachment_id)[-1] or "1") * 64,
        uploaded_by_user_id=4,
    )


def test_request_info_requires_reviewer_and_comment(engine):
    with Session(engine) as session:
        row = _seed(session)

        with pytest.raises(PurchaseRequisitionAuthorizationError):
            request_info_purchase_requisition(
                row.id,
                "Falta evidencia.",
                _user(4, "GERENTE"),
                session=session,
            )

        with pytest.raises(
            PurchaseRequisitionValidationError,
            match="comment es obligatorio",
        ):
            request_info_purchase_requisition(
                row.id,
                " ",
                _user(2, "GERENCIA DEPORTIVA"),
                session=session,
            )

        updated = request_info_purchase_requisition(
            row.id,
            "Aclarar daño.",
            _user(2, "GERENCIA DEPORTIVA"),
            session=session,
        )
        session.commit()

        assert updated.status == "NEEDS_INFO"
        assert updated.events[-1].event_type == "INFO_REQUESTED"
        assert updated.events[-1].comment == "Aclarar daño."


def test_requester_can_edit_and_resubmit_from_needs_info(engine):
    with Session(engine) as session:
        row = _seed(session)
        request_info_purchase_requisition(
            row.id,
            "Corregir datos.",
            _user(2, "GERENCIA DEPORTIVA"),
            session=session,
        )
        session.commit()

        requester_edit_purchase_requisition(
            row.id,
            {
                "reason": "DAMAGE",
                "priority": "HIGH",
                "justification": "Daño confirmado.",
                "items": [{
                    "item_description": "Elíptica",
                    "quantity": 2,
                }],
            },
            _user(1, "RECEPCIONISTA"),
            session=session,
        )
        updated = resubmit_purchase_requisition(
            row.id,
            _user(1, "RECEPCIONISTA"),
            comment="Información corregida.",
            session=session,
        )
        session.commit()

        assert updated.status == "PENDING_REVIEW"
        assert updated.reason == "DAMAGE"
        assert updated.priority == "HIGH"
        assert updated.items[0].item_description == "Elíptica"
        assert updated.events[-1].event_type == "RESUBMITTED"


def test_non_requester_cannot_edit_or_resubmit(engine):
    with Session(engine) as session:
        row = _seed(session)
        request_info_purchase_requisition(
            row.id,
            "Corregir.",
            _user(2, "GERENCIA DEPORTIVA"),
            session=session,
        )
        session.commit()

        with pytest.raises(PurchaseRequisitionAuthorizationError):
            requester_edit_purchase_requisition(
                row.id,
                {"justification": "Cambio"},
                _user(4, "GERENTE"),
                session=session,
            )

        with pytest.raises(PurchaseRequisitionAuthorizationError):
            resubmit_purchase_requisition(
                row.id,
                _user(4, "GERENTE"),
                session=session,
            )


@pytest.mark.parametrize(
    ("reviewer_id", "reviewer_role"),
    [
        (2, "GERENCIA DEPORTIVA"),
        (3, "ADMINISTRADOR"),
    ],
)
def test_authorized_reviewer_can_approve(
    engine,
    reviewer_id,
    reviewer_role,
):
    with Session(engine) as session:
        row = _seed(session)
        approved = approve_purchase_requisition(
            row.id,
            _user(reviewer_id, reviewer_role),
            comment="Aprobado para cotización.",
            session=session,
        )
        session.commit()

        assert approved.status == "IN_QUOTATION"
        assert approved.approved_by_user_id == reviewer_id
        assert approved.approved_at is not None
        assert approved.approval_comment == (
            "Aprobado para cotización."
        )
        assert approved.events[-2].event_type == "APPROVED"
        assert approved.events[-2].to_status == "IN_QUOTATION"
        assert approved.events[-1].event_type == (
            "ROUTED_TO_MAINTENANCE"
        )
        assert approved.events[-1].to_status == "IN_QUOTATION"


def test_unauthorized_user_cannot_approve(engine):
    with Session(engine) as session:
        row = _seed(session)
        with pytest.raises(PurchaseRequisitionAuthorizationError):
            approve_purchase_requisition(
                row.id,
                _user(4, "GERENTE"),
                session=session,
            )


def test_reject_requires_reason_and_is_terminal_for_mvp(engine):
    with Session(engine) as session:
        row = _seed(session)

        with pytest.raises(
            PurchaseRequisitionValidationError,
            match="reason es obligatorio",
        ):
            reject_purchase_requisition(
                row.id,
                " ",
                _user(2, "GERENCIA DEPORTIVA"),
                session=session,
            )

        rejected = reject_purchase_requisition(
            row.id,
            "No procede por condición del equipo.",
            _user(2, "GERENCIA DEPORTIVA"),
            session=session,
        )
        session.commit()

        assert rejected.status == "REJECTED"
        assert rejected.rejected_at is not None
        assert rejected.events[-1].event_type == "REJECTED"

        with pytest.raises(PurchaseRequisitionConflictError):
            approve_purchase_requisition(
                row.id,
                _user(3, "ADMINISTRADOR"),
                session=session,
            )


def test_invalid_transition_is_rejected(engine):
    with Session(engine) as session:
        row = _seed(session)
        with pytest.raises(PurchaseRequisitionConflictError):
            resubmit_purchase_requisition(
                row.id,
                _user(1, "RECEPCIONISTA"),
                session=session,
            )


def test_requester_edit_after_decision_is_rejected(engine):
    with Session(engine) as session:
        row = _seed(session)
        approve_purchase_requisition(
            row.id,
            _user(2, "GERENCIA DEPORTIVA"),
            session=session,
        )
        session.commit()

        with pytest.raises(PurchaseRequisitionConflictError):
            requester_edit_purchase_requisition(
                row.id,
                {"justification": "Cambio tardío."},
                _user(1, "RECEPCIONISTA"),
                session=session,
            )


def test_second_resubmit_is_business_conflict(engine):
    with Session(engine) as session:
        row = _seed(session)
        request_info_purchase_requisition(
            row.id,
            "Corregir.",
            _user(2, "GERENCIA DEPORTIVA"),
            session=session,
        )
        session.commit()

        resubmit_purchase_requisition(
            row.id,
            _user(1, "RECEPCIONISTA"),
            session=session,
        )
        session.commit()

        with pytest.raises(PurchaseRequisitionConflictError):
            resubmit_purchase_requisition(
                row.id,
                _user(1, "RECEPCIONISTA"),
                session=session,
            )


def test_second_decision_after_approve_is_business_conflict(engine):
    with Session(engine) as session:
        row = _seed(session)
        approve_purchase_requisition(
            row.id,
            _user(2, "GERENCIA DEPORTIVA"),
            session=session,
        )
        session.commit()

        with pytest.raises(PurchaseRequisitionConflictError):
            reject_purchase_requisition(
                row.id,
                "Decisión tardía.",
                _user(3, "ADMINISTRADOR"),
                session=session,
            )

def test_submit_selected_quote_for_finance(engine):
    with Session(engine) as session:
        row, quote = _seed_finance_ready(session)

        updated = submit_purchase_requisition_quote_for_finance(
            row.id,
            _user(5, "MANTENIMIENTO"),
            session=session,
        )
        session.commit()

        assert updated.status == "QUOTE_PENDING_FINANCE_APPROVAL"
        assert quote.finance_status == "PENDING"
        assert quote.finance_submitted_by_user_id == 5
        assert quote.finance_submitted_at is not None
        assert updated.events[-1].event_type == (
            "QUOTE_SUBMITTED_FOR_FINANCE_APPROVAL"
        )
        assert updated.events[-1].metadata_json["quote_id"] == quote.id


def test_submit_quote_requires_selection_and_active_finance_approver(engine):
    with Session(engine) as session:
        row, _ = _seed_finance_ready(
            session,
            selected=False,
        )
        with pytest.raises(
            PurchaseRequisitionValidationError,
            match="seleccionar una cotización",
        ):
            submit_purchase_requisition_quote_for_finance(
                row.id,
                _user(5, "MANTENIMIENTO"),
                session=session,
            )

    with Session(engine) as session:
        row, _ = _seed_finance_ready(
            session,
            add_approver=False,
        )
        with pytest.raises(
            PurchaseRequisitionConflictError,
            match="No hay aprobador financiero activo",
        ):
            submit_purchase_requisition_quote_for_finance(
                row.id,
                _user(5, "MANTENIMIENTO"),
                session=session,
            )


def test_finance_approver_approves_quote_and_routes_to_payment(engine):
    with Session(engine) as session:
        row, quote = _seed_finance_ready(session)
        submit_purchase_requisition_quote_for_finance(
            row.id,
            _user(5, "MANTENIMIENTO"),
            session=session,
        )
        session.flush()

        with pytest.raises(PurchaseRequisitionAuthorizationError):
            approve_purchase_requisition_quote_by_finance(
                row.id,
                _user(3, "ADMINISTRADOR"),
                session=session,
            )

        approved = approve_purchase_requisition_quote_by_finance(
            row.id,
            _user(6, "RECEPCIONISTA"),
            comment="Cotización autorizada.",
            session=session,
        )
        session.commit()

        assert approved.status == "PAYMENT_REQUESTED"
        assert quote.finance_status == "APPROVED"
        assert quote.finance_decided_by_user_id == 6
        assert quote.finance_decided_at is not None
        assert quote.finance_comment == "Cotización autorizada."
        assert approved.events[-2].event_type == (
            "QUOTE_APPROVED_BY_FINANCE"
        )
        assert approved.events[-2].from_status == (
            "QUOTE_PENDING_FINANCE_APPROVAL"
        )
        assert approved.events[-2].to_status == "PAYMENT_REQUESTED"
        assert approved.events[-1].event_type == "PAYMENT_REQUESTED"


def test_finance_reject_requires_reason_and_releases_selection(engine):
    with Session(engine) as session:
        row, quote = _seed_finance_ready(session)
        submit_purchase_requisition_quote_for_finance(
            row.id,
            _user(5, "MANTENIMIENTO"),
            session=session,
        )
        session.flush()

        with pytest.raises(
            PurchaseRequisitionValidationError,
            match="reason es obligatorio",
        ):
            reject_purchase_requisition_quote_by_finance(
                row.id,
                " ",
                _user(6, "RECEPCIONISTA"),
                session=session,
            )

        rejected = reject_purchase_requisition_quote_by_finance(
            row.id,
            "Monto fuera de autorización.",
            _user(6, "RECEPCIONISTA"),
            session=session,
        )
        session.commit()

        assert rejected.status == "IN_QUOTATION"
        assert quote.finance_status == "REJECTED"
        assert quote.finance_decided_by_user_id == 6
        assert quote.finance_comment == "Monto fuera de autorización."
        assert quote.is_selected is False
        assert quote.selected_by_user_id is None
        assert quote.selected_at is None
        assert rejected.events[-1].event_type == (
            "QUOTE_REJECTED_BY_FINANCE"
        )

        with pytest.raises(PurchaseRequisitionConflictError):
            approve_purchase_requisition_quote_by_finance(
                row.id,
                _user(6, "RECEPCIONISTA"),
                session=session,
            )

def test_logistics_advances_payment_shipping_import_and_final(engine):
    with Session(engine) as session:
        row, quote = _seed_logistics_ready(session)

        shipping = advance_purchase_requisition_logistics(
            row.id,
            "SHIPPING_IN_PROGRESS",
            _user(5, "MANTENIMIENTO"),
            session=session,
        )
        assert shipping.status == "SHIPPING_IN_PROGRESS"
        assert shipping.events[-1].event_type == "SHIPPING_STARTED"
        assert shipping.events[-1].from_status == "PAYMENT_REQUESTED"
        assert shipping.events[-1].to_status == "SHIPPING_IN_PROGRESS"

        importing = advance_purchase_requisition_logistics(
            row.id,
            "IMPORT_IN_PROGRESS",
            _user(5, "MANTENIMIENTO"),
            session=session,
        )
        assert importing.status == "IMPORT_IN_PROGRESS"
        assert importing.events[-1].event_type == "IMPORT_STARTED"
        assert importing.events[-1].metadata_json == {
            "import_required": True
        }

        final = advance_purchase_requisition_logistics(
            row.id,
            "FINAL_DESTINATION_SHIPMENT",
            _user(5, "MANTENIMIENTO"),
            session=session,
        )
        session.commit()

        assert final.status == "FINAL_DESTINATION_SHIPMENT"
        assert final.events[-1].event_type == (
            "FINAL_DESTINATION_SHIPMENT_STARTED"
        )
        assert final.events[-1].from_status == "IMPORT_IN_PROGRESS"
        assert final.events[-1].metadata_json == {
            "import_required": True
        }
        assert quote.finance_status == "APPROVED"
        assert quote.is_selected is True


def test_logistics_can_skip_import_only_from_shipping_and_audits_decision(engine):
    with Session(engine) as session:
        row, _ = _seed_logistics_ready(session)

        advance_purchase_requisition_logistics(
            row.id,
            "SHIPPING_IN_PROGRESS",
            _user(5, "MANTENIMIENTO"),
            session=session,
        )
        final = advance_purchase_requisition_logistics(
            row.id,
            "FINAL_DESTINATION_SHIPMENT",
            _user(5, "MANTENIMIENTO"),
            session=session,
        )
        session.commit()

        assert final.status == "FINAL_DESTINATION_SHIPMENT"
        assert final.events[-2].event_type == "IMPORT_NOT_APPLICABLE"
        assert final.events[-2].from_status == "SHIPPING_IN_PROGRESS"
        assert final.events[-2].to_status == "SHIPPING_IN_PROGRESS"
        assert final.events[-2].metadata_json == {
            "import_required": False
        }
        assert final.events[-1].event_type == (
            "FINAL_DESTINATION_SHIPMENT_STARTED"
        )
        assert final.events[-1].from_status == "SHIPPING_IN_PROGRESS"
        assert final.events[-1].to_status == (
            "FINAL_DESTINATION_SHIPMENT"
        )
        assert final.events[-1].metadata_json == {
            "import_required": False
        }


def test_logistics_rejects_skips_invalid_targets_and_unauthorized_actor(engine):
    with Session(engine) as session:
        row, _ = _seed_logistics_ready(session)

        with pytest.raises(PurchaseRequisitionConflictError):
            advance_purchase_requisition_logistics(
                row.id,
                "FINAL_DESTINATION_SHIPMENT",
                _user(5, "MANTENIMIENTO"),
                session=session,
            )

        with pytest.raises(PurchaseRequisitionAuthorizationError):
            advance_purchase_requisition_logistics(
                row.id,
                "SHIPPING_IN_PROGRESS",
                _user(4, "GERENTE"),
                session=session,
            )

        with pytest.raises(
            PurchaseRequisitionValidationError,
            match="target_status inválido",
        ):
            advance_purchase_requisition_logistics(
                row.id,
                "CLOSED",
                _user(5, "MANTENIMIENTO"),
                session=session,
            )


def test_logistics_requires_current_approved_selected_quote(engine):
    with Session(engine) as session:
        row, quote = _seed_logistics_ready(session)
        quote.is_selected = False
        session.flush()

        with pytest.raises(
            PurchaseRequisitionConflictError,
            match="cotización financiera aprobada vigente",
        ):
            advance_purchase_requisition_logistics(
                row.id,
                "SHIPPING_IN_PROGRESS",
                _user(5, "MANTENIMIENTO"),
                session=session,
            )

def test_origin_manager_confirms_receipt_and_closes(engine):
    with Session(engine) as session:
        row, quote = _seed_final_destination(session)

        closed = confirm_purchase_requisition_receipt(
            row.id,
            _user(4, "GERENTE"),
            comment="Equipo recibido completo.",
            session=session,
        )
        session.commit()

        assert closed.status == "CLOSED"
        assert quote.finance_status == "APPROVED"
        assert closed.events[-1].event_type == "RECEIVED"
        assert closed.events[-1].from_status == (
            "FINAL_DESTINATION_SHIPMENT"
        )
        assert closed.events[-1].to_status == "CLOSED"
        assert closed.events[-1].comment == "Equipo recibido completo."
        assert closed.events[-1].metadata_json == {
            "evidence_attachment_ids": []
        }

        with pytest.raises(PurchaseRequisitionConflictError):
            confirm_purchase_requisition_receipt(
                row.id,
                _user(4, "GERENTE"),
                session=session,
            )


def test_receipt_confirmation_validates_branch_and_optional_evidence(engine):
    with Session(engine) as session:
        row, _ = _seed_final_destination(session)
        session.add(
            _receipt_attachment(10, "RECEIPT_EVIDENCE")
        )
        session.flush()

        with pytest.raises(PurchaseRequisitionAuthorizationError):
            confirm_purchase_requisition_receipt(
                row.id,
                _user(4, "GERENTE", branch_id=20),
                evidence_attachment_ids=[10],
                session=session,
            )

        closed = confirm_purchase_requisition_receipt(
            row.id,
            _user(4, "GERENTE"),
            evidence_attachment_ids=[10, 10],
            session=session,
        )
        session.commit()

        assert closed.events[-1].metadata_json == {
            "evidence_attachment_ids": [10]
        }


def test_manager_reports_receipt_issue_with_required_typed_evidence(engine):
    with Session(engine) as session:
        row, _ = _seed_final_destination(session)
        session.add_all([
            _receipt_attachment(20, "RECEIPT_ISSUE_EVIDENCE"),
            _receipt_attachment(21, "RECEIPT_EVIDENCE"),
        ])
        session.flush()

        with pytest.raises(
            PurchaseRequisitionValidationError,
            match="issue_type inválido",
        ):
            report_purchase_requisition_receipt_issue(
                row.id,
                "UNKNOWN",
                "Llegó con daño.",
                [20],
                _user(4, "GERENTE"),
                session=session,
            )

        with pytest.raises(
            PurchaseRequisitionValidationError,
            match="al menos una evidencia",
        ):
            report_purchase_requisition_receipt_issue(
                row.id,
                "DAMAGED",
                "Llegó con daño.",
                [],
                _user(4, "GERENTE"),
                session=session,
            )

        with pytest.raises(
            PurchaseRequisitionValidationError,
            match="tipo inválido",
        ):
            report_purchase_requisition_receipt_issue(
                row.id,
                "DAMAGED",
                "Llegó con daño.",
                [21],
                _user(4, "GERENTE"),
                session=session,
            )

        issue = report_purchase_requisition_receipt_issue(
            row.id,
            "DAMAGED",
            "Llegó con daño en estructura.",
            [20],
            _user(4, "GERENTE"),
            session=session,
        )
        session.commit()

        assert issue.status == "RECEIPT_ISSUE"
        assert issue.events[-1].event_type == "RECEIPT_ISSUE_REPORTED"
        assert issue.events[-1].from_status == (
            "FINAL_DESTINATION_SHIPMENT"
        )
        assert issue.events[-1].to_status == "RECEIPT_ISSUE"
        assert issue.events[-1].comment == (
            "Llegó con daño en estructura."
        )
        assert issue.events[-1].metadata_json == {
            "issue_type": "DAMAGED",
            "evidence_attachment_ids": [20],
        }


def test_maintenance_resumes_logistics_after_receipt_issue(engine):
    with Session(engine) as session:
        row, _ = _seed_final_destination(session)
        session.add(
            _receipt_attachment(30, "RECEIPT_ISSUE_EVIDENCE")
        )
        session.flush()

        report_purchase_requisition_receipt_issue(
            row.id,
            "INCOMPLETE",
            "Falta una pieza.",
            [30],
            _user(4, "GERENTE"),
            session=session,
        )
        session.flush()

        with pytest.raises(PurchaseRequisitionAuthorizationError):
            resume_purchase_requisition_logistics(
                row.id,
                "Se solicitará la pieza.",
                _user(4, "GERENTE"),
                session=session,
            )

        with pytest.raises(
            PurchaseRequisitionValidationError,
            match="comment es obligatorio",
        ):
            resume_purchase_requisition_logistics(
                row.id,
                " ",
                _user(5, "MANTENIMIENTO"),
                session=session,
            )

        resumed = resume_purchase_requisition_logistics(
            row.id,
            "Proveedor enviará la pieza faltante.",
            _user(5, "MANTENIMIENTO"),
            session=session,
        )
        session.commit()

        assert resumed.status == "SHIPPING_IN_PROGRESS"
        assert resumed.events[-1].event_type == (
            "RECEIPT_ISSUE_RESOLUTION_STARTED"
        )
        assert resumed.events[-1].from_status == "RECEIPT_ISSUE"
        assert resumed.events[-1].to_status == "SHIPPING_IN_PROGRESS"
        assert resumed.events[-1].comment == (
            "Proveedor enviará la pieza faltante."
        )

def test_admin_correction_requires_admin_reason_comment_and_allowed_pair(engine):
    with Session(engine) as session:
        row = _seed(session)
        request_info_purchase_requisition(
            row.id,
            "Completar datos.",
            _user(2, "GERENCIA DEPORTIVA"),
            session=session,
        )
        session.flush()

        with pytest.raises(PurchaseRequisitionAuthorizationError):
            administratively_correct_purchase_requisition(
                row.id,
                "PENDING_REVIEW",
                "Error operativo",
                "Corrección requerida.",
                _user(4, "GERENTE"),
                session=session,
            )

        with pytest.raises(
            PurchaseRequisitionValidationError,
            match="reason es obligatorio",
        ):
            administratively_correct_purchase_requisition(
                row.id,
                "PENDING_REVIEW",
                " ",
                "Corrección requerida.",
                _user(3, "ADMINISTRADOR"),
                session=session,
            )

        with pytest.raises(
            PurchaseRequisitionValidationError,
            match="comment es obligatorio",
        ):
            administratively_correct_purchase_requisition(
                row.id,
                "PENDING_REVIEW",
                "Error operativo",
                " ",
                _user(3, "ADMINISTRADOR"),
                session=session,
            )

        with pytest.raises(PurchaseRequisitionConflictError):
            administratively_correct_purchase_requisition(
                row.id,
                "CLOSED",
                "Error operativo",
                "No se permite cerrar por corrección.",
                _user(3, "ADMINISTRADOR"),
                session=session,
            )


def test_admin_correction_reopens_rejected_and_clears_rejected_projection(engine):
    with Session(engine) as session:
        row = _seed(session)
        reject_purchase_requisition(
            row.id,
            "No procede.",
            _user(2, "GERENCIA DEPORTIVA"),
            session=session,
        )
        session.flush()
        assert row.rejected_at is not None

        corrected = administratively_correct_purchase_requisition(
            row.id,
            "PENDING_REVIEW",
            "Rechazo capturado por error",
            "Regresar a revisión.",
            _user(3, "ADMINISTRADOR"),
            session=session,
        )
        session.commit()

        assert corrected.status == "PENDING_REVIEW"
        assert corrected.rejected_at is None
        assert any(
            event.event_type == "REJECTED"
            for event in corrected.events
        )
        assert corrected.events[-1].event_type == (
            "ADMINISTRATIVE_CORRECTION"
        )
        assert corrected.events[-1].metadata_json["reason"] == (
            "Rechazo capturado por error"
        )


def test_admin_correction_reopens_initial_approval_and_clears_projection(engine):
    with Session(engine) as session:
        row = _seed(session)
        approve_purchase_requisition(
            row.id,
            _user(2, "GERENCIA DEPORTIVA"),
            comment="Procede.",
            session=session,
        )
        session.flush()

        assert row.approved_by_user_id == 2
        assert row.approved_at is not None

        corrected = administratively_correct_purchase_requisition(
            row.id,
            "PENDING_REVIEW",
            "Aprobación equivocada",
            "Debe revisarse nuevamente.",
            _user(3, "ADMINISTRADOR"),
            session=session,
        )
        session.commit()

        assert corrected.status == "PENDING_REVIEW"
        assert corrected.approved_by_user_id is None
        assert corrected.approved_at is None
        assert corrected.approval_comment is None
        assert any(
            event.event_type == "APPROVED"
            for event in corrected.events
        )
        assert corrected.events[-1].metadata_json[
            "invalidates_operational_effect"
        ] == "APPROVED"


def test_admin_correction_cancels_pending_finance_submission(engine):
    with Session(engine) as session:
        row, quote = _seed_finance_ready(session)
        submit_purchase_requisition_quote_for_finance(
            row.id,
            _user(5, "MANTENIMIENTO"),
            session=session,
        )
        session.flush()

        assert row.status == "QUOTE_PENDING_FINANCE_APPROVAL"
        assert quote.finance_status == "PENDING"
        assert quote.finance_submitted_at is not None

        corrected = administratively_correct_purchase_requisition(
            row.id,
            "IN_QUOTATION",
            "Envío financiero equivocado",
            "Regresar a cotización.",
            _user(3, "ADMINISTRADOR"),
            session=session,
        )
        session.commit()

        assert corrected.status == "IN_QUOTATION"
        assert quote.finance_status == "DRAFT"
        assert quote.is_selected is True
        assert quote.finance_submitted_by_user_id is None
        assert quote.finance_submitted_at is None
        assert corrected.events[-1].metadata_json[
            "cancel_finance_submission"
        ] is True


def test_admin_correction_reopens_finance_decision_from_payment(engine):
    with Session(engine) as session:
        row, quote = _seed_logistics_ready(session)

        corrected = administratively_correct_purchase_requisition(
            row.id,
            "QUOTE_PENDING_FINANCE_APPROVAL",
            "Aprobación financiera equivocada",
            "Finanzas debe decidir nuevamente.",
            _user(3, "ADMINISTRADOR"),
            session=session,
        )
        session.commit()

        assert corrected.status == "QUOTE_PENDING_FINANCE_APPROVAL"
        assert quote.finance_status == "PENDING"
        assert quote.finance_decided_by_user_id is None
        assert quote.finance_decided_at is None
        assert quote.finance_comment is None
        assert quote.finance_submitted_at is not None
        assert corrected.events[-1].metadata_json[
            "reopen_finance_decision"
        ] is True


def test_admin_correction_rolls_back_logistics_one_control(engine):
    with Session(engine) as session:
        row, _ = _seed_logistics_ready(session)
        advance_purchase_requisition_logistics(
            row.id,
            "SHIPPING_IN_PROGRESS",
            _user(5, "MANTENIMIENTO"),
            session=session,
        )
        session.flush()

        administratively_correct_purchase_requisition(
            row.id,
            "PAYMENT_REQUESTED",
            "Avance prematuro",
            "Pago aún no estaba listo.",
            _user(3, "ADMINISTRADOR"),
            session=session,
        )
        assert row.status == "PAYMENT_REQUESTED"

        advance_purchase_requisition_logistics(
            row.id,
            "SHIPPING_IN_PROGRESS",
            _user(5, "MANTENIMIENTO"),
            session=session,
        )
        advance_purchase_requisition_logistics(
            row.id,
            "IMPORT_IN_PROGRESS",
            _user(5, "MANTENIMIENTO"),
            session=session,
        )
        session.flush()

        administratively_correct_purchase_requisition(
            row.id,
            "SHIPPING_IN_PROGRESS",
            "Importación marcada por error",
            "Regresar al proceso de envío.",
            _user(3, "ADMINISTRADOR"),
            session=session,
        )
        session.commit()

        assert row.status == "SHIPPING_IN_PROGRESS"


def test_admin_correction_final_destination_without_import_respects_metadata(engine):
    with Session(engine) as session:
        row, _ = _seed_final_destination(session)

        with pytest.raises(PurchaseRequisitionConflictError):
            administratively_correct_purchase_requisition(
                row.id,
                "IMPORT_IN_PROGRESS",
                "Ruta incorrecta",
                "No debía ir a importación.",
                _user(3, "ADMINISTRADOR"),
                session=session,
            )

        corrected = administratively_correct_purchase_requisition(
            row.id,
            "SHIPPING_IN_PROGRESS",
            "Destino final marcado prematuramente",
            "Regresar a envío.",
            _user(3, "ADMINISTRADOR"),
            session=session,
        )
        session.commit()

        assert corrected.status == "SHIPPING_IN_PROGRESS"
        assert corrected.events[-1].metadata_json[
            "import_required"
        ] is False


def test_admin_correction_final_destination_with_import_respects_metadata(engine):
    with Session(engine) as session:
        row, _ = _seed_logistics_ready(session)
        advance_purchase_requisition_logistics(
            row.id,
            "SHIPPING_IN_PROGRESS",
            _user(5, "MANTENIMIENTO"),
            session=session,
        )
        advance_purchase_requisition_logistics(
            row.id,
            "IMPORT_IN_PROGRESS",
            _user(5, "MANTENIMIENTO"),
            session=session,
        )
        advance_purchase_requisition_logistics(
            row.id,
            "FINAL_DESTINATION_SHIPMENT",
            _user(5, "MANTENIMIENTO"),
            session=session,
        )
        session.flush()

        with pytest.raises(PurchaseRequisitionConflictError):
            administratively_correct_purchase_requisition(
                row.id,
                "SHIPPING_IN_PROGRESS",
                "Ruta incorrecta",
                "Importación sí aplica.",
                _user(3, "ADMINISTRADOR"),
                session=session,
            )

        corrected = administratively_correct_purchase_requisition(
            row.id,
            "IMPORT_IN_PROGRESS",
            "Destino final marcado prematuramente",
            "Regresar a importación.",
            _user(3, "ADMINISTRADOR"),
            session=session,
        )
        session.commit()

        assert corrected.status == "IMPORT_IN_PROGRESS"
        assert corrected.events[-1].metadata_json[
            "import_required"
        ] is True


def test_admin_correction_reopens_receipt_issue_without_erasing_history(engine):
    with Session(engine) as session:
        row, _ = _seed_final_destination(session)
        session.add(
            _receipt_attachment(40, "RECEIPT_ISSUE_EVIDENCE")
        )
        session.flush()

        report_purchase_requisition_receipt_issue(
            row.id,
            "WRONG_ITEM",
            "Equipo incorrecto.",
            [40],
            _user(4, "GERENTE"),
            session=session,
        )
        session.flush()

        corrected = administratively_correct_purchase_requisition(
            row.id,
            "FINAL_DESTINATION_SHIPMENT",
            "Incidencia capturada por error",
            "Regresar a validación de recibido.",
            _user(3, "ADMINISTRADOR"),
            session=session,
        )
        session.commit()

        assert corrected.status == "FINAL_DESTINATION_SHIPMENT"
        assert any(
            event.event_type == "RECEIPT_ISSUE_REPORTED"
            for event in corrected.events
        )
        assert corrected.events[-1].metadata_json[
            "invalidate_receipt_issue_operational_effect"
        ] is True


def test_admin_correction_reopens_closed_to_final_without_erasing_history(engine):
    with Session(engine) as session:
        row, _ = _seed_final_destination(session)
        confirm_purchase_requisition_receipt(
            row.id,
            _user(4, "GERENTE"),
            session=session,
        )
        session.flush()

        corrected = administratively_correct_purchase_requisition(
            row.id,
            "FINAL_DESTINATION_SHIPMENT",
            "Recepción confirmada por error",
            "Reabrir para validar nuevamente.",
            _user(3, "ADMINISTRADOR"),
            session=session,
        )
        session.commit()

        assert corrected.status == "FINAL_DESTINATION_SHIPMENT"
        assert any(
            event.event_type == "RECEIVED"
            for event in corrected.events
        )
        assert corrected.events[-1].metadata_json[
            "reopen_after_receipt"
        ] is True


def test_admin_correction_reopens_closed_to_receipt_issue_without_erasing_history(engine):
    with Session(engine) as session:
        row, _ = _seed_final_destination(session)
        confirm_purchase_requisition_receipt(
            row.id,
            _user(4, "GERENTE"),
            session=session,
        )
        session.flush()

        corrected = administratively_correct_purchase_requisition(
            row.id,
            "RECEIPT_ISSUE",
            "Recepción realmente no conforme",
            "Reabrir como incidencia.",
            _user(3, "ADMINISTRADOR"),
            session=session,
        )
        session.commit()

        assert corrected.status == "RECEIPT_ISSUE"
        assert any(
            event.event_type == "RECEIVED"
            for event in corrected.events
        )
        assert corrected.events[-1].metadata_json[
            "reopen_after_receipt"
        ] is True
        assert corrected.events[-1].metadata_json[
            "target_receipt_issue"
        ] is True
