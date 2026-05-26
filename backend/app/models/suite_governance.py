# app/models/suite_governance.py

from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now():
    return datetime.now(timezone.utc)


class SuiteRegionORM(db.Model):
    __tablename__ = "suite_regions"

    id = db.Column(db.Integer, primary_key=True)

    region_key = db.Column(
        db.String(80),
        nullable=False,
        unique=True,
        index=True,
    )

    region_label = db.Column(
        db.String(120),
        nullable=False,
    )

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=db.text("true"),
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=db.func.now(),
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
        server_default=db.func.now(),
    )

    sucursal_assignments = db.relationship(
        "SuiteSucursalRegionAssignmentORM",
        back_populates="region",
        cascade="all, delete-orphan",
    )

    managers = db.relationship(
        "SuiteRegionManagerORM",
        back_populates="region",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<SuiteRegion {self.region_key}>"


class SuiteSucursalRegionAssignmentORM(db.Model):
    __tablename__ = "suite_sucursal_region_assignments"

    id = db.Column(db.Integer, primary_key=True)

    sucursal_id = db.Column(
        db.Integer,
        db.ForeignKey("sucursales.sucursal_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    region_id = db.Column(
        db.Integer,
        db.ForeignKey("suite_regions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    is_current = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=db.text("true"),
        index=True,
    )

    valid_from = db.Column(
        db.Date,
        nullable=True,
    )

    valid_to = db.Column(
        db.Date,
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=db.func.now(),
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
        server_default=db.func.now(),
    )

    region = db.relationship(
        "SuiteRegionORM",
        back_populates="sucursal_assignments",
    )

    sucursal = db.relationship(
        "Sucursal",
        lazy="joined",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "sucursal_id",
            "region_id",
            "valid_from",
            name="uq_suite_sucursal_region_assignment_period",
        ),
    )

    def __repr__(self):
        return (
            f"<SuiteSucursalRegionAssignment "
            f"sucursal_id={self.sucursal_id} region_id={self.region_id}>"
        )


class SuiteRegionManagerORM(db.Model):
    __tablename__ = "suite_region_managers"

    id = db.Column(db.Integer, primary_key=True)

    region_id = db.Column(
        db.Integer,
        db.ForeignKey("suite_regions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=db.text("true"),
        index=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=db.func.now(),
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
        server_default=db.func.now(),
    )

    region = db.relationship(
        "SuiteRegionORM",
        back_populates="managers",
    )

    user = db.relationship(
        "UserORM",
        lazy="joined",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "region_id",
            "user_id",
            name="uq_suite_region_manager_region_user",
        ),
    )

    def __repr__(self):
        return (
            f"<SuiteRegionManager "
            f"region_id={self.region_id} user_id={self.user_id}>"
        )