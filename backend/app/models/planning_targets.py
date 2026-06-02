# backend/app/models/planning_targets.py

from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db

from sqlalchemy.dialects.postgresql import JSONB


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PlanningModelConfigORM(db.Model):
    __tablename__ = "planning_model_configs"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)

    name = db.Column(db.Text, nullable=False)
    version = db.Column(db.Integer, nullable=False)
    status = db.Column(db.Text, nullable=False, default="BORRADOR")

    description = db.Column(db.Text, nullable=True)

    trend_window_months = db.Column(db.Integer, nullable=False, default=3)
    trend_closed_months_only = db.Column(db.Boolean, nullable=False, default=True)

    arpu_strategy = db.Column(db.Text, nullable=False, default="PROMEDIO_3M")
    bajas_strategy = db.Column(
        db.Text,
        nullable=False,
        default="PROMEDIO_HISTORICO_SUCURSAL",
    )
    reactivaciones_strategy = db.Column(
        db.Text,
        nullable=False,
        default="PROMEDIO_HISTORICO_SUCURSAL",
    )
    domiciliados_strategy = db.Column(
        db.Text,
        nullable=False,
        default="PORCENTAJE_CLIENTES_NUEVOS",
    )
    aggregators_strategy = db.Column(
        db.Text,
        nullable=False,
        default="SEPARADAS_SOLO_INGRESO",
    )
    new_branch_strategy = db.Column(
        db.Text,
        nullable=False,
        default="PROMEDIO_REGIONAL",
    )

    risk_rules_json = db.Column(JSONB, nullable=True)
    parameters_json = db.Column(JSONB, nullable=True)

    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    activated_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    activated_at = db.Column(db.DateTime(timezone=True), nullable=True)

    replaced_by_config_id = db.Column(
        db.BigInteger,
        db.ForeignKey("planning_model_configs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    notes = db.Column(db.Text, nullable=True)

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

    created_by_user = db.relationship(
        "UserORM",
        foreign_keys=[created_by_user_id],
    )
    activated_by_user = db.relationship(
        "UserORM",
        foreign_keys=[activated_by_user_id],
    )
    replaced_by_config = db.relationship(
        "PlanningModelConfigORM",
        remote_side=[id],
    )

    __table_args__ = (
        db.UniqueConstraint(
            "name",
            "version",
            name="uq_planning_model_configs_name_version",
        ),
        db.Index("ix_planning_model_configs_status", "status"),
    )


class PlanningTargetBatchORM(db.Model):
    __tablename__ = "planning_target_batches"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)

    target_month = db.Column(db.Date, nullable=False, index=True)
    version = db.Column(db.Integer, nullable=False)
    status = db.Column(db.Text, nullable=False, default="BORRADOR")
    scope = db.Column(db.Text, nullable=False, default="MONTHLY_BATCH")
    source_type = db.Column(db.Text, nullable=False, default="MANUAL")

    source_upload_id = db.Column(
        db.Integer,
        db.ForeignKey("warehouse_uploads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    model_config_id = db.Column(
        db.BigInteger,
        db.ForeignKey("planning_model_configs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    scenario_base = db.Column(db.Text, nullable=True)

    proposed_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    proposed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    approved_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    approved_at = db.Column(db.DateTime(timezone=True), nullable=True)

    rejected_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    rejected_at = db.Column(db.DateTime(timezone=True), nullable=True)
    rejection_comment = db.Column(db.Text, nullable=True)

    published_at = db.Column(db.DateTime(timezone=True), nullable=True)
    is_canonical = db.Column(db.Boolean, nullable=False, default=False)

    notes = db.Column(db.Text, nullable=True)

    created_by_user_id = db.Column(
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

    model_config = db.relationship("PlanningModelConfigORM")
    source_upload = db.relationship("WarehouseUploadORM")

    proposed_by_user = db.relationship(
        "UserORM",
        foreign_keys=[proposed_by_user_id],
    )
    approved_by_user = db.relationship(
        "UserORM",
        foreign_keys=[approved_by_user_id],
    )
    rejected_by_user = db.relationship(
        "UserORM",
        foreign_keys=[rejected_by_user_id],
    )
    created_by_user = db.relationship(
        "UserORM",
        foreign_keys=[created_by_user_id],
    )

    branch_rows = db.relationship(
        "PlanningTargetBranchRowORM",
        back_populates="batch",
        cascade="all, delete-orphan",
    )
    approval_events = db.relationship(
        "PlanningTargetApprovalEventORM",
        back_populates="batch",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "target_month",
            "version",
            name="uq_planning_target_batches_month_version",
        ),
        db.Index("ix_planning_target_batches_status", "status"),
        db.Index("ix_planning_target_batches_scope", "scope"),
        db.Index("ix_planning_target_batches_is_canonical", "is_canonical"),
    )


class PlanningTargetBranchRowORM(db.Model):
    __tablename__ = "planning_target_branch_rows"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)

    batch_id = db.Column(
        db.BigInteger,
        db.ForeignKey("planning_target_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    target_month = db.Column(db.Date, nullable=False, index=True)

    sucursal_canon = db.Column(
        db.Text,
        db.ForeignKey("track_branch_catalog.sucursal_canon", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    m2_sin_circulaciones = db.Column(db.Numeric(12, 2), nullable=False)
    usuarios_inicio_mes = db.Column(db.Integer, nullable=False)
    proyeccion_usuarios_cierre_mes = db.Column(db.Integer, nullable=False)

    meta_faycgo_mes = db.Column(db.Numeric(14, 2), nullable=False)
    meta_clientes_nuevos_mes = db.Column(db.Integer, nullable=False)
    meta_reactivaciones_mes = db.Column(db.Integer, nullable=False)
    meta_bajas_mes = db.Column(db.Integer, nullable=False)
    meta_nuevos_domiciliados_mes = db.Column(db.Integer, nullable=False)
    meta_arpu_mes = db.Column(db.Numeric(14, 2), nullable=False)
    meta_venta_tienda_mes = db.Column(db.Numeric(14, 2), nullable=False)

    ingreso_agregadoras_estimado = db.Column(db.Numeric(14, 2), nullable=True)
    usuarios_agregadoras_estimado = db.Column(db.Integer, nullable=True)

    scenario_used = db.Column(db.Text, nullable=True)
    trend_classification = db.Column(db.Text, nullable=True)
    risk_level = db.Column(db.Text, nullable=True)

    status = db.Column(db.Text, nullable=False, default="PROPUESTA")

    previous_branch_row_id = db.Column(
        db.BigInteger,
        db.ForeignKey("planning_target_branch_rows.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    published_track_monthly_target_id = db.Column(
        db.BigInteger,
        db.ForeignKey("track_monthly_targets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    notes = db.Column(db.Text, nullable=True)

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
        "PlanningTargetBatchORM",
        back_populates="branch_rows",
    )
    branch_catalog = db.relationship("TrackBranchCatalogORM")
    previous_branch_row = db.relationship(
        "PlanningTargetBranchRowORM",
        remote_side=[id],
    )
    published_track_monthly_target = db.relationship("TrackMonthlyTargetORM")

    adjustments = db.relationship(
        "PlanningTargetAdjustmentORM",
        back_populates="branch_row",
        cascade="all, delete-orphan",
    )
    approval_events = db.relationship(
        "PlanningTargetApprovalEventORM",
        back_populates="branch_row",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "batch_id",
            "sucursal_canon",
            name="uq_planning_target_branch_rows_batch_branch",
        ),
        db.Index("ix_planning_target_branch_rows_status", "status"),
    )


class PlanningTargetAdjustmentORM(db.Model):
    __tablename__ = "planning_target_adjustments"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)

    branch_row_id = db.Column(
        db.BigInteger,
        db.ForeignKey("planning_target_branch_rows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    variable_key = db.Column(db.Text, nullable=False, index=True)
    adjustment_value = db.Column(db.Numeric(14, 2), nullable=True)
    adjustment_type = db.Column(db.Text, nullable=False)
    driver_type = db.Column(db.Text, nullable=False, index=True)
    justification = db.Column(db.Text, nullable=False)

    created_by_user_id = db.Column(
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

    branch_row = db.relationship(
        "PlanningTargetBranchRowORM",
        back_populates="adjustments",
    )
    created_by_user = db.relationship("UserORM")


class PlanningTargetApprovalEventORM(db.Model):
    __tablename__ = "planning_target_approval_events"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)

    batch_id = db.Column(
        db.BigInteger,
        db.ForeignKey("planning_target_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    branch_row_id = db.Column(
        db.BigInteger,
        db.ForeignKey("planning_target_branch_rows.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    event_type = db.Column(db.Text, nullable=False, index=True)
    from_status = db.Column(db.Text, nullable=True)
    to_status = db.Column(db.Text, nullable=True)

    actor_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_username_snapshot = db.Column(db.Text, nullable=True)

    comment = db.Column(db.Text, nullable=True)
    metadata_json = db.Column(JSONB, nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        index=True,
    )

    batch = db.relationship(
        "PlanningTargetBatchORM",
        back_populates="approval_events",
    )
    branch_row = db.relationship(
        "PlanningTargetBranchRowORM",
        back_populates="approval_events",
    )
    actor_user = db.relationship("UserORM")
    
class PlanningOperatorORM(db.Model):
    __tablename__ = "planning_operators"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    can_view = db.Column(db.Boolean, nullable=False, default=True)
    can_edit = db.Column(db.Boolean, nullable=False, default=False)
    can_submit = db.Column(db.Boolean, nullable=False, default=False)
    can_approve = db.Column(db.Boolean, nullable=False, default=False)
    can_publish = db.Column(db.Boolean, nullable=False, default=False)
    can_configure_model = db.Column(db.Boolean, nullable=False, default=False)

    is_active = db.Column(db.Boolean, nullable=False, default=True)

    added_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    notes = db.Column(db.Text, nullable=True)

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

    user = db.relationship(
        "UserORM",
        foreign_keys=[user_id],
    )
    added_by_user = db.relationship(
        "UserORM",
        foreign_keys=[added_by_user_id],
    )
    
