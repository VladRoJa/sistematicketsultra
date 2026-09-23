from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ContactCenterContactORM(db.Model):
    __tablename__ = "contact_center_contacts"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    display_name = db.Column(db.String(255), nullable=True)
    primary_phone_raw = db.Column(db.String(100), nullable=False)
    phone_mx10 = db.Column(db.String(10), nullable=True)
    email = db.Column(db.String(255), nullable=True)
    preferred_sucursal_id = db.Column(
        db.Integer,
        db.ForeignKey("sucursales.sucursal_id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=db.text("true"),
    )
    merged_into_contact_id = db.Column(
        db.BigInteger,
        db.ForeignKey("contact_center_contacts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
    )

    preferred_sucursal = db.relationship("Sucursal")
    created_by_user = db.relationship(
        "UserORM",
        foreign_keys=[created_by_user_id],
    )
    updated_by_user = db.relationship(
        "UserORM",
        foreign_keys=[updated_by_user_id],
    )

    __table_args__ = (
        db.Index(
            "ix_contact_center_contacts_phone_mx10",
            "phone_mx10",
        ),
        db.Index(
            "ix_contact_center_contacts_email",
            "email",
        ),
        db.Index(
            "ix_contact_center_contacts_active",
            "is_active",
        ),
    )


class ContactCenterContactLinkORM(db.Model):
    __tablename__ = "contact_center_contact_links"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    contact_id = db.Column(
        db.BigInteger,
        db.ForeignKey("contact_center_contacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_type = db.Column(db.String(40), nullable=False)
    source_key = db.Column(db.String(255), nullable=False)
    source_row_id = db.Column(db.BigInteger, nullable=True)
    source_metadata_json = db.Column(db.JSON, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )

    contact = db.relationship("ContactCenterContactORM")

    __table_args__ = (
        db.UniqueConstraint(
            "source_type",
            "source_key",
            name="uq_contact_center_links_source",
        ),
        db.CheckConstraint(
            "source_type IN ("
            "'IVENTAS_CONTACT', "
            "'REACTIVATION_RECIPIENT', "
            "'MARKETING_CAMPAIGN', "
            "'MESSAGE', "
            "'MANUAL'"
            ")",
            name="ck_contact_center_links_source_type",
        ),
        db.Index(
            "ix_contact_center_links_contact_id",
            "contact_id",
        ),
    )


class ContactCenterCaseORM(db.Model):
    __tablename__ = "contact_center_cases"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    contact_id = db.Column(
        db.BigInteger,
        db.ForeignKey("contact_center_contacts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_type = db.Column(db.String(30), nullable=False)
    source_ref = db.Column(db.String(255), nullable=True)
    sucursal_id = db.Column(
        db.Integer,
        db.ForeignKey("sucursales.sucursal_id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    status = db.Column(
        db.String(30),
        nullable=False,
        default="NEW",
        server_default="NEW",
    )
    next_action_at = db.Column(db.DateTime(timezone=True), nullable=True)
    opened_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )
    closed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    closed_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
    )

    contact = db.relationship("ContactCenterContactORM")
    sucursal = db.relationship("Sucursal")
    assigned_user = db.relationship(
        "UserORM",
        foreign_keys=[assigned_user_id],
    )

    __table_args__ = (
        db.CheckConstraint(
            "source_type IN ('CRM', 'MESSAGE', 'REACTIVATION', 'CAMPAIGN', 'MANUAL')",
            name="ck_contact_center_cases_source_type",
        ),
        db.CheckConstraint(
            "status IN ('NEW', 'IN_PROGRESS', 'FOLLOW_UP', 'APPOINTMENT', 'CLOSED')",
            name="ck_contact_center_cases_status",
        ),
        db.Index(
            "ix_contact_center_cases_assignee_status",
            "assigned_user_id",
            "status",
        ),
        db.Index(
            "ix_contact_center_cases_contact_id",
            "contact_id",
        ),
        db.Index(
            "ix_contact_center_cases_next_action_at",
            "next_action_at",
        ),
        db.Index(
            "ix_contact_center_cases_sucursal_id",
            "sucursal_id",
        ),
    )


class ContactCenterInteractionORM(db.Model):
    __tablename__ = "contact_center_interactions"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    case_id = db.Column(
        db.BigInteger,
        db.ForeignKey("contact_center_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    contact_id = db.Column(
        db.BigInteger,
        db.ForeignKey("contact_center_contacts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    interaction_type = db.Column(
        db.String(30),
        nullable=False,
        default="CALL",
        server_default="CALL",
    )
    outcome = db.Column(db.String(40), nullable=False)
    comment = db.Column(db.Text, nullable=True)
    next_action_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )

    case = db.relationship("ContactCenterCaseORM")
    contact = db.relationship("ContactCenterContactORM")
    created_by_user = db.relationship("UserORM")

    __table_args__ = (
        db.CheckConstraint(
            "interaction_type IN ('CALL', 'MESSAGE', 'NOTE', 'SYSTEM')",
            name="ck_contact_center_interactions_type",
        ),
        db.CheckConstraint(
            "outcome IN ("
            "'NO_ANSWER', "
            "'CALL_BACK', "
            "'INTERESTED', "
            "'APPOINTMENT', "
            "'NOT_INTERESTED', "
            "'WRONG_NUMBER', "
            "'DO_NOT_CONTACT', "
            "'NOTE'"
            ")",
            name="ck_contact_center_interactions_outcome",
        ),
        db.Index(
            "ix_contact_center_interactions_case_created",
            "case_id",
            "created_at",
        ),
        db.Index(
            "ix_contact_center_interactions_contact_id",
            "contact_id",
        ),
    )


class ContactCenterAppointmentORM(db.Model):
    __tablename__ = "contact_center_appointments"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    case_id = db.Column(
        db.BigInteger,
        db.ForeignKey("contact_center_cases.id", ondelete="RESTRICT"),
        nullable=False,
    )
    contact_id = db.Column(
        db.BigInteger,
        db.ForeignKey("contact_center_contacts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sucursal_id = db.Column(
        db.Integer,
        db.ForeignKey("sucursales.sucursal_id", ondelete="RESTRICT"),
        nullable=False,
    )
    scheduled_at = db.Column(db.DateTime(timezone=True), nullable=False)
    timezone = db.Column(
        db.String(64),
        nullable=False,
        default="America/Tijuana",
        server_default="America/Tijuana",
    )
    status = db.Column(
        db.String(20),
        nullable=False,
        default="SCHEDULED",
        server_default="SCHEDULED",
    )
    outcome = db.Column(db.String(50), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    closed_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    closed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    rescheduled_to_appointment_id = db.Column(
        db.BigInteger,
        db.ForeignKey("contact_center_appointments.id", ondelete="SET NULL"),
        nullable=True,
    )
    purchase_reported = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=db.text("false"),
    )
    purchase_reported_at = db.Column(db.DateTime(timezone=True), nullable=True)
    purchase_reported_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    purchase_verification_status = db.Column(
        db.String(30),
        nullable=False,
        default="NOT_REPORTED",
        server_default="NOT_REPORTED",
    )
    venta_total_snapshot_id = db.Column(
        db.Integer,
        db.ForeignKey("venta_total_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )
    venta_total_snapshot_row_id = db.Column(
        db.Integer,
        db.ForeignKey("venta_total_snapshot_rows.id", ondelete="SET NULL"),
        nullable=True,
    )
    verified_purchase_at = db.Column(db.DateTime(timezone=True), nullable=True)
    verified_amount = db.Column(db.Numeric(14, 2), nullable=True)
    verified_tariff = db.Column(db.String(255), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
    )

    case = db.relationship("ContactCenterCaseORM")
    contact = db.relationship("ContactCenterContactORM")
    sucursal = db.relationship("Sucursal")

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('SCHEDULED', 'CANCELLED', 'RESCHEDULED', 'CLOSED')",
            name="ck_contact_center_appointments_status",
        ),
        db.CheckConstraint(
            "outcome IS NULL OR outcome IN ("
            "'ATTENDED_PURCHASE_REPORTED', "
            "'ATTENDED_NO_PURCHASE', "
            "'NO_SHOW', "
            "'CANCELLED', "
            "'RESCHEDULED'"
            ")",
            name="ck_contact_center_appointments_outcome",
        ),
        db.CheckConstraint(
            "purchase_verification_status IN ("
            "'NOT_REPORTED', "
            "'REPORTED_PENDING', "
            "'VERIFIED', "
            "'REVIEW', "
            "'NOT_FOUND_YET'"
            ")",
            name="ck_contact_center_appointments_purchase_verification",
        ),
        db.Index(
            "ix_contact_center_appointments_branch_scheduled",
            "sucursal_id",
            "scheduled_at",
        ),
        db.Index(
            "ix_contact_center_appointments_status_scheduled",
            "status",
            "scheduled_at",
        ),
        db.Index(
            "ix_contact_center_appointments_contact_id",
            "contact_id",
        ),
        db.Index(
            "ix_contact_center_appointments_case_id",
            "case_id",
        ),
    )


class ContactCenterContactMergeEventORM(db.Model):
    __tablename__ = "contact_center_contact_merge_events"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    survivor_contact_id = db.Column(
        db.BigInteger,
        db.ForeignKey("contact_center_contacts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    merged_contact_id = db.Column(
        db.BigInteger,
        db.ForeignKey("contact_center_contacts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    field_resolution_json = db.Column(db.JSON, nullable=False, default=dict)
    merged_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )

    __table_args__ = (
        db.CheckConstraint(
            "survivor_contact_id <> merged_contact_id",
            name="ck_contact_center_merge_distinct_contacts",
        ),
        db.Index(
            "ix_contact_center_merge_survivor",
            "survivor_contact_id",
        ),
        db.Index(
            "ix_contact_center_merge_merged",
            "merged_contact_id",
        ),
    )


class ContactCenterNotificationORM(db.Model):
    __tablename__ = "contact_center_notifications"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    appointment_id = db.Column(
        db.BigInteger,
        db.ForeignKey("contact_center_appointments.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type = db.Column(db.String(40), nullable=False)
    recipients_json = db.Column(db.JSON, nullable=False, default=list)
    status = db.Column(db.String(20), nullable=False)
    error = db.Column(db.Text, nullable=True)
    sent_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('PENDING', 'SENT', 'FAILED')",
            name="ck_contact_center_notifications_status",
        ),
        db.Index(
            "ix_contact_center_notifications_appointment",
            "appointment_id",
            "created_at",
        ),
    )
