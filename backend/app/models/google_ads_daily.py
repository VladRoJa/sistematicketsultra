"""Google Ads daily data imported from Warehouse raw files.

Name-based keys are temporary: the source spreadsheet has no campaign_id.
A future API reconciler MUST use an explicit name-to-id mapping.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


class GoogleAdsDailyMetricORM(db.Model):
    __tablename__ = "google_ads_daily_metrics"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    customer_id = db.Column(db.String(10), nullable=False)
    campaign_id = db.Column(db.String(32), nullable=True)
    campaign_key = db.Column(db.String(80), nullable=False)
    campaign_name = db.Column(db.String(255), nullable=False)
    report_date = db.Column(db.Date, nullable=False)
    currency_code = db.Column(db.String(3), nullable=False)
    cost = db.Column(db.Numeric(18, 2), nullable=False)
    impressions = db.Column(db.BigInteger, nullable=False)
    clicks = db.Column(db.BigInteger, nullable=False)
    conversions = db.Column(db.Numeric(18, 4), nullable=False)
    conversion_value = db.Column(db.Numeric(18, 2), nullable=False)
    source_kind = db.Column(db.String(32), nullable=False, default="WAREHOUSE_XLSX")
    source_upload_id = db.Column(
        db.Integer, db.ForeignKey("warehouse_uploads.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.UniqueConstraint(
            "customer_id", "campaign_key", "report_date",
            name="uq_google_ads_daily_customer_campaign_day",
        ),
        db.Index("ix_google_ads_daily_customer_date", "customer_id", "report_date"),
        db.CheckConstraint("cost >= 0", name="ck_google_ads_daily_cost"),
        db.CheckConstraint("impressions >= 0", name="ck_google_ads_daily_impressions"),
        db.CheckConstraint("clicks >= 0", name="ck_google_ads_daily_clicks"),
        db.CheckConstraint("conversions >= 0", name="ck_google_ads_daily_conversions"),
        db.CheckConstraint("conversion_value >= 0", name="ck_google_ads_daily_value"),
    )
