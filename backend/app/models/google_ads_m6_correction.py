"""Isolated, unpublished M6 late-correction candidates (no write endpoint).

Candidate rows are never queried by the existing Funnel readers. Their RAW
sources remain immutable Warehouse documents; publication requires a distinct,
future, authenticated promotion protocol.
"""
from __future__ import annotations

from app.extensions import db


class GoogleAdsM6CorrectionCaseORM(db.Model):
    __tablename__ = "google_ads_m6_correction_cases"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    customer_id = db.Column(db.String(10), nullable=False)
    business_date = db.Column(db.Date, nullable=False)
    revision = db.Column(db.Integer, nullable=False)
    expected_publication_id = db.Column(
        db.BigInteger, db.ForeignKey(
            "google_ads_m6_daily_publications.id", ondelete="RESTRICT"
        ), nullable=True
    )
    campaign_upload_id = db.Column(
        db.Integer, db.ForeignKey("warehouse_uploads.id", ondelete="RESTRICT"),
        nullable=False,
    )
    ad_group_upload_id = db.Column(
        db.Integer, db.ForeignKey("warehouse_uploads.id", ondelete="RESTRICT"),
        nullable=False,
    )
    approval_version_id = db.Column(
        db.BigInteger, db.ForeignKey(
            "google_ads_branch_approval_versions.id", ondelete="RESTRICT"
        ), nullable=False,
    )
    campaign_sha256 = db.Column(db.String(64), nullable=False)
    ad_group_sha256 = db.Column(db.String(64), nullable=False)
    requested_by_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reason = db.Column(db.Text, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=db.func.now()
    )

    __table_args__ = (
        db.UniqueConstraint(
            "customer_id", "business_date", "revision",
            name="uq_ga_m6_corr_case_revision",
        ),
        db.CheckConstraint(
            "customer_id ~ '^[0-9]{10}$'", name="ck_ga_m6_corr_customer"
        ),
        db.CheckConstraint(
            "business_date >= DATE '2026-10-13'", name="ck_ga_m6_corr_date"
        ),
        db.CheckConstraint("revision > 0", name="ck_ga_m6_corr_revision"),
        db.CheckConstraint(
            "revision = 1 OR expected_publication_id IS NOT NULL",
            name="ck_ga_m6_corr_prior_revision",
        ),
        db.CheckConstraint(
            "campaign_upload_id <> ad_group_upload_id",
            name="ck_ga_m6_corr_sources",
        ),
        db.CheckConstraint(
            "campaign_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_ga_m6_corr_campaign_sha",
        ),
        db.CheckConstraint(
            "ad_group_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_ga_m6_corr_group_sha",
        ),
        db.CheckConstraint(
            "length(btrim(reason)) > 0", name="ck_ga_m6_corr_reason"
        ),
        db.Index("ix_ga_m6_corr_customer_day", "customer_id", "business_date"),
    )


class GoogleAdsM6CorrectionCampaignORM(db.Model):
    __tablename__ = "google_ads_m6_correction_campaign_facts"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    case_id = db.Column(db.BigInteger, db.ForeignKey(
        "google_ads_m6_correction_cases.id", ondelete="RESTRICT"
    ), nullable=False)
    campaign_key = db.Column(db.String(80), nullable=False)
    campaign_name = db.Column(db.String(255), nullable=False)
    currency_code = db.Column(db.String(3), nullable=False)
    cost = db.Column(db.Numeric(18, 2), nullable=False)
    impressions = db.Column(db.BigInteger, nullable=False)
    clicks = db.Column(db.BigInteger, nullable=False)
    conversions = db.Column(db.Numeric(18, 4), nullable=False)
    conversion_value = db.Column(db.Numeric(18, 2), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=db.func.now()
    )

    __table_args__ = (
        db.UniqueConstraint(
            "case_id", "campaign_key", name="uq_ga_m6_corr_campaign_key"
        ),
        db.CheckConstraint(
            "campaign_key ~ '^name:[a-f0-9]{64}$'",
            name="ck_ga_m6_corr_campaign_key",
        ),
        db.CheckConstraint(
            "currency_code = 'MXN'", name="ck_ga_m6_corr_campaign_currency"
        ),
        db.CheckConstraint(
            "cost >= 0 AND impressions >= 0 AND clicks >= 0 AND "
            "conversions >= 0 AND conversion_value >= 0",
            name="ck_ga_m6_corr_campaign_metrics",
        ),
        db.Index("ix_ga_m6_corr_campaign_case", "case_id"),
    )


class GoogleAdsM6CorrectionGroupORM(db.Model):
    __tablename__ = "google_ads_m6_correction_group_facts"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    case_id = db.Column(db.BigInteger, db.ForeignKey(
        "google_ads_m6_correction_cases.id", ondelete="RESTRICT"
    ), nullable=False)
    campaign_key = db.Column(db.String(80), nullable=False)
    ad_group_key = db.Column(db.String(80), nullable=False)
    campaign_name = db.Column(db.String(255), nullable=False)
    ad_group_name = db.Column(db.String(255), nullable=False)
    currency_code = db.Column(db.String(3), nullable=False)
    cost = db.Column(db.Numeric(18, 2), nullable=False)
    impressions = db.Column(db.BigInteger, nullable=False)
    clicks = db.Column(db.BigInteger, nullable=False)
    conversions = db.Column(db.Numeric(18, 4), nullable=False)
    free_pass_conversions = db.Column(db.Numeric(18, 4), nullable=False)
    web_purchase_conversions = db.Column(db.Numeric(18, 4), nullable=False)
    conversion_value = db.Column(db.Numeric(18, 2), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=db.func.now()
    )

    __table_args__ = (
        db.UniqueConstraint(
            "case_id", "campaign_key", "ad_group_key",
            name="uq_ga_m6_corr_group_key",
        ),
        db.CheckConstraint(
            "campaign_key ~ '^name:[a-f0-9]{64}$'",
            name="ck_ga_m6_corr_group_campaign_key",
        ),
        db.CheckConstraint(
            "ad_group_key ~ '^name:[a-f0-9]{64}$'",
            name="ck_ga_m6_corr_group_key",
        ),
        db.CheckConstraint(
            "currency_code = 'MXN'", name="ck_ga_m6_corr_group_currency"
        ),
        db.CheckConstraint(
            "cost >= 0 AND impressions >= 0 AND clicks >= 0 AND "
            "conversions >= 0 AND free_pass_conversions >= 0 AND "
            "web_purchase_conversions >= 0 AND conversion_value >= 0",
            name="ck_ga_m6_corr_group_metrics",
        ),
        db.Index("ix_ga_m6_corr_group_case", "case_id"),
    )
