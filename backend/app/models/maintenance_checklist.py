# backend/app/models/maintenance_checklist.py

from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now():
    return datetime.now(timezone.utc)


class MaintenanceChecklistTemplateORM(db.Model):
    __tablename__ = "maintenance_checklist_templates"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    template_key = db.Column(db.String(100), nullable=False, unique=True)
    familia_equipo_id = db.Column(
        db.Integer,
        db.ForeignKey("familia_equipo.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    nombre = db.Column(db.String(180), nullable=False)
    actividad_key = db.Column(db.String(180), nullable=True)
    activo = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=db.text("true"),
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

    familia = db.relationship("FamiliaEquipoORM")
    items = db.relationship(
        "MaintenanceChecklistItemORM",
        back_populates="template",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MaintenanceChecklistItemORM.orden",
    )

    __table_args__ = (
        db.Index(
            "ix_maintenance_checklist_templates_family_active",
            "familia_equipo_id",
            "activo",
        ),
        db.Index(
            "ix_maintenance_checklist_templates_activity",
            "familia_equipo_id",
            "actividad_key",
        ),
    )


class MaintenanceChecklistItemORM(db.Model):
    __tablename__ = "maintenance_checklist_items"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    template_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "maintenance_checklist_templates.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    item_key = db.Column(db.String(100), nullable=False)
    etiqueta = db.Column(db.String(220), nullable=False)
    orden = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default=db.text("0"),
    )
    requerido = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=db.text("true"),
    )
    activo = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=db.text("true"),
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

    template = db.relationship(
        "MaintenanceChecklistTemplateORM",
        back_populates="items",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "template_id",
            "item_key",
            name="uq_maintenance_checklist_item_key",
        ),
        db.Index(
            "ix_maintenance_checklist_items_template_active_order",
            "template_id",
            "activo",
            "orden",
        ),
    )
