#   backend\app\warehouse\services\commercial_promotions_service.py

from sqlalchemy import text

from app import db


class CommercialPromotionsService:
    """
    Servicio read-only para análisis comercial de promociones.

    Alcance MVP:
    - Fuente: Venta Total.
    - Solo ventas activas.
    - Solo último snapshot canónico por mes.
    - Solo sucursales canonizadas vía track_branch_aliases.
    - Clasificación por warehouse_commercial_catalog.
    - No incluye agregadoras.
    - No incluye registros no asociados a club como CORPORATIVO, BECA o SUCURSAL EN LÍNEA.
    """

    @staticmethod
    def get_ranking_general():
        sql = text(
            """
            WITH latest_canonical_snapshot_per_month AS (
              SELECT DISTINCT ON (date_trunc('month', business_date))
                id AS snapshot_id,
                business_date,
                date_trunc('month', business_date)::date AS snapshot_month
              FROM venta_total_snapshots
              WHERE snapshot_kind = 'daily'
                AND is_canonical = true
              ORDER BY
                date_trunc('month', business_date),
                business_date DESC,
                id DESC
            ),
            ventas_base AS (
              SELECT
                s.snapshot_id,
                s.business_date,
                s.snapshot_month,
                to_date(r.fecha, 'DD-MM-YY') AS fecha_venta,
                date_trunc('month', to_date(r.fecha, 'DD-MM-YY'))::date AS mes,
                r.sucursal AS sucursal_raw,
                a.sucursal_canon,
                r.descripcion AS descripcion_raw,
                r.cantidad,
                r.total
              FROM latest_canonical_snapshot_per_month s
              JOIN venta_total_snapshot_rows r
                ON r.snapshot_id = s.snapshot_id
              JOIN track_branch_aliases a
                ON a.source_family = 'gasca_family'
                AND a.is_active = true
                AND upper(trim(a.raw_branch_name)) = upper(trim(r.sucursal))
              WHERE r.estatus = 'ACTIVO'
                AND date_trunc('month', to_date(r.fecha, 'DD-MM-YY'))::date = s.snapshot_month
            ),
            ventas_clasificadas AS (
              SELECT
                v.mes,
                v.business_date,
                v.sucursal_canon,
                v.descripcion_raw,
                c.commercial_canon,
                c.family,
                c.subfamily,
                c.needs_business_validation,
                v.cantidad,
                v.total
              FROM ventas_base v
              JOIN warehouse_commercial_catalog c
                ON c.is_active = true
                AND c.is_promo = true
                AND upper(trim(c.raw_description)) = upper(trim(v.descripcion_raw))
              WHERE v.total > 0
            ),
            total_periodo AS (
              SELECT
                SUM(total) AS denominador_venta_total_canonizado
              FROM ventas_base
            ),
            ranking_general AS (
              SELECT
                commercial_canon,
                family,
                COUNT(DISTINCT mes) AS meses_con_venta,
                COUNT(*) AS operaciones,
                SUM(cantidad) AS unidades,
                SUM(total) AS ingreso_promo,
                ROUND(SUM(total) / NULLIF(SUM(cantidad), 0), 2) AS ticket_promedio,
                BOOL_OR(needs_business_validation) AS requiere_validacion_negocio
              FROM ventas_clasificadas
              GROUP BY
                commercial_canon,
                family
            )
            SELECT
              r.commercial_canon,
              r.family,
              r.meses_con_venta,
              r.operaciones,
              r.unidades,
              r.ingreso_promo,
              r.ticket_promedio,
              t.denominador_venta_total_canonizado,
              ROUND(
                (
                  r.ingreso_promo
                  / NULLIF(t.denominador_venta_total_canonizado, 0)
                ) * 100,
                2
              ) AS porcentaje_sobre_venta_total,
              r.requiere_validacion_negocio
            FROM ranking_general r
            CROSS JOIN total_periodo t
            ORDER BY
              r.ingreso_promo DESC;
            """
        )

        result = db.session.execute(sql).mappings().all()

        return [dict(row) for row in result]
    
    @staticmethod
    def get_top_by_month():
        sql = text(
            """
            WITH latest_canonical_snapshot_per_month AS (
              SELECT DISTINCT ON (date_trunc('month', business_date))
                id AS snapshot_id,
                business_date,
                date_trunc('month', business_date)::date AS snapshot_month
              FROM venta_total_snapshots
              WHERE snapshot_kind = 'daily'
                AND is_canonical = true
              ORDER BY
                date_trunc('month', business_date),
                business_date DESC,
                id DESC
            ),
            ventas_base AS (
              SELECT
                s.snapshot_id,
                s.business_date,
                s.snapshot_month,
                to_date(r.fecha, 'DD-MM-YY') AS fecha_venta,
                date_trunc('month', to_date(r.fecha, 'DD-MM-YY'))::date AS mes,
                r.sucursal AS sucursal_raw,
                a.sucursal_canon,
                r.descripcion AS descripcion_raw,
                r.cantidad,
                r.total
              FROM latest_canonical_snapshot_per_month s
              JOIN venta_total_snapshot_rows r
                ON r.snapshot_id = s.snapshot_id
              JOIN track_branch_aliases a
                ON a.source_family = 'gasca_family'
                AND a.is_active = true
                AND upper(trim(a.raw_branch_name)) = upper(trim(r.sucursal))
              WHERE r.estatus = 'ACTIVO'
                AND date_trunc('month', to_date(r.fecha, 'DD-MM-YY'))::date = s.snapshot_month
            ),
            ventas_clasificadas AS (
              SELECT
                v.mes,
                v.business_date AS corte_snapshot,
                v.sucursal_canon,
                v.descripcion_raw,
                c.commercial_canon,
                c.family,
                c.subfamily,
                c.needs_business_validation,
                v.cantidad,
                v.total
              FROM ventas_base v
              JOIN warehouse_commercial_catalog c
                ON c.is_active = true
                AND c.is_promo = true
                AND upper(trim(c.raw_description)) = upper(trim(v.descripcion_raw))
              WHERE v.total > 0
            ),
            total_mes AS (
              SELECT
                mes,
                SUM(total) AS denominador_venta_total_mes
              FROM ventas_base
              GROUP BY mes
            ),
            promo_mes AS (
              SELECT
                mes,
                corte_snapshot,
                commercial_canon,
                family,
                COUNT(*) AS operaciones,
                SUM(cantidad) AS unidades,
                SUM(total) AS ingreso_promo,
                ROUND(SUM(total) / NULLIF(SUM(cantidad), 0), 2) AS ticket_promedio,
                BOOL_OR(needs_business_validation) AS requiere_validacion_negocio
              FROM ventas_clasificadas
              GROUP BY
                mes,
                corte_snapshot,
                commercial_canon,
                family
            ),
            ranking AS (
              SELECT
                p.*,
                t.denominador_venta_total_mes,
                ROUND(
                  (
                    p.ingreso_promo
                    / NULLIF(t.denominador_venta_total_mes, 0)
                  ) * 100,
                  2
                ) AS porcentaje_sobre_venta_total_mes,
                ROW_NUMBER() OVER (
                  PARTITION BY p.mes
                  ORDER BY p.ingreso_promo DESC
                ) AS ranking_mes
              FROM promo_mes p
              JOIN total_mes t
                ON t.mes = p.mes
            )
            SELECT
              mes,
              corte_snapshot,
              ranking_mes,
              commercial_canon,
              family,
              operaciones,
              unidades,
              ingreso_promo,
              ticket_promedio,
              denominador_venta_total_mes,
              porcentaje_sobre_venta_total_mes,
              requiere_validacion_negocio
            FROM ranking
            WHERE ranking_mes <= 5
            ORDER BY
              mes,
              ranking_mes;
            """
        )

        result = db.session.execute(sql).mappings().all()

        return [dict(row) for row in result]
    
    @staticmethod
    def get_top_by_branch():
        sql = text(
            """
            WITH latest_canonical_snapshot_per_month AS (
              SELECT DISTINCT ON (date_trunc('month', business_date))
                id AS snapshot_id,
                business_date,
                date_trunc('month', business_date)::date AS snapshot_month
              FROM venta_total_snapshots
              WHERE snapshot_kind = 'daily'
                AND is_canonical = true
              ORDER BY
                date_trunc('month', business_date),
                business_date DESC,
                id DESC
            ),
            ventas_base AS (
              SELECT
                s.snapshot_id,
                s.business_date,
                s.snapshot_month,
                to_date(r.fecha, 'DD-MM-YY') AS fecha_venta,
                date_trunc('month', to_date(r.fecha, 'DD-MM-YY'))::date AS mes,
                r.sucursal AS sucursal_raw,
                a.sucursal_canon,
                r.descripcion AS descripcion_raw,
                r.cantidad,
                r.total
              FROM latest_canonical_snapshot_per_month s
              JOIN venta_total_snapshot_rows r
                ON r.snapshot_id = s.snapshot_id
              JOIN track_branch_aliases a
                ON a.source_family = 'gasca_family'
                AND a.is_active = true
                AND upper(trim(a.raw_branch_name)) = upper(trim(r.sucursal))
              WHERE r.estatus = 'ACTIVO'
                AND date_trunc('month', to_date(r.fecha, 'DD-MM-YY'))::date = s.snapshot_month
            ),
            ventas_clasificadas AS (
              SELECT
                v.mes,
                v.business_date,
                v.sucursal_canon,
                v.descripcion_raw,
                c.commercial_canon,
                c.family,
                c.subfamily,
                c.needs_business_validation,
                v.cantidad,
                v.total
              FROM ventas_base v
              JOIN warehouse_commercial_catalog c
                ON c.is_active = true
                AND c.is_promo = true
                AND upper(trim(c.raw_description)) = upper(trim(v.descripcion_raw))
              WHERE v.total > 0
            ),
            total_sucursal AS (
              SELECT
                sucursal_canon,
                SUM(total) AS denominador_venta_total_sucursal
              FROM ventas_base
              GROUP BY sucursal_canon
            ),
            promo_sucursal AS (
              SELECT
                sucursal_canon,
                commercial_canon,
                family,
                COUNT(DISTINCT mes) AS meses_con_venta,
                COUNT(*) AS operaciones,
                SUM(cantidad) AS unidades,
                SUM(total) AS ingreso_promo,
                ROUND(SUM(total) / NULLIF(SUM(cantidad), 0), 2) AS ticket_promedio,
                BOOL_OR(needs_business_validation) AS requiere_validacion_negocio
              FROM ventas_clasificadas
              GROUP BY
                sucursal_canon,
                commercial_canon,
                family
            ),
            ranking AS (
              SELECT
                p.*,
                t.denominador_venta_total_sucursal,
                ROUND(
                  (
                    p.ingreso_promo
                    / NULLIF(t.denominador_venta_total_sucursal, 0)
                  ) * 100,
                  2
                ) AS porcentaje_sobre_venta_total_sucursal,
                ROW_NUMBER() OVER (
                  PARTITION BY p.sucursal_canon
                  ORDER BY p.ingreso_promo DESC
                ) AS ranking_sucursal
              FROM promo_sucursal p
              JOIN total_sucursal t
                ON t.sucursal_canon = p.sucursal_canon
            )
            SELECT
              sucursal_canon,
              commercial_canon AS promo_ganadora,
              family,
              meses_con_venta,
              operaciones,
              unidades,
              ingreso_promo,
              ticket_promedio,
              denominador_venta_total_sucursal,
              porcentaje_sobre_venta_total_sucursal,
              CASE
                WHEN porcentaje_sobre_venta_total_sucursal >= 5 THEN 'impacto_fuerte'
                WHEN porcentaje_sobre_venta_total_sucursal >= 2 THEN 'impacto_medio'
                ELSE 'impacto_bajo_no_concluyente'
              END AS lectura_impacto,
              requiere_validacion_negocio
            FROM ranking
            WHERE ranking_sucursal = 1
            ORDER BY
              porcentaje_sobre_venta_total_sucursal DESC,
              ingreso_promo DESC;
            """
        )

        result = db.session.execute(sql).mappings().all()

        return [dict(row) for row in result]
    
    @staticmethod
    def get_unmapped_descriptions():
        sql = text(
            """
            WITH latest_canonical_snapshot_per_month AS (
              SELECT DISTINCT ON (date_trunc('month', business_date))
                id AS snapshot_id,
                business_date,
                date_trunc('month', business_date)::date AS snapshot_month
              FROM venta_total_snapshots
              WHERE snapshot_kind = 'daily'
                AND is_canonical = true
              ORDER BY
                date_trunc('month', business_date),
                business_date DESC,
                id DESC
            ),
            ventas_base AS (
              SELECT
                s.snapshot_id,
                s.business_date,
                s.snapshot_month,
                to_date(r.fecha, 'DD-MM-YY') AS fecha_venta,
                date_trunc('month', to_date(r.fecha, 'DD-MM-YY'))::date AS mes,
                r.sucursal AS sucursal_raw,
                a.sucursal_canon,
                r.descripcion AS descripcion_raw,
                r.cantidad,
                r.total
              FROM latest_canonical_snapshot_per_month s
              JOIN venta_total_snapshot_rows r
                ON r.snapshot_id = s.snapshot_id
              JOIN track_branch_aliases a
                ON a.source_family = 'gasca_family'
                AND a.is_active = true
                AND upper(trim(a.raw_branch_name)) = upper(trim(r.sucursal))
              WHERE r.estatus = 'ACTIVO'
                AND r.total > 0
                AND date_trunc('month', to_date(r.fecha, 'DD-MM-YY'))::date = s.snapshot_month
            ),
            candidate_descriptions AS (
              SELECT
                v.*
              FROM ventas_base v
              LEFT JOIN warehouse_commercial_catalog c
                ON c.is_active = true
                AND upper(trim(c.raw_description)) = upper(trim(v.descripcion_raw))
              WHERE c.id IS NULL
                AND (
                  v.descripcion_raw ILIKE '%PROMO%'
                  OR v.descripcion_raw ILIKE '%GRATIS%'
                  OR v.descripcion_raw ILIKE '%50%%'
                  OR v.descripcion_raw ILIKE '%BORRON%'
                  OR v.descripcion_raw ILIKE '%BORRÓN%'
                  OR v.descripcion_raw ILIKE '%PREVENTA%'
                  OR v.descripcion_raw ILIKE '%BUEN FIN%'
                  OR v.descripcion_raw ILIKE '%HOT SALE%'
                  OR v.descripcion_raw ILIKE '%SAN VALENT%'
                  OR v.descripcion_raw ILIKE '%NAVIDAD%'
                  OR v.descripcion_raw ILIKE '%PRIMER PAGO%'
                  OR v.descripcion_raw ILIKE '%2DO MES%'
                  OR v.descripcion_raw ILIKE '%3 X 2%'
                  OR v.descripcion_raw ILIKE '%DESCUENTO%'
                  OR v.descripcion_raw ILIKE '%INSCRIP%'
                )
            )
            SELECT
              descripcion_raw,
              COUNT(*) AS operaciones,
              SUM(cantidad) AS unidades,
              SUM(total) AS ingreso_total,
              ROUND(SUM(total) / NULLIF(SUM(cantidad), 0), 2) AS ticket_promedio,
              COUNT(DISTINCT sucursal_canon) AS sucursales_detectadas,
              MIN(mes) AS primer_mes_detectado,
              MAX(mes) AS ultimo_mes_detectado
            FROM candidate_descriptions
            GROUP BY descripcion_raw
            ORDER BY ingreso_total DESC, operaciones DESC
            LIMIT 200;
            """
        )

        result = db.session.execute(sql).mappings().all()

        return [dict(row) for row in result]
    
    @staticmethod
    def get_summary():
        ranking = CommercialPromotionsService.get_ranking_general()
        by_branch = CommercialPromotionsService.get_top_by_branch()
        unmapped = CommercialPromotionsService.get_unmapped_descriptions()

        period_sql = text(
            """
            WITH latest_canonical_snapshot_per_month AS (
              SELECT DISTINCT ON (date_trunc('month', business_date))
                id AS snapshot_id,
                business_date,
                date_trunc('month', business_date)::date AS snapshot_month
              FROM venta_total_snapshots
              WHERE snapshot_kind = 'daily'
                AND is_canonical = true
              ORDER BY
                date_trunc('month', business_date),
                business_date DESC,
                id DESC
            )
            SELECT
              MIN(snapshot_month) AS first_month,
              MAX(snapshot_month) AS last_month,
              MAX(business_date) AS last_snapshot_cutoff,
              COUNT(*) AS analyzed_months
            FROM latest_canonical_snapshot_per_month;
            """
        )

        period_row = db.session.execute(period_sql).mappings().first()

        winner = ranking[0] if ranking else None

        denominador = None
        ingreso_promo_total = 0

        if ranking:
            denominador = ranking[0].get("denominador_venta_total_canonizado")
            ingreso_promo_total = sum(
                row.get("ingreso_promo") or 0
                for row in ranking
            )

        porcentaje_promo_total = None
        if denominador:
            porcentaje_promo_total = round(
                (ingreso_promo_total / denominador) * 100,
                2,
            )

        strong_branches = 0
        medium_branches = 0
        low_branches = 0

        for row in by_branch:
            lectura = row.get("lectura_impacto")

            if lectura == "impacto_fuerte":
                strong_branches += 1
            elif lectura == "impacto_medio":
                medium_branches += 1
            else:
                low_branches += 1

        return {
            "period": {
                "first_month": period_row.get("first_month") if period_row else None,
                "last_month": period_row.get("last_month") if period_row else None,
                "last_snapshot_cutoff": period_row.get("last_snapshot_cutoff") if period_row else None,
                "analyzed_months": period_row.get("analyzed_months") if period_row else 0,
            },
            "winner": winner,
            "totals": {
                "denominador_venta_total_canonizado": denominador,
                "ingreso_promo_total": ingreso_promo_total,
                "porcentaje_promo_total": porcentaje_promo_total,
            },
            "impact": {
                "strong_branches": strong_branches,
                "medium_branches": medium_branches,
                "low_branches": low_branches,
                "total_branches": len(by_branch),
            },
            "unmapped": {
                "candidate_count": len(unmapped),
            },
        }