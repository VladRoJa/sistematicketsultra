from app.extensions import db


class FamiliaEquipoORM(db.Model):
    __tablename__ = "familia_equipo"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(40), nullable=False)
    nombre = db.Column(db.String(120), nullable=False)
    categoria_inventario_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "catalogo_categoria_inventario.id",
            name="fk_familia_equipo_categoria_inventario",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    activo = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=db.text("true"),
    )
    creado_en = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
    )
    actualizado_en = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
        onupdate=db.func.now(),
    )

    categoria_inventario = db.relationship(
        "CategoriaInventario",
        foreign_keys=[categoria_inventario_id],
    )
    fallas = db.relationship(
        "FallaMantenimientoORM",
        back_populates="familia",
        order_by="FallaMantenimientoORM.orden",
    )

    __table_args__ = (
        db.UniqueConstraint("key", name="uq_familia_equipo_key"),
        db.Index(
            "ix_familia_equipo_categoria_inventario_id",
            "categoria_inventario_id",
        ),
        db.Index("ix_familia_equipo_activo", "activo"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "key": self.key,
            "nombre": self.nombre,
            "categoria_inventario_id": self.categoria_inventario_id,
            "activo": bool(self.activo),
        }


class FallaMantenimientoORM(db.Model):
    __tablename__ = "falla_mantenimiento"

    id = db.Column(db.Integer, primary_key=True)
    familia_equipo_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "familia_equipo.id",
            name="fk_falla_mantenimiento_familia_equipo",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    key = db.Column(db.String(120), nullable=False)
    nombre = db.Column(db.String(180), nullable=False)
    activo = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=db.text("true"),
    )
    orden = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default=db.text("0"),
    )
    creado_en = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
    )
    actualizado_en = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=db.func.now(),
        onupdate=db.func.now(),
    )

    familia = db.relationship(
        "FamiliaEquipoORM",
        back_populates="fallas",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "familia_equipo_id",
            "key",
            name="uq_falla_mantenimiento_familia_key",
        ),
        db.Index(
            "ix_falla_mantenimiento_familia_activo_orden",
            "familia_equipo_id",
            "activo",
            "orden",
        ),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "familia_equipo_id": self.familia_equipo_id,
            "key": self.key,
            "nombre": self.nombre,
            "activo": bool(self.activo),
            "orden": self.orden,
        }
