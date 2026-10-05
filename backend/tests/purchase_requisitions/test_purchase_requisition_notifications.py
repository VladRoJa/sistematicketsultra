from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, Column, Integer, MetaData, String, Table, Text, create_engine, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.purchase_requisition import (
    PurchaseRequisitionEventORM,
    PurchaseRequisitionItemORM,
    PurchaseRequisitionNotificationORM,
    PurchaseRequisitionORM,
)
from app.services.purchase_requisition_notification_service import (
    dispatch_event_notifications,
    latest_event_id,
    resolve_notification_recipients,
)
from app.services.purchase_requisition_service import (
    create_purchase_requisition,
)
from app.services.purchase_requisition_workflow_service import (
    approve_purchase_requisition,
    reject_purchase_requisition,
    request_info_purchase_requisition,
    resubmit_purchase_requisition,
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
        Column("username", String(100), nullable=False),
        Column("password", String(255), nullable=False),
        Column("rol", String(50), nullable=False),
        Column("sucursal_id", Integer, nullable=False),
        Column("department_id", Integer, nullable=False),
        Column("email", String(255), nullable=True),
    )
    Table(
        "sucursales",
        metadata,
        Column("sucursal_id", Integer, primary_key=True),
    )
    PurchaseRequisitionORM.__table__.to_metadata(metadata)
    PurchaseRequisitionItemORM.__table__.to_metadata(metadata)
    PurchaseRequisitionEventORM.__table__.to_metadata(metadata)
    PurchaseRequisitionNotificationORM.__table__.to_metadata(metadata)

    with value.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        metadata.create_all(connection)
        connection.exec_driver_sql(
            "INSERT INTO sucursales (sucursal_id) VALUES (10)"
        )
        rows = [
            (1, "requester", "RECEPCIONISTA", "requester@example.com"),
            (2, "sports", "GERENCIA DEPORTIVA", "sports@example.com"),
            (3, "admin", "ADMINISTRADOR", "admin@example.com"),
            (4, "maint", "MANTENIMIENTO", "maint@example.com"),
            (5, "srmaint", "SR_MANTENIMIENTO", "srmaint@example.com"),
            (6, "auxmaint", "AUX_MANTENIMIENTO", "auxmaint@example.com"),
        ]
        for user_id, username, role, email in rows:
            connection.exec_driver_sql(
                "INSERT INTO users "
                "(id, username, password, rol, sucursal_id, department_id, email) "
                "VALUES (?, ?, 'x', ?, 10, 1, ?)",
                (user_id, username, role, email),
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


def _create(session):
    row = create_purchase_requisition(
        _payload(),
        _user(1, "RECEPCIONISTA"),
        session=session,
    )
    session.commit()
    return row


def _event(session, requisition_id, event_type):
    event_id = latest_event_id(
        requisition_id,
        event_type,
        session=session,
    )
    assert event_id is not None
    return session.get(PurchaseRequisitionEventORM, event_id)


def test_created_targets_only_sports_reviewers(engine):
    with Session(engine) as session:
        row = _create(session)
        event = _event(session, row.id, "CREATED")
        recipients = resolve_notification_recipients(
            session,
            row,
            event.event_type,
        )

        assert recipients == [(2, "sports@example.com")]


def test_info_requested_and_rejected_target_only_requester(engine):
    with Session(engine) as session:
        row = _create(session)
        request_info_purchase_requisition(
            row.id,
            "Aclarar.",
            _user(2, "GERENCIA DEPORTIVA"),
            session=session,
        )
        session.commit()

        event = _event(session, row.id, "INFO_REQUESTED")
        assert resolve_notification_recipients(
            session,
            row,
            event.event_type,
        ) == [(1, "requester@example.com")]

        resubmit_purchase_requisition(
            row.id,
            _user(1, "RECEPCIONISTA"),
            session=session,
        )
        session.commit()
        reject_purchase_requisition(
            row.id,
            "No procede.",
            _user(2, "GERENCIA DEPORTIVA"),
            session=session,
        )
        session.commit()

        event = _event(session, row.id, "REJECTED")
        assert resolve_notification_recipients(
            session,
            row,
            event.event_type,
        ) == [(1, "requester@example.com")]


def test_approved_targets_requester_and_all_maintenance_roles(engine):
    with Session(engine) as session:
        row = _create(session)
        approve_purchase_requisition(
            row.id,
            _user(3, "ADMINISTRADOR"),
            comment="Autorizada.",
            session=session,
        )
        session.commit()

        event = _event(session, row.id, "APPROVED")
        recipients = {
            email
            for _, email in resolve_notification_recipients(
                session,
                row,
                event.event_type,
            )
        }
        assert recipients == {
            "requester@example.com",
            "maint@example.com",
            "srmaint@example.com",
            "auxmaint@example.com",
        }

        routed = session.scalars(
            select(PurchaseRequisitionEventORM).where(
                PurchaseRequisitionEventORM.requisition_id == row.id,
                PurchaseRequisitionEventORM.event_type
                == "ROUTED_TO_MAINTENANCE",
            )
        ).all()
        assert len(routed) == 1


def test_notification_retry_does_not_duplicate_sent_email(engine):
    sent = []

    def fake_sender(to_list, subject, html):
        sent.append((tuple(to_list), subject, html))

    with Session(engine) as session:
        row = _create(session)
        event = _event(session, row.id, "CREATED")

        first = dispatch_event_notifications(
            event.id,
            session=session,
            sender=fake_sender,
        )
        second = dispatch_event_notifications(
            event.id,
            session=session,
            sender=fake_sender,
        )

        assert len(first) == 1
        assert len(second) == 1
        assert len(sent) == 1
        assert first[0].status == "SENT"
        count = session.scalar(
            select(PurchaseRequisitionNotificationORM)
            .where(
                PurchaseRequisitionNotificationORM.event_id
                == event.id
            )
            .count()
        ) if False else None
        rows = session.scalars(
            select(PurchaseRequisitionNotificationORM).where(
                PurchaseRequisitionNotificationORM.event_id
                == event.id
            )
        ).all()
        assert len(rows) == 1
        assert rows[0].attempts == 1


def test_email_failure_does_not_revert_approved_business_state(engine):
    def failing_sender(to_list, subject, html):
        raise RuntimeError("smtp unavailable")

    with Session(engine) as session:
        row = _create(session)
        approve_purchase_requisition(
            row.id,
            _user(3, "ADMINISTRADOR"),
            session=session,
        )
        session.commit()
        event = _event(session, row.id, "APPROVED")

        deliveries = dispatch_event_notifications(
            event.id,
            session=session,
            sender=failing_sender,
        )

        session.expire_all()
        persisted = session.get(PurchaseRequisitionORM, row.id)
        assert persisted.status == "IN_QUOTATION"
        assert len(deliveries) == 4
        assert all(
            delivery.status == "FAILED"
            for delivery in deliveries
        )


def test_routed_event_has_no_separate_email_target(engine):
    with Session(engine) as session:
        row = _create(session)
        approve_purchase_requisition(
            row.id,
            _user(3, "ADMINISTRADOR"),
            session=session,
        )
        session.commit()
        event = _event(
            session,
            row.id,
            "ROUTED_TO_MAINTENANCE",
        )
        assert resolve_notification_recipients(
            session,
            row,
            event.event_type,
        ) == []
