from app.extensions import db


class IventasTemplateUploadORM(db.Model):
    __tablename__ = "marketing_iventas_template_uploads"

    id = db.Column(db.Integer, primary_key=True)
    requested_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())
    status = db.Column(db.String(20), nullable=False, index=True)
    template = db.Column(db.JSON, nullable=False)
    branches = db.Column(db.JSON, nullable=False)
    image = db.Column(db.LargeBinary)
    image_type = db.Column(db.String(20))
    next_review_at = db.Column(db.DateTime(timezone=True), index=True)
