from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MarketingMonthlyInputORM(db.Model):
    __tablename__ = "marketing_monthly_inputs"

    id = db.Column(
        db.BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    month_start = db.Column(
        db.Date,
        nullable=False,
    )
    sucursal_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "sucursales.sucursal_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    investment = db.Column(
        db.Numeric(14, 2),
        nullable=False,
    )
    leads = db.Column(
        db.Integer,
        nullable=False,
    )
    notes = db.Column(
        db.Text,
        nullable=True,
    )
    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    updated_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
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

    sucursal = db.relationship("Sucursal")
    created_by_user = db.relationship(
        "UserORM",
        foreign_keys=[created_by_user_id],
    )
    updated_by_user = db.relationship(
        "UserORM",
        foreign_keys=[updated_by_user_id],
    )

    __table_args__ = (
        db.UniqueConstraint(
            "month_start",
            "sucursal_id",
            name="uq_marketing_monthly_inputs_month_branch",
        ),
        db.CheckConstraint(
            "month_start = date_trunc('month', month_start)::date",
            name="ck_marketing_monthly_inputs_first_day",
        ),
        db.CheckConstraint(
            "investment >= 0",
            name="ck_marketing_monthly_inputs_investment_nonnegative",
        ),
        db.CheckConstraint(
            "leads >= 0",
            name="ck_marketing_monthly_inputs_leads_nonnegative",
        ),
        db.Index(
            "ix_marketing_monthly_inputs_month_start",
            "month_start",
        ),
        db.Index(
            "ix_marketing_monthly_inputs_sucursal_id",
            "sucursal_id",
        ),
    )
