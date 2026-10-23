"""Inventarios V2 E2: propuestas persistentes; no mutan el inventario oficial.

E2 registra evidencia y valores observados. Aprobar/aplicar son funciones de E3.
"""
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.extensions import db


class InventarioSolicitudCorreccionORM(db.Model):
    __tablename__ = "inventario_correccion_solicitudes"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    tipo = db.Column(db.String(40), nullable=False)
    estado = db.Column(
        db.String(24),
        nullable=False,
        default="PENDING",
        server_default="PENDING",
    )
    sucursal_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "sucursales.sucursal_id",
            name="fk_inv_corr_solicitudes_sucursal",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    inventario_id = db.Column(db.Integer, nullable=True)
    campo = db.Column(db.String(64), nullable=True)
    valor_original = db.Column(JSONB, nullable=True)
    valor_propuesto = db.Column(JSONB, nullable=True)
    hallazgo_provisional = db.Column(JSONB, nullable=True)
    baseline_canonico = db.Column(JSONB, nullable=False)
    fecha_observacion_local = db.Column(db.Date, nullable=True)
    motivo = db.Column(db.Text, nullable=False)
    evidencia_descriptiva = db.Column(db.Text, nullable=True)
    creado_por_usuario_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            name="fk_inv_corr_solicitudes_creador",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    creado_en_utc = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=db.func.now(),
    )
    idempotency_key = db.Column(UUID(as_uuid=True), nullable=False)
    request_fingerprint = db.Column(db.String(64), nullable=False)

    __table_args__ = (
        # La unicidad existente del par en inventario_sucursal permite
        # impedir referencias cruzadas a otra sucursal directamente en DB.
        # Para UNREGISTERED_FIND inventario_id es NULL y la FK compuesta
        # no se comprueba (MATCH SIMPLE); sucursal_id sigue teniendo FK propia.
        db.ForeignKeyConstraint(
            ["inventario_id", "sucursal_id"],
            ["inventario_sucursal.inventario_id", "inventario_sucursal.sucursal_id"],
            name="fk_inv_corr_solicitudes_stock_sucursal",
            ondelete="RESTRICT",
        ),
        db.CheckConstraint(
            "tipo IN ('MASTER_FIELD', 'QUANTITY_DIFFERENCE', "
            "'NOT_LOCATED', 'UNREGISTERED_FIND')",
            name="ck_inv_corr_solicitudes_tipo",
        ),
        db.CheckConstraint(
            "estado IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_inv_corr_solicitudes_estado",
        ),
        db.CheckConstraint(
            "("
            "tipo = 'UNREGISTERED_FIND' AND inventario_id IS NULL "
            "AND hallazgo_provisional IS NOT NULL AND campo IS NULL"
            ") OR ("
            "tipo <> 'UNREGISTERED_FIND' AND inventario_id IS NOT NULL "
            "AND hallazgo_provisional IS NULL"
            ")",
            name="ck_inv_corr_solicitudes_identidad",
        ),
        db.CheckConstraint(
            "(tipo = 'MASTER_FIELD' AND campo IS NOT NULL AND valor_propuesto IS NOT NULL) "
            "OR (tipo <> 'MASTER_FIELD' AND campo IS NULL)",
            name="ck_inv_corr_solicitudes_campo",
        ),
        db.CheckConstraint(
            "char_length(btrim(motivo)) BETWEEN 10 AND 2000",
            name="ck_inv_corr_solicitudes_motivo",
        ),
        db.CheckConstraint(
            "char_length(request_fingerprint) = 64",
            name="ck_inv_corr_solicitudes_fingerprint",
        ),
        db.UniqueConstraint(
            "creado_por_usuario_id",
            "idempotency_key",
            name="uq_inv_corr_solicitudes_actor_idempotencia",
        ),
        db.Index(
            "ix_inv_corr_solicitudes_sucursal_estado_fecha",
            "sucursal_id",
            "estado",
            "creado_en_utc",
        ),
        db.Index(
            "ix_inv_corr_solicitudes_inventario_estado",
            "inventario_id",
            "estado",
        ),
        db.Index(
            "ix_inv_corr_solicitudes_creador_fecha",
            "creado_por_usuario_id",
            "creado_en_utc",
        ),
    )
