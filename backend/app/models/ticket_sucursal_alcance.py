"""Branch scope of a BI Vlad request; one ticket, many affected branches."""
from app.extensions import db


class TicketSucursalAlcanceORM(db.Model):
    __tablename__ = "ticket_sucursales_alcance"

    ticket_id = db.Column(
        db.Integer, db.ForeignKey("tickets.id", ondelete="CASCADE"),
        primary_key=True,
    )
    sucursal_id = db.Column(
        db.Integer, db.ForeignKey("sucursales.sucursal_id", ondelete="RESTRICT"),
        primary_key=True,
    )

    ticket = db.relationship("Ticket", back_populates="sucursales_alcance")
    sucursal = db.relationship("Sucursal", foreign_keys=[sucursal_id], lazy="joined")

    __table_args__ = (
        db.Index("ix_ticket_sucursales_alcance_sucursal_id", "sucursal_id"),
    )
