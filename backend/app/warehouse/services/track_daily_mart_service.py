#   backend\app\warehouse\services\track_daily_mart_service.py


from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.extensions import db
from app.models.warehouse import (
    TrackBranchCatalogORM,
    TrackMonthlyTargetORM,
    TrackSourceDesempenoDailyORM,
    TrackSourceIngresosDailyORM,
    TrackSourceNuevosDailyORM,
    TrackSourceDomiciliadosEfectivosDailyORM,
    TrackDailyMartORM,
)


SUPPORTED_GENERATION_MODES = frozenset(
    {
        "official_closed_day",
        "manual_preview",
    }
)


class TrackDailyMartServiceError(RuntimeError):
    """Error base del builder del mart diario del Track."""


def _ensure_date(value: Any, *, field_name: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except Exception as exc:
            raise TrackDailyMartServiceError(
                f"No se pudo convertir a date el campo {field_name!r}: {value!r}"
            ) from exc

    raise TrackDailyMartServiceError(
        f"Valor inválido para {field_name!r}: {value!r}"
    )


def _ensure_generation_mode(value: Any) -> str:
    normalized = str(value or "").strip()
    if normalized not in SUPPORTED_GENERATION_MODES:
        raise TrackDailyMartServiceError(
            "generation_mode inválido. "
            f"Permitidos: {sorted(SUPPORTED_GENERATION_MODES)}"
        )
    return normalized


def _first_day_of_month(value: date) -> date:
    return value.replace(day=1)


def _resolve_source_dates_for_track_date(
    *,
    track_date: date,
    generation_mode: str,
) -> dict[str, date]:
    normalized_generation_mode = _ensure_generation_mode(generation_mode)

    if normalized_generation_mode in {"official_closed_day", "manual_preview"}:
        return {
            "desempeno": track_date,
            "ingresos": track_date,
            "nuevos": track_date,
            "domiciliados": track_date,
        }

    raise TrackDailyMartServiceError(
        f"No se pudo resolver source dates para generation_mode={normalized_generation_mode!r}"
    )


def build_track_daily_mart_for_date(
    *,
    business_date: Any,
    generation_mode: str = "official_closed_day",
) -> list[dict[str, Any]]:
    track_date = _ensure_date(
        business_date,
        field_name="business_date",
    )
    normalized_generation_mode = _ensure_generation_mode(generation_mode)
    target_month = _first_day_of_month(track_date)
    source_dates = _resolve_source_dates_for_track_date(
        track_date=track_date,
        generation_mode=normalized_generation_mode,
    )

    active_branches = (
        TrackBranchCatalogORM.query.filter_by(is_track_active=True)
        .order_by(TrackBranchCatalogORM.display_order.asc())
        .all()
    )

    if not active_branches:
        raise TrackDailyMartServiceError(
            "No existen sucursales activas en track_branch_catalog."
        )

    targets = (
        TrackMonthlyTargetORM.query.filter_by(
            target_month=target_month,
            is_active=True,
        )
        .all()
    )
    targets_by_branch = {
        row.sucursal_canon: row
        for row in targets
    }

    desempeno_rows = (
        TrackSourceDesempenoDailyORM.query.filter_by(
            business_date=source_dates["desempeno"],
        )
        .all()
    )
    desempeno_by_branch = {
        row.sucursal_canon: row
        for row in desempeno_rows
    }

    ingresos_rows = (
        TrackSourceIngresosDailyORM.query.filter_by(
            business_date=source_dates["ingresos"],
        )
        .all()
    )
    ingresos_by_branch = {
        row.sucursal_canon: row
        for row in ingresos_rows
    }

    nuevos_rows = (
        TrackSourceNuevosDailyORM.query.filter_by(
            business_date=source_dates["nuevos"],
        )
        .all()
    )
    nuevos_by_branch = {
        row.sucursal_canon: row
        for row in nuevos_rows
    }

    domiciliados_rows = (
        TrackSourceDomiciliadosEfectivosDailyORM.query.filter_by(
            business_date=source_dates["domiciliados"],
        )
        .all()
    )
    domiciliados_by_branch = {
        row.sucursal_canon: row
        for row in domiciliados_rows
    }

    result: list[dict[str, Any]] = []

    for branch in active_branches:
        target_row = targets_by_branch.get(branch.sucursal_canon)
        desempeno_row = desempeno_by_branch.get(branch.sucursal_canon)
        ingresos_row = ingresos_by_branch.get(branch.sucursal_canon)
        nuevos_row = nuevos_by_branch.get(branch.sucursal_canon)
        domiciliados_row = domiciliados_by_branch.get(branch.sucursal_canon)

        ingreso_real_base_mtd = (
            ingresos_row.ingreso_real_base_mtd if ingresos_row else None
        )
        ingreso_real_agregadora_mtd = (
            ingresos_row.ingreso_real_agregadora_mtd if ingresos_row else None
        )
        ingreso_real_total_mtd = (
            ingresos_row.ingreso_real_total_mtd if ingresos_row else None
        )

        ingreso_real_mtd = ingreso_real_total_mtd
        if ingreso_real_mtd is None and ingresos_row:
            ingreso_real_mtd = ingresos_row.ingreso_real_mtd

        result.append(
            {
                "track_date": track_date.isoformat(),
                "generation_mode": normalized_generation_mode,
                "sucursal_canon": branch.sucursal_canon,
                "target_month": target_month.isoformat(),

                # F2
                "m2_sin_circulaciones": (
                    target_row.m2_sin_circulaciones if target_row else None
                ),
                "usuarios_inicio_mes": (
                    target_row.usuarios_inicio_mes if target_row else None
                ),
                "proyeccion_usuarios_cierre_mes": (
                    target_row.proyeccion_usuarios_cierre_mes if target_row else None
                ),
                "meta_faycgo_mes": (
                    target_row.meta_faycgo_mes if target_row else None
                ),
                "meta_clientes_nuevos_mes": (
                    target_row.meta_clientes_nuevos_mes if target_row else None
                ),
                "meta_reactivaciones_mes": (
                    target_row.meta_reactivaciones_mes if target_row else None
                ),
                "meta_bajas_mes": (
                    target_row.meta_bajas_mes if target_row else None
                ),
                "meta_nuevos_domiciliados_mes": (
                    target_row.meta_nuevos_domiciliados_mes if target_row else None
                ),
                "meta_arpu_mes": (
                    target_row.meta_arpu_mes if target_row else None
                ),
                "meta_venta_tienda_mes": (
                    target_row.meta_venta_tienda_mes if target_row else None
                ),

                # F3
                "usuarios_activos_actual": (
                    desempeno_row.usuarios_activos_actual if desempeno_row else None
                ),
                "reactivaciones_real_mtd": (
                    desempeno_row.reactivaciones_real_mtd if desempeno_row else None
                ),
                "bajas_reales_mtd": (
                    desempeno_row.bajas_reales_mtd if desempeno_row else None
                ),

                # F4
                "ingreso_real_base_mtd": ingreso_real_base_mtd,
                "ingreso_real_agregadora_mtd": ingreso_real_agregadora_mtd,
                "ingreso_real_total_mtd": ingreso_real_total_mtd,
                "ingreso_real_mtd": ingreso_real_mtd,

                # F5
                "clientes_nuevos_real_mtd": (
                    nuevos_row.clientes_nuevos_real_mtd if nuevos_row else None
                ),

                # F6
                "nuevos_domiciliados_real_mtd": (
                    domiciliados_row.nuevos_domiciliados_real_mtd
                    if domiciliados_row else None
                ),

                # lineage: source business dates
                "source_business_date_desempeno": (
                    desempeno_row.business_date.isoformat() if desempeno_row else None
                ),
                "source_business_date_ingresos": (
                    ingresos_row.business_date.isoformat() if ingresos_row else None
                ),
                "source_business_date_agregadoras": (
                    ingresos_row.source_business_date_agregadoras.isoformat()
                    if ingresos_row and ingresos_row.source_business_date_agregadoras
                    else None
                ),
                "source_business_date_nuevos": (
                    nuevos_row.business_date.isoformat() if nuevos_row else None
                ),
                "source_business_date_domiciliados": (
                    domiciliados_row.business_date.isoformat()
                    if domiciliados_row else None
                ),

                # lineage: source snapshot ids
                "source_snapshot_id_desempeno": (
                    desempeno_row.source_snapshot_id if desempeno_row else None
                ),
                "source_snapshot_id_ingresos": (
                    ingresos_row.source_snapshot_id_reporte_direccion
                    if ingresos_row else None
                ),
                "source_snapshot_id_nuevos": (
                    nuevos_row.source_snapshot_id if nuevos_row else None
                ),
                "source_snapshot_id_domiciliados": (
                    domiciliados_row.source_snapshot_id if domiciliados_row else None
                ),
            }
        )

    return result


def refresh_track_daily_mart_for_date(
    *,
    business_date: Any,
    generation_mode: str = "official_closed_day",
    track_daily_version_id: int | None = None,
) -> dict[str, Any]:
    track_date = _ensure_date(
        business_date,
        field_name="business_date",
    )
    normalized_generation_mode = _ensure_generation_mode(generation_mode)

    rows = build_track_daily_mart_for_date(
        business_date=track_date,
        generation_mode=normalized_generation_mode,
    )

    try:
        if track_daily_version_id is not None:
            TrackDailyMartORM.query.filter_by(
                track_daily_version_id=track_daily_version_id,
            ).delete(synchronize_session=False)
        else:
            TrackDailyMartORM.query.filter_by(
                track_date=track_date,
                generation_mode=normalized_generation_mode,
            ).delete(synchronize_session=False)

        for row in rows:
            db.session.add(
                TrackDailyMartORM(
                    track_date=_ensure_date(
                        row["track_date"],
                        field_name="track_date",
                    ),
                    track_daily_version_id=track_daily_version_id,
                    generation_mode=row["generation_mode"],
                    sucursal_canon=row["sucursal_canon"],
                    target_month=_ensure_date(
                        row["target_month"],
                        field_name="target_month",
                    ),

                    m2_sin_circulaciones=row["m2_sin_circulaciones"],
                    usuarios_inicio_mes=row["usuarios_inicio_mes"],
                    proyeccion_usuarios_cierre_mes=row["proyeccion_usuarios_cierre_mes"],
                    meta_faycgo_mes=row["meta_faycgo_mes"],
                    meta_clientes_nuevos_mes=row["meta_clientes_nuevos_mes"],
                    meta_reactivaciones_mes=row["meta_reactivaciones_mes"],
                    meta_bajas_mes=row["meta_bajas_mes"],
                    meta_nuevos_domiciliados_mes=row["meta_nuevos_domiciliados_mes"],
                    meta_arpu_mes=row["meta_arpu_mes"],
                    meta_venta_tienda_mes=row["meta_venta_tienda_mes"],

                    usuarios_activos_actual=row["usuarios_activos_actual"],
                    reactivaciones_real_mtd=row["reactivaciones_real_mtd"],
                    bajas_reales_mtd=row["bajas_reales_mtd"],

                    ingreso_real_base_mtd=row["ingreso_real_base_mtd"],
                    ingreso_real_agregadora_mtd=row["ingreso_real_agregadora_mtd"],
                    ingreso_real_total_mtd=row["ingreso_real_total_mtd"],
                    ingreso_real_mtd=row["ingreso_real_mtd"],

                    clientes_nuevos_real_mtd=row["clientes_nuevos_real_mtd"],
                    nuevos_domiciliados_real_mtd=row["nuevos_domiciliados_real_mtd"],

                    source_business_date_desempeno=(
                        _ensure_date(
                            row["source_business_date_desempeno"],
                            field_name="source_business_date_desempeno",
                        )
                        if row["source_business_date_desempeno"] is not None
                        else None
                    ),
                    source_business_date_ingresos=(
                        _ensure_date(
                            row["source_business_date_ingresos"],
                            field_name="source_business_date_ingresos",
                        )
                        if row["source_business_date_ingresos"] is not None
                        else None
                    ),
                    source_business_date_nuevos=(
                        _ensure_date(
                            row["source_business_date_nuevos"],
                            field_name="source_business_date_nuevos",
                        )
                        if row["source_business_date_nuevos"] is not None
                        else None
                    ),
                    source_business_date_domiciliados=(
                        _ensure_date(
                            row["source_business_date_domiciliados"],
                            field_name="source_business_date_domiciliados",
                        )
                        if row["source_business_date_domiciliados"] is not None
                        else None
                    ),

                    source_snapshot_id_desempeno=row["source_snapshot_id_desempeno"],
                    source_snapshot_id_ingresos=row["source_snapshot_id_ingresos"],
                    source_business_date_agregadoras=(
                        _ensure_date(
                            row["source_business_date_agregadoras"],
                            field_name="source_business_date_agregadoras",
                        )
                        if row["source_business_date_agregadoras"] is not None
                        else None
                    ),
                    source_snapshot_id_nuevos=row["source_snapshot_id_nuevos"],
                    source_snapshot_id_domiciliados=row["source_snapshot_id_domiciliados"],
                )
            )

        db.session.commit()

    except Exception:
        db.session.rollback()
        raise

    return {
        "status": "refreshed",
        "track_date": track_date.isoformat(),
        "generation_mode": normalized_generation_mode,
        "rows_inserted": len(rows),
    }
    
def delete_track_daily_mart_rows_for_version(
    *,
    track_daily_version_id: int,
    auto_commit: bool = False,
) -> dict[str, int]:
    deleted_count = (
        TrackDailyMartORM.query.filter_by(
            track_daily_version_id=track_daily_version_id,
        ).delete(synchronize_session=False)
    )

    db.session.flush()

    if auto_commit:
        db.session.commit()

    return {
        "track_daily_version_id": track_daily_version_id,
        "rows_deleted": deleted_count,
    }