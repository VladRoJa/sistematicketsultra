from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import JSONB

from app.extensions import db


_JSON_DOCUMENT = db.JSON().with_variant(JSONB, "postgresql")


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


class MarketingReactivationTariffORM(db.Model):
    __tablename__ = "marketing_reactivation_tariffs"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    tarifa_key = db.Column(db.String(255), nullable=False)
    tarifa_raw = db.Column(db.String(255), nullable=False)
    categoria_tarifa = db.Column(db.String(100), nullable=False)
    reactivation_group = db.Column(db.String(30), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    source = db.Column(db.String(255), nullable=False)
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

    __table_args__ = (
        db.UniqueConstraint(
            "tarifa_key",
            name="uq_marketing_reactivation_tariffs_tarifa_key",
        ),
        db.CheckConstraint(
            "reactivation_group IN "
            "('REACTIVATE', 'DOMICILIATED_FLOW', 'EXCLUDE', 'REVIEW')",
            name="ck_marketing_reactivation_tariffs_group",
        ),
        db.Index(
            "ix_marketing_reactivation_tariffs_active_group",
            "is_active",
            "reactivation_group",
        ),
    )


class MarketingCampaignV2TariffORM(db.Model):
    __tablename__ = "marketing_campaign_v2_tariffs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tarifa_key = db.Column(db.String(255), nullable=False)
    tarifa_raw = db.Column(db.String(255), nullable=False)
    categoria_tarifa = db.Column(db.String(100), nullable=False)
    audience_family = db.Column(db.String(30), nullable=False)

    __table_args__ = (
        db.UniqueConstraint(
            "tarifa_key",
            name="uq_marketing_campaign_v2_tariffs_tarifa_key",
        ),
        db.CheckConstraint(
            "audience_family IN "
            "('DOMICILIADO', 'TRIMESTRAL', 'CONVENIO', "
            "'SEMESTRE', 'ESTUDIANTE', 'MES', 'OUT_OF_SEGMENT')",
            name="ck_marketing_campaign_v2_tariffs_audience_family",
        ),
        db.Index(
            "ix_marketing_campaign_v2_tariffs_audience_family",
            "audience_family",
        ),
    )


class MarketingCampaignV2TariffOverrideORM(db.Model):
    __tablename__ = "marketing_campaign_v2_tariff_overrides"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    tarifa_key = db.Column(db.String(255), nullable=False)
    tarifa_raw = db.Column(db.String(255), nullable=False)
    categoria_tarifa = db.Column(db.String(100), nullable=False)
    audience_family = db.Column(db.String(30), nullable=False)
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
        server_default=db.text("CURRENT_TIMESTAMP"),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
        server_default=db.text("CURRENT_TIMESTAMP"),
    )

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
            "tarifa_key",
            name="uq_marketing_campaign_v2_tariff_overrides_tarifa_key",
        ),
        db.CheckConstraint(
            "audience_family IN "
            "('DOMICILIADO', 'TRIMESTRAL', 'CONVENIO', "
            "'SEMESTRE', 'ESTUDIANTE', 'MES', 'OUT_OF_SEGMENT')",
            name="ck_marketing_campaign_v2_tariff_overrides_family",
        ),
        db.Index(
            "ix_marketing_campaign_v2_tariff_overrides_family",
            "audience_family",
        ),
    )


class MarketingCampaignV2BlacklistORM(db.Model):
    __tablename__ = "marketing_campaign_v2_blacklist"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    phone_mx10 = db.Column(db.String(10), nullable=False)
    source_filename = db.Column(db.String(255), nullable=True)
    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=db.text("CURRENT_TIMESTAMP"),
    )

    created_by_user = db.relationship(
        "UserORM",
        foreign_keys=[created_by_user_id],
    )

    __table_args__ = (
        db.UniqueConstraint(
            "phone_mx10",
            name="uq_marketing_campaign_v2_blacklist_phone_mx10",
        ),
        db.CheckConstraint(
            "length(phone_mx10) = 10",
            name="ck_marketing_campaign_v2_blacklist_phone_length",
        ),
        db.Index(
            "ix_marketing_campaign_v2_blacklist_created_at",
            "created_at",
        ),
    )


class MarketingCampaignV2ChannelBindingORM(db.Model):
    __tablename__ = "marketing_campaign_v2_channel_bindings"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    provider = db.Column(db.String(50), nullable=False)
    sucursal_id = db.Column(
        db.Integer,
        db.ForeignKey("sucursales.sucursal_id", ondelete="RESTRICT"),
        nullable=False,
    )
    sucursal_canon = db.Column(
        db.String(100),
        db.ForeignKey("track_branch_catalog.sucursal_canon", ondelete="RESTRICT"),
        nullable=False,
    )
    provider_channel_id = db.Column(db.String(255), nullable=False)
    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=db.true(),
    )
    is_default = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=db.true(),
    )
    metadata_json = db.Column(
        db.JSON,
        nullable=False,
        default=dict,
        server_default=db.text("'{}'"),
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
        server_default=db.text("CURRENT_TIMESTAMP"),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
        server_default=db.text("CURRENT_TIMESTAMP"),
    )

    sucursal = db.relationship("Sucursal")
    created_by_user = db.relationship("UserORM", foreign_keys=[created_by_user_id])
    updated_by_user = db.relationship("UserORM", foreign_keys=[updated_by_user_id])

    __table_args__ = (
        db.UniqueConstraint(
            "provider",
            "provider_channel_id",
            name="uq_marketing_campaign_v2_channel_provider_identity",
        ),
        db.CheckConstraint(
            "length(trim(provider)) > 0 AND provider = upper(trim(provider))",
            name="ck_marketing_campaign_v2_channel_provider",
        ),
        db.CheckConstraint(
            "length(trim(sucursal_canon)) > 0",
            name="ck_marketing_campaign_v2_channel_sucursal_canon",
        ),
        db.CheckConstraint(
            "length(trim(provider_channel_id)) > 0",
            name="ck_marketing_campaign_v2_channel_provider_channel_id",
        ),
        db.Index(
            "ix_marketing_campaign_v2_channel_sucursal",
            "provider",
            "sucursal_id",
            "is_active",
        ),
        db.Index(
            "uq_marketing_campaign_v2_channel_default_active",
            "provider",
            "sucursal_id",
            unique=True,
            postgresql_where=db.text("is_active = true AND is_default = true"),
            sqlite_where=db.text("is_active = 1 AND is_default = 1"),
        ),
    )


class MarketingCampaignV2TemplateORM(db.Model):
    __tablename__ = "marketing_campaign_v2_templates"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    provider = db.Column(db.String(50), nullable=False)
    template_name = db.Column(db.String(255), nullable=False)
    label = db.Column(db.String(255), nullable=False)
    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=db.true(),
    )
    purposes_json = db.Column(
        db.JSON,
        nullable=False,
        default=list,
        server_default=db.text("'[]'"),
    )
    variables_json = db.Column(
        db.JSON,
        nullable=False,
        default=dict,
        server_default=db.text("'{}'"),
    )
    compatible_channel_ids_json = db.Column(
        db.JSON,
        nullable=False,
        default=list,
        server_default=db.text("'[]'"),
    )
    metadata_json = db.Column(
        db.JSON,
        nullable=False,
        default=dict,
        server_default=db.text("'{}'"),
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
        server_default=db.text("CURRENT_TIMESTAMP"),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
        server_default=db.text("CURRENT_TIMESTAMP"),
    )

    created_by_user = db.relationship("UserORM", foreign_keys=[created_by_user_id])
    updated_by_user = db.relationship("UserORM", foreign_keys=[updated_by_user_id])

    __table_args__ = (
        db.UniqueConstraint(
            "provider",
            "template_name",
            name="uq_marketing_campaign_v2_template_provider_name",
        ),
        db.CheckConstraint(
            "length(trim(provider)) > 0 AND provider = upper(trim(provider))",
            name="ck_marketing_campaign_v2_template_provider",
        ),
        db.CheckConstraint(
            "length(trim(template_name)) > 0 AND template_name = trim(template_name)",
            name="ck_marketing_campaign_v2_template_name",
        ),
        db.CheckConstraint(
            "length(trim(label)) > 0",
            name="ck_marketing_campaign_v2_template_label",
        ),
        db.Index(
            "ix_marketing_campaign_v2_template_active",
            "provider",
            "is_active",
        ),
    )


class MarketingCampaignV2ORM(db.Model):
    __tablename__ = "marketing_campaign_v2_campaigns"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    purpose = db.Column(
        db.String(30),
        nullable=False,
        default="UNCLASSIFIED",
        server_default=db.text("'UNCLASSIFIED'"),
    )
    source = db.Column(db.String(100), nullable=False)
    provider = db.Column(db.String(50), nullable=True)
    provider_campaign_id = db.Column(db.String(255), nullable=True)
    audience_definition_json = db.Column(
        db.JSON,
        nullable=False,
        default=dict,
        server_default=db.text("'{}'"),
    )
    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    frozen_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=db.text("CURRENT_TIMESTAMP"),
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=db.text("CURRENT_TIMESTAMP"),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
        server_default=db.text("CURRENT_TIMESTAMP"),
    )

    created_by_user = db.relationship(
        "UserORM",
        foreign_keys=[created_by_user_id],
    )
    recipients = db.relationship(
        "MarketingCampaignV2RecipientORM",
        back_populates="campaign",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MarketingCampaignV2RecipientORM.id",
    )
    provider_stats_snapshots = db.relationship(
        "MarketingCampaignV2ProviderStatsSnapshotORM",
        back_populates="campaign",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=(
            "MarketingCampaignV2ProviderStatsSnapshotORM.fetched_at"
        ),
    )
    provider_campaigns = db.relationship(
        "MarketingCampaignV2ProviderCampaignORM",
        back_populates="campaign",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MarketingCampaignV2ProviderCampaignORM.id",
    )

    __table_args__ = (
        db.CheckConstraint(
            "purpose IN "
            "('NEW_SALE', 'REACTIVATION', 'ACTIVE_MEMBERS', 'UNCLASSIFIED')",
            name="ck_marketing_campaign_v2_campaigns_purpose",
        ),
        db.CheckConstraint(
            "(provider IS NULL AND provider_campaign_id IS NULL) OR "
            "(provider IS NOT NULL AND provider_campaign_id IS NOT NULL "
            "AND length(trim(provider)) > 0 "
            "AND length(trim(provider_campaign_id)) > 0 "
            "AND provider = upper(trim(provider)) "
            "AND provider_campaign_id = trim(provider_campaign_id))",
            name="ck_marketing_campaign_v2_campaigns_provider_binding_complete",
        ),
        db.UniqueConstraint(
            "provider",
            "provider_campaign_id",
            name="uq_marketing_campaign_v2_campaigns_provider_identity",
        ),
        db.Index(
            "ix_marketing_campaign_v2_campaigns_created_at",
            "created_at",
        ),
        db.Index(
            "ix_marketing_campaign_v2_campaigns_purpose",
            "purpose",
        ),
        db.Index(
            "ix_marketing_campaign_v2_campaigns_source",
            "source",
        ),
    )


class MarketingCampaignV2ProviderCampaignORM(db.Model):
    __tablename__ = "marketing_campaign_v2_provider_campaigns"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    campaign_v2_id = db.Column(
        db.BigInteger,
        db.ForeignKey("marketing_campaign_v2_campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider = db.Column(db.String(50), nullable=False)
    sucursal_id = db.Column(
        db.Integer,
        db.ForeignKey("sucursales.sucursal_id", ondelete="RESTRICT"),
        nullable=False,
    )
    sucursal_canon = db.Column(db.String(100), nullable=False)
    channel_binding_id = db.Column(
        db.BigInteger,
        db.ForeignKey("marketing_campaign_v2_channel_bindings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider_channel_id = db.Column(db.String(255), nullable=False)
    template_id = db.Column(
        db.BigInteger,
        db.ForeignKey("marketing_campaign_v2_templates.id", ondelete="RESTRICT"),
        nullable=False,
    )
    template_name = db.Column(db.String(255), nullable=False)
    template_snapshot_json = db.Column(
        db.JSON,
        nullable=False,
        default=dict,
        server_default=db.text("'{}'"),
    )
    recipient_count = db.Column(db.Integer, nullable=False)
    dispatch_fingerprint = db.Column(db.String(64), nullable=False)
    idempotency_key = db.Column(db.String(64), nullable=False)
    status = db.Column(
        db.String(30),
        nullable=False,
        default="PREPARED",
        server_default=db.text("'PREPARED'"),
    )
    provider_campaign_id = db.Column(db.String(255), nullable=True)
    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    submitted_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    scheduled_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    scheduled_timezone = db.Column(db.String(100), nullable=True)
    scheduled_local_at = db.Column(
        db.DateTime(timezone=False),
        nullable=True,
    )
    scheduled_for = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )
    provider_send_at = db.Column(db.String(64), nullable=True)
    reconciliation_resolution = db.Column(db.String(40), nullable=True)
    reconciliation_note = db.Column(db.Text, nullable=True)
    reconciliation_snapshot_json = db.Column(
        db.JSON,
        nullable=False,
        default=dict,
        server_default=db.text("'{}'"),
    )
    reconciled_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reconciled_at = db.Column(db.DateTime(timezone=True), nullable=True)
    retry_attempt_count = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default=db.text("0"),
    )
    retry_last_attempt_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )
    retry_next_allowed_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )
    retry_last_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    retry_history_json = db.Column(
        db.JSON,
        nullable=False,
        default=list,
        server_default=db.text("'[]'"),
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=db.text("CURRENT_TIMESTAMP"),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
        server_default=db.text("CURRENT_TIMESTAMP"),
    )
    submit_started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    submitted_at = db.Column(db.DateTime(timezone=True), nullable=True)
    provider_deduplicated = db.Column(db.Boolean, nullable=True)
    request_snapshot_json = db.Column(
        db.JSON,
        nullable=False,
        default=dict,
        server_default=db.text("'{}'"),
    )
    provider_response_json = db.Column(
        db.JSON,
        nullable=False,
        default=dict,
        server_default=db.text("'{}'"),
    )
    error_code = db.Column(db.String(100), nullable=True)
    support_ref = db.Column(db.String(200), nullable=True)

    campaign = db.relationship(
        "MarketingCampaignV2ORM",
        back_populates="provider_campaigns",
    )
    channel_binding = db.relationship("MarketingCampaignV2ChannelBindingORM")
    template = db.relationship("MarketingCampaignV2TemplateORM")
    sucursal = db.relationship("Sucursal")
    created_by_user = db.relationship("UserORM", foreign_keys=[created_by_user_id])
    submitted_by_user = db.relationship("UserORM", foreign_keys=[submitted_by_user_id])
    scheduled_by_user = db.relationship("UserORM", foreign_keys=[scheduled_by_user_id])
    reconciled_by_user = db.relationship("UserORM", foreign_keys=[reconciled_by_user_id])
    retry_last_by_user = db.relationship("UserORM", foreign_keys=[retry_last_by_user_id])

    __table_args__ = (
        db.UniqueConstraint(
            "idempotency_key",
            name="uq_marketing_campaign_v2_provider_campaign_idempotency",
        ),
        db.UniqueConstraint(
            "provider",
            "provider_campaign_id",
            name="uq_marketing_campaign_v2_provider_campaign_external_identity",
        ),
        db.CheckConstraint(
            "recipient_count >= 0",
            name="ck_marketing_campaign_v2_provider_campaign_recipient_count",
        ),
        db.CheckConstraint(
            "length(dispatch_fingerprint) = 64 AND length(idempotency_key) = 64",
            name="ck_marketing_campaign_v2_provider_campaign_fingerprints",
        ),
        db.CheckConstraint(
            "status IN ('PREPARED', 'READY', 'BLOCKED', 'SUBMITTING', "
            "'SUBMITTED', 'SCHEDULED', 'RETRY_ELIGIBLE', "
            "'RETRY_EXHAUSTED', 'PROVIDER_ERROR', "
            "'RECONCILIATION_REQUIRED')",
            name="ck_marketing_campaign_v2_provider_campaign_status",
        ),
        db.CheckConstraint(
            "reconciliation_resolution IS NULL OR "
            "reconciliation_resolution IN ("
            "'PROVIDER_CAMPAIGN_FOUND', 'NOT_CREATED_CONFIRMED'"
            ")",
            name="ck_mkt_v2_provider_campaign_reconciliation_resolution",
        ),
        db.CheckConstraint(
            "("
            "reconciliation_resolution IS NULL "
            "AND reconciled_at IS NULL "
            "AND reconciliation_note IS NULL"
            ") OR ("
            "reconciliation_resolution IS NOT NULL "
            "AND reconciled_at IS NOT NULL "
            "AND reconciliation_note IS NOT NULL "
            "AND length(trim(reconciliation_note)) > 0"
            ")",
            name="ck_mkt_v2_provider_campaign_reconciliation_audit",
        ),
        db.CheckConstraint(
            "reconciliation_resolution <> 'PROVIDER_CAMPAIGN_FOUND' "
            "OR provider_campaign_id IS NOT NULL",
            name="ck_mkt_v2_provider_campaign_reconciled_found",
        ),
        db.CheckConstraint(
            "retry_attempt_count >= 0 AND retry_attempt_count <= 3",
            name="ck_mkt_v2_provider_campaign_retry_attempts",
        ),
        db.CheckConstraint(
            "status <> 'RETRY_ELIGIBLE' OR ("
            "reconciliation_resolution = 'NOT_CREATED_CONFIRMED' "
            "AND provider_campaign_id IS NULL "
            "AND retry_attempt_count < 3"
            ")",
            name="ck_mkt_v2_provider_campaign_retry_eligible",
        ),
        db.CheckConstraint(
            "status <> 'RETRY_EXHAUSTED' OR ("
            "reconciliation_resolution = 'NOT_CREATED_CONFIRMED' "
            "AND provider_campaign_id IS NULL "
            "AND retry_attempt_count >= 3"
            ")",
            name="ck_mkt_v2_provider_campaign_retry_exhausted",
        ),
        db.CheckConstraint(
            "("
            "scheduled_timezone IS NULL AND scheduled_local_at IS NULL "
            "AND scheduled_for IS NULL AND provider_send_at IS NULL"
            ") OR ("
            "scheduled_timezone IS NOT NULL AND scheduled_local_at IS NOT NULL "
            "AND scheduled_for IS NOT NULL AND provider_send_at IS NOT NULL"
            ")",
            name="ck_marketing_campaign_v2_provider_campaign_schedule_complete",
        ),
        db.CheckConstraint(
            "length(trim(provider)) > 0 AND provider = upper(trim(provider))",
            name="ck_marketing_campaign_v2_provider_campaign_provider",
        ),
        db.Index(
            "ix_marketing_campaign_v2_provider_campaign_parent",
            "campaign_v2_id",
            "sucursal_id",
        ),
        db.Index(
            "ix_marketing_campaign_v2_provider_campaign_status",
            "status",
        ),
        db.Index(
            "ix_marketing_campaign_v2_provider_campaign_scheduled_for",
            "scheduled_for",
        ),
        db.Index(
            "ix_mkt_v2_provider_campaign_retry_next",
            "retry_next_allowed_at",
        ),
    )


class MarketingCampaignV2RecipientDispatchExclusionORM(db.Model):
    """Audit-only exclusion from one campaign's sendable projection.

    The original recipient and its evidence remain immutable.
    """

    __tablename__ = "marketing_campaign_v2_recipient_dispatch_exclusions"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    campaign_id = db.Column(
        db.BigInteger,
        db.ForeignKey("marketing_campaign_v2_campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    recipient_id = db.Column(
        db.BigInteger,
        db.ForeignKey("marketing_campaign_v2_recipients.id", ondelete="CASCADE"),
        nullable=False,
    )
    reason = db.Column(db.String(80), nullable=False)
    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=db.text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        db.UniqueConstraint(
            "campaign_id", "recipient_id",
            name="uq_mkt_v2_recipient_dispatch_exclusions_campaign_recipient",
        ),
        db.CheckConstraint(
            "reason = 'AMBIGUOUS_BRANCH_EVIDENCE'",
            name="ck_mkt_v2_recipient_dispatch_exclusion_reason",
        ),
        db.Index("ix_mkt_v2_dispatch_exclusions_recipient_id", "recipient_id"),
    )


class MarketingCampaignV2RecipientORM(db.Model):
    __tablename__ = "marketing_campaign_v2_recipients"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    campaign_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "marketing_campaign_v2_campaigns.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    phone_mx10 = db.Column(db.String(10), nullable=False)
    source = db.Column(db.String(100), nullable=False)
    socios_vencidos_cartera_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "socios_vencidos_cartera.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    socios_activos_snapshot_row_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "socios_activos_snapshot_rows.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    member_id = db.Column(db.String(64), nullable=True)
    member_pin = db.Column(db.String(64), nullable=True)
    member_name = db.Column(db.String(255), nullable=True)
    sucursal = db.Column(db.String(255), nullable=True)
    tarifa_raw = db.Column(db.String(255), nullable=True)
    categoria_tarifa = db.Column(db.String(100), nullable=True)
    audience_family = db.Column(db.String(30), nullable=True)
    fecha_vencimiento_date = db.Column(db.Date, nullable=True)
    inclusion_reason = db.Column(db.String(100), nullable=True)
    conflict_fields_json = db.Column(
        db.JSON,
        nullable=False,
        default=list,
        server_default=db.text("'[]'"),
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=db.text("CURRENT_TIMESTAMP"),
    )

    campaign = db.relationship(
        "MarketingCampaignV2ORM",
        back_populates="recipients",
    )
    socios_vencidos_cartera = db.relationship(
        "SociosVencidosCarteraORM",
    )
    socios_activos_snapshot_row = db.relationship(
        "SociosActivosSnapshotRowORM",
    )
    evidence_rows = db.relationship(
        "MarketingCampaignV2RecipientEvidenceORM",
        back_populates="recipient",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MarketingCampaignV2RecipientEvidenceORM.evidence_order",
    )
    provider_stats_observations = db.relationship(
        "MarketingCampaignV2ProviderRecipientObservationORM",
        back_populates="campaign_recipient",
        passive_deletes=True,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "campaign_id",
            "phone_mx10",
            name="uq_marketing_campaign_v2_recipients_campaign_phone",
        ),
        db.CheckConstraint(
            "length(phone_mx10) = 10",
            name="ck_marketing_campaign_v2_recipients_phone_mx10_length",
        ),
        db.CheckConstraint(
            "audience_family IS NULL OR audience_family IN "
            "('DOMICILIADO', 'TRIMESTRAL', 'CONVENIO', "
            "'SEMESTRE', 'ESTUDIANTE', 'MES', 'OUT_OF_SEGMENT')",
            name="ck_marketing_campaign_v2_recipients_audience_family",
        ),
        db.Index(
            "ix_marketing_campaign_v2_recipients_campaign_id",
            "campaign_id",
        ),
        db.Index(
            "ix_marketing_campaign_v2_recipients_phone_mx10",
            "phone_mx10",
        ),
        db.Index(
            "ix_marketing_campaign_v2_recipients_vencidos_cartera_id",
            "socios_vencidos_cartera_id",
        ),
        db.Index(
            "ix_marketing_campaign_v2_recipients_activos_snapshot_row_id",
            "socios_activos_snapshot_row_id",
        ),
    )


class MarketingCampaignV2RecipientEvidenceORM(db.Model):
    __tablename__ = "marketing_campaign_v2_recipient_evidence"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    recipient_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "marketing_campaign_v2_recipients.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    evidence_order = db.Column(db.Integer, nullable=False)
    source = db.Column(db.String(100), nullable=False)
    phone_raw = db.Column(db.String(64), nullable=True)
    phone_mx10 = db.Column(db.String(10), nullable=False)
    socios_vencidos_cartera_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "socios_vencidos_cartera.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    socios_activos_snapshot_row_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "socios_activos_snapshot_rows.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    socios_activos_snapshot_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "socios_activos_snapshots.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    member_id = db.Column(db.String(64), nullable=True)
    member_pin = db.Column(db.String(64), nullable=True)
    member_name = db.Column(db.String(255), nullable=True)
    sucursal = db.Column(db.String(255), nullable=True)
    sucursal_key = db.Column(db.String(255), nullable=True)
    tarifa_raw = db.Column(db.String(255), nullable=True)
    tarifa_key = db.Column(db.String(255), nullable=True)
    categoria_tarifa = db.Column(db.String(100), nullable=True)
    audience_family = db.Column(db.String(30), nullable=True)
    fecha_vencimiento_date = db.Column(db.Date, nullable=True)
    current_status = db.Column(db.String(50), nullable=True)
    evidence_json = db.Column(
        db.JSON,
        nullable=False,
        default=list,
        server_default=db.text("'[]'"),
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=db.text("CURRENT_TIMESTAMP"),
    )

    recipient = db.relationship(
        "MarketingCampaignV2RecipientORM",
        back_populates="evidence_rows",
    )
    socios_vencidos_cartera = db.relationship(
        "SociosVencidosCarteraORM",
    )
    socios_activos_snapshot_row = db.relationship(
        "SociosActivosSnapshotRowORM",
    )
    socios_activos_snapshot = db.relationship(
        "SociosActivosSnapshotORM",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "recipient_id",
            "evidence_order",
            name="uq_marketing_campaign_v2_evidence_recipient_order",
        ),
        db.CheckConstraint(
            "length(phone_mx10) = 10",
            name="ck_marketing_campaign_v2_evidence_phone_mx10_length",
        ),
        db.CheckConstraint(
            "audience_family IS NULL OR audience_family IN "
            "('DOMICILIADO', 'TRIMESTRAL', 'CONVENIO', "
            "'SEMESTRE', 'ESTUDIANTE', 'MES', 'OUT_OF_SEGMENT')",
            name="ck_marketing_campaign_v2_evidence_audience_family",
        ),
        db.Index(
            "ix_marketing_campaign_v2_evidence_recipient_id",
            "recipient_id",
        ),
        db.Index(
            "ix_marketing_campaign_v2_evidence_vencidos_cartera_id",
            "socios_vencidos_cartera_id",
        ),
        db.Index(
            "ix_marketing_campaign_v2_evidence_activos_snapshot_row_id",
            "socios_activos_snapshot_row_id",
        ),
        db.Index(
            "ix_marketing_campaign_v2_evidence_activos_snapshot_id",
            "socios_activos_snapshot_id",
        ),
    )


class MarketingCampaignV2ProviderStatsSnapshotORM(db.Model):
    __tablename__ = "marketing_campaign_v2_provider_stats_snapshots"

    provider_campaign_child_id = db.Column(
        db.BigInteger,
        db.ForeignKey("marketing_campaign_v2_provider_campaigns.id", ondelete="SET NULL"),
        nullable=True,
    )

    id = db.Column(
        db.BigInteger().with_variant(db.Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    campaign_v2_id = db.Column(
        db.BigInteger,
        db.ForeignKey("marketing_campaign_v2_campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider = db.Column(db.String(50), nullable=False)
    provider_campaign_id = db.Column(db.String(255), nullable=False)
    analytics_status = db.Column(db.String(50), nullable=True)
    fetched_at = db.Column(db.DateTime(timezone=True), nullable=False)
    raw_successful = db.Column(db.Integer, nullable=False)
    raw_failed = db.Column(db.Integer, nullable=False)
    raw_sent = db.Column(db.Integer, nullable=False)
    raw_delivered = db.Column(db.Integer, nullable=False)
    raw_viewed = db.Column(db.Integer, nullable=False)
    raw_answered = db.Column(db.Integer, nullable=False)
    raw_interaction_groups = db.Column(db.Integer, nullable=False)
    raw_interaction_items = db.Column(db.Integer, nullable=False)
    analytics_json = db.Column(_JSON_DOCUMENT, nullable=True)
    button_interactions_json = db.Column(
        _JSON_DOCUMENT,
        nullable=False,
        default=list,
        server_default=db.text("'[]'"),
    )
    provider_recipient_count = db.Column(db.Integer, nullable=False)
    matched_recipient_count = db.Column(db.Integer, nullable=False)
    unmatched_provider_count = db.Column(db.Integer, nullable=False)
    frozen_recipient_without_provider_status_count = db.Column(
        db.Integer,
        nullable=False,
    )
    fingerprint = db.Column(db.String(64), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=db.text("CURRENT_TIMESTAMP"),
    )

    campaign = db.relationship(
        "MarketingCampaignV2ORM",
        back_populates="provider_stats_snapshots",
    )
    observations = db.relationship(
        "MarketingCampaignV2ProviderRecipientObservationORM",
        back_populates="snapshot",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MarketingCampaignV2ProviderRecipientObservationORM.id",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "campaign_v2_id",
            "provider",
            "provider_campaign_id",
            "fingerprint",
            name="uq_marketing_campaign_v2_provider_stats_snapshot_identity",
        ),
        db.CheckConstraint(
            "length(fingerprint) = 64",
            name="ck_marketing_campaign_v2_provider_stats_fingerprint_length",
        ),
        db.CheckConstraint(
            "raw_successful >= 0 AND raw_failed >= 0 AND raw_sent >= 0 "
            "AND raw_delivered >= 0 AND raw_viewed >= 0 AND raw_answered >= 0 "
            "AND raw_interaction_groups >= 0 AND raw_interaction_items >= 0",
            name="ck_marketing_campaign_v2_provider_stats_raw_counts_nonnegative",
        ),
        db.CheckConstraint(
            "provider_recipient_count >= 0 AND matched_recipient_count >= 0 "
            "AND unmatched_provider_count >= 0 "
            "AND frozen_recipient_without_provider_status_count >= 0",
            name="ck_marketing_campaign_v2_provider_stats_diagnostics_nonnegative",
        ),
        db.Index(
            "ix_marketing_campaign_v2_provider_stats_campaign_fetched",
            "campaign_v2_id",
            "fetched_at",
        ),
    )


class MarketingCampaignV2ProviderRecipientObservationORM(db.Model):
    __tablename__ = "marketing_campaign_v2_provider_recipient_observations"

    id = db.Column(
        db.BigInteger().with_variant(db.Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    snapshot_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "marketing_campaign_v2_provider_stats_snapshots.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    normalized_phone = db.Column(db.String(128), nullable=False)
    campaign_recipient_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "marketing_campaign_v2_recipients.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    outcome = db.Column(db.String(20), nullable=False)
    delivery_bucket = db.Column(db.String(20), nullable=True)
    button_labels_json = db.Column(
        _JSON_DOCUMENT,
        nullable=False,
        default=list,
        server_default=db.text("'[]'"),
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=db.text("CURRENT_TIMESTAMP"),
    )

    snapshot = db.relationship(
        "MarketingCampaignV2ProviderStatsSnapshotORM",
        back_populates="observations",
    )
    campaign_recipient = db.relationship(
        "MarketingCampaignV2RecipientORM",
        back_populates="provider_stats_observations",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "snapshot_id",
            "normalized_phone",
            name="uq_marketing_campaign_v2_provider_obs_snapshot_phone",
        ),
        db.CheckConstraint(
            "outcome IN ('SUCCESSFUL', 'FAILED')",
            name="ck_marketing_campaign_v2_provider_obs_outcome",
        ),
        db.CheckConstraint(
            "(outcome = 'FAILED' AND delivery_bucket IS NULL) OR "
            "(outcome = 'SUCCESSFUL' AND delivery_bucket IN "
            "('SENT', 'DELIVERED', 'VIEWED'))",
            name="ck_marketing_campaign_v2_provider_obs_delivery",
        ),
        db.Index(
            "ix_marketing_campaign_v2_provider_obs_snapshot_id",
            "snapshot_id",
        ),
        db.Index(
            "ix_marketing_campaign_v2_provider_obs_campaign_recipient_id",
            "campaign_recipient_id",
        ),
        db.Index(
            "ix_marketing_campaign_v2_provider_obs_normalized_phone",
            "normalized_phone",
        ),
    )


class MarketingReactivationCampaignORM(db.Model):
    __tablename__ = "marketing_reactivation_campaigns"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="DRAFT")
    date_from = db.Column(db.Date, nullable=False)
    date_to = db.Column(db.Date, nullable=False)
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
    exported_at = db.Column(db.DateTime(timezone=True), nullable=True)
    sent_at = db.Column(db.DateTime(timezone=True), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    filters_json = db.Column(db.JSON, nullable=False, default=dict)
    recipient_count = db.Column(db.Integer, nullable=False, default=0)
    attribution_window_days = db.Column(
        db.Integer,
        nullable=False,
        default=14,
        server_default=db.text("14"),
    )

    created_by_user = db.relationship(
        "UserORM",
        foreign_keys=[created_by_user_id],
    )
    recipients = db.relationship(
        "MarketingReactivationCampaignRecipientORM",
        back_populates="campaign",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MarketingReactivationCampaignRecipientORM.id",
    )

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('DRAFT', 'EXPORTED', 'SENT', 'CANCELLED')",
            name="ck_marketing_reactivation_campaigns_status",
        ),
        db.CheckConstraint(
            "date_from <= date_to",
            name="ck_marketing_reactivation_campaigns_date_range",
        ),
        db.CheckConstraint(
            "recipient_count >= 0",
            name="ck_marketing_reactivation_campaigns_recipient_count",
        ),
        db.CheckConstraint(
            "attribution_window_days BETWEEN 1 AND 90",
            name="ck_marketing_reactivation_campaigns_attribution_window",
        ),
        db.Index(
            "ix_marketing_reactivation_campaigns_created_at",
            "created_at",
        ),
        db.Index(
            "ix_marketing_reactivation_campaigns_status",
            "status",
        ),
    )


class MarketingReactivationCampaignRecipientORM(db.Model):
    __tablename__ = "marketing_reactivation_campaign_recipients"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    campaign_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "marketing_reactivation_campaigns.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    socios_vencidos_cartera_id = db.Column(
        db.BigInteger,
        db.ForeignKey("socios_vencidos_cartera.id", ondelete="RESTRICT"),
        nullable=True,
    )
    phone_mx10 = db.Column(db.String(10), nullable=False)
    member_name = db.Column(db.String(255), nullable=True)
    sucursal = db.Column(db.String(255), nullable=False)
    fecha_vencimiento_date = db.Column(db.Date, nullable=True)
    tarifa = db.Column(db.String(255), nullable=True)
    inclusion_status = db.Column(db.String(40), nullable=False)
    exclusion_reason = db.Column(db.String(100), nullable=True)
    operational_status = db.Column(db.String(50), nullable=False)
    operational_reason = db.Column(db.String(100), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )

    campaign = db.relationship(
        "MarketingReactivationCampaignORM",
        back_populates="recipients",
    )
    socios_vencidos_cartera = db.relationship(
        "SociosVencidosCarteraORM",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "campaign_id",
            "phone_mx10",
            name="uq_marketing_reactivation_recipients_campaign_phone",
        ),
        db.Index(
            "ix_marketing_reactivation_recipients_campaign_id",
            "campaign_id",
        ),
        db.Index(
            "ix_marketing_reactivation_recipients_phone_mx10",
            "phone_mx10",
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

    is_from_ads = db.Column(
        db.Boolean,
        nullable=True,
    )

    ads_source_id = db.Column(
        db.String(255),
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
            "ix_marketing_iventas_contacts_run_ads_first_message",
            "sync_run_id",
            "is_from_ads",
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


class MarketingMetaSyncRunORM(db.Model):
    __tablename__ = "marketing_meta_sync_runs"

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
    accounts_requested = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )
    accounts_completed = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )
    accounts_failed = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )
    pages_received = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )
    insights_received = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )
    insights_unique = db.Column(
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
        "MarketingMetaRawPageORM",
        back_populates="sync_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    ad_insights = db.relationship(
        "MarketingMetaAdInsightORM",
        back_populates="sync_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        db.CheckConstraint(
            "date_from <= date_to",
            name="ck_marketing_meta_sync_runs_date_range",
        ),
        db.CheckConstraint(
            "status IN ("
            "'RUNNING', "
            "'COMPLETED', "
            "'PARTIAL', "
            "'FAILED'"
            ")",
            name="ck_marketing_meta_sync_runs_status",
        ),
        db.CheckConstraint(
            "accounts_requested >= 0 "
            "AND accounts_completed >= 0 "
            "AND accounts_failed >= 0 "
            "AND pages_received >= 0 "
            "AND insights_received >= 0 "
            "AND insights_unique >= 0",
            name="ck_marketing_meta_sync_runs_counts_nonnegative",
        ),
        db.CheckConstraint(
            "NOT is_canonical "
            "OR ("
            "status = 'COMPLETED' "
            "AND accounts_failed = 0"
            ")",
            name="ck_marketing_meta_sync_runs_canonical_valid",
        ),
        db.Index(
            "ix_marketing_meta_sync_runs_period_key",
            "period_key",
        ),
        db.Index(
            "ix_marketing_meta_sync_runs_status",
            "status",
        ),
        db.Index(
            "ix_marketing_meta_sync_runs_is_canonical",
            "is_canonical",
        ),
        db.Index(
            "uq_marketing_meta_sync_runs_canonical_period",
            "period_key",
            unique=True,
            postgresql_where=db.text(
                "is_canonical = true"
            ),
        ),
    )


class MarketingMetaRawPageORM(db.Model):
    __tablename__ = "marketing_meta_raw_pages"

    id = db.Column(
        db.BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    sync_run_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "marketing_meta_sync_runs.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    account_id = db.Column(
        db.String(64),
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
    rows_count = db.Column(
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
        "MarketingMetaSyncRunORM",
        back_populates="raw_pages",
    )
    ad_insights = db.relationship(
        "MarketingMetaAdInsightORM",
        back_populates="raw_page",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "sync_run_id",
            "account_id",
            "page_number",
            name="uq_marketing_meta_raw_pages_run_account_page",
        ),
        db.CheckConstraint(
            "page_number >= 1",
            name="ck_marketing_meta_raw_pages_page_positive",
        ),
        db.CheckConstraint(
            "rows_count IS NULL OR rows_count >= 0",
            name="ck_marketing_meta_raw_pages_rows_nonnegative",
        ),
        db.CheckConstraint(
            "http_status >= 100 AND http_status <= 599",
            name="ck_marketing_meta_raw_pages_http_status",
        ),
        db.Index(
            "ix_marketing_meta_raw_pages_sync_run_id",
            "sync_run_id",
        ),
        db.Index(
            "ix_marketing_meta_raw_pages_account_id",
            "account_id",
        ),
    )


class MarketingMetaAdInsightORM(db.Model):
    __tablename__ = "marketing_meta_ad_insights"

    id = db.Column(
        db.BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    sync_run_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "marketing_meta_sync_runs.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    raw_page_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "marketing_meta_raw_pages.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    account_id = db.Column(
        db.String(64),
        nullable=False,
    )
    account_name = db.Column(
        db.Text,
        nullable=True,
    )
    campaign_id = db.Column(
        db.String(64),
        nullable=False,
    )
    campaign_name = db.Column(
        db.Text,
        nullable=True,
    )
    adset_id = db.Column(
        db.String(64),
        nullable=False,
    )
    adset_name = db.Column(
        db.Text,
        nullable=True,
    )
    ad_id = db.Column(
        db.String(64),
        nullable=False,
    )
    ad_name = db.Column(
        db.Text,
        nullable=True,
    )
    date_start = db.Column(
        db.Date,
        nullable=False,
    )
    date_stop = db.Column(
        db.Date,
        nullable=False,
    )
    spend = db.Column(
        db.Numeric(16, 4),
        nullable=False,
    )
    reach = db.Column(
        db.BigInteger,
        nullable=False,
    )
    impressions = db.Column(
        db.BigInteger,
        nullable=False,
    )
    clicks = db.Column(
        db.BigInteger,
        nullable=False,
    )
    actions_json = db.Column(
        db.JSON,
        nullable=False,
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
        "MarketingMetaSyncRunORM",
        back_populates="ad_insights",
    )
    raw_page = db.relationship(
        "MarketingMetaRawPageORM",
        back_populates="ad_insights",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "sync_run_id",
            "account_id",
            "ad_id",
            "date_start",
            "date_stop",
            name="uq_marketing_meta_insights_run_ad_period",
        ),
        db.CheckConstraint(
            "date_start <= date_stop",
            name="ck_marketing_meta_insights_date_range",
        ),
        db.CheckConstraint(
            "spend >= 0 "
            "AND reach >= 0 "
            "AND impressions >= 0 "
            "AND clicks >= 0",
            name="ck_marketing_meta_insights_metrics_nonnegative",
        ),
        db.Index(
            "ix_marketing_meta_insights_sync_run_id",
            "sync_run_id",
        ),
        db.Index(
            "ix_marketing_meta_insights_raw_page_id",
            "raw_page_id",
        ),
        db.Index(
            "ix_marketing_meta_insights_account_id",
            "account_id",
        ),
        db.Index(
            "ix_marketing_meta_insights_ad_id",
            "ad_id",
        ),
        db.Index(
            "ix_marketing_meta_insights_date_start",
            "date_start",
        ),
        db.Index(
            "ix_marketing_meta_insights_row_hash",
            "row_hash",
        ),
    )
