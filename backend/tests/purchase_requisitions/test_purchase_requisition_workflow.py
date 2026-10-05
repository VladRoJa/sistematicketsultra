from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, Column, Integer, MetaData, String, Table, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.purchase_requisition import (
    PurchaseRequisitionEventORM,
    PurchaseRequisitionItemORM,
    PurchaseRequisitionORM,
)
from app.services.purchase_requisition_service import (
    PurchaseRequisitionValidationError,
    create_purchase_requisition,
)
from app.services.purchase_requisition_workflow_service import (
    PurchaseRequisitionConflictError,
    approve_purchase_requisition,
    reject_purchase_requisition,
    request_info_purchase_requisition,
    requester_edit_purchase_requisition,
    resubmit_purchase_requisition,
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
    with value.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        metadata.create_all(connection)
        connection.exec_driver_sql(
            "INSERT INTO users (id, username, rol) VALUES "
            "(1, 'requester', 'RECEPCIONISTA'), "
            "(2, 'sports', 'GERENCIA DEPORTIVA'), "
            "(3, 'admin', 'ADMINISTRADOR'), "
            "(4, 'manager', 'GERENTE')"
        )
        connection.exec_driver_sql(
            "INSERT INTO sucursales (sucursal_id) VALUES (10)"
        )
    try:
        yield value
    finally:
        value.dispose()


def _user(user_id, role):
    return SimpleNamespace(
        id=user_id,
        username=f"user-{user_id}",
        rol=role,
        sucursal_id=10,
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
