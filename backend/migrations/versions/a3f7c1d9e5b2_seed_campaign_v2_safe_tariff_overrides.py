"""seed safe Campaign V2 tariff overrides from approved catalog

Revision ID: a3f7c1d9e5b2
Revises: d8e4b1a6c2f9
Create Date: 2026-10-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "a3f7c1d9e5b2"
down_revision = "d8e4b1a6c2f9"
branch_labels = None
depends_on = None


_EXPECTED_ROW_COUNT = 198
_EXCLUDED_CONFLICT_KEYS = frozenset(('SEMANA SLRC $199', 'TARJETA DE REGALO', 'TRIMESTRE NAVIDAD'))
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
    ('$349 ATLETA CAR/COBACH ROSARITO', '$349 ATLETA CAR/COBACH ROSARITO', 'Convenio', 'CONVENIO'),
    ('1 DIA', '1 DIA', 'Diario', 'DOMICILIADO'),
    ('1 MES $899', '1 MES $899', 'Mensualidad', 'DOMICILIADO'),
    ('1 MES EN LINEA $699', '1 MES EN LINEA $699', 'Mensualidad', 'DOMICILIADO'),
    ('12 MESES EN LINEA $5,490', '12 MESES EN LINEA $5,490', 'Anualidad', 'SEMESTRE'),
    ('2 DIAS CORTESIA', '2 DIAS CORTESIA', 'Pase de Cortesía', 'DOMICILIADO'),
    ('2 MESES', '2 MESES', 'Bimestre', 'TRIMESTRAL'),
    ('2 MESES PROMO', '2 MESES PROMO', 'Bimestre', 'TRIMESTRAL'),
    ('2 MESES X $ 1250', '2 MESES X $ 1250', 'Bimestre', 'TRIMESTRAL'),
    ('3 MESES', '3 MESES', 'Trimestre', 'TRIMESTRAL'),
    ('3 MESES $1,899', '3 MESES $1,899', 'Trimestre', 'TRIMESTRAL'),
    ('3 MESES ANIVERSARIO $1499 EN SUCURSAL', '3 MESES ANIVERSARIO $1499 EN SUCURSAL', 'Trimestre', 'TRIMESTRAL'),
    ('3 MESES EN LINEA', '3 MESES EN LINEA', 'Trimestre', 'TRIMESTRAL'),
    ('3 MESES EN MOSTRADOR $1,699', '3 MESES EN MOSTRADOR $1,699', 'Trimestre', 'TRIMESTRAL'),
    ('3 MESES PROMO', '3 MESES PROMO', 'Trimestre', 'TRIMESTRAL'),
    ('3 MESES X $1,690 1 MES DE REGALO', '3 MESES X $1,690 1 MES DE REGALO', 'Trimestre', 'TRIMESTRAL'),
    ('3 MESES X 1490 PROMO ENE 24', '3 MESES X 1490 PROMO ENE 24', 'Trimestre', 'TRIMESTRAL'),
    ('3 MESES X 1690 PROMO ENE 24', '3 MESES X 1690 PROMO ENE 24', 'Trimestre', 'TRIMESTRAL'),
    ('3 MESES X1290', '3 MESES X1290', 'Trimestre', 'TRIMESTRAL'),
    ('399 HOT SALE', '399 HOT SALE', 'Recurrente', 'DOMICILIADO'),
    ('50% 1ER MES + INSCRIPCIÓN SIN PLAZO (TOTAL PRIMER PAGO: $549.50)', '50% 1ER MES + INSCRIPCIÓN SIN PLAZO (TOTAL PRIMER PAGO: $549.50)', 'Recurrente', 'DOMICILIADO'),
    ('50% 1ER MES + INSCRIPCIÓN X 12 MESES (TOTAL PRIMER PAGO: $499.50)', '50% 1ER MES + INSCRIPCIÓN X 12 MESES (TOTAL PRIMER PAGO: $499.50)', 'Domiciliado', 'DOMICILIADO'),
    ('50% 1ER MES + INSCRIPCIÓN X 6 MESES (TOTAL PRIMER PAGO: $524.50)', '50% 1ER MES + INSCRIPCIÓN X 6 MESES (TOTAL PRIMER PAGO: $524.50)', 'Domiciliado', 'DOMICILIADO'),
    ('50% 1ER MES 12 MESES $499', '50% 1ER MES 12 MESES $499', 'Domiciliado', 'DOMICILIADO'),
    ('50% 1ER MES 6 MESES $549', '50% 1ER MES 6 MESES $549', 'Domiciliado', 'DOMICILIADO'),
    ('50% 1ER MES 60+ 12 MESES', '50% 1ER MES 60+ 12 MESES', 'Domiciliado', 'DOMICILIADO'),
    ('50% 1ER MES 60+ 6 MESES', '50% 1ER MES 60+ 6 MESES', 'Domiciliado', 'DOMICILIADO'),
    ('50% 1ER MES 60+ SIN PLAZO', '50% 1ER MES 60+ SIN PLAZO', 'Recurrente', 'DOMICILIADO'),
    ('50% 1ER MES SIN PLAZO $599', '50% 1ER MES SIN PLAZO $599', 'Recurrente', 'DOMICILIADO'),
    ('ANUALIDAD', 'ANUALIDAD', 'Anualidad', 'SEMESTRE'),
    ('ANUALIDAD 2024', 'ANUALIDAD 2024', 'Anualidad', 'SEMESTRE'),
    ('ANUALIDAD 2X1 $2,999.50', 'ANUALIDAD 2X1 $2,999.50', 'Anualidad', 'SEMESTRE'),
    ('ANUALIDAD 2X1 $2,999.50 - LA VIGENCIA DE 12 MESES', 'ANUALIDAD 2X1 $2,999.50 - LA VIGENCIA DE 12 MESES', 'Anualidad', 'SEMESTRE'),
    ('ANUALIDAD DE $4,999.00 3 MESES DE REGALO', 'ANUALIDAD DE $4,999.00 3 MESES DE REGALO', 'Anualidad', 'SEMESTRE'),
    ('ANUALIDAD EN LINEA', 'ANUALIDAD EN LINEA', 'Anualidad', 'SEMESTRE'),
    ('ANUALIDAD EN MOSTRADOR $5,999', 'ANUALIDAD EN MOSTRADOR $5,999', 'Anualidad', 'SEMESTRE'),
    ('ANUALIDAD LB', 'ANUALIDAD LB', 'Anualidad', 'SEMESTRE'),
    ('ANUALIDAD PROMO', 'ANUALIDAD PROMO', 'Anualidad', 'SEMESTRE'),
    ('ANUALIDAD SEMPRA', 'ANUALIDAD SEMPRA', 'Anualidad', 'SEMESTRE'),
    ('BECA', 'BECA', 'Beca', 'OUT_OF_SEGMENT'),
    ('BECA 1 DIAS', 'BECA 1 DIAS', 'Beca', 'OUT_OF_SEGMENT'),
    ('BECA 6 MESES', 'BECA 6 MESES', 'Beca', 'OUT_OF_SEGMENT'),
    ('BORRON 12 MESES PRIMER MES $699 (449 + 250)', 'BORRON 12 MESES PRIMER MES $699 (449 + 250)', 'Domiciliado', 'DOMICILIADO'),
    ('BORRON 6 MESES PRIMER MES 699 (449 + 250)', 'BORRON 6 MESES PRIMER MES 699 (449 + 250)', 'Domiciliado', 'DOMICILIADO'),
    ('BORRON Y CUENTA NUEVA 12 MESES', 'BORRON Y CUENTA NUEVA 12 MESES', 'Domiciliado', 'DOMICILIADO'),
    ('BORRON Y CUENTA NUEVA 12 MESES $499', 'BORRON Y CUENTA NUEVA 12 MESES $499', 'Domiciliado', 'DOMICILIADO'),
    ('BORRON Y CUENTA NUEVA 6 MESES', 'BORRON Y CUENTA NUEVA 6 MESES', 'Domiciliado', 'DOMICILIADO'),
    ('BORRON Y CUENTA NUEVA SIN PLAZO $649', 'BORRON Y CUENTA NUEVA SIN PLAZO $649', 'Domiciliado', 'DOMICILIADO'),
    ('BORRON Y CUENTA NUEVA TDC 12 MESES', 'BORRON Y CUENTA NUEVA TDC 12 MESES', 'Domiciliado', 'DOMICILIADO'),
    ('BORRON Y CUENTA NUEVA TDC 6 MESES', 'BORRON Y CUENTA NUEVA TDC 6 MESES', 'Domiciliado', 'DOMICILIADO'),
    ('BORRON Y CUENTA NUEVA TDC SIN PLAZO', 'BORRON Y CUENTA NUEVA TDC SIN PLAZO', 'Recurrente', 'DOMICILIADO'),
    ('BORRÓN Y CUENTA NUEVA ABRIL', 'BORRÓN Y CUENTA NUEVA ABRIL', 'Domiciliado', 'DOMICILIADO'),
    ('BORRÓN Y CUENTA NUEVA MAYO $649', 'BORRÓN Y CUENTA NUEVA MAYO $649', 'Domiciliado', 'DOMICILIADO'),
    ('BORRÓN Y CUENTA NUEVA SIN PLAZO', 'BORRÓN Y CUENTA NUEVA SIN PLAZO', 'Recurrente', 'DOMICILIADO'),
    ('BUEN FIT PAGO EN LÍNEA 3 MESES X $1350', 'BUEN FIT PAGO EN LÍNEA 3 MESES X $1350', 'Trimestre', 'TRIMESTRAL'),
    ('BUEN FIT PAGO EN LÍNEA ANUALIDAD X $3999', 'BUEN FIT PAGO EN LÍNEA ANUALIDAD X $3999', 'Anualidad', 'SEMESTRE'),
    ('COBACH $399', 'COBACH $399', 'Estudiante', 'ESTUDIANTE'),
    ('CONVENIO', 'CONVENIO', 'Convenio', 'CONVENIO'),
    ('CONVENIO $599', 'CONVENIO $599', 'Convenio', 'CONVENIO'),
    ('CONVENIO DOMICILIADO $549', 'CONVENIO DOMICILIADO $549', 'Convenio', 'CONVENIO'),
    ('CONVENIO EMPRESAS', 'CONVENIO EMPRESAS', 'Convenio', 'CONVENIO'),
    ('CONVENIO PERSAL 6 MESES', 'CONVENIO PERSAL 6 MESES', 'Convenio', 'CONVENIO'),
    ('CONVENIO PROMO NOVIEMBRE $599', 'CONVENIO PROMO NOVIEMBRE $599', 'Convenio', 'CONVENIO'),
    ('CONVENIOS $549', 'CONVENIOS $549', 'Convenio', 'CONVENIO'),
    ('CORTESIA 30 DIAS', 'CORTESIA 30 DIAS', 'Mensualidad', 'DOMICILIADO'),
    ('CORTESIA DIARIA', 'CORTESIA DIARIA', 'Pase de Cortesía', 'DOMICILIADO'),
    ('CORTESIA MENSUAL 1', 'CORTESIA MENSUAL 1', 'Pase de Cortesía', 'DOMICILIADO'),
    ('CUPON 1ER MES', 'CUPON 1ER MES', 'Mensualidad', 'DOMICILIADO'),
    ('DIARIO', 'DIARIO', 'Diario', 'DOMICILIADO'),
    ('DIARIO $100', 'DIARIO $100', 'Diario', 'DOMICILIADO'),
    ('DIARIO $130', 'DIARIO $130', 'Diario', 'DOMICILIADO'),
    ('DIARIO A DOMICILIADO 12 MESES', 'DIARIO A DOMICILIADO 12 MESES', 'Domiciliado', 'DOMICILIADO'),
    ('DIARIO LM', 'DIARIO LM', 'Diario', 'DOMICILIADO'),
    ('DIARIO NUEVO', 'DIARIO NUEVO', 'Diario', 'DOMICILIADO'),
    ('DIARIO TOTAL PASS', 'DIARIO TOTAL PASS', 'Agregadora', 'OUT_OF_SEGMENT'),
    ('DICIEMBRE GRATIS', 'DICIEMBRE GRATIS', 'Mensualidad', 'DOMICILIADO'),
    ('DOMICILIADO $449 6 MESES BUENFIT', 'DOMICILIADO $449 6 MESES BUENFIT', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO $549 3 MESES BUENFIT', 'DOMICILIADO $549 3 MESES BUENFIT', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO 12 MESES $399 JULIO', 'DOMICILIADO 12 MESES $399 JULIO', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO 12 MESES $449 (LOS 12 MESES)', 'DOMICILIADO 12 MESES $449 (LOS 12 MESES)', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO 12 MESES $499', 'DOMICILIADO 12 MESES $499', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO 12 MESES $549 ABRIL 2026', 'DOMICILIADO 12 MESES $549 ABRIL 2026', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO 12 MESES $549 LE', 'DOMICILIADO 12 MESES $549 LE', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO 12 MESES $549 MARZO 2026', 'DOMICILIADO 12 MESES $549 MARZO 2026', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO 12 MESES $649 HE', 'DOMICILIADO 12 MESES $649 HE', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO 12 MESES + 250 INSCRIPCIÓN 2DO MES GRATIS', 'DOMICILIADO 12 MESES + 250 INSCRIPCIÓN 2DO MES GRATIS', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO 12 MESES 2DO MES GRATIS', 'DOMICILIADO 12 MESES 2DO MES GRATIS', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO 12 MESES PLAN FAMILIAR $999', 'DOMICILIADO 12 MESES PLAN FAMILIAR $999', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO 12 MESES PLAN FAMILIAR $999 (ADULTO + ADULTO)', 'DOMICILIADO 12 MESES PLAN FAMILIAR $999 (ADULTO + ADULTO)', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO 12 MESES PROMO NOVIEMBRE $499', 'DOMICILIADO 12 MESES PROMO NOVIEMBRE $499', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO 12 MESES; $399 (LOS 12 MESES)', 'DOMICILIADO 12 MESES; $399 (LOS 12 MESES)', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO 1ER MES GRATIS 12 MESES $499', 'DOMICILIADO 1ER MES GRATIS 12 MESES $499', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO 1ER MES GRATIS 6 MESES $549', 'DOMICILIADO 1ER MES GRATIS 6 MESES $549', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO 6 MESES $ 549', 'DOMICILIADO 6 MESES $ 549', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO 6 MESES $399 JULIO', 'DOMICILIADO 6 MESES $399 JULIO', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO 6 MESES $549 (LOS 6 MESES)', 'DOMICILIADO 6 MESES $549 (LOS 6 MESES)', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO 6 MESES + 250 INSCRIPCIÓN 2DO MES GRATIS', 'DOMICILIADO 6 MESES + 250 INSCRIPCIÓN 2DO MES GRATIS', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO 6 MESES 2DO MES GRATIS', 'DOMICILIADO 6 MESES 2DO MES GRATIS', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO 6 MESES MAYO $499', 'DOMICILIADO 6 MESES MAYO $499', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO 6 MESES PROMO NOVIEMBRE$549', 'DOMICILIADO 6 MESES PROMO NOVIEMBRE$549', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO 6 MESES: $399 (LOS 6 MESES)', 'DOMICILIADO 6 MESES: $399 (LOS 6 MESES)', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO 6 MESES; $449 (LOS 6 MESES)', 'DOMICILIADO 6 MESES; $449 (LOS 6 MESES)', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO ANUAL', 'DOMICILIADO ANUAL', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO NAVIDAD 3 MESES INSCRIPCION GRATIS $549', 'DOMICILIADO NAVIDAD 3 MESES INSCRIPCION GRATIS $549', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO PLAN 6 MESES $449', 'DOMICILIADO PLAN 6 MESES $449', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO PLAN ULTRA PAGO INCIAL 12 MESES $1,449', 'DOMICILIADO PLAN ULTRA PAGO INCIAL 12 MESES $1,449', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO SANTA 12 MESES $499', 'DOMICILIADO SANTA 12 MESES $499', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO SEMESTRAL', 'DOMICILIADO SEMESTRAL', 'Domiciliado', 'DOMICILIADO'),
    ('DOMICILIADO SIN PLAZO $599', 'DOMICILIADO SIN PLAZO $599', 'Recurrente', 'DOMICILIADO'),
    ('DOMICILIADO SIN PLAZO PROMO NOVIEMBRE $599', 'DOMICILIADO SIN PLAZO PROMO NOVIEMBRE $599', 'Domiciliado', 'DOMICILIADO'),
    ('ELEMENT 399', 'ELEMENT 399', 'Convenio', 'CONVENIO'),
    ('ESTUDIANTE', 'ESTUDIANTE', 'Estudiante', 'ESTUDIANTE'),
    ('ESTUDIANTE $599', 'ESTUDIANTE $599', 'Estudiante', 'ESTUDIANTE'),
    ('ESTUDIANTE PROMO NOVIEMBRE $599', 'ESTUDIANTE PROMO NOVIEMBRE $599', 'Estudiante', 'ESTUDIANTE'),
    ('ESTUDIANTE/CONVENIO', 'ESTUDIANTE/CONVENIO', 'Estudiante', 'ESTUDIANTE'),
    ('ESTUDIANTES $ 599 SLRC', 'ESTUDIANTES $ 599 SLRC', 'Estudiante', 'ESTUDIANTE'),
    ('ESTUDIANTES 2 MESES X $999', 'ESTUDIANTES 2 MESES X $999', 'Estudiante', 'ESTUDIANTE'),
    ('ESTUDIANTES 3 MESES X $1200', 'ESTUDIANTES 3 MESES X $1200', 'Estudiante', 'ESTUDIANTE'),
    ('GYMPASS', 'GYMPASS', 'Agregadora', 'OUT_OF_SEGMENT'),
    ('INSCRIPCION $600', 'INSCRIPCION $600', 'Mensualidad', 'DOMICILIADO'),
    ('INSCRIPCIÓN', 'INSCRIPCIÓN', 'Mensualidad', 'DOMICILIADO'),
    ('INSCRIPCIÓN $250', 'INSCRIPCIÓN $250', 'Mensualidad', 'DOMICILIADO'),
    ('INSCRIPCIÓN $400', 'INSCRIPCIÓN $400', 'Mensualidad', 'DOMICILIADO'),
    ('MEMBRESIA ESPECIAL', 'MEMBRESIA ESPECIAL', 'Mensualidad', 'DOMICILIADO'),
    ('MENSUALIDAD', 'MENSUALIDAD', 'Mensualidad', 'DOMICILIADO'),
    ('MENSUALIDAD $799', 'MENSUALIDAD $799', 'Mensualidad', 'DOMICILIADO'),
    ('MENSUALIDAD 749', 'MENSUALIDAD 749', 'Mensualidad', 'DOMICILIADO'),
    ('MENSUALIDAD AGENTE 375', 'MENSUALIDAD AGENTE 375', 'Mensualidad', 'DOMICILIADO'),
    ('MENSUALIDAD CONVENIOS', 'MENSUALIDAD CONVENIOS', 'Convenio', 'CONVENIO'),
    ('MENSUALIDAD ESPECIAL', 'MENSUALIDAD ESPECIAL', 'Mensualidad', 'DOMICILIADO'),
    ('MENSUALIDAD LB/STA', 'MENSUALIDAD LB/STA', 'Mensualidad', 'DOMICILIADO'),
    ('MENSUALIDAD NAVIDEÑA', 'MENSUALIDAD NAVIDEÑA', 'Mensualidad', 'DOMICILIADO'),
    ('MENSUALIDAD NVA', 'MENSUALIDAD NVA', 'Mensualidad', 'DOMICILIADO'),
    ('MENSUALIDAD SL', 'MENSUALIDAD SL', 'Mensualidad', 'DOMICILIADO'),
    ('MENSUALIDAD STA CAT/SL/LB', 'MENSUALIDAD STA CAT/SL/LB', 'Mensualidad', 'DOMICILIADO'),
    ('MES REWARD', 'MES REWARD', 'Mes Reward', 'OUT_OF_SEGMENT'),
    ('PAGO EN LINEA', 'PAGO EN LINEA', 'Mensualidad', 'DOMICILIADO'),
    ('PAGO EN LINEA 3 MESES', 'PAGO EN LINEA 3 MESES', 'Mensualidad', 'DOMICILIADO'),
    ('PASE 2 DIAS GRATIS', 'PASE 2 DIAS GRATIS', 'Pase de Cortesía', 'DOMICILIADO'),
    ('PASE GYMPASS', 'PASE GYMPASS', 'Agregadora', 'OUT_OF_SEGMENT'),
    ('PASE RECORRIDO', 'PASE RECORRIDO', 'Pase de Cortesía', 'DOMICILIADO'),
    ('PASE TOTAL PASS', 'PASE TOTAL PASS', 'Agregadora', 'OUT_OF_SEGMENT'),
    ('PLAN FAMILIA / AMIGOS X $499', 'PLAN FAMILIA / AMIGOS X $499', 'Domiciliado', 'DOMICILIADO'),
    ('PLAN FAMILIAR RECURRENTE $999', 'PLAN FAMILIAR RECURRENTE $999', 'Recurrente', 'DOMICILIADO'),
    ('PLAN RECURRENTE PAGO INCIAL $1,449 LE', 'PLAN RECURRENTE PAGO INCIAL $1,449 LE', 'Recurrente', 'DOMICILIADO'),
    ('PRIMER MES', 'PRIMER MES', 'Mensualidad', 'DOMICILIADO'),
    ('PRIMER PAGO 399 POSTERIOR 549', 'PRIMER PAGO 399 POSTERIOR 549', 'Recurrente', 'DOMICILIADO'),
    ('PROMO 14 FEB', 'PROMO 14 FEB', 'Mensualidad', 'DOMICILIADO'),
    ('PROMO 2 X 800', 'PROMO 2 X 800', 'Bimestre', 'TRIMESTRAL'),
    ('PROMO 2X 800', 'PROMO 2X 800', 'Bimestre', 'TRIMESTRAL'),
    ('PROMO 2X800', 'PROMO 2X800', 'Bimestre', 'TRIMESTRAL'),
    ('PROMO 3 MESES', 'PROMO 3 MESES', 'Trimestre', 'TRIMESTRAL'),
    ('PROMO 3 MESES JUN 2024', 'PROMO 3 MESES JUN 2024', 'Trimestre', 'TRIMESTRAL'),
    ('PROMO 3 MESES SAN VALENTIN', 'PROMO 3 MESES SAN VALENTIN', 'Trimestre', 'TRIMESTRAL'),
    ('PROMO 3 X 2 $1,100', 'PROMO 3 X 2 $1,100', 'Trimestre', 'TRIMESTRAL'),
    ('PROMO 399 PRIMER PAGO', 'PROMO 399 PRIMER PAGO', 'Recurrente', 'DOMICILIADO'),
    ('PROMO 498 PRIMER PAGO', 'PROMO 498 PRIMER PAGO', 'Recurrente', 'DOMICILIADO'),
    ('PROMO 6 MESES SAN VALENTIN', 'PROMO 6 MESES SAN VALENTIN', 'Recurrente', 'DOMICILIADO'),
    ('PROMO AMIGO BAJA', 'PROMO AMIGO BAJA', 'Mensualidad', 'DOMICILIADO'),
    ('PROMO ANIVERSARIO SL', 'PROMO ANIVERSARIO SL', 'Mensualidad', 'DOMICILIADO'),
    ('PROMO BUEN FIN', 'PROMO BUEN FIN', 'Mensualidad', 'DOMICILIADO'),
    ('PROMO CIERRE ENERO', 'PROMO CIERRE ENERO', 'Mensualidad', 'DOMICILIADO'),
    ('PROMO DIA DE LA MUJER', 'PROMO DIA DE LA MUJER', 'Mensualidad', 'DOMICILIADO'),
    ('PROMO DICIEMBRE 3 MESES POR $1,350', 'PROMO DICIEMBRE 3 MESES POR $1,350', 'Trimestre', 'TRIMESTRAL'),
    ('PROMO ENERO 12 MESES', 'PROMO ENERO 12 MESES', 'Domiciliado', 'DOMICILIADO'),
    ('PROMO FEBRERO 12 MESES', 'PROMO FEBRERO 12 MESES', 'Domiciliado', 'DOMICILIADO'),
    ('PROMO IXTAPALUCA', 'PROMO IXTAPALUCA', 'Mensualidad', 'DOMICILIADO'),
    ('PROMO REFERIDO', 'PROMO REFERIDO', 'Mensualidad', 'DOMICILIADO'),
    ('PROMO SAN VALENTIN RECURRENTE', 'PROMO SAN VALENTIN RECURRENTE', 'Recurrente', 'DOMICILIADO'),
    ('PROMO SANTA CATARINA', 'PROMO SANTA CATARINA', 'Mensualidad', 'DOMICILIADO'),
    ('PROMOCIÓN FIN DE AÑO 2019', 'PROMOCIÓN FIN DE AÑO 2019', 'Mensualidad', 'DOMICILIADO'),
    ('RECURRENTE $499 CONVENIO', 'RECURRENTE $499 CONVENIO', 'Recurrente', 'DOMICILIADO'),
    ('RECURRENTE $599', 'RECURRENTE $599', 'Recurrente', 'DOMICILIADO'),
    ('RECURRENTE $649 LE', 'RECURRENTE $649 LE', 'Recurrente', 'DOMICILIADO'),
    ('RECURRENTE 399', 'RECURRENTE 399', 'Recurrente', 'DOMICILIADO'),
    ('RECURRENTE JUBILADOS $399', 'RECURRENTE JUBILADOS $399', 'Recurrente', 'DOMICILIADO'),
    ('RECURRENTE REACTIVACION', 'RECURRENTE REACTIVACION', 'Recurrente', 'DOMICILIADO'),
    ('RECURRENTE SIN PLAZO', 'RECURRENTE SIN PLAZO', 'Recurrente', 'DOMICILIADO'),
    ('RECURRENTE SIN PLAZO NVA', 'RECURRENTE SIN PLAZO NVA', 'Recurrente', 'DOMICILIADO'),
    ('RECURRENTE ULTRAFITKIDS $399', 'RECURRENTE ULTRAFITKIDS $399', 'Recurrente', 'DOMICILIADO'),
    ('RENOVACION DICIEMBRE', 'RENOVACION DICIEMBRE', 'Mensualidad', 'DOMICILIADO'),
    ('SALVATIERRA $399', 'SALVATIERRA $399', 'Estudiante', 'ESTUDIANTE'),
    ('SALVATIERRA SIN PLAZO', 'SALVATIERRA SIN PLAZO', 'Estudiante', 'ESTUDIANTE'),
    ('SAN LUIS PERSONALIZADO', 'SAN LUIS PERSONALIZADO', 'Instructor', 'OUT_OF_SEGMENT'),
    ('SEMANA', 'SEMANA', 'Trimestre', 'TRIMESTRAL'),
    ('SEMANA $250', 'SEMANA $250', 'Semana', 'MES'),
    ('SEMANA $349', 'SEMANA $349', 'Semana', 'MES'),
    ('SEMANA $400', 'SEMANA $400', 'Semana', 'MES'),
    ('SEMANA INSTRUCTOR PERSONALIZADO', 'SEMANA INSTRUCTOR PERSONALIZADO', 'Instructor', 'OUT_OF_SEGMENT'),
    ('SEMANA INSTRUCTOR PERSONALIZADO EXTERNO $699', 'SEMANA INSTRUCTOR PERSONALIZADO EXTERNO $699', 'Instructor', 'OUT_OF_SEGMENT'),
    ('SEMANA SANTA 3 MESES X 1499', 'SEMANA SANTA 3 MESES X 1499', 'Semana', 'MES'),
    ('SEMANAL', 'SEMANAL', 'Semana', 'MES'),
    ('SEMESTRE', 'SEMESTRE', 'Semestre', 'SEMESTRE'),
    ('SUPERCLASE', 'SUPERCLASE', 'Instructor', 'OUT_OF_SEGMENT'),
    ('TARIFA ESTUDIANTE', 'TARIFA ESTUDIANTE', 'Estudiante', 'ESTUDIANTE'),
    ('TRES MESES POR 1,490', 'TRES MESES POR 1,490', 'Trimestre', 'TRIMESTRAL'),
    ('TRIMESTRAL $1,890', 'TRIMESTRAL $1,890', 'Trimestre', 'TRIMESTRAL'),
    ('ULTRA FIT KIDS SIN PLAZO $399', 'ULTRA FIT KIDS SIN PLAZO $399', 'Recurrente', 'DOMICILIADO'),
)


def _validated_rows() -> list[dict[str, str]]:
    if len(_SAFE_TARIFF_ROWS) != _EXPECTED_ROW_COUNT:
        raise RuntimeError(
            "Campaign V2 safe tariff seed row count mismatch: "
            f"expected {_EXPECTED_ROW_COUNT}, got {len(_SAFE_TARIFF_ROWS)}"
        )

    rows: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    for tarifa_key, tarifa_raw, categoria_tarifa, audience_family in _SAFE_TARIFF_ROWS:
        if not tarifa_key or not tarifa_raw or not categoria_tarifa:
            raise RuntimeError("Campaign V2 safe tariff seed contains an empty value")
        if tarifa_key in _EXCLUDED_CONFLICT_KEYS:
            raise RuntimeError(
                f"Conflicting tariff must not be seeded automatically: {tarifa_key!r}"
            )
        if tarifa_key in seen_keys:
            raise RuntimeError(
                f"Duplicate Campaign V2 safe tariff key: {tarifa_key!r}"
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
