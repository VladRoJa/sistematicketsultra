"""Explicit versioned Google Ads M6 daily publication; never seeded by ingestion."""
from __future__ import annotations

import sqlalchemy as sa
from app.extensions import db


class GoogleAdsM6DailyPublicationORM(db.Model):
    __tablename__ = "google_ads_m6_daily_publications"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    customer_id = db.Column(db.String(10), nullable=False)
    business_date = db.Column(db.Date, nullable=False)
    revision = db.Column(db.Integer, nullable=False)
    campaign_upload_id = db.Column(
        db.Integer, db.ForeignKey("warehouse_uploads.id", ondelete="RESTRICT"),
        nullable=False,
    )
    ad_group_upload_id = db.Column(
        db.Integer, db.ForeignKey("warehouse_uploads.id", ondelete="RESTRICT"),
        nullable=False,
    )
    approval_version_id = db.Column(
        db.BigInteger,
        db.ForeignKey("google_ads_branch_approval_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    campaign_sha256 = db.Column(db.String(64), nullable=False)
    ad_group_sha256 = db.Column(db.String(64), nullable=False)
    is_canonical = db.Column(db.Boolean, nullable=False, default=False)
    published_by_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    published_on = db.Column(db.Date, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        server_default=db.func.now(),
    )

    __table_args__ = (
        db.UniqueConstraint(
            "customer_id", "business_date", "revision",
            name="uq_ga_m6_pub_revision",
        ),
        db.Index(
            "uq_ga_m6_pub_canonical_day", "customer_id", "business_date",
            unique=True, postgresql_where=sa.text("is_canonical"),
        ),
        db.Index(
            "ix_ga_m6_pub_sources", "campaign_upload_id", "ad_group_upload_id",
        ),
        db.CheckConstraint(
            "customer_id ~ '^[0-9]{10}$'", name="ck_ga_m6_pub_customer",
        ),
        db.CheckConstraint(
            "business_date >= DATE '2026-10-13'",
            name="ck_ga_m6_pub_first_day",
        ),
        db.CheckConstraint("revision > 0", name="ck_ga_m6_pub_revision"),
        db.CheckConstraint(
            "campaign_upload_id <> ad_group_upload_id",
            name="ck_ga_m6_pub_distinct_sources",
        ),
        db.CheckConstraint(
            "campaign_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_ga_m6_pub_campaign_sha",
        ),
        db.CheckConstraint(
            "ad_group_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_ga_m6_pub_group_sha",
        ),
    )
