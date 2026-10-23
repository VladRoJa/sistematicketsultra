"""Fase A P23: denegaciones reales del servicio de aprobación financiera.

SQLite efímero con modelos ORM reales, sin PostgreSQL, HTTP, JWT ni grants.
No cambia autorización; fija el comportamiento legacy y las invariantes de no
mutación ante rechazos por actor, estado o cotización.
"""
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, Column, Integer, MetaData, String, Table, create_engine, select, func
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.purchase_requisition import (
    PurchaseRequisitionAttachmentORM,
    PurchaseRequisitionEventORM,
    PurchaseRequisitionFinanceApproverORM,
    PurchaseRequisitionORM,
    PurchaseRequisitionQuoteORM,
    PurchaseRequisitionQuoteFinanceStatus as QuoteStatus,
    PurchaseRequisitionStatus as Status,
)
from app.services.purchase_requisition_workflow_service import (
    PurchaseRequisitionConflictError,
    approve_purchase_requisition_quote_by_finance,
)
from app.utils.purchase_requisition_permissions import (
    PurchaseRequisitionAuthorizationError,
    can_purchase_requisition_approve_quote,
)


@compiles(BigInteger, "sqlite")
def _sqlite_bigint(_type, _compiler, **_kwargs):
    return "INTEGER"


@pytest.fixture
def finance_engine():
    engine = create_engine("sqlite://")
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
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        metadata.create_all(conn)
        conn.exec_driver_sql(
            "INSERT INTO users (id, username, rol) VALUES "
            "(1, 'solicitante', 'RECEPCIONISTA'), "
            "(3, 'administrador', 'ADMINISTRADOR'), "
            "(6, 'aprobador', 'RECEPCIONISTA'), "
            "(7, 'coordinador', 'COORDINADOR_MANTENIMIENTO'), "
            "(8, 'noasignado', 'GERENCIA DEPORTIVA')"
        )
        conn.exec_driver_sql("INSERT INTO sucursales (sucursal_id) VALUES (10), (20)")
    try:
        yield engine
    finally:
        engine.dispose()


def _user(user_id, role, branch_id=10):
    return SimpleNamespace(
        id=user_id, rol=role, username=f"qa-{user_id}",
        sucursal_id=branch_id, sucursales_ids=[branch_id],
    )


def _seed_pending(session):
    requisition = PurchaseRequisitionORM(
        id=1, public_id="P23-QA-001", sucursal_id=10,
        created_by_user_id=1, reason="REPLACEMENT",
        justification="Equipo por reemplazar.",
        status=Status.QUOTE_PENDING_FINANCE_APPROVAL,
    )
    session.add(requisition)
    session.flush()
    attachment = PurchaseRequisitionAttachmentORM(
        id=1, requisition_id=1, attachment_type="QUOTE",
        original_filename="qa_quote.pdf",
        storage_key="qa/p23/quote.pdf",
        mime_type="application/pdf", size_bytes=128,
        sha256="a" * 64, uploaded_by_user_id=1,
    )
    session.add(attachment)
    session.flush()
    quote = PurchaseRequisitionQuoteORM(
        id=1, requisition_id=1, supplier_name="Proveedor QA",
        amount=1500, currency="MXN", quote_date=date(2026, 10, 23),
        attachment_id=1, created_by_user_id=1,
        is_selected=True, selected_by_user_id=1,
        finance_status=QuoteStatus.PENDING,
        finance_submitted_by_user_id=1,
    )
    session.add(quote)
    for user_id in (6, 7):
        session.add(PurchaseRequisitionFinanceApproverORM(
            user_id=user_id, is_active=True, added_by_user_id=3,
        ))
    session.commit()
    return requisition, quote


def _state(session):
    req = session.get(PurchaseRequisitionORM, 1)
    quote = session.get(PurchaseRequisitionQuoteORM, 1)
    count = session.scalar(
        select(func.count(PurchaseRequisitionEventORM.id))
        .where(PurchaseRequisitionEventORM.requisition_id == 1)
    )
    return (
        req.status,
        quote.is_selected,
        quote.finance_status,
        quote.finance_decided_by_user_id,
        quote.finance_decided_at,
        quote.finance_comment,
        count,
    )


def _assert_denial_atomic(session, operation, error, message=None):
    before = _state(session)
    if message:
        with pytest.raises(error, match=message):
            operation()
    else:
        with pytest.raises(error):
            operation()
    session.flush()
    assert _state(session) == before, "A denied approval mutated requisition/quote/audit"


@pytest.mark.parametrize(
    "actor",
    [
        _user(3, "ADMINISTRADOR"),
        _user(8, "GERENCIA DEPORTIVA"),
        _user(0, "RECEPCIONISTA"),
        _user(6, "COORDINADOR_MANTENIMIENTO"),
    ],
    ids=[
        "admin_without_finance_assignment",
        "business_reviewer_without_finance_assignment",
        "invalid_actor_id",
        "coordinator_role_blocked_even_with_approved_user_id",
    ],
)
def test_p23_finance_approval_denies_unentitled_actor_without_writes(
    finance_engine, actor
):
    with Session(finance_engine) as session:
        _seed_pending(session)
        if actor.id == 6 and actor.rol == "COORDINADOR_MANTENIMIENTO":
            # Perfil ficticio: mismo ID asignado, pero rol expresamente excluido.
            pass
        assert not can_purchase_requisition_approve_quote(actor, session=session)
        _assert_denial_atomic(
            session,
            lambda: approve_purchase_requisition_quote_by_finance(
                1, actor, session=session
            ),
            PurchaseRequisitionAuthorizationError,
            "No autorizado",
        )


def test_p23_inactive_approver_is_revoked_before_any_mutation(finance_engine):
    with Session(finance_engine) as session:
        _seed_pending(session)
        approver = session.scalar(
            select(PurchaseRequisitionFinanceApproverORM)
            .where(PurchaseRequisitionFinanceApproverORM.user_id == 6)
        )
        approver.is_active = False
        session.flush()
        actor = _user(6, "RECEPCIONISTA")
        assert not can_purchase_requisition_approve_quote(actor, session=session)
        _assert_denial_atomic(
            session,
            lambda: approve_purchase_requisition_quote_by_finance(
                1, actor, session=session
            ),
            PurchaseRequisitionAuthorizationError,
        )


@pytest.mark.parametrize("state", [
    Status.IN_QUOTATION,
    Status.PAYMENT_REQUESTED,
    Status.CLOSED,
])
def test_p23_invalid_requisition_state_is_business_conflict_without_writes(
    finance_engine, state
):
    with Session(finance_engine) as session:
        _seed_pending(session)
        session.get(PurchaseRequisitionORM, 1).status = state
        session.flush()
        actor = _user(6, "RECEPCIONISTA")
        assert can_purchase_requisition_approve_quote(actor, session=session)
        _assert_denial_atomic(
            session,
            lambda: approve_purchase_requisition_quote_by_finance(
                1, actor, session=session
            ),
            PurchaseRequisitionConflictError,
            "ya no está en un estado válido",
        )


@pytest.mark.parametrize("selected,quote_status", [
    (False, QuoteStatus.PENDING),
    (True, QuoteStatus.DRAFT),
    (True, QuoteStatus.REJECTED),
    (True, QuoteStatus.APPROVED),
])
def test_p23_missing_or_nonpending_selected_quote_blocks_approval(
    finance_engine, selected, quote_status
):
    with Session(finance_engine) as session:
        _seed_pending(session)
        quote = session.get(PurchaseRequisitionQuoteORM, 1)
        quote.is_selected = selected
        quote.finance_status = quote_status
        session.flush()
        actor = _user(6, "RECEPCIONISTA")
        _assert_denial_atomic(
            session,
            lambda: approve_purchase_requisition_quote_by_finance(
                1, actor, session=session
            ),
            PurchaseRequisitionConflictError,
            "No existe una cotización pendiente válida",
        )


def test_p23_global_finance_allowlist_currently_has_no_branch_restriction(
    finance_engine
):
    """Caracteriza el comportamiento EXISTENTE, no aprueba su politica futura."""
    with Session(finance_engine) as session:
        _seed_pending(session)
        actor = _user(6, "RECEPCIONISTA", branch_id=20)
        assert can_purchase_requisition_approve_quote(actor, session=session)
        result = approve_purchase_requisition_quote_by_finance(
            1, actor, session=session
        )
        session.flush()
        assert result.sucursal_id == 10
        assert result.status == Status.PAYMENT_REQUESTED
        quote = session.get(PurchaseRequisitionQuoteORM, 1)
        assert quote.finance_status == QuoteStatus.APPROVED
        assert quote.finance_decided_by_user_id == 6
        assert _state(session)[-1] == 2
        # La permitida aprobación de sucursal ajena exige decisión de política:
        # la allowlist es global en el helper actual, NO filtro por sucursal.


def test_p23_success_is_not_inherited_by_unassigned_admin(finance_engine):
    with Session(finance_engine) as session:
        _seed_pending(session)
        # Aunque coexiste un aprobador activo, otro usuario no hereda acceso.
        actor = _user(3, "ADMINISTRADOR")
        assert not can_purchase_requisition_approve_quote(actor, session=session)
        _assert_denial_atomic(
            session,
            lambda: approve_purchase_requisition_quote_by_finance(
                1, actor, session=session
            ),
            PurchaseRequisitionAuthorizationError,
        )
