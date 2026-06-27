from __future__ import annotations

from datetime import datetime, timezone

from app import db


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GascaSmsRequestStatus:
    PENDING = "pending"
    GASCA_SEARCHING = "gasca_searching"
    READY_TO_SEND = "ready_to_send"
    MULTIPLE_CANDIDATES_SELECTED_LATEST = "multiple_candidates_selected_latest"
    SMS_SENDING = "sms_sending"
    SENT = "sent"

    CODE_NOT_FOUND = "code_not_found"
    PHONE_NOT_FOUND_FOR_PIN = "phone_not_found_for_pin"
    CODE_NOT_GENERATED_TODAY = "code_not_generated_today"
    CODE_ALREADY_USED = "code_already_used"
    PHONE_REQUIRED_FOR_CONTRACT = "phone_required_for_contract"

    MANUAL_REVIEW = "manual_review"
    FAILED = "failed"

    ALL = (
        PENDING,
        GASCA_SEARCHING,
        READY_TO_SEND,
        MULTIPLE_CANDIDATES_SELECTED_LATEST,
        SMS_SENDING,
        SENT,
        CODE_NOT_FOUND,
        PHONE_NOT_FOUND_FOR_PIN,
        CODE_NOT_GENERATED_TODAY,
        CODE_ALREADY_USED,
        PHONE_REQUIRED_FOR_CONTRACT,
        MANUAL_REVIEW,
        FAILED,
    )


class GascaSmsRequestORM(db.Model):
    __tablename__ = "gasca_sms_requests"

    id = db.Column(db.Integer, primary_key=True)

    pin_raw = db.Column(db.String(32), nullable=False)
    pin_normalized = db.Column(db.String(5), nullable=False, index=True)

    requested_phone_raw = db.Column(db.String(64), nullable=False)
    requested_phone_digits = db.Column(db.String(32), nullable=False, index=True)
    requested_phone_masked = db.Column(db.String(32), nullable=False)

    motivo = db.Column(db.String(80), nullable=False)
    motivo_detalle = db.Column(db.Text, nullable=True)

    status = db.Column(
        db.String(80),
        nullable=False,
        default=GascaSmsRequestStatus.PENDING,
        index=True,
    )
    user_message = db.Column(db.Text, nullable=True)
    internal_error = db.Column(db.Text, nullable=True)

    requested_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sucursal_id = db.Column(
        db.Integer,
        db.ForeignKey("sucursales.sucursal_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    gasca_nombre_masked = db.Column(db.String(180), nullable=True)
    gasca_phone_masked = db.Column(db.String(32), nullable=True)
    gasca_code_masked = db.Column(db.String(32), nullable=True)
    gasca_generated_raw = db.Column(db.String(32), nullable=True)
    gasca_used_raw = db.Column(db.String(32), nullable=True)
    gasca_sucursal = db.Column(db.String(120), nullable=True)

    sms_provider = db.Column(db.String(80), nullable=True)
    sms_message_masked = db.Column(db.Text, nullable=True)

    attempt_count = db.Column(db.Integer, nullable=False, default=0)
    last_attempt_at = db.Column(db.DateTime(timezone=True), nullable=True)
    processed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    sent_at = db.Column(db.DateTime(timezone=True), nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    requested_by = db.relationship(
        "UserORM",
        foreign_keys=[requested_by_user_id],
    )
    sucursal = db.relationship(
        "Sucursal",
        foreign_keys=[sucursal_id],
    )

    __table_args__ = (
        db.Index(
            "ix_gasca_sms_requests_status_created_at",
            "status",
            "created_at",
        ),
        db.Index(
            "ix_gasca_sms_requests_pin_phone_created_at",
            "pin_normalized",
            "requested_phone_digits",
            "created_at",
        ),
        db.Index(
            "ix_gasca_sms_requests_sucursal_created_at",
            "sucursal_id",
            "created_at",
        ),
    )

    def to_public_dict(self) -> dict:
        return {
            "id": self.id,
            "pin_normalized": self.pin_normalized,
            "requested_phone_masked": self.requested_phone_masked,
            "motivo": self.motivo,
            "motivo_detalle": self.motivo_detalle,
            "status": self.status,
            "user_message": self.user_message,
            "sucursal_id": self.sucursal_id,
            "requested_by_user_id": self.requested_by_user_id,
            "gasca_nombre_masked": self.gasca_nombre_masked,
            "gasca_phone_masked": self.gasca_phone_masked,
            "gasca_code_masked": self.gasca_code_masked,
            "gasca_generated_raw": self.gasca_generated_raw,
            "gasca_used_raw": self.gasca_used_raw,
            "gasca_sucursal": self.gasca_sucursal,
            "sms_provider": self.sms_provider,
            "attempt_count": self.attempt_count,
            "last_attempt_at": self.last_attempt_at.isoformat() if self.last_attempt_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
