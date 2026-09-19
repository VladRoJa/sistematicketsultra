# backend/app/models/maintenance_preventive.py

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import JSONB

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MaintenancePreventiveBatchORM(db.Model):
    __tablename__ = "maintenance_preventive_batches"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)

    batch_key = db.Column(db.String(80), nullable=False, unique=True)
    nombre = db.Column(db.String(160), nullable=False)
    source_type = db.Column(db.String(20), nullable=False)
    status = db.Column(
        db.String(20),
        nullable=False,
        default="BORRADOR",
        server_default="BORRADOR",
    )

    period_start = db.Column(db.Date, nullable=True)
    period_end = db.Column(db.Date, nullable=True)

    source_filename = db.Column(db.String(255), nullable=True)
    source_sha256 = db.Column(db.String(64), nullable=True)

    notes = db.Column(db.Text, nullable=True)

    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    published_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
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
    published_at = db.Column(db.DateTime(timezone=True), nullable=True)

    created_by_user = db.relationship(
        "UserORM",
        foreign_keys=[created_by_user_id],
    )
    published_by_user = db.relationship(
        "UserORM",
        foreign_keys=[published_by_user_id],
    )

    items = db.relationship(
        "MaintenancePreventiveItemORM",
        back_populates="batch",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MaintenancePreventiveItemORM.id",
    )

    __table_args__ = (
        db.CheckConstraint(
            "source_type IN ('MANUAL', 'ARCHIVO')",
            name="ck_maintenance_preventive_batches_source_type",
        ),
        db.CheckConstraint(
            "status IN ('BORRADOR', 'PUBLICADO', 'CANCELADO')",
            name="ck_maintenance_preventive_batches_status",
        ),
        db.CheckConstraint(
            "period_start IS NULL OR period_end IS NULL OR period_start <= period_end",
            name="ck_maintenance_preventive_batches_period",
        ),
        db.Index(
            "ix_maintenance_preventive_batches_status",
            "status",
        ),
        db.Index(
            "ix_maintenance_preventive_batches_period",
            "period_start",
            "period_end",
        ),
        db.Index(
            "ix_maintenance_preventive_batches_source_sha256",
            "source_sha256",
        ),
    )


class MaintenancePreventiveItemORM(db.Model):
    __tablename__ = "maintenance_preventive_items"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)

    batch_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "maintenance_preventive_batches.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    source_row_number = db.Column(db.Integer, nullable=True)

    sucursal_id = db.Column(
        db.Integer,
        db.ForeignKey("sucursales.sucursal_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    inventario_id = db.Column(
        db.Integer,
        db.ForeignKey("inventario_general.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    responsable_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    fecha_programada = db.Column(db.Date, nullable=False, index=True)
    actividad = db.Column(db.Text, nullable=False)
    observaciones = db.Column(db.Text, nullable=True)

    validation_status = db.Column(
        db.String(20),
        nullable=False,
        default="PENDIENTE",
        server_default="PENDIENTE",
    )
    validation_errors = db.Column(JSONB, nullable=True)

    ticket_id = db.Column(
        db.Integer,
        db.ForeignKey("tickets.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
        index=True,
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

    batch = db.relationship(
        "MaintenancePreventiveBatchORM",
        back_populates="items",
    )
    sucursal = db.relationship("Sucursal")
    inventario = db.relationship("InventarioGeneral")
    responsable_user = db.relationship("UserORM")
    ticket = db.relationship("Ticket")

    __table_args__ = (
        db.CheckConstraint(
            "validation_status IN ('PENDIENTE', 'VALIDO', 'ERROR')",
            name="ck_maintenance_preventive_items_validation_status",
        ),
        db.UniqueConstraint(
            "batch_id",
            "source_row_number",
            name="uq_maintenance_preventive_items_batch_source_row",
        ),
        db.Index(
            "ix_maintenance_preventive_items_batch_validation",
            "batch_id",
            "validation_status",
        ),
        db.Index(
            "ix_maintenance_preventive_items_schedule",
            "fecha_programada",
            "sucursal_id",
        ),
    )
