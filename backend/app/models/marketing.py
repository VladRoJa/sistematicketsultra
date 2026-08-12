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


class MarketingIventasSyncRunORM(db.Model):
    __tablename__ = "marketing_iventas_sync_runs"

    id = db.Column(
        db.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    period_key = db.Column(
        db.String(64),
        nullable=False,
    )

    date_from = db.Column(
        db.Date,
        nullable=False,
    )

    date_to = db.Column(
        db.Date,
        nullable=False,
    )

    started_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
    )

    finished_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    status = db.Column(
        db.String(20),
        nullable=False,
    )

    branches_requested = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    branches_completed = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    branches_failed = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    contacts_received = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    contacts_unique = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    contacts_with_phone = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    contacts_mx10_matchable = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    contacts_non_mx_or_unresolved = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    contacts_with_first_message = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    contacts_with_any_tag = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    contacts_with_meta_ad_tag = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    contacts_with_multiple_meta_ad_tags = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    aliases_resolved = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    aliases_unresolved = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    is_canonical = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )

    raw_pages = db.relationship(
        "MarketingIventasRawPageORM",
        back_populates="sync_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    contacts = db.relationship(
        "MarketingIventasContactORM",
        back_populates="sync_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        db.CheckConstraint(
            "date_from <= date_to",
            name="ck_marketing_iventas_sync_runs_date_range",
        ),
        db.CheckConstraint(
            "status IN ("
            "'RUNNING', "
            "'COMPLETED', "
            "'PARTIAL', "
            "'FAILED'"
            ")",
            name="ck_marketing_iventas_sync_runs_status",
        ),
        db.CheckConstraint(
            "branches_requested >= 0 "
            "AND branches_completed >= 0 "
            "AND branches_failed >= 0 "
            "AND contacts_received >= 0 "
            "AND contacts_unique >= 0 "
            "AND contacts_with_phone >= 0 "
            "AND contacts_mx10_matchable >= 0 "
            "AND contacts_non_mx_or_unresolved >= 0 "
            "AND contacts_with_first_message >= 0 "
            "AND contacts_with_any_tag >= 0 "
            "AND contacts_with_meta_ad_tag >= 0 "
            "AND contacts_with_multiple_meta_ad_tags >= 0 "
            "AND aliases_resolved >= 0 "
            "AND aliases_unresolved >= 0",
            name="ck_marketing_iventas_sync_runs_counts_nonnegative",
        ),
        db.CheckConstraint(
            "NOT is_canonical "
            "OR ("
            "status = 'COMPLETED' "
            "AND branches_failed = 0 "
            "AND aliases_unresolved = 0"
            ")",
            name="ck_marketing_iventas_sync_runs_canonical_valid",
        ),
        db.Index(
            "ix_marketing_iventas_sync_runs_period_key",
            "period_key",
        ),
        db.Index(
            "ix_marketing_iventas_sync_runs_status",
            "status",
        ),
        db.Index(
            "ix_marketing_iventas_sync_runs_is_canonical",
            "is_canonical",
        ),
        db.Index(
            "uq_marketing_iventas_sync_runs_canonical_period",
            "period_key",
            unique=True,
            postgresql_where=db.text(
                "is_canonical = true"
            ),
        ),
    )


class MarketingIventasRawPageORM(db.Model):
    __tablename__ = "marketing_iventas_raw_pages"

    id = db.Column(
        db.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    sync_run_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "marketing_iventas_sync_runs.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    branch_code = db.Column(
        db.String(100),
        nullable=False,
    )

    page_number = db.Column(
        db.Integer,
        nullable=False,
    )

    request_cursor = db.Column(
        db.Text,
        nullable=True,
    )

    next_cursor = db.Column(
        db.Text,
        nullable=True,
    )

    has_more = db.Column(
        db.Boolean,
        nullable=True,
    )

    contacts_count = db.Column(
        db.Integer,
        nullable=True,
    )

    http_status = db.Column(
        db.Integer,
        nullable=False,
    )

    payload_json = db.Column(
        db.Text,
        nullable=False,
    )

    received_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
    )

    sync_run = db.relationship(
        "MarketingIventasSyncRunORM",
        back_populates="raw_pages",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "sync_run_id",
            "branch_code",
            "page_number",
            name="uq_marketing_iventas_raw_pages_run_branch_page",
        ),
        db.CheckConstraint(
            "page_number >= 1",
            name="ck_marketing_iventas_raw_pages_page_positive",
        ),
        db.CheckConstraint(
            "contacts_count IS NULL OR contacts_count >= 0",
            name="ck_marketing_iventas_raw_pages_contacts_count_nonnegative",
        ),
        db.CheckConstraint(
            "http_status >= 100 AND http_status <= 599",
            name="ck_marketing_iventas_raw_pages_http_status",
        ),
        db.Index(
            "ix_marketing_iventas_raw_pages_sync_run_id",
            "sync_run_id",
        ),
        db.Index(
            "ix_marketing_iventas_raw_pages_branch_code",
            "branch_code",
        ),
    )


class MarketingIventasContactORM(db.Model):
    __tablename__ = "marketing_iventas_contacts"

    id = db.Column(
        db.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    sync_run_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "marketing_iventas_sync_runs.id",
            ondelete="CASCADE",
        ),
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

    branch_code = db.Column(
        db.String(100),
        nullable=False,
    )

    contact_id = db.Column(
        db.String(255),
        nullable=False,
    )

    name = db.Column(
        db.String(255),
        nullable=True,
    )

    phone_raw = db.Column(
        db.String(100),
        nullable=True,
    )

    phone_digits = db.Column(
        db.String(100),
        nullable=True,
    )

    phone_mx10 = db.Column(
        db.String(10),
        nullable=True,
    )

    phone_match_status = db.Column(
        db.String(40),
        nullable=False,
    )

    created_at_utc = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
    )

    created_at_local = db.Column(
        db.DateTime(timezone=False),
        nullable=False,
    )

    created_date_local = db.Column(
        db.Date,
        nullable=False,
    )

    first_message_at_utc = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    first_message_at_local = db.Column(
        db.DateTime(timezone=False),
        nullable=True,
    )

    first_message_date_local = db.Column(
        db.Date,
        nullable=True,
    )

    channel_id = db.Column(
        db.String(255),
        nullable=True,
    )

    channel_name = db.Column(
        db.String(255),
        nullable=True,
    )

    channel_phone = db.Column(
        db.String(100),
        nullable=True,
    )

    channel_platform = db.Column(
        db.String(100),
        nullable=True,
    )

    agent_json = db.Column(
        db.JSON,
        nullable=True,
    )

    last_message_status = db.Column(
        db.String(100),
        nullable=True,
    )

    last_outbound_message_at_utc = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    row_hash = db.Column(
        db.String(64),
        nullable=False,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )

    sync_run = db.relationship(
        "MarketingIventasSyncRunORM",
        back_populates="contacts",
    )

    sucursal = db.relationship(
        "Sucursal",
    )

    tags = db.relationship(
        "MarketingIventasContactTagORM",
        back_populates="contact",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "sync_run_id",
            "branch_code",
            "contact_id",
            name="uq_marketing_iventas_contacts_run_branch_contact",
        ),
        db.UniqueConstraint(
            "id",
            "sync_run_id",
            "branch_code",
            "contact_id",
            name="uq_marketing_iventas_contacts_row_identity",
        ),
        db.Index(
            "ix_marketing_iventas_contacts_sync_run_id",
            "sync_run_id",
        ),
        db.Index(
            "ix_marketing_iventas_contacts_sucursal_id",
            "sucursal_id",
        ),
        db.Index(
            "ix_marketing_iventas_contacts_branch_code",
            "branch_code",
        ),
        db.Index(
            "ix_marketing_iventas_contacts_contact_id",
            "contact_id",
        ),
        db.Index(
            "ix_marketing_iventas_contacts_phone_mx10",
            "phone_mx10",
        ),
        db.Index(
            "ix_marketing_iventas_contacts_created_date_local",
            "created_date_local",
        ),
        db.Index(
            "ix_marketing_iventas_contacts_first_message_date_local",
            "first_message_date_local",
        ),
        db.Index(
            "ix_marketing_iventas_contacts_row_hash",
            "row_hash",
        ),
    )


class MarketingIventasContactTagORM(db.Model):
    __tablename__ = "marketing_iventas_contact_tags"

    id = db.Column(
        db.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    sync_run_id = db.Column(
        db.BigInteger,
        nullable=False,
    )

    iventas_contact_row_id = db.Column(
        db.BigInteger,
        nullable=False,
    )

    branch_code = db.Column(
        db.String(100),
        nullable=False,
    )

    contact_id = db.Column(
        db.String(255),
        nullable=False,
    )

    tag_raw = db.Column(
        db.String(255),
        nullable=False,
    )

    tag_kind = db.Column(
        db.String(20),
        nullable=False,
    )

    meta_ad_id = db.Column(
        db.String(64),
        nullable=True,
    )

    observed_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )

    contact = db.relationship(
        "MarketingIventasContactORM",
        back_populates="tags",
    )

    __table_args__ = (
        db.ForeignKeyConstraint(
            [
                "iventas_contact_row_id",
                "sync_run_id",
                "branch_code",
                "contact_id",
            ],
            [
                "marketing_iventas_contacts.id",
                "marketing_iventas_contacts.sync_run_id",
                "marketing_iventas_contacts.branch_code",
                "marketing_iventas_contacts.contact_id",
            ],
            name=(
                "fk_marketing_iventas_contact_tags_"
                "contact_identity"
            ),
            ondelete="CASCADE",
        ),
        db.UniqueConstraint(
            "sync_run_id",
            "iventas_contact_row_id",
            "tag_raw",
            name="uq_marketing_iventas_contact_tags_run_contact_tag",
        ),
        db.CheckConstraint(
            "tag_kind IN ('META_AD', 'OTHER')",
            name="ck_marketing_iventas_contact_tags_kind",
        ),
        db.Index(
            "ix_marketing_iventas_contact_tags_sync_run_id",
            "sync_run_id",
        ),
        db.Index(
            "ix_marketing_iventas_contact_tags_contact_row_id",
            "iventas_contact_row_id",
        ),
        db.Index(
            "ix_marketing_iventas_contact_tags_contact_id",
            "contact_id",
        ),
        db.Index(
            "ix_marketing_iventas_contact_tags_meta_ad_id",
            "meta_ad_id",
        ),
    )
