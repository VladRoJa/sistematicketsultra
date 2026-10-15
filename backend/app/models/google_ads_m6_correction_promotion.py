"""Append-only link: approved candidate decision -> canonical M6 publication."""
from app.extensions import db


class GoogleAdsM6CorrectionPromotionORM(db.Model):
    __tablename__ = "google_ads_m6_correction_promotions"
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    case_id = db.Column(
        db.BigInteger, db.ForeignKey("google_ads_m6_correction_cases.id",
                                     ondelete="RESTRICT"),
        nullable=False, unique=True,
    )
    publication_id = db.Column(
        db.BigInteger, db.ForeignKey("google_ads_m6_daily_publications.id",
                                     ondelete="RESTRICT"),
        nullable=False, unique=True,
    )
    decision_id = db.Column(
        db.BigInteger, db.ForeignKey("google_ads_m6_correction_decisions.id",
                                     ondelete="RESTRICT"),
        nullable=False, unique=True,
    )
    superseded_publication_id = db.Column(
        db.BigInteger, db.ForeignKey("google_ads_m6_daily_publications.id",
                                     ondelete="RESTRICT"),
        nullable=True,
    )
    promoted_by_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    snapshot_sha256 = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           server_default=db.func.now())

    __table_args__ = (
        db.CheckConstraint("snapshot_sha256 ~ '^[a-f0-9]{64}$'",
                           name="ck_ga_m6_corr_promotion_sha"),
        db.CheckConstraint("publication_id <> superseded_publication_id",
                           name="ck_ga_m6_corr_promotion_distinct"),
    )
