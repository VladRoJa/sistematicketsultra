# kpi_daily_canonicality_resolver.py


from __future__ import annotations

from typing import Any


SUPPORTED_KPI_REPORT_TYPES = frozenset(
    {
        "kpi_desempeno",
        "kpi_ventas_nuevos_socios",
    }
)

SUPPORTED_SNAPSHOT_KINDS = frozenset({"daily"})


class KpiDailyCanonicalityResolverError(RuntimeError):
    """Error base del resolver de canonicalidad para KPIs diarios."""


def resolve_kpi_daily_canonicality(
    *,
    business_date,
    snapshot_kind: str,
    existing_canonical_snapshot,
    report_type_key: str,
) -> dict[str, Any]:
    """
    Política inicial de canonicalidad para KPIs:
    - scope: report_type_key + business_date + snapshot_kind
    - regla: latest successful wins

    Este resolver asume que el repository ya filtró el snapshot canónico
    existente para la misma combinación lógica.
    """
    if report_type_key not in SUPPORTED_KPI_REPORT_TYPES:
        raise KpiDailyCanonicalityResolverError(
            f"report_type_key no soportado por el resolver KPI: {report_type_key!r}"
        )

    if snapshot_kind not in SUPPORTED_SNAPSHOT_KINDS:
        raise KpiDailyCanonicalityResolverError(
            f"snapshot_kind no soportado por el resolver KPI: {snapshot_kind!r}"
        )

    if existing_canonical_snapshot is None:
        return {
            "is_canonical": True,
            "replace_existing_canonical": False,
            "reason": "first_successful_daily_snapshot_for_scope",
        }

    return {
        "is_canonical": True,
        "replace_existing_canonical": True,
        "reason": "latest_successful_daily_snapshot_wins",
    }


def register_kpi_daily_canonicality_resolvers(app) -> None:
    """
    Registra el mismo resolver para los dos KPIs diarios.
    """
    app.config["WAREHOUSE_KPI_DESEMPENO_CANONICALITY_RESOLVER"] = (
        resolve_kpi_daily_canonicality
    )
    app.config["WAREHOUSE_KPI_VENTAS_NUEVOS_SOCIOS_CANONICALITY_RESOLVER"] = (
        resolve_kpi_daily_canonicality
    )