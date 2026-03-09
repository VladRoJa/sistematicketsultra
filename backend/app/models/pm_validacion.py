#backend\app\models\pm_validacion.py


from datetime import datetime, timezone
from app.extensions import db


class PmValidacionORM(db.Model):
    __tablename__ = "pm_validaciones"

    id = db.Column(db.Integer, primary_key=True)

    bitacora_pm_id = db.Column(
        db.Integer,
        db.ForeignKey("pm_bitacoras.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # "VALIDADO" | "RECHAZADO"
    decision = db.Column(db.String(20), nullable=False)

    motivo = db.Column(db.Text, nullable=True)

    validado_por_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    validado_en = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    bitacora_pm = db.relationship(
        "PmBitacoraORM",
        backref=db.backref("pm_validacion", uselist=False, passive_deletes=True),
    )

    __table_args__ = (
        db.CheckConstraint(
            "decision IN ('VALIDADO', 'RECHAZADO')",
            name="ck_pm_validaciones_decision",
        ),
    )