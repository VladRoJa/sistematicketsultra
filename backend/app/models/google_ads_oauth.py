"""Encrypted, single-account Google Ads OAuth grant for Suite Ultra.

Refresh tokens never appear in API responses or application logs.
The single row records the configured target account; Google Ads API access
to that account must still be independently verified before any ingestion.
"""

from app.extensions import db


class GoogleAdsOAuthCredentialORM(db.Model):
    __tablename__ = "google_ads_oauth_credentials"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.String(16), nullable=False)
    encrypted_refresh_token = db.Column(db.Text, nullable=False)
    authorized_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
        onupdate=db.func.now(),
    )

    __table_args__ = (
        db.CheckConstraint("id = 1", name="ck_google_ads_oauth_single_grant"),
    )
