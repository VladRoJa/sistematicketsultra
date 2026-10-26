"""Inventarios V2 E3: journal append-only de decisiones y efectos oficiales.

Solo tablas/modelos. Ningun endpoint o autorizacion E3 se activa con este modulo.
"""
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import JSONB, UUID
from app.extensions import db


class InventarioCorreccionDecisionORM(db.Model):
    __tablename__ = "inventario_correccion_decisiones"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    solicitud_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "inventario_correccion_solicitudes.id",
            name="fk_inv_corr_decision_solicitud", ondelete="RESTRICT",
        ),
        nullable=False,
    )
    decision = db.Column(db.String(16), nullable=False)
    actor_usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", name="fk_inv_corr_decision_actor", ondelete="RESTRICT"),
        nullable=False,
    )
    decidido_en_utc = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=db.func.now(),
    )
    motivo_decision = db.Column(db.Text, nullable=False)
    resolucion = db.Column(JSONB(none_as_null=True), nullable=True)
    efecto_anterior = db.Column(JSONB(none_as_null=True), nullable=True)
    efecto_posterior = db.Column(JSONB(none_as_null=True), nullable=True)
    idempotency_key = db.Column(UUID(as_uuid=True), nullable=False)
    request_fingerprint = db.Column(db.String(64), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("solicitud_id", name="uq_inv_corr_decision_solicitud"),
        db.UniqueConstraint("id", "solicitud_id", name="uq_inv_corr_decision_par"),
        db.UniqueConstraint(
            "actor_usuario_id", "idempotency_key",
            name="uq_inv_corr_decision_actor_key",
        ),
        db.CheckConstraint(
            "decision IN ('APPROVED', 'REJECTED')",
            name="ck_inv_corr_decision_tipo",
        ),
        db.CheckConstraint(
            "char_length(btrim(motivo_decision)) BETWEEN 10 AND 2000",
            name="ck_inv_corr_decision_motivo",
        ),
        db.CheckConstraint(
            "char_length(request_fingerprint) = 64",
            name="ck_inv_corr_decision_fingerprint",
        ),
        db.Index("ix_inv_corr_decision_actor_fecha", "actor_usuario_id", "decidido_en_utc"),
    )


class InventarioCorreccionAjusteORM(db.Model):
    """Ajuste fisico, no es entrada/salida de movimientos V1."""
    __tablename__ = "inventario_correccion_ajustes"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    decision_id = db.Column(db.BigInteger, nullable=False)
    solicitud_id = db.Column(db.BigInteger, nullable=False)
    inventario_id = db.Column(db.Integer, nullable=False)
    sucursal_id = db.Column(db.Integer, nullable=False)
    stock_anterior = db.Column(db.Integer, nullable=False)
    stock_nuevo = db.Column(db.Integer, nullable=False)
    delta_firmada = db.Column(db.Integer, nullable=False)
    actor_usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", name="fk_inv_corr_ajuste_actor", ondelete="RESTRICT"),
        nullable=False,
    )
    ocurrido_en_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=db.func.now(),
    )
    motivo = db.Column(db.Text, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("decision_id", name="uq_inv_corr_ajuste_decision"),
        db.ForeignKeyConstraint(
            ["decision_id", "solicitud_id"],
            ["inventario_correccion_decisiones.id", "inventario_correccion_decisiones.solicitud_id"],
            name="fk_inv_corr_ajuste_decision_solicitud", ondelete="RESTRICT",
        ),
        db.UniqueConstraint("solicitud_id", name="uq_inv_corr_ajuste_solicitud"),
        db.ForeignKeyConstraint(
            ["inventario_id", "sucursal_id"],
            ["inventario_sucursal.inventario_id", "inventario_sucursal.sucursal_id"],
            name="fk_inv_corr_ajuste_stock_sucursal", ondelete="RESTRICT",
        ),
        db.CheckConstraint(
            "stock_anterior >= 0 AND stock_nuevo >= 0",
            name="ck_inv_corr_ajuste_stock_no_negativo",
        ),
        db.CheckConstraint(
            "stock_anterior + delta_firmada = stock_nuevo",
            name="ck_inv_corr_ajuste_delta",
        ),
        db.CheckConstraint(
            "char_length(btrim(motivo)) >= 10",
            name="ck_inv_corr_ajuste_motivo",
        ),
        db.Index(
            "ix_inv_corr_ajuste_referencia_fecha",
            "inventario_id", "sucursal_id", "ocurrido_en_utc",
        ),
    )


class InventarioCorreccionMaestroAuditORM(db.Model):
    __tablename__ = "inventario_correccion_maestro_auditoria"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    decision_id = db.Column(db.BigInteger, nullable=False)
    solicitud_id = db.Column(db.BigInteger, nullable=False)
    inventario_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "inventario_general.id",
            name="fk_inv_corr_maestro_inventario", ondelete="RESTRICT",
        ), nullable=False,
    )
    campo = db.Column(db.String(64), nullable=False)
    valor_anterior = db.Column(JSONB(none_as_null=True), nullable=True)
    valor_nuevo = db.Column(JSONB(none_as_null=True), nullable=True)
    actor_usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", name="fk_inv_corr_maestro_actor", ondelete="RESTRICT"),
        nullable=False,
    )
    ocurrido_en_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=db.func.now(),
    )
    motivo = db.Column(db.Text, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("decision_id", name="uq_inv_corr_maestro_decision"),
        db.ForeignKeyConstraint(
            ["decision_id", "solicitud_id"],
            ["inventario_correccion_decisiones.id", "inventario_correccion_decisiones.solicitud_id"],
            name="fk_inv_corr_maestro_decision_solicitud", ondelete="RESTRICT",
        ),
        db.UniqueConstraint("solicitud_id", name="uq_inv_corr_maestro_solicitud"),
        db.CheckConstraint(
            "campo IN ('nombre', 'marca', 'codigo_interno', 'no_equipo', "
            "'unidad_medida', 'tipo', 'categoria_inventario_id', 'familia_equipo_id')",
            name="ck_inv_corr_maestro_campo",
        ),
        db.CheckConstraint(
            "char_length(btrim(motivo)) >= 10",
            name="ck_inv_corr_maestro_motivo",
        ),
        db.Index(
            "ix_inv_corr_maestro_referencia_fecha",
            "inventario_id", "ocurrido_en_utc",
        ),
    )


class InventarioCorreccionAltaAuditORM(db.Model):
    """Vinculacion o alta explicita de un hallazgo, no se activa en esta fase."""
    __tablename__ = "inventario_correccion_altas_auditoria"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    decision_id = db.Column(db.BigInteger, nullable=False)
    solicitud_id = db.Column(db.BigInteger, nullable=False)
    inventario_id_resultante = db.Column(
        db.Integer,
        db.ForeignKey(
            "inventario_general.id",
            name="fk_inv_corr_alta_inventario", ondelete="RESTRICT",
        ), nullable=False,
    )
    sucursal_id = db.Column(db.Integer, nullable=False)
    modalidad = db.Column(db.String(16), nullable=False)
    stock_anterior = db.Column(db.Integer, nullable=False)
    stock_nuevo = db.Column(db.Integer, nullable=False)
    actor_usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", name="fk_inv_corr_alta_actor", ondelete="RESTRICT"),
        nullable=False,
    )
    ocurrido_en_utc = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=db.func.now(),
    )
    motivo = db.Column(db.Text, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("decision_id", name="uq_inv_corr_alta_decision"),
        db.ForeignKeyConstraint(
            ["decision_id", "solicitud_id"],
            ["inventario_correccion_decisiones.id", "inventario_correccion_decisiones.solicitud_id"],
            name="fk_inv_corr_alta_decision_solicitud", ondelete="RESTRICT",
        ),
        db.UniqueConstraint("solicitud_id", name="uq_inv_corr_alta_solicitud"),
        db.ForeignKeyConstraint(
            ["inventario_id_resultante", "sucursal_id"],
            ["inventario_sucursal.inventario_id", "inventario_sucursal.sucursal_id"],
            name="fk_inv_corr_alta_stock_sucursal", ondelete="RESTRICT",
        ),
        db.CheckConstraint(
            "modalidad IN ('CREACION', 'VINCULACION')",
            name="ck_inv_corr_alta_modalidad",
        ),
        db.CheckConstraint(
            "stock_anterior >= 0 AND stock_nuevo >= 0",
            name="ck_inv_corr_alta_stock",
        ),
        db.CheckConstraint(
            "char_length(btrim(motivo)) >= 10",
            name="ck_inv_corr_alta_motivo",
        ),
        db.Index(
            "ix_inv_corr_alta_referencia_fecha",
            "inventario_id_resultante", "sucursal_id", "ocurrido_en_utc",
        ),
    )
