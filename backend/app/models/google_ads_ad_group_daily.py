"""Warehouse Google Ads group-by-day facts.

This table is a detailed drill-down, not another investment source to sum
with google_ads_daily_metrics. Names are provisional identifiers until
Google Ads API campaign/ad-group IDs can be verified explicitly.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


class GoogleAdsAdGroupDailyMetricORM(db.Model):
    __tablename__ = "google_ads_ad_group_daily_metrics"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    customer_id = db.Column(db.String(10), nullable=False)
    campaign_id = db.Column(db.String(32), nullable=True)
    ad_group_id = db.Column(db.String(32), nullable=True)
    campaign_key = db.Column(db.String(80), nullable=False)
    ad_group_key = db.Column(db.String(80), nullable=False)
    campaign_name = db.Column(db.String(255), nullable=False)
    ad_group_name = db.Column(db.String(255), nullable=False)
    report_date = db.Column(db.Date, nullable=False)
    currency_code = db.Column(db.String(3), nullable=False)
    cost = db.Column(db.Numeric(18, 2), nullable=False)
    impressions = db.Column(db.BigInteger, nullable=False)
    clicks = db.Column(db.BigInteger, nullable=False)
    conversions = db.Column(db.Numeric(18, 4), nullable=False)
    free_pass_conversions = db.Column(db.Numeric(18, 4), nullable=False)
    web_purchase_conversions = db.Column(db.Numeric(18, 4), nullable=False)
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
            "customer_id", "campaign_key", "ad_group_key", "report_date",
            name="uq_google_ads_group_daily_customer_campaign_group_day",
        ),
        db.Index(
            "ix_google_ads_group_daily_customer_date",
            "customer_id", "report_date",
        ),
        db.CheckConstraint("cost >= 0", name="ck_google_ads_group_daily_cost"),
        db.CheckConstraint("clicks >= 0", name="ck_google_ads_group_daily_clicks"),
        db.CheckConstraint("impressions >= 0", name="ck_google_ads_group_daily_impr"),
        db.CheckConstraint("conversions >= 0", name="ck_google_ads_group_daily_conv"),
        db.CheckConstraint("free_pass_conversions >= 0", name="ck_google_ads_group_daily_pass"),
        db.CheckConstraint("web_purchase_conversions >= 0", name="ck_google_ads_group_daily_purchase"),
        db.CheckConstraint("conversion_value >= 0", name="ck_google_ads_group_daily_value"),
    )
