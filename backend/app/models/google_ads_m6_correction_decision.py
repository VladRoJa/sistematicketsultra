"""Append-only independent review of a versioned M6 candidate snapshot."""
from app.extensions import db


class GoogleAdsM6CorrectionDecisionORM(db.Model):
    __tablename__ = "google_ads_m6_correction_decisions"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    case_id = db.Column(
        db.BigInteger,
        db.ForeignKey("google_ads_m6_correction_cases.id", ondelete="RESTRICT"),
        nullable=False, unique=True,
    )
    reviewed_by_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    decision = db.Column(db.String(10), nullable=False)
    snapshot_sha256 = db.Column(db.String(64), nullable=False)
    review_note = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True),
                           nullable=False, server_default=db.func.now())

    __table_args__ = (
        db.CheckConstraint("decision IN ('APPROVED', 'REJECTED')",
                           name="ck_ga_m6_corr_decision"),
        db.CheckConstraint("snapshot_sha256 ~ '^[a-f0-9]{64}$'",
                           name="ck_ga_m6_corr_decision_sha"),
        db.CheckConstraint("length(btrim(review_note)) >= 10",
                           name="ck_ga_m6_corr_review_note"),
        db.Index("ix_ga_m6_corr_decision_reviewer", "reviewed_by_user_id"),
    )
