"""seed evidence-backed safe Campaign V2 tariff overrides

Revision ID: b5d9e2a7c1f4
Revises: a3f7c1d9e5b2
Create Date: 2026-10-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "b5d9e2a7c1f4"
down_revision = "a3f7c1d9e5b2"
branch_labels = None
depends_on = None


_EXPECTED_ROW_COUNT = 113
_REVIEW_ONLY_KEYS = frozenset(('ATLETA 6 MESES', 'SEMANA SLRC $199', 'TARJETA DE REGALO', '3 X 2 MESES POR $998', 'MES REACTIVACION IXTAPALUCA', 'CORTESIA CLASES', '14 MESES POR $7,139', 'ATLETA 12 MESES', '3 X 2 MESES POR $1,198 METEPEC', 'ANUALIDAD CONVENIO $3999', 'SAN VALENTÍN PRIMER MES $299.50', 'PENALIZACIÓN', 'CONVENIO DK FOOD RECURRENTE $499', 'CONVENIO LABORATORIOS DELIA BARRAZA RECURRENTE $499', 'PROMO MARZO ANTICIPADO $649', '6 MESES', 'CONVENIO CARLS JR RECURRENTE $499', 'CONVENIO CCP RECURRENTE $499', 'CONVENIO MOBI MUEBLES RECURRENTE $499', 'CONVENIO YOGUFRUT RECURRENTE $499', 'MES DE REGALO X ANUALIDAD', 'PROMO MEXICALI BSB', 'TARIFA PRUEBA REC'))
_VALID_AUDIENCE_FAMILIES = frozenset({
    "DOMICILIADO",
    "TRIMESTRAL",
    "CONVENIO",
    "SEMESTRE",
    "ESTUDIANTE",
    "MES",
    "OUT_OF_SEGMENT",
})

_SAFE_TARIFF_ROWS = (
    ('MENSUALIDAD CULIACAN', 'MENSUALIDAD CULIACAN', 'Mensualidad', 'DOMICILIADO'),
    ('MEMBRESIA CULIACAN', 'MEMBRESIA CULIACAN', 'Mensualidad', 'DOMICILIADO'),
    ('DOMICILIADO 12 MESES (CON PLAZO)', 'DOMICILIADO 12 MESES (CON PLAZO)', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO 12 MESES $599 METEPEC', 'DOMICILIADO 12 MESES $599 METEPEC', 'Domiciliado', 'DOMICILIADO'),
    ('ANUALIDAD $2,999', 'ANUALIDAD $2,999', 'Anualidad', 'SEMESTRE'),
    ('TRIMESTRE ESTUDIANTE $1,499', 'TRIMESTRE ESTUDIANTE $1,499', 'Trimestre', 'TRIMESTRAL'),
    ('DOMICILIADO 12 MESES $599 PASEO VILLALTA', 'DOMICILIADO 12 MESES $599 PASEO VILLALTA', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO PLAN ULTRA PAGO INCIAL 12 MESES $1,549 HE', 'DOMICILIADO PLAN ULTRA PAGO INCIAL 12 MESES $1,549 HE', 'Domiciliado', 'DOMICILIADO'),
    ('TRIMESTRAL $1,799', 'TRIMESTRAL $1,799', 'Trimestre', 'TRIMESTRAL'),
    ('PREVENTA DOMICILIADO 12 MESES SERRANIA $849', 'PREVENTA DOMICILIADO 12 MESES SERRANIA $849', 'Domiciliado', 'DOMICILIADO'),
    ('RECURRENTE $799 HE', 'RECURRENTE $799 HE', 'Recurrente', 'DOMICILIADO'),
    ('DOMICILIADO SIN PLAZO $699 HE', 'DOMICILIADO SIN PLAZO $699 HE', 'Recurrente', 'DOMICILIADO'),
    ('SEMESTRAL 7 MESES $2,999', 'SEMESTRAL 7 MESES $2,999', 'Semestre', 'SEMESTRE'),
    ('SEMESTRAL MAYO 7 MESES $2,999', 'SEMESTRAL MAYO 7 MESES $2,999', 'Semestre', 'SEMESTRE'),
    ('TRIMESTRAL $1,699', 'TRIMESTRAL $1,699', 'Trimestre', 'TRIMESTRAL'),
    ('TRIMESTRE ESTUDIANTE', 'TRIMESTRE ESTUDIANTE', 'Trimestre', 'TRIMESTRAL'),
    ('ANUALIDAD 13 MESES X $3,999', 'ANUALIDAD 13 MESES X $3,999', 'Anualidad', 'SEMESTRE'),
    ('SEMESTRE $2,999', 'SEMESTRE $2,999', 'Semestre', 'SEMESTRE'),
    ('TRIMESTRE CONVENIO $1,499', 'TRIMESTRE CONVENIO $1,499', 'Trimestre', 'TRIMESTRAL'),
    ('ANUALIDAD $3,999', 'ANUALIDAD $3,999', 'Anualidad', 'SEMESTRE'),
    ('ANUALIDAD + MES REGALO $5,999', 'ANUALIDAD + MES REGALO $5,999', 'Anualidad', 'SEMESTRE'),
    ('PLAN RECURRENTE PAGO INCIAL $1,549 HE', 'PLAN RECURRENTE PAGO INCIAL $1,549 HE', 'Recurrente', 'DOMICILIADO'),
    ('BORRON Y CUENTA NUEVA $999', 'BORRON Y CUENTA NUEVA $999', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO 12 MESES $499 PREVENTA', 'DOMICILIADO 12 MESES $499 PREVENTA', 'Domiciliado', 'DOMICILIADO'),
    ('PREVENTA DOMICILIADO SIN PLAZO SERRANIA $949', 'PREVENTA DOMICILIADO SIN PLAZO SERRANIA $949', 'Recurrente', 'DOMICILIADO'),
    ('PROMO AMIGO CLN', 'PROMO AMIGO CLN', 'Mensualidad', 'DOMICILIADO'),
    ('ANUALIDAD + MES REGALO $6,999', 'ANUALIDAD + MES REGALO $6,999', 'Anualidad', 'SEMESTRE'),
    ('ANUALIDAD PROMO 11 X 14 MESES METEPEC', 'ANUALIDAD PROMO 11 X 14 MESES METEPEC', 'Anualidad', 'SEMESTRE'),
    ('TRIMESTRAL HE $1,899', 'TRIMESTRAL HE $1,899', 'Trimestre', 'TRIMESTRAL'),
    ('BORRON Y CUENTA NUEVA HE 12 MESES', 'BORRON Y CUENTA NUEVA HE 12 MESES', 'Domiciliado', 'DOMICILIADO'),
    ('3 MESES $2,099', '3 MESES $2,099', 'Trimestre', 'TRIMESTRAL'),
    ('1 MES $999', '1 MES $999', 'Mensualidad', 'DOMICILIADO'),
    ('ANUALIDAD $3,999 + DICIEMBRE DE REGALO', 'ANUALIDAD $3,999 + DICIEMBRE DE REGALO', 'Anualidad', 'SEMESTRE'),
    ('ANUALIDAD $4,449', 'ANUALIDAD $4,449', 'Anualidad', 'SEMESTRE'),
    ('DIA', 'DIA', 'Diario', 'DOMICILIADO'),
    ('ANUALIDAD LM', 'ANUALIDAD LM', 'Anualidad', 'SEMESTRE'),
    ('SEMESTRE HE $3,499', 'SEMESTRE HE $3,499', 'Semestre', 'SEMESTRE'),
    ('2 MESES IXTAPALUCA $749', '2 MESES IXTAPALUCA $749', 'Bimestre', 'TRIMESTRAL'),
    ('TRIMESTRAL $1,899', 'TRIMESTRAL $1,899', 'Trimestre', 'TRIMESTRAL'),
    ('ANUALIDAD 14 MESES X $3,999', 'ANUALIDAD 14 MESES X $3,999', 'Anualidad', 'SEMESTRE'),
    ('CONVENIO PLAZA LOMA BONITA $499', 'CONVENIO PLAZA LOMA BONITA $499', 'Convenio', 'CONVENIO'),
    ('ANUALIDAD $4,999', 'ANUALIDAD $4,999', 'Anualidad', 'SEMESTRE'),
    ('ANUALIDAD 3999', 'ANUALIDAD 3999', 'Anualidad', 'SEMESTRE'),
    ('ANUALIDAD PROMO $3,999', 'ANUALIDAD PROMO $3,999', 'Anualidad', 'SEMESTRE'),
    ('3 MESES REACTIVACION IXTAPALUCA', '3 MESES REACTIVACION IXTAPALUCA', 'Trimestre', 'TRIMESTRAL'),
    ('ANUALIDAD PREFERENCIAL $4,999', 'ANUALIDAD PREFERENCIAL $4,999', 'Anualidad', 'SEMESTRE'),
    ('RECURRENTE $749', 'RECURRENTE $749', 'Recurrente', 'DOMICILIADO'),
    ('ANUALIDAD VIP $3999 (VIGENCIA 15 MESES)', 'ANUALIDAD VIP $3999 (VIGENCIA 15 MESES)', 'Anualidad', 'SEMESTRE'),
    ('PREVENTA ANUALIDAD + MES REGALO SERRANIA $10,899', 'PREVENTA ANUALIDAD + MES REGALO SERRANIA $10,899', 'Anualidad', 'SEMESTRE'),
    ('RECURRENTE LANZAMIENTO PAGINA WEB $549 LE', 'RECURRENTE LANZAMIENTO PAGINA WEB $549 LE', 'Recurrente', 'DOMICILIADO'),
    ('SEMESTRAL 7 MESES $3,499', 'SEMESTRAL 7 MESES $3,499', 'Semestre', 'SEMESTRE'),
    ('12 MESES SAN VALENTÍN PRIMER MES $249.50', '12 MESES SAN VALENTÍN PRIMER MES $249.50', 'Domiciliado', 'DOMICILIADO'),
    ('6 MESES SAN VALENTÍN PRIMER MES $274.50', '6 MESES SAN VALENTÍN PRIMER MES $274.50', 'Domiciliado', 'DOMICILIADO'),
    ('SEMESTRAL MAYO 7 MESES $3,499', 'SEMESTRAL MAYO 7 MESES $3,499', 'Semestre', 'SEMESTRE'),
    ('VENTA ESPECIAL BUEN FIN ANUALIDAD X $3,999', 'VENTA ESPECIAL BUEN FIN ANUALIDAD X $3,999', 'Anualidad', 'SEMESTRE'),
    ('DOMICILIADO 12 MESES PLAN FAMILIAR $999 (GRUPAL)', 'DOMICILIADO 12 MESES PLAN FAMILIAR $999 (GRUPAL)', 'Domiciliado', 'DOMICILIADO'),
    ('ANUALIDAD PROMO 11 X 14 MESES PASEO VILLALTA $7,188', 'ANUALIDAD PROMO 11 X 14 MESES PASEO VILLALTA $7,188', 'Anualidad', 'SEMESTRE'),
    ('ULTRA FIT KIDS SIN PLAZO $499', 'ULTRA FIT KIDS SIN PLAZO $499', 'Recurrente', 'DOMICILIADO'),
    ('1RA MENSUALIDAD SANTA C', '1RA MENSUALIDAD SANTA C', 'Mensualidad', 'DOMICILIADO'),
    ('BORRÓN Y CUENTA NUEVA $2,999', 'BORRÓN Y CUENTA NUEVA $2,999', 'Domiciliado', 'DOMICILIADO'),
    ('PREVENTA SEMESTRE PREPAGO SERRANIA $5,399', 'PREVENTA SEMESTRE PREPAGO SERRANIA $5,399', 'Semestre', 'SEMESTRE'),
    ('DOMICILIADO 12 MESES $499 TLALNEPANTLA', 'DOMICILIADO 12 MESES $499 TLALNEPANTLA', 'Domiciliado', 'DOMICILIADO'),
    ('ANUALIDAD PROMO 11 X 14 MESES PASEO VILLALTA', 'ANUALIDAD PROMO 11 X 14 MESES PASEO VILLALTA', 'Anualidad', 'SEMESTRE'),
    ('CORTESIA UN DIA', 'CORTESIA UN DIA', 'Pase de Cortesía', 'DOMICILIADO'),
    ('CONVENIO ESPECIAL', 'CONVENIO ESPECIAL', 'Convenio', 'CONVENIO'),
    ('MENSUAL BTM HIGH SOCIO $499', 'MENSUAL BTM HIGH SOCIO $499', 'Mensualidad', 'DOMICILIADO'),
    ('RECURRENTE LANZAMIENTO PAGINA WEB $649 HE', 'RECURRENTE LANZAMIENTO PAGINA WEB $649 HE', 'Recurrente', 'DOMICILIADO'),
    ('2 X 800', '2 X 800', 'Bimestre', 'TRIMESTRAL'),
    ('MENSUAL BTM LOW SOCIO $449', 'MENSUAL BTM LOW SOCIO $449', 'Mensualidad', 'DOMICILIADO'),
    ('PLAN FAMILIAR RECURRENTE $999 (GRUPAL)', 'PLAN FAMILIAR RECURRENTE $999 (GRUPAL)', 'Recurrente', 'DOMICILIADO'),
    ('ANUALIDAD PROMO $3,500', 'ANUALIDAD PROMO $3,500', 'Anualidad', 'SEMESTRE'),
    ('CONVENIO CEDIS CUCAPA WALDOS 12 MESES $399', 'CONVENIO CEDIS CUCAPA WALDOS 12 MESES $399', 'Convenio', 'CONVENIO'),
    ('CONVENIO PERSAL 2026', 'CONVENIO PERSAL 2026', 'Convenio', 'CONVENIO'),
    ('CONVENIO STEREN 12 MESES $399', 'CONVENIO STEREN 12 MESES $399', 'Convenio', 'CONVENIO'),
    ('ANUALIDAD 2X1 $5999', 'ANUALIDAD 2X1 $5999', 'Anualidad', 'SEMESTRE'),
    ('ANUALIDAD B2B IXTAPALUCA', 'ANUALIDAD B2B IXTAPALUCA', 'Anualidad', 'SEMESTRE'),
    ('ANUALIDAD INSURGENTES 12 X 14 $7,788', 'ANUALIDAD INSURGENTES 12 X 14 $7,788', 'Anualidad', 'SEMESTRE'),
    ('BORRON Y CUENTA NUEVA $999 HE', 'BORRON Y CUENTA NUEVA $999 HE', 'Domiciliado', 'DOMICILIADO'),
    ('CONVENIO BANCO AZTECA 12 MESES $399', 'CONVENIO BANCO AZTECA 12 MESES $399', 'Convenio', 'CONVENIO'),
    ('RECURRENTE $799', 'RECURRENTE $799', 'Recurrente', 'DOMICILIADO'),
    ('ANUALIDAD 2X1 $5999 - LA VIGENCIA DE 24 MESES', 'ANUALIDAD 2X1 $5999 - LA VIGENCIA DE 24 MESES', 'Anualidad', 'SEMESTRE'),
    ('ANUALIDAD ZONA COSTA $4,999', 'ANUALIDAD ZONA COSTA $4,999', 'Anualidad', 'SEMESTRE'),
    ('BORRÓN Y CUENTA NUEVA ANIVERSARIO $649', 'BORRÓN Y CUENTA NUEVA ANIVERSARIO $649', 'Domiciliado', 'DOMICILIADO'),
    ('CONVENIO ALCALDIA $549', 'CONVENIO ALCALDIA $549', 'Convenio', 'CONVENIO'),
    ('CONVENIO DK FOOD 12 MESES $399', 'CONVENIO DK FOOD 12 MESES $399', 'Convenio', 'CONVENIO'),
    ('CONVENIO WORLD LUXURY RESTAURANTS 12 MESES $599', 'CONVENIO WORLD LUXURY RESTAURANTS 12 MESES $599', 'Convenio', 'CONVENIO'),
    ('TRIMESTRAL LANZAMIENTO PAGINA WEB $1,599 HE', 'TRIMESTRAL LANZAMIENTO PAGINA WEB $1,599 HE', 'Trimestre', 'TRIMESTRAL'),
    ('BORRÓN Y CUENTA NUEVA ANIVERSARIO $749', 'BORRÓN Y CUENTA NUEVA ANIVERSARIO $749', 'Domiciliado', 'DOMICILIADO'),
    ('CONVENIO PANAMA 6 MESES $399', 'CONVENIO PANAMA 6 MESES $399', 'Convenio', 'CONVENIO'),
    ('CONVENIO PASTELERIA LETY 12 MESES $399', 'CONVENIO PASTELERIA LETY 12 MESES $399', 'Convenio', 'CONVENIO'),
    ('MENSUALIDAD LM', 'MENSUALIDAD LM', 'Mensualidad', 'DOMICILIADO'),
    ('TRIMESTRAL LANZAMIENTO PAGINA WEB $1,499 LE', 'TRIMESTRAL LANZAMIENTO PAGINA WEB $1,499 LE', 'Trimestre', 'TRIMESTRAL'),
    ('TRIMESTRE BTM HIGH EXTERNO $1,899', 'TRIMESTRE BTM HIGH EXTERNO $1,899', 'Trimestre', 'TRIMESTRAL'),
    ('3 MESES COBACH $1,199', '3 MESES COBACH $1,199', 'Trimestre', 'TRIMESTRAL'),
    ('ANUALIDAD 14 MESES X $5,489', 'ANUALIDAD 14 MESES X $5,489', 'Anualidad', 'SEMESTRE'),
    ('ANUALIDAD CIERRE ENERO', 'ANUALIDAD CIERRE ENERO', 'Anualidad', 'SEMESTRE'),
    ('ANUALIDAD CLN', 'ANUALIDAD CLN', 'Anualidad', 'SEMESTRE'),
    ('ANUALIDAD ESPECIAL', 'ANUALIDAD ESPECIAL', 'Anualidad', 'SEMESTRE'),
    ('BECA EMPLEADO', 'BECA EMPLEADO', 'Beca', 'OUT_OF_SEGMENT'),
    ('COMBO ADULTO - HIJO DOMICILIADO 12 MESES $1,199', 'COMBO ADULTO - HIJO DOMICILIADO 12 MESES $1,199', 'Domiciliado', 'DOMICILIADO'),
    ('CONVENIO CECYTE 12 MESES $399', 'CONVENIO CECYTE 12 MESES $399', 'Convenio', 'CONVENIO'),
    ('CONVENIO CIRCUS PARK 12 MESES $399', 'CONVENIO CIRCUS PARK 12 MESES $399', 'Convenio', 'CONVENIO'),
    ('CONVENIO NATURAL BALANCE 12 MESES $399', 'CONVENIO NATURAL BALANCE 12 MESES $399', 'Convenio', 'CONVENIO'),
    ('CONVENIO NISSAN 12 MESES $399', 'CONVENIO NISSAN 12 MESES $399', 'Convenio', 'CONVENIO'),
    ('CONVENIO PROTEGES 12 MESES $399', 'CONVENIO PROTEGES 12 MESES $399', 'Convenio', 'CONVENIO'),
    ('CONVENIO SUKARNE 12 MESES $399', 'CONVENIO SUKARNE 12 MESES $399', 'Convenio', 'CONVENIO'),
    ('CONVENIO VALDEZ BALUARTE 12 MESES $399', 'CONVENIO VALDEZ BALUARTE 12 MESES $399', 'Convenio', 'CONVENIO'),
    ('DIARIO SANTANDER', 'DIARIO SANTANDER', 'Diario', 'DOMICILIADO'),
    ('DOMICILIADO 6 MESES MAYO HE $699', 'DOMICILIADO 6 MESES MAYO HE $699', 'Domiciliado', 'DOMICILIADO'),
    ('INSCRIPCION 300', 'INSCRIPCION 300', 'Mensualidad', 'DOMICILIADO'),
    ('PROMO ANUALIDAD SAN VALENTIN', 'PROMO ANUALIDAD SAN VALENTIN', 'Anualidad', 'SEMESTRE'),
    ('PROMO SALTILLO 3 MESES', 'PROMO SALTILLO 3 MESES', 'Trimestre', 'TRIMESTRAL'),
    ('RECURRENTE STRILITOS', 'RECURRENTE STRILITOS', 'Recurrente', 'DOMICILIADO'),
)


def _validated_rows() -> list[dict[str, str]]:
    if len(_SAFE_TARIFF_ROWS) != _EXPECTED_ROW_COUNT:
        raise RuntimeError(
            "Campaign V2 inferred safe tariff seed row count mismatch: "
            f"expected {_EXPECTED_ROW_COUNT}, got {len(_SAFE_TARIFF_ROWS)}"
        )

    rows: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    for tarifa_key, tarifa_raw, categoria_tarifa, audience_family in _SAFE_TARIFF_ROWS:
        if not tarifa_key or not tarifa_raw or not categoria_tarifa:
            raise RuntimeError("Campaign V2 inferred safe tariff seed contains an empty value")
        if tarifa_key in _REVIEW_ONLY_KEYS:
            raise RuntimeError(
                f"Review-only tariff must not be seeded automatically: {tarifa_key!r}"
            )
        if tarifa_key in seen_keys:
            raise RuntimeError(
                f"Duplicate Campaign V2 inferred safe tariff key: {tarifa_key!r}"
            )
        if audience_family not in _VALID_AUDIENCE_FAMILIES:
            raise RuntimeError(
                f"Invalid audience family for {tarifa_key!r}: {audience_family!r}"
            )

        seen_keys.add(tarifa_key)
        rows.append(
            {
                "tarifa_key": tarifa_key,
                "tarifa_raw": tarifa_raw,
                "categoria_tarifa": categoria_tarifa,
                "audience_family": audience_family,
            }
        )

    return rows


def upgrade():
    bind = op.get_bind()
    rows = _validated_rows()

    base_keys = set(
        bind.execute(
            sa.text("SELECT tarifa_key FROM marketing_campaign_v2_tariffs")
        ).scalars()
    )
    override_keys = set(
        bind.execute(
            sa.text("SELECT tarifa_key FROM marketing_campaign_v2_tariff_overrides")
        ).scalars()
    )
    existing_keys = base_keys | override_keys

    rows_to_insert = [
        row
        for row in rows
        if row["tarifa_key"] not in existing_keys
    ]
    if not rows_to_insert:
        return

    override_table = sa.table(
        "marketing_campaign_v2_tariff_overrides",
        sa.column("tarifa_key", sa.String(length=255)),
        sa.column("tarifa_raw", sa.String(length=255)),
        sa.column("categoria_tarifa", sa.String(length=100)),
        sa.column("audience_family", sa.String(length=30)),
    )
    op.bulk_insert(override_table, rows_to_insert)


def downgrade():
    bind = op.get_bind()
    override_table = sa.table(
        "marketing_campaign_v2_tariff_overrides",
        sa.column("tarifa_key", sa.String(length=255)),
        sa.column("categoria_tarifa", sa.String(length=100)),
        sa.column("audience_family", sa.String(length=30)),
        sa.column("created_by_user_id", sa.Integer()),
        sa.column("updated_by_user_id", sa.Integer()),
    )

    for row in _validated_rows():
        bind.execute(
            override_table.delete().where(
                sa.and_(
                    override_table.c.tarifa_key == row["tarifa_key"],
                    override_table.c.categoria_tarifa == row["categoria_tarifa"],
                    override_table.c.audience_family == row["audience_family"],
                    override_table.c.created_by_user_id.is_(None),
                    override_table.c.updated_by_user_id.is_(None),
                )
            )
        )
