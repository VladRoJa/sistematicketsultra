from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PurchaseRequisitionCategory:
    GYM_EQUIPMENT = "GYM_EQUIPMENT"
    ALL = (GYM_EQUIPMENT,)


class PurchaseRequisitionReason:
    REPLACEMENT = "REPLACEMENT"
    NEW_EQUIPMENT = "NEW_EQUIPMENT"
    DAMAGE = "DAMAGE"
    EXPANSION = "EXPANSION"
    OTHER = "OTHER"
    ALL = (REPLACEMENT, NEW_EQUIPMENT, DAMAGE, EXPANSION, OTHER)


class PurchaseRequisitionPriority:
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    ALL = (NORMAL, HIGH, CRITICAL)


class PurchaseRequisitionStatus:
    PENDING_REVIEW = "PENDING_REVIEW"
    NEEDS_INFO = "NEEDS_INFO"
    REJECTED = "REJECTED"
    IN_QUOTATION = "IN_QUOTATION"
    CLOSED = "CLOSED"
    ALL = (PENDING_REVIEW, NEEDS_INFO, REJECTED, IN_QUOTATION, CLOSED)


class PurchaseRequisitionEventType:
    CREATED = "CREATED"
    INFO_REQUESTED = "INFO_REQUESTED"
    RESUBMITTED = "RESUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ROUTED_TO_MAINTENANCE = "ROUTED_TO_MAINTENANCE"
    ATTACHMENT_ADDED = "ATTACHMENT_ADDED"
    ALL = (
        CREATED,
        INFO_REQUESTED,
        RESUBMITTED,
        APPROVED,
        REJECTED,
        ROUTED_TO_MAINTENANCE,
        ATTACHMENT_ADDED,
    )


def _sql_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class PurchaseRequisitionORM(db.Model):
    __tablename__ = "purchase_requisitions"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    public_id = db.Column(db.String(32), nullable=False, unique=True)
    sucursal_id = db.Column(
        db.Integer,
        db.ForeignKey("sucursales.sucursal_id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    category = db.Column(
        db.String(40),
        nullable=False,
        default=PurchaseRequisitionCategory.GYM_EQUIPMENT,
        server_default=PurchaseRequisitionCategory.GYM_EQUIPMENT,
    )
    reason = db.Column(db.String(40), nullable=False)
    justification = db.Column(db.Text, nullable=False)
    priority = db.Column(
        db.String(20),
        nullable=False,
        default=PurchaseRequisitionPriority.NORMAL,
        server_default=PurchaseRequisitionPriority.NORMAL,
    )
    status = db.Column(
        db.String(30),
        nullable=False,
        default=PurchaseRequisitionStatus.PENDING_REVIEW,
        server_default=PurchaseRequisitionStatus.PENDING_REVIEW,
    )
    approved_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at = db.Column(db.DateTime(timezone=True), nullable=True)
    approval_comment = db.Column(db.Text, nullable=True)
    rejected_at = db.Column(db.DateTime(timezone=True), nullable=True)
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

    sucursal = db.relationship("Sucursal")
    created_by_user = db.relationship(
        "UserORM",
        foreign_keys=[created_by_user_id],
    )
    approved_by_user = db.relationship(
        "UserORM",
        foreign_keys=[approved_by_user_id],
    )
    items = db.relationship(
        "PurchaseRequisitionItemORM",
        back_populates="requisition",
        cascade="all, delete-orphan",
        order_by="PurchaseRequisitionItemORM.id",
    )
    events = db.relationship(
        "PurchaseRequisitionEventORM",
        back_populates="requisition",
        cascade="all, delete-orphan",
        order_by="PurchaseRequisitionEventORM.id",
    )
    attachments = db.relationship(
        "PurchaseRequisitionAttachmentORM",
        back_populates="requisition",
        order_by="PurchaseRequisitionAttachmentORM.id",
    )

    __table_args__ = (
        db.CheckConstraint(
            f"category IN ({_sql_values(PurchaseRequisitionCategory.ALL)})",
            name="ck_purchase_requisitions_category",
        ),
        db.CheckConstraint(
            f"reason IN ({_sql_values(PurchaseRequisitionReason.ALL)})",
            name="ck_purchase_requisitions_reason",
        ),
        db.CheckConstraint(
            f"priority IN ({_sql_values(PurchaseRequisitionPriority.ALL)})",
            name="ck_purchase_requisitions_priority",
        ),
        db.CheckConstraint(
            f"status IN ({_sql_values(PurchaseRequisitionStatus.ALL)})",
            name="ck_purchase_requisitions_status",
        ),
        db.CheckConstraint(
            "length(trim(justification)) > 0",
            name="ck_purchase_requisitions_justification_nonempty",
        ),
        db.Index(
            "ix_purchase_requisitions_sucursal_status",
            "sucursal_id",
            "status",
        ),
        db.Index(
            "ix_purchase_requisitions_status_created",
            "status",
            "created_at",
        ),
    )

    def to_dict(
        self,
        *,
        include_items: bool = False,
        include_events: bool = False,
        include_attachments: bool = False,
    ) -> dict:
        payload = {
            "id": self.id,
            "public_id": self.public_id,
            "sucursal_id": self.sucursal_id,
            "created_by_user_id": self.created_by_user_id,
            "category": self.category,
            "reason": self.reason,
            "justification": self.justification,
            "priority": self.priority,
            "status": self.status,
            "approved_by_user_id": self.approved_by_user_id,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "approval_comment": self.approval_comment,
            "rejected_at": self.rejected_at.isoformat() if self.rejected_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_items:
            payload["items"] = [item.to_dict() for item in self.items]
        if include_events:
            payload["events"] = [event.to_dict() for event in self.events]
        if include_attachments:
            payload["attachments"] = [
                attachment.to_dict()
                for attachment in self.attachments
                if attachment.deleted_at is None
            ]
        return payload


class PurchaseRequisitionItemORM(db.Model):
    __tablename__ = "purchase_requisition_items"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    requisition_id = db.Column(
        db.BigInteger,
        db.ForeignKey("purchase_requisitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    item_description = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )

    requisition = db.relationship(
        "PurchaseRequisitionORM",
        back_populates="items",
    )

    __table_args__ = (
        db.CheckConstraint(
            "quantity > 0",
            name="ck_purchase_requisition_items_quantity_positive",
        ),
        db.CheckConstraint(
            "length(trim(item_description)) > 0",
            name="ck_purchase_requisition_items_description_nonempty",
        ),
        db.Index(
            "ix_purchase_requisition_items_requisition_id",
            "requisition_id",
        ),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "requisition_id": self.requisition_id,
            "item_description": self.item_description,
            "quantity": self.quantity,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PurchaseRequisitionEventORM(db.Model):
    __tablename__ = "purchase_requisition_events"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    requisition_id = db.Column(
        db.BigInteger,
        db.ForeignKey("purchase_requisitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type = db.Column(db.String(50), nullable=False)
    actor_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    from_status = db.Column(db.String(30), nullable=True)
    to_status = db.Column(db.String(30), nullable=True)
    comment = db.Column(db.Text, nullable=True)
    metadata_json = db.Column(db.JSON, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )

    requisition = db.relationship(
        "PurchaseRequisitionORM",
        back_populates="events",
    )
    actor_user = db.relationship("UserORM")

    __table_args__ = (
        db.CheckConstraint(
            f"event_type IN ({_sql_values(PurchaseRequisitionEventType.ALL)})",
            name="ck_purchase_requisition_events_type",
        ),
        db.CheckConstraint(
            "from_status IS NULL OR "
            f"from_status IN ({_sql_values(PurchaseRequisitionStatus.ALL)})",
            name="ck_purchase_requisition_events_from_status",
        ),
        db.CheckConstraint(
            "to_status IS NULL OR "
            f"to_status IN ({_sql_values(PurchaseRequisitionStatus.ALL)})",
            name="ck_purchase_requisition_events_to_status",
        ),
        db.Index(
            "ix_purchase_requisition_events_requisition_created",
            "requisition_id",
            "created_at",
        ),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "requisition_id": self.requisition_id,
            "event_type": self.event_type,
            "actor_user_id": self.actor_user_id,
            "from_status": self.from_status,
            "to_status": self.to_status,
            "comment": self.comment,
            "metadata_json": self.metadata_json,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }



class PurchaseRequisitionNotificationORM(db.Model):
    __tablename__ = "purchase_requisition_notifications"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    event_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "purchase_requisition_events.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    recipient_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    recipient_email = db.Column(db.String(255), nullable=False)
    channel = db.Column(
        db.String(20),
        nullable=False,
        default="EMAIL",
        server_default="EMAIL",
    )
    status = db.Column(
        db.String(20),
        nullable=False,
        default="PENDING",
        server_default="PENDING",
    )
    attempts = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    last_error = db.Column(db.Text, nullable=True)
    sent_at = db.Column(db.DateTime(timezone=True), nullable=True)
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

    event = db.relationship("PurchaseRequisitionEventORM")
    recipient_user = db.relationship("UserORM")

    __table_args__ = (
        db.CheckConstraint(
            "channel IN ('EMAIL')",
            name="ck_purchase_requisition_notifications_channel",
        ),
        db.CheckConstraint(
            "status IN ('PENDING', 'SENT', 'FAILED')",
            name="ck_purchase_requisition_notifications_status",
        ),
        db.CheckConstraint(
            "attempts >= 0",
            name="ck_purchase_requisition_notifications_attempts",
        ),
        db.UniqueConstraint(
            "event_id",
            "recipient_email",
            "channel",
            name="uq_purchase_requisition_notification_delivery",
        ),
        db.Index(
            "ix_purchase_requisition_notifications_event",
            "event_id",
        ),
        db.Index(
            "ix_purchase_requisition_notifications_status",
            "status",
        ),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_id": self.event_id,
            "recipient_user_id": self.recipient_user_id,
            "recipient_email": self.recipient_email,
            "channel": self.channel,
            "status": self.status,
            "attempts": self.attempts,
            "last_error": self.last_error,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }



class PurchaseRequisitionAttachmentORM(db.Model):
    __tablename__ = "purchase_requisition_attachments"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    requisition_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "purchase_requisitions.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    event_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "purchase_requisition_events.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    attachment_type = db.Column(db.String(20), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    storage_key = db.Column(db.String(500), nullable=False, unique=True)
    mime_type = db.Column(db.String(100), nullable=False)
    size_bytes = db.Column(db.BigInteger, nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    uploaded_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )
    deleted_at = db.Column(db.DateTime(timezone=True), nullable=True)

    requisition = db.relationship(
        "PurchaseRequisitionORM",
        back_populates="attachments",
    )
    event = db.relationship("PurchaseRequisitionEventORM")
    uploaded_by_user = db.relationship("UserORM")

    __table_args__ = (
        db.CheckConstraint(
            "attachment_type IN ('EVIDENCE', 'QUOTE', 'OTHER')",
            name="ck_purchase_requisition_attachments_type",
        ),
        db.CheckConstraint(
            "size_bytes > 0",
            name="ck_purchase_requisition_attachments_size_positive",
        ),
        db.Index(
            "ix_purchase_requisition_attachments_requisition",
            "requisition_id",
            "created_at",
        ),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "requisition_id": self.requisition_id,
            "event_id": self.event_id,
            "attachment_type": self.attachment_type,
            "original_filename": self.original_filename,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "uploaded_by_user_id": self.uploaded_by_user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
        }
