"""Vínculos secundarios/primarios entre tickets de Mantenimiento y aparatos.

La fuente operativa legacy tickets.aparato_id continúa vigente en M1.
No crea vínculos automáticamente ni altera el flujo de Tickets V1.
"""

from datetime import datetime, timezone

from app.extensions import db


class TicketAparatoORM(db.Model):
    __tablename__ = "ticket_aparatos"

    ticket_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "tickets.id",
            name="fk_ticket_aparatos_ticket",
            ondelete="CASCADE",
        ),
        primary_key=True,
        nullable=False,
    )
    inventario_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "inventario_general.id",
            name="fk_ticket_aparatos_inventario",
            ondelete="RESTRICT",
        ),
        primary_key=True,
        nullable=False,
    )
    vinculado_en_utc = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=db.func.now(),
    )

    # M4: NULL implica pendiente. El actor y la fecha se actualizan juntos.
    recibido_en_utc = db.Column(db.DateTime(timezone=True), nullable=True)
    recibido_por = db.Column(db.String(100), nullable=True)

    ticket = db.relationship(
        "Ticket",
        back_populates="aparatos_asociados",
    )
    inventario = db.relationship("InventarioGeneral")

    __table_args__ = (
        db.CheckConstraint(
            "(recibido_en_utc IS NULL AND recibido_por IS NULL) OR "
            "(recibido_en_utc IS NOT NULL AND recibido_por IS NOT NULL)",
            name="ck_ticket_aparatos_recepcion_par",
        ),
        db.PrimaryKeyConstraint(
            "ticket_id",
            "inventario_id",
            name="pk_ticket_aparatos",
        ),
        db.Index(
            "ix_ticket_aparatos_inventario_ticket",
            "inventario_id",
            "ticket_id",
        ),
    )
