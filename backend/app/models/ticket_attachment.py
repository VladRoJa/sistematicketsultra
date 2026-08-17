from datetime import datetime, timezone

from app.extensions import db


class TicketAttachmentORM(db.Model):
    """
    Metadata persistente de archivos adjuntos a tickets.

    El archivo físico vive fuera de PostgreSQL.
    Esta fila permanece incluso después de que el archivo haya sido eliminado
    por la política de retención.
    """

    __tablename__ = "ticket_attachments"

    id = db.Column(
        db.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    ticket_id = db.Column(
        db.Integer,
        db.ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    original_filename = db.Column(
        db.String(255),
        nullable=False,
    )

    storage_key = db.Column(
        db.String(500),
        nullable=False,
        unique=True,
    )

    mime_type = db.Column(
        db.String(100),
        nullable=False,
    )

    size_bytes = db.Column(
        db.BigInteger,
        nullable=False,
    )

    width = db.Column(
        db.Integer,
        nullable=True,
    )

    height = db.Column(
        db.Integer,
        nullable=True,
    )

    sha256 = db.Column(
        db.String(64),
        nullable=False,
    )

    optimization_mode = db.Column(
        db.String(32),
        nullable=False,
        default="original",
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    emailed_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    delete_after = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    deleted_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        db.Index(
            "ix_ticket_attachments_cleanup",
            "deleted_at",
            "delete_after",
        ),
    )
