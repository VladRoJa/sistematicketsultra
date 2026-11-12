"""Socios equivalentes de agregadoras, proyectados sin alterar el mart ni sus versiones.

Se usa un único snapshot canónico MTD por fuente y fecha. Ninguna fecha
posterior a la consultada puede participar en una lectura histórica.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from app.models.warehouse import (
    IngresosTotalpassSnapshotORM,
    IngresosTotalpassSnapshotRowORM,
    IngresosWellhubSnapshotORM,
    IngresosWellhubSnapshotRowORM,
)

# Tarifario vigente a partir de 2026-04-01. No extrapolar hacia atrás.
TOTALPASS_TARIFF_START = date(2026, 4, 1)
TP_GO_DIV_12 = frozenset({
    "CARROUSEL_TJ", "SANTA_FE", "INDEPENDENCIA", "LOMA_BONITA",
    "SEND_MXL", "VILLA_VERDE", "PABELLON_RTO", "SAN_LUIS",
})
TP_DIV_10 = frozenset({
    "SEND_CHIH", "AZAHARES_CUL", "MISION_ENS", "PAPALOTE_TJ",
    "PASEO_LA_PAZ", "PASEO_2000", "TEC_MXL", "VILLAS_DEL_REY",
    "SEND_CUL", "STA_CATARINA", "IXTAPALUCA", "SAN_ISIDRO_CUL",
    "SEND_SALTILLO", "TLALNEPANTLA", "SALTILLO_VILLALTA",
    "METEPEC", "INSURGENTES", "SERRANIA",
})
if TP_GO_DIV_12 & TP_DIV_10 or len(TP_GO_DIV_12 | TP_DIV_10) != 26:
    raise RuntimeError("Tabulador TotalPass no corresponde a las 26 sucursales.")

TEN = Decimal("10")


def _snapshots_in_month(model, track_date: date) -> dict[date, object]:
    month_start = track_date.replace(day=1)
    snapshots = (
        model.query.filter(
            model.business_date >= month_start,
            model.business_date <= track_date,
            model.snapshot_kind == "daily",
            model.is_canonical.is_(True),
        )
        .order_by(model.business_date.desc(), model.id.desc())
        .all()
    )
    # Si alguna fuente guardó dos canónicos por fecha, usar solo el último.
    result = {}
    for snapshot in snapshots:
        result.setdefault(snapshot.business_date, snapshot)
    return result


def _wellhub_visits(snapshot_id: int) -> dict[str, int | None]:
    visits: dict[str, int | None] = {}
    rows = IngresosWellhubSnapshotRowORM.query.filter_by(
        snapshot_id=snapshot_id
    ).all()
    for row in rows:
        branch = row.sucursal_canon
        if row.total_checkins_mtd is None:
            visits[branch] = None
        elif visits.get(branch) is not None:
            count = int(row.total_checkins_mtd)
            if count < 0:
                raise ValueError("Check-ins negativos de Wellhub.")
            visits[branch] = visits.get(branch, 0) + count
    return visits


def _totalpass_visits(snapshot_id: int) -> dict[str, int | None]:
    visits: dict[str, int | None] = {}
    rows = IngresosTotalpassSnapshotRowORM.query.filter_by(
        snapshot_id=snapshot_id
    ).all()
    for row in rows:
        branch = row.sucursal_canon
        if branch in visits:
            raise ValueError(f"TotalPass duplicó sucursal {branch}.")
        if branch not in TP_GO_DIV_12 and branch not in TP_DIV_10:
            raise ValueError(f"TotalPass sin divisor aprobado: {branch}.")
        count = row.usage_count
        if count is not None and int(count) < 0:
            raise ValueError("Visitas negativas de TotalPass.")
        visits[branch] = int(count) if count is not None else None
    return visits


def socios_equivalentes_por_fecha(track_date: date) -> dict:
    """Devuelve metadatos de corte y valores sin redondeos por sucursal.

    En meses anteriores a abril 2026 Wellhub sigue disponible, pero
    TotalPass no se infiere con un tabulador posterior.
    """
    wellhub = _snapshots_in_month(IngresosWellhubSnapshotORM, track_date)
    totalpass_historico = track_date < TOTALPASS_TARIFF_START
    totalpass = (
        {} if totalpass_historico
        else _snapshots_in_month(IngresosTotalpassSnapshotORM, track_date)
    )

    dates = set(wellhub) if totalpass_historico else set(wellhub) & set(totalpass)
    if not dates:
        return {
            "estado": "sin_corte",
            "fecha_corte": None,
            "snapshot_id_wellhub": None,
            "snapshot_id_totalpass": None,
            "por_sucursal": {},
        }

    cutoff = max(dates)
    wh_snapshot = wellhub[cutoff]
    tp_snapshot = None if totalpass_historico else totalpass[cutoff]
    wh_visits = _wellhub_visits(wh_snapshot.id)
    tp_visits = _totalpass_visits(tp_snapshot.id) if tp_snapshot else {}

    per_branch = {}
    for branch in wh_visits.keys() | tp_visits.keys():
        wh = wh_visits.get(branch)
        tp = tp_visits.get(branch)
        wh_eq = Decimal(wh) / TEN if wh is not None else None
        divisor = 12 if branch in TP_GO_DIV_12 else 10 if branch in TP_DIV_10 else None
        tp_eq = Decimal(tp) / Decimal(divisor) if tp is not None and divisor else None
        if tp is not None and divisor is None:
            raise ValueError(f"TotalPass sin divisor aprobado: {branch}.")
        per_branch[branch] = {
            "socios_wellhub_eq": wh_eq,
            "socios_totalpass_eq": tp_eq,
            "socios_agregadoras_eq": (
                wh_eq + tp_eq
                if wh_eq is not None and tp_eq is not None else None
            ),
        }

    return {
        "estado": "parcial_tarifa_historica" if totalpass_historico else "completo",
        "fecha_corte": cutoff.isoformat(),
        "snapshot_id_wellhub": wh_snapshot.id,
        "snapshot_id_totalpass": tp_snapshot.id if tp_snapshot else None,
        "por_sucursal": per_branch,
    }


def add_equivalentes_to_mart_rows(serialized_rows: list[dict], report: dict) -> None:
    """Extiende respuestas de lectura; nunca modifica TrackDailyMartORM."""
    for row in serialized_rows:
        equivalentes = report["por_sucursal"].get(row["sucursal_canon"], {})
        wh = equivalentes.get("socios_wellhub_eq")
        tp = equivalentes.get("socios_totalpass_eq")
        agg = equivalentes.get("socios_agregadoras_eq")
        ultra = row.get("usuarios_activos_actual")
        m2 = row.get("m2_sin_circulaciones")
        total = Decimal(str(ultra)) + agg if ultra is not None and agg is not None else None
        ocupacion = (
            total / Decimal(str(m2))
            if total is not None and m2 is not None and Decimal(str(m2)) > 0
            else None
        )
        row.update({
            "socios_wellhub_eq": float(wh) if wh is not None else None,
            "socios_totalpass_eq": float(tp) if tp is not None else None,
            "socios_agregadoras_eq": float(agg) if agg is not None else None,
            "socios_totales_eq": float(total) if total is not None else None,
            "ocupacion_total_eq": float(ocupacion) if ocupacion is not None else None,
        })
