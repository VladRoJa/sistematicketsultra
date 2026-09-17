from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SalesCompositionSnapshotORM(db.Model):
    __tablename__ = "sales_composition_snapshots"

    id = db.Column(db.Integer, primary_key=True)
    warehouse_upload_id = db.Column(
        db.Integer,
        db.ForeignKey("warehouse_uploads.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    report_type_key = db.Column(db.String(80), nullable=False)
    date_from = db.Column(db.Date, nullable=False)
    date_to = db.Column(db.Date, nullable=False)
    business_date = db.Column(db.Date, nullable=False)
    captured_at = db.Column(db.DateTime(timezone=True), nullable=False)
    is_canonical = db.Column(db.Boolean, nullable=False, default=False)
    current_label = db.Column(db.String(120), nullable=False)
    comparison_label = db.Column(db.String(120), nullable=False)
    row_count_detected = db.Column(db.Integer, nullable=False)
    row_count_valid = db.Column(db.Integer, nullable=False)
    row_count_rejected = db.Column(db.Integer, nullable=False, default=0)
    summary_totals = db.Column(db.JSON, nullable=False, default=dict)
    data_quality = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
    )

    warehouse_upload = db.relationship("WarehouseUploadORM")
    rows = db.relationship(
        "SalesCompositionRowORM",
        back_populates="snapshot",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        db.Index("ix_sales_comp_snapshots_business_date", "business_date"),
        db.Index(
            "ix_sales_comp_snapshots_canonical",
            "is_canonical",
            "business_date",
        ),
    )


class SalesCompositionRowORM(db.Model):
    __tablename__ = "sales_composition_rows"

    id = db.Column(db.Integer, primary_key=True)
    snapshot_id = db.Column(
        db.Integer,
        db.ForeignKey("sales_composition_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    row_index = db.Column(db.Integer, nullable=False)
    source_sheet = db.Column(db.String(80), nullable=False)
    source_row_number = db.Column(db.Integer, nullable=False)
    row_kind = db.Column(db.String(20), nullable=False)
    tariff_row_index = db.Column(db.Integer, nullable=False)
    sales_mode = db.Column(db.String(20), nullable=False)
    family = db.Column(db.String(120), nullable=True)
    contract_type = db.Column(db.String(120), nullable=True)
    plan_type = db.Column(db.String(80), nullable=True)
    tariff_name = db.Column(db.String(255), nullable=False)
    source_cost = db.Column(db.Numeric(18, 2), nullable=True)
    monthly_equivalent = db.Column(db.Numeric(18, 2), nullable=True)
    free_months_raw = db.Column(db.String(80), nullable=True)
    branch_raw = db.Column(db.String(255), nullable=True)
    current_quantity = db.Column(db.Numeric(18, 2), nullable=False)
    current_flow = db.Column(db.Numeric(18, 2), nullable=False)
    comparison_quantity = db.Column(db.Numeric(18, 2), nullable=False)
    comparison_flow = db.Column(db.Numeric(18, 2), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
    )

    snapshot = db.relationship(
        "SalesCompositionSnapshotORM",
        back_populates="rows",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "snapshot_id",
            "row_index",
            name="uq_sales_composition_rows_snapshot_row",
        ),
        db.Index(
            "ix_sales_comp_rows_snapshot_kind",
            "snapshot_id",
            "row_kind",
        ),
        db.Index(
            "ix_sales_comp_rows_snapshot_mode",
            "snapshot_id",
            "sales_mode",
        ),
        db.Index(
            "ix_sales_comp_rows_snapshot_branch",
            "snapshot_id",
            "branch_raw",
        ),
    )
