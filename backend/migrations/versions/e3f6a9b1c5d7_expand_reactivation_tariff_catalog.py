"""expand reactivation tariff catalog with high-confidence backlog

Revision ID: e3f6a9b1c5d7
Revises: d2e5f8a0b4c6
Create Date: 2026-09-10
"""

from __future__ import annotations

import re
import unicodedata

from alembic import op
import sqlalchemy as sa


revision: str = "e3f6a9b1c5d7"
down_revision: str = "d2e5f8a0b4c6"
branch_labels = None
depends_on = None


_SOURCE = "Suite Ultra - auditoría global cartera 2026-09-10"

# Only high-confidence classifications are included here. Ambiguous weekly,
# daily, scholarship, gift-card, Kids and promotion-only names remain outside
# the catalog until Marketing defines their business rule explicitly.
_TARIFFS = (
    ("MENSUALIDAD CULIACAN", "Mensualidad", "REACTIVATE"),
    ("MEMBRESIA CULIACAN", "Membresía", "REACTIVATE"),
    ("MEMBRESIA LM", "Membresía", "REACTIVATE"),
    ("DOMICILIADO 12 MESES $649 HE", "Domiciliado", "DOMICILIATED_FLOW"),
    ("MENSUALIDAD ESPECIAL", "Mensualidad", "REACTIVATE"),
    ("MEMBRESIA ESPECIAL", "Membresía", "REACTIVATE"),
    ("DOMICILIADO 12 MESES (CON PLAZO)", "Domiciliado", "DOMICILIATED_FLOW"),
    ("DOMICILIADO 12 MESES $599 METEPEC", "Domiciliado", "DOMICILIATED_FLOW"),
    ("PROMO 3 MESES", "Trimestre", "REACTIVATE"),
    ("MENSUALIDAD SL", "Mensualidad", "REACTIVATE"),
    ("CONVENIO DOMICILIADO $549", "Domiciliado", "DOMICILIATED_FLOW"),
    ("RECURRENTE $799 HE", "Recurrente", "DOMICILIATED_FLOW"),
    ("TRIMESTRE ESTUDIANTE", "Estudiante", "REACTIVATE"),
    ("DOMICILIADO PLAN ULTRA PAGO INCIAL 12 MESES $1,549 HE", "Domiciliado", "DOMICILIATED_FLOW"),
    ("DOMICILIADO 12 MESES $599 PASEO VILLALTA", "Domiciliado", "DOMICILIATED_FLOW"),
    ("ATLETA 6 MESES", "Semestre", "REACTIVATE"),
    ("ANUALIDAD SEMPRA", "Anualidad", "REACTIVATE"),
    ("PLAN RECURRENTE PAGO INCIAL $1,549 HE", "Recurrente", "DOMICILIATED_FLOW"),
    ("ANUALIDAD 2X1 $2,999.50", "Anualidad", "REACTIVATE"),
    ("1 MES $999", "Mensualidad", "REACTIVATE"),
    ("3 MESES $2,099", "Trimestre", "REACTIVATE"),
    ("TRIMESTRE ESTUDIANTE $1,499", "Estudiante", "REACTIVATE"),
    ("DOMICILIADO 12 MESES $499 PREVENTA", "Domiciliado", "DOMICILIATED_FLOW"),
    ("DOMICILIADO SIN PLAZO $699 HE", "Recurrente", "DOMICILIATED_FLOW"),
    ("2 MESES IXTAPALUCA $749", "Bimestre", "REACTIVATE"),
    ("DOMICILIADO 12 MESES $399 JULIO", "Domiciliado", "DOMICILIATED_FLOW"),
    ("ANUALIDAD 3999", "Anualidad", "REACTIVATE"),
    ("3 MESES REACTIVACION IXTAPALUCA", "Trimestre", "REACTIVATE"),
    ("ANUALIDAD VIP $3999 (VIGENCIA 15 MESES)", "Anualidad", "REACTIVATE"),
)


def _normalize_tariff_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().upper()
    return re.sub(r"\s+", " ", normalized)


def _rows() -> list[dict[str, object]]:
    return [
        {
            "tarifa_key": _normalize_tariff_key(tarifa_raw),
            "tarifa_raw": tarifa_raw,
            "categoria_tarifa": categoria_tarifa,
            "reactivation_group": reactivation_group,
            "is_active": True,
            "source": _SOURCE,
        }
        for tarifa_raw, categoria_tarifa, reactivation_group in _TARIFFS
    ]


def upgrade():
    tariff_table = sa.table(
        "marketing_reactivation_tariffs",
        sa.column("tarifa_key", sa.String(length=255)),
        sa.column("tarifa_raw", sa.String(length=255)),
        sa.column("categoria_tarifa", sa.String(length=100)),
        sa.column("reactivation_group", sa.String(length=30)),
        sa.column("is_active", sa.Boolean()),
        sa.column("source", sa.String(length=255)),
    )
    op.bulk_insert(tariff_table, _rows())


def downgrade():
    tariff_table = sa.table(
        "marketing_reactivation_tariffs",
        sa.column("tarifa_key", sa.String(length=255)),
        sa.column("source", sa.String(length=255)),
    )
    keys = [_normalize_tariff_key(row[0]) for row in _TARIFFS]
    op.execute(
        tariff_table.delete().where(
            sa.and_(
                tariff_table.c.source == _SOURCE,
                tariff_table.c.tarifa_key.in_(keys),
            )
        )
    )
