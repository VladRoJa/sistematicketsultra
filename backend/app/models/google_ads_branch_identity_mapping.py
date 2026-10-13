"""Approved provisional Google Ads campaign/group → Suite branch identities.

M5 schema only: rows are never created from group names implicitly.
The future attribution reader must also validate branch activity,
upload provenance, account scope, coverage, and reconciliation.
"""
from __future__ import annotations

from app.extensions import db


class GoogleAdsBranchIdentityMappingORM(db.Model):
    __tablename__ = "google_ads_branch_identity_mappings"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    customer_id = db.Column(db.String(10), nullable=False)
    campaign_key = db.Column(db.String(80), nullable=False)
    ad_group_key = db.Column(db.String(80), nullable=False)
    sucursal_canon = db.Column(
        db.Text,
        db.ForeignKey("track_branch_catalog.sucursal_canon", ondelete="RESTRICT"),
        nullable=False,
    )
    source_upload_id = db.Column(
        db.Integer,
        db.ForeignKey("warehouse_uploads.id", ondelete="RESTRICT"),
        nullable=False,
    )
    valid_from = db.Column(db.Date, nullable=False)
    valid_to = db.Column(db.Date, nullable=False)
    approval_status = db.Column(db.String(40), nullable=False)
    approval_reference = db.Column(db.String(255), nullable=False)
    approved_on = db.Column(db.Date, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(),
        nullable=False,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "customer_id", "campaign_key", "ad_group_key",
            name="uq_google_ads_m5_identity",
        ),
        db.CheckConstraint(
            "customer_id ~ '^[0-9]{10}$'",
            name="ck_google_ads_m5_customer",
        ),
        db.CheckConstraint(
            "campaign_key ~ '^name:[a-f0-9]{64}$'",
            name="ck_google_ads_m5_campaign_key",
        ),
        db.CheckConstraint(
            "ad_group_key ~ '^name:[a-f0-9]{64}$'",
            name="ck_google_ads_m5_ad_group_key",
        ),
        db.CheckConstraint(
            "valid_from <= valid_to",
            name="ck_google_ads_m5_valid_dates",
        ),
        db.CheckConstraint(
            "approval_status = 'APPROVED_PROVISIONAL_XLSX'",
            name="ck_google_ads_m5_provisional",
        ),
        db.CheckConstraint(
            "length(btrim(approval_reference)) > 0",
            name="ck_google_ads_m5_approval_ref",
        ),
        db.Index(
            "ix_google_ads_m5_branch_dates",
            "sucursal_canon", "valid_from", "valid_to",
        ),
        db.Index(
            "ix_google_ads_m5_customer_dates",
            "customer_id", "valid_from", "valid_to",
        ),
    )
