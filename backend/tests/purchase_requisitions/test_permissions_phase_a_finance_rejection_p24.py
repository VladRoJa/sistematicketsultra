"""Fase A P24: rechazo financiero, denegaciones atomicas y transicion valida.

Usa el servicio de Requisiciones REAL con SQLAlchemy y SQLite temporal.
No se realizan requests HTTP, ni se consulta PostgreSQL, ni se altera el
catalogo de permisos ni los guards de produccion.
"""
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import (
    BigInteger, Column, Integer, MetaData, String, Table, create_engine,
    func, select,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.purchase_requisition import (
    PurchaseRequisitionAttachmentORM,
    PurchaseRequisitionEventORM,
    PurchaseRequisitionEventType as Event,
    PurchaseRequisitionFinanceApproverORM,
    PurchaseRequisitionORM,
    PurchaseRequisitionQuoteORM,
    PurchaseRequisitionQuoteFinanceStatus as QuoteState,
    PurchaseRequisitionStatus as Status,
)
from app.services.purchase_requisition_service import (
    PurchaseRequisitionValidationError,
)
from app.services.purchase_requisition_workflow_service import (
    PurchaseRequisitionConflictError,
    reject_purchase_requisition_quote_by_finance,
)
from app.utils.purchase_requisition_permissions import (
    PurchaseRequisitionAuthorizationError,
    can_purchase_requisition_approve_quote,
)


@compiles(BigInteger, "sqlite")
def _p24_integer_bigint(_type, _compiler, **_kwargs):
    return "INTEGER"


@pytest.fixture
def engine():
    value = create_engine("sqlite://")
    metadata = MetaData()
    Table(
        "users", metadata,
        Column("id", Integer, primary_key=True),
        Column("username", String(100)),
        Column("rol", String(80)),
    )
    Table("sucursales", metadata, Column("sucursal_id", Integer, primary_key=True))
    for orm in (
        PurchaseRequisitionORM,
        PurchaseRequisitionEventORM,
        PurchaseRequisitionAttachmentORM,
        PurchaseRequisitionQuoteORM,
        PurchaseRequisitionFinanceApproverORM,
    ):
        orm.__table__.to_metadata(metadata)
    with value.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        metadata.create_all(conn)
        conn.exec_driver_sql(
            "INSERT INTO users (id, username, rol) VALUES "
            "(1, 'solicitante', 'RECEPCIONISTA'), "
            "(3, 'admin', 'ADMINISTRADOR'), "
            "(6, 'aprobador', 'RECEPCIONISTA'), "
            "(7, 'coordinador', 'COORDINADOR_MANTENIMIENTO'), "
            "(8, 'revisor', 'GERENCIA DEPORTIVA')"
        )
        conn.exec_driver_sql("INSERT INTO sucursales (sucursal_id) VALUES (10), (20)")
    try:
        yield value
    finally:
        value.dispose()


def _actor(user_id, role, branch=10):
    return SimpleNamespace(
        id=user_id, rol=role, username=f"qa-{user_id}",
        sucursal_id=branch, sucursales_ids=[branch],
    )


def _seed(session):
    row = PurchaseRequisitionORM(
        id=1, public_id="P24-QA-001", sucursal_id=10,
        created_by_user_id=1, reason="REPLACEMENT",
        justification="Equipo ficticio por reemplazar.",
        status=Status.QUOTE_PENDING_FINANCE_APPROVAL,
    )
    session.add(row)
    session.flush()
    session.add(PurchaseRequisitionAttachmentORM(
        id=1, requisition_id=1, attachment_type="QUOTE",
        original_filename="p24.pdf", storage_key="qa/p24/quote.pdf",
        mime_type="application/pdf", size_bytes=100,
        sha256="b" * 64, uploaded_by_user_id=1,
    ))
    session.flush()
    quote = PurchaseRequisitionQuoteORM(
        id=1, requisition_id=1, supplier_name="Proveedor ficticio",
        amount=1600, currency="MXN", quote_date=date(2026, 10, 23),
        attachment_id=1, created_by_user_id=1,
        is_selected=True, selected_by_user_id=1,
        finance_status=QuoteState.PENDING, finance_submitted_by_user_id=1,
    )
    session.add(quote)
    for user_id in (6, 7):
        session.add(PurchaseRequisitionFinanceApproverORM(
            user_id=user_id, is_active=True, added_by_user_id=3,
        ))
    session.commit()
    return row, quote


def _snapshot(session):
    row = session.get(PurchaseRequisitionORM, 1)
    quote = session.get(PurchaseRequisitionQuoteORM, 1)
    events = session.scalars(
        select(PurchaseRequisitionEventORM)
        .where(PurchaseRequisitionEventORM.requisition_id == 1)
        .order_by(PurchaseRequisitionEventORM.id)
    ).all()
    return (
        row.status,
        quote.is_selected,
        quote.selected_by_user_id,
        quote.selected_at,
        quote.finance_status,
        quote.finance_decided_by_user_id,
        quote.finance_decided_at,
        quote.finance_comment,
        tuple((e.event_type, e.actor_user_id, e.from_status, e.to_status) for e in events),
    )


def _must_deny_without_write(session, operation, error, match=None):
    before = _snapshot(session)
    with pytest.raises(error, match=match):
        operation()
    session.flush()
    assert _snapshot(session) == before, "Denied rejection changed state or events"


@pytest.mark.parametrize("user", [
    _actor(3, "ADMINISTRADOR"),
    _actor(8, "GERENCIA DEPORTIVA"),
    _actor(0, "RECEPCIONISTA"),
    _actor(6, "COORDINADOR_MANTENIMIENTO"),
], ids=[
    "admin_without_finance_appointment",
    "reviewer_without_finance_appointment",
    "nonpositive_user_id",
    "coordinator_excluded_even_if_finance_assigned",
])
def test_p24_unentitled_actor_cannot_reject_or_write(engine, user):
    with Session(engine) as session:
        _seed(session)
        assert not can_purchase_requisition_approve_quote(user, session=session)
        _must_deny_without_write(
            session,
            lambda: reject_purchase_requisition_quote_by_finance(
                1, "Revisar presupuesto.", user, session=session,
            ),
            PurchaseRequisitionAuthorizationError, "No autorizado",
        )


def test_p24_inactive_finance_approver_denied_before_mutation(engine):
    with Session(engine) as session:
        _seed(session)
        finance = session.scalar(
            select(PurchaseRequisitionFinanceApproverORM)
            .where(PurchaseRequisitionFinanceApproverORM.user_id == 6)
        )
        finance.is_active = False
        session.flush()
        user = _actor(6, "RECEPCIONISTA")
        assert not can_purchase_requisition_approve_quote(user, session=session)
        _must_deny_without_write(
            session,
            lambda: reject_purchase_requisition_quote_by_finance(
                1, "Revisar.", user, session=session
            ),
            PurchaseRequisitionAuthorizationError,
        )


@pytest.mark.parametrize("state", [
    Status.IN_QUOTATION,
    Status.PAYMENT_REQUESTED,
    Status.CLOSED,
])
def test_p24_wrong_requisition_state_denied_without_writes(engine, state):
    with Session(engine) as session:
        _seed(session)
        session.get(PurchaseRequisitionORM, 1).status = state
        session.flush()
        _must_deny_without_write(
            session,
            lambda: reject_purchase_requisition_quote_by_finance(
                1, "Revisar.", _actor(6, "RECEPCIONISTA"), session=session
            ),
            PurchaseRequisitionConflictError, "ya no está en un estado válido",
        )


@pytest.mark.parametrize("selected,finance_status", [
    (False, QuoteState.PENDING),
    (True, QuoteState.DRAFT),
    (True, QuoteState.REJECTED),
    (True, QuoteState.APPROVED),
])
def test_p24_invalid_selected_quote_denied_without_writes(
    engine, selected, finance_status
):
    with Session(engine) as session:
        _seed(session)
        quote = session.get(PurchaseRequisitionQuoteORM, 1)
        quote.is_selected = selected
        quote.finance_status = finance_status
        session.flush()
        _must_deny_without_write(
            session,
            lambda: reject_purchase_requisition_quote_by_finance(
                1, "Revisar.", _actor(6, "RECEPCIONISTA"), session=session
            ),
            PurchaseRequisitionConflictError, "No existe una cotización pendiente válida",
        )


@pytest.mark.parametrize("reason", [None, "", "   ", "\t\n"])
def test_p24_empty_reason_denied_without_writes(engine, reason):
    with Session(engine) as session:
        _seed(session)
        _must_deny_without_write(
            session,
            lambda: reject_purchase_requisition_quote_by_finance(
                1, reason, _actor(6, "RECEPCIONISTA"), session=session
            ),
            PurchaseRequisitionValidationError, "reason es obligatorio",
        )


def test_p24_valid_rejection_releases_selected_quote_and_adds_one_event(engine):
    with Session(engine) as session:
        _seed(session)
        actor = _actor(6, "RECEPCIONISTA")
        rejected = reject_purchase_requisition_quote_by_finance(
            1, "  Precio superior al autorizado.  ", actor, session=session
        )
        session.flush()
        quote = session.get(PurchaseRequisitionQuoteORM, 1)
        assert rejected.status == Status.IN_QUOTATION
        assert quote.finance_status == QuoteState.REJECTED
        assert quote.is_selected is False
        assert quote.selected_by_user_id is None
        assert quote.selected_at is None
        assert quote.finance_decided_by_user_id == 6
        assert quote.finance_decided_at is not None
        assert quote.finance_comment == "Precio superior al autorizado."
        events = session.scalars(
            select(PurchaseRequisitionEventORM)
            .where(PurchaseRequisitionEventORM.requisition_id == 1)
        ).all()
        assert len(events) == 1
        assert events[0].event_type == Event.QUOTE_REJECTED_BY_FINANCE
        assert events[0].actor_user_id == 6
        assert events[0].from_status == Status.QUOTE_PENDING_FINANCE_APPROVAL
        assert events[0].to_status == Status.IN_QUOTATION


def test_p24_repeating_rejection_cannot_add_a_second_audit_event(engine):
    with Session(engine) as session:
        _seed(session)
        actor = _actor(6, "RECEPCIONISTA")
        reject_purchase_requisition_quote_by_finance(
            1, "Rechazo inicial.", actor, session=session
        )
        session.flush()
        _must_deny_without_write(
            session,
            lambda: reject_purchase_requisition_quote_by_finance(
                1, "Rechazo duplicado.", actor, session=session
            ),
            PurchaseRequisitionConflictError, "ya no está en un estado válido",
        )


def test_p24_cross_branch_rejection_characterizes_global_finance_allowlist(engine):
    """No asume que el alcance global actual sea la politica definitiva."""
    with Session(engine) as session:
        _seed(session)
        user = _actor(6, "RECEPCIONISTA", branch=20)
        assert can_purchase_requisition_approve_quote(user, session=session)
        rejected = reject_purchase_requisition_quote_by_finance(
            1, "Revisar presupuesto.", user, session=session
        )
        session.flush()
        assert rejected.sucursal_id == 10
        assert rejected.status == Status.IN_QUOTATION
        assert session.get(PurchaseRequisitionQuoteORM, 1).finance_status == QuoteState.REJECTED
        assert session.scalar(
            select(func.count(PurchaseRequisitionEventORM.id))
        ) == 1
