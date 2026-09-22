# backend/app/models/pm_bitacora.py

from datetime import datetime, timezone

from app.extensions import db


class PmBitacoraORM(db.Model):
    __tablename__ = "pm_bitacoras"

    id = db.Column(db.Integer, primary_key=True)

    # Nuevas ejecuciones preventivas nacen de un Ticket real. Nullable para
    # conservar todo el histórico del PM legacy.
    ticket_id = db.Column(
        db.Integer,
        db.ForeignKey("tickets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    inventario_id = db.Column(
        db.Integer,
        db.ForeignKey("inventario_general.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    target_type = db.Column(
        db.String(20),
        nullable=False,
        default="EQUIPO",
        server_default="EQUIPO",
    )
    building_element_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "maintenance_building_elements.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
        index=True,
    )

    sucursal_id = db.Column(
        db.Integer,
        db.ForeignKey("sucursales.sucursal_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    fecha = db.Column(db.Date, nullable=False, index=True)

    resultado = db.Column(db.String(20), nullable=False)

    tipo_mantenimiento = db.Column(db.String(20), nullable=True)

    notas = db.Column(db.Text, nullable=True)

    estado_encontrado = db.Column(db.String(30), nullable=True)
    hallazgo_detectado = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=db.text("false"),
    )
    hallazgo_descripcion = db.Column(db.Text, nullable=True)

    checks = db.Column(db.JSON, nullable=False, default=dict)

    # Snapshot inmutable del procedimiento vigente al ejecutar. Evita que
    # cambios futuros de etiquetas/orden reescriban visualmente el histórico.
    checklist_snapshot = db.Column(db.JSON, nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    ticket = db.relationship(
        "Ticket",
        foreign_keys=[ticket_id],
        backref="pm_bitacoras_ticket",
    )
    building_element = db.relationship(
        "MaintenanceBuildingElementORM",
        foreign_keys=[building_element_id],
    )

    __table_args__ = (
        db.CheckConstraint(
            "resultado IN ('OK', 'FALLA', 'OBS')",
            name="ck_pm_bitacoras_resultado",
        ),
        db.CheckConstraint(
            "tipo_mantenimiento IN ('PREVENTIVO', 'CORRECTIVO', 'ESTETICO', 'MEJORA')",
            name="ck_pm_bitacoras_tipo_mantenimiento",
        ),
        db.CheckConstraint(
            "estado_encontrado IS NULL OR estado_encontrado IN "
            "('BUENO', 'REQUIERE_ATENCION', 'FUERA_SERVICIO')",
            name="ck_pm_bitacoras_estado_encontrado",
        ),
        db.CheckConstraint(
            "target_type IN ('EQUIPO', 'EDIFICIO')",
            name="ck_pm_bitacoras_target_type",
        ),
        db.CheckConstraint(
            "((target_type = 'EQUIPO' AND inventario_id IS NOT NULL "
            "AND building_element_id IS NULL) OR "
            "(target_type = 'EDIFICIO' AND inventario_id IS NULL "
            "AND building_element_id IS NOT NULL))",
            name="ck_pm_bitacoras_target_reference",
        ),
        db.Index(
            "ix_pm_bitacoras_ticket_created",
            "ticket_id",
            "created_at",
        ),
    )