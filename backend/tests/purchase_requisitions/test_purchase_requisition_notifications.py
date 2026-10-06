from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, Column, Integer, MetaData, String, Table, Text, create_engine, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.purchase_requisition import (
    PurchaseRequisitionEventORM,
    PurchaseRequisitionFinanceApproverORM,
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
    PurchaseRequisitionFinanceApproverORM.__table__.to_metadata(metadata)

    with value.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        metadata.create_all(connection)
        connection.exec_driver_sql(
            "INSERT INTO sucursales (sucursal_id) VALUES (10)"
        )
        rows = [
            (1, "requester", "RECEPCIONISTA", 10, "requester@example.com"),
            (2, "sports", "GERENCIA DEPORTIVA", 10, "sports@example.com"),
            (3, "admin", "ADMINISTRADOR", 10, "admin@example.com"),
            (4, "maint", "MANTENIMIENTO", 10, "maint@example.com"),
            (5, "srmaint", "SR_MANTENIMIENTO", 10, "srmaint@example.com"),
            (6, "auxmaint", "AUX_MANTENIMIENTO", 10, "auxmaint@example.com"),
            (7, "finance1", "RECEPCIONISTA", 10, "finance@example.com"),
            (8, "finance2", "GERENTE", 20, "inactive-finance@example.com"),
            (9, "finance3", "RECEPCIONISTA", 10, "FINANCE@example.com"),
            (10, "manager-a", "GERENTE", 10, "manager-a@example.com"),
            (11, "manager-b", "GERENTE", 10, "manager-b@example.com"),
            (12, "manager-other", "GERENTE", 20, "manager-other@example.com"),
        ]
        for user_id, username, role, branch_id, email in rows:
            connection.exec_driver_sql(
                "INSERT INTO users "
                "(id, username, password, rol, sucursal_id, department_id, email) "
                "VALUES (?, ?, 'x', ?, ?, 1, ?)",
                (user_id, username, role, branch_id, email),
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

def test_finance_events_follow_e1_notification_matrix(engine):
    with Session(engine) as session:
        row = _create(session)
        session.add_all([
            PurchaseRequisitionFinanceApproverORM(
                user_id=7,
                is_active=True,
                added_by_user_id=3,
            ),
            PurchaseRequisitionFinanceApproverORM(
                user_id=8,
                is_active=False,
                added_by_user_id=3,
            ),
            PurchaseRequisitionFinanceApproverORM(
                user_id=9,
                is_active=True,
                added_by_user_id=3,
            ),
        ])
        session.commit()

        finance_recipients = resolve_notification_recipients(
            session,
            row,
            "QUOTE_SUBMITTED_FOR_FINANCE_APPROVAL",
        )
        assert len(finance_recipients) == 1
        assert {
            email for _, email in finance_recipients
        } == {"finance@example.com"}

        maintenance_expected = {
            "maint@example.com",
            "srmaint@example.com",
            "auxmaint@example.com",
        }
        for event_type in (
            "QUOTE_APPROVED_BY_FINANCE",
            "QUOTE_REJECTED_BY_FINANCE",
        ):
            assert {
                email
                for _, email in resolve_notification_recipients(
                    session,
                    row,
                    event_type,
                )
            } == maintenance_expected

        assert resolve_notification_recipients(
            session,
            row,
            "PAYMENT_REQUESTED",
        ) == []

def test_final_destination_targets_only_origin_branch_managers(engine):
    with Session(engine) as session:
        row = _create(session)

        recipients = resolve_notification_recipients(
            session,
            row,
            "FINAL_DESTINATION_SHIPMENT_STARTED",
        )

        assert {
            email for _, email in recipients
        } == {
            "manager-a@example.com",
            "manager-b@example.com",
        }
        assert "manager-other@example.com" not in {
            email for _, email in recipients
        }
        assert "inactive-finance@example.com" not in {
            email for _, email in recipients
        }

def test_receipt_events_follow_e1_notification_matrix(engine):
    with Session(engine) as session:
        row = _create(session)

        maintenance_expected = {
            "maint@example.com",
            "srmaint@example.com",
            "auxmaint@example.com",
        }

        issue_recipients = resolve_notification_recipients(
            session,
            row,
            "RECEIPT_ISSUE_REPORTED",
        )
        assert {
            email for _, email in issue_recipients
        } == maintenance_expected

        assert resolve_notification_recipients(
            session,
            row,
            "RECEIPT_ISSUE_RESOLUTION_STARTED",
        ) == []

        received_recipients = resolve_notification_recipients(
            session,
            row,
            "RECEIVED",
        )
        assert {
            email for _, email in received_recipients
        } == maintenance_expected | {"sports@example.com"}

def test_administrative_correction_notifies_new_owner(engine):
    with Session(engine) as session:
        row = _create(session)
        session.add_all([
            PurchaseRequisitionFinanceApproverORM(
                user_id=7,
                is_active=True,
                added_by_user_id=3,
            ),
            PurchaseRequisitionFinanceApproverORM(
                user_id=9,
                is_active=True,
                added_by_user_id=3,
            ),
        ])
        session.commit()

        maintenance_expected = {
            "maint@example.com",
            "srmaint@example.com",
            "auxmaint@example.com",
        }

        cases = [
            (
                "PENDING_REVIEW",
                {"sports@example.com"},
            ),
            (
                "IN_QUOTATION",
                maintenance_expected,
            ),
            (
                "QUOTE_PENDING_FINANCE_APPROVAL",
                {"finance@example.com"},
            ),
            (
                "PAYMENT_REQUESTED",
                maintenance_expected,
            ),
            (
                "SHIPPING_IN_PROGRESS",
                maintenance_expected,
            ),
            (
                "IMPORT_IN_PROGRESS",
                maintenance_expected,
            ),
            (
                "RECEIPT_ISSUE",
                maintenance_expected,
            ),
            (
                "FINAL_DESTINATION_SHIPMENT",
                {
                    "manager-a@example.com",
                    "manager-b@example.com",
                },
            ),
        ]

        for status, expected in cases:
            row.status = status
            session.flush()
            recipients = resolve_notification_recipients(
                session,
                row,
                "ADMINISTRATIVE_CORRECTION",
            )
            assert {
                email for _, email in recipients
            } == expected


def test_closed_reopen_correction_notifies_maintenance_and_branch_managers(engine):
    with Session(engine) as session:
        row = _create(session)
        row.status = "FINAL_DESTINATION_SHIPMENT"
        session.add(
            PurchaseRequisitionEventORM(
                requisition_id=row.id,
                event_type="ADMINISTRATIVE_CORRECTION",
                actor_user_id=3,
                from_status="CLOSED",
                to_status="FINAL_DESTINATION_SHIPMENT",
                comment="Reapertura controlada.",
                metadata_json={
                    "reason": "Recepción confirmada por error",
                    "reopen_after_receipt": True,
                },
            )
        )
        session.commit()

        recipients = resolve_notification_recipients(
            session,
            row,
            "ADMINISTRATIVE_CORRECTION",
        )

        assert {
            email for _, email in recipients
        } == {
            "maint@example.com",
            "srmaint@example.com",
            "auxmaint@example.com",
            "manager-a@example.com",
            "manager-b@example.com",
        }
