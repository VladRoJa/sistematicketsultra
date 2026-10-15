"""M6 Google Ads: versioned, explicitly approved branch identity continuity.

M5 historical mappings remain immutable. These approvals are independent of
subsequent daily Warehouse uploads; each fact retains its own upload provenance.
No automatic identity inference or approval is performed by these models.
"""
from __future__ import annotations

from app.extensions import db


class GoogleAdsBranchApprovalVersionORM(db.Model):
    __tablename__ = "google_ads_branch_approval_versions"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    customer_id = db.Column(db.String(10), nullable=False)
    approval_reference = db.Column(db.String(255), nullable=False)
    source_approval_reference = db.Column(db.String(255), nullable=False)
    valid_from = db.Column(db.Date, nullable=False)
    valid_to = db.Column(db.Date, nullable=True)
    source_campaign_upload_id = db.Column(
        db.Integer,
        db.ForeignKey("warehouse_uploads.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_ad_group_upload_id = db.Column(
        db.Integer,
        db.ForeignKey("warehouse_uploads.id", ondelete="RESTRICT"),
        nullable=False,
    )
    approved_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    approved_on = db.Column(db.Date, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=db.func.now(),
    )

    __table_args__ = (
        db.UniqueConstraint(
            "customer_id", "approval_reference",
            name="uq_ga_m6_approval_reference",
        ),
        db.UniqueConstraint(
            "customer_id", "valid_from",
            name="uq_ga_m6_approval_start",
        ),
        db.CheckConstraint(
            "customer_id ~ '^[0-9]{10}$'",
            name="ck_ga_m6_approval_customer",
        ),
        db.CheckConstraint(
            "valid_to IS NULL OR valid_from <= valid_to",
            name="ck_ga_m6_approval_dates",
        ),
        db.CheckConstraint(
            "source_campaign_upload_id <> source_ad_group_upload_id",
            name="ck_ga_m6_distinct_sources",
        ),
        db.CheckConstraint(
            "length(btrim(approval_reference)) > 0",
            name="ck_ga_m6_approval_reference",
        ),
        db.CheckConstraint(
            "length(btrim(source_approval_reference)) > 0",
            name="ck_ga_m6_approval_origin",
        ),
        db.Index(
            "ix_ga_m6_approval_customer_dates",
            "customer_id", "valid_from", "valid_to",
        ),
    )


class GoogleAdsBranchApprovedIdentityORM(db.Model):
    __tablename__ = "google_ads_branch_approved_identities"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    approval_version_id = db.Column(
        db.BigInteger,
        db.ForeignKey("google_ads_branch_approval_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    campaign_key = db.Column(db.String(80), nullable=False)
    ad_group_key = db.Column(db.String(80), nullable=False)
    sucursal_canon = db.Column(
        db.Text,
        db.ForeignKey("track_branch_catalog.sucursal_canon", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=db.func.now(),
    )

    __table_args__ = (
        db.UniqueConstraint(
            "approval_version_id", "campaign_key", "ad_group_key",
            name="uq_ga_m6_version_identity",
        ),
        db.CheckConstraint(
            "campaign_key ~ '^name:[a-f0-9]{64}$'",
            name="ck_ga_m6_campaign_key",
        ),
        db.CheckConstraint(
            "ad_group_key ~ '^name:[a-f0-9]{64}$'",
            name="ck_ga_m6_ad_group_key",
        ),
        db.Index(
            "ix_ga_m6_identity_version_branch",
            "approval_version_id", "sucursal_canon",
        ),
    )
