#    backend\app\track_alerts\services\track_alert_rules_service.py


from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from app.extensions import db
from app.models.warehouse import TrackDailyMartORM


@dataclass(frozen=True)
class TrackAlertCandidate:
    track_date: date
    sucursal_canon: str | None
    alert_code: str
    severity: str
    title: str
    message: str
    metric_value: Decimal | None = None
    threshold_value: Decimal | None = None
    ranking_position: int | None = None
    metadata_json: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "track_date": self.track_date.isoformat(),
            "sucursal_canon": self.sucursal_canon,
            "alert_code": self.alert_code,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "metric_value": str(self.metric_value) if self.metric_value is not None else None,
            "threshold_value": str(self.threshold_value) if self.threshold_value is not None else None,
            "ranking_position": self.ranking_position,
            "metadata_json": self.metadata_json or {},
        }


def evaluate_track_alerts(
    track_date: date,
    generation_mode: str = "manual_preview",
) -> list[TrackAlertCandidate]:
    rows = (
        db.session.query(TrackDailyMartORM)
        .filter(
            TrackDailyMartORM.track_date == track_date,
            TrackDailyMartORM.generation_mode == generation_mode,
        )
        .all()
    )

    if not rows:
        return []

    alerts: list[TrackAlertCandidate] = []
    alerts.extend(_evaluate_income_ranking(track_date=track_date, rows=rows))
    alerts.extend(_evaluate_new_clients_ranking(track_date=track_date, rows=rows))

    return alerts


def _get_income_value(row: TrackDailyMartORM) -> Decimal:
    value = row.ingreso_real_total_mtd
    if value is None:
        value = row.ingreso_real_mtd
    return Decimal(value or 0)


def _evaluate_income_ranking(
    track_date: date,
    rows: list[TrackDailyMartORM],
) -> list[TrackAlertCandidate]:
    eligible_rows = [
        row
        for row in rows
        if _has_faycgo_target(row)
    ]

    ranked_rows = sorted(
        eligible_rows,
        key=_get_income_value,
        reverse=True,
    )

    if len(ranked_rows) < 6:
        return []

    alerts: list[TrackAlertCandidate] = []

    top_rows = ranked_rows[:3]
    bottom_rows = list(reversed(ranked_rows[-3:]))

    for index, row in enumerate(top_rows, start=1):
        income_value = _get_income_value(row)

        alerts.append(
            TrackAlertCandidate(
                track_date=track_date,
                sucursal_canon=row.sucursal_canon,
                alert_code="TOP_INGRESOS_MTD",
                severity="SUCCESS",
                title=f"Top {index} nacional en ingreso real acumulado",
                message=(
                    f"{row.sucursal_canon} está en posición {index} nacional "
                    f"por ingreso real acumulado del mes."
                ),
                metric_value=income_value,
                ranking_position=index,
                metadata_json={
                    "metric": "ingreso_real_total_mtd",
                    "generation_mode": row.generation_mode,
                    "total_branches": len(ranked_rows),
                    "eligibility_rule": "meta_faycgo_mes > 0",
                },
            )
        )

    total = len(ranked_rows)
    for offset, row in enumerate(bottom_rows, start=0):
        position = total - offset
        income_value = _get_income_value(row)

        alerts.append(
            TrackAlertCandidate(
                track_date=track_date,
                sucursal_canon=row.sucursal_canon,
                alert_code="BOTTOM_INGRESOS_MTD",
                severity="WARNING",
                title=f"Riesgo: posición {position} nacional en ingreso real",
                message=(
                    f"{row.sucursal_canon} está en posición {position} de {total} "
                    f"por ingreso real acumulado del mes."
                ),
                metric_value=income_value,
                ranking_position=position,
                metadata_json={
                    "metric": "ingreso_real_total_mtd",
                    "generation_mode": row.generation_mode,
                    "total_branches": total,
                    "eligibility_rule": "meta_faycgo_mes > 0",
                },
            )
        )

    return alerts

def _evaluate_new_clients_ranking(
    track_date: date,
    rows: list[TrackDailyMartORM],
) -> list[TrackAlertCandidate]:
    eligible_rows = [
        row
        for row in rows
        if _has_faycgo_target(row)
    ]

    ranked_rows = sorted(
        eligible_rows,
        key=lambda row: row.clientes_nuevos_real_mtd or 0,
        reverse=True,
    )

    if len(ranked_rows) < 6:
        return []

    alerts: list[TrackAlertCandidate] = []

    top_rows = ranked_rows[:3]
    bottom_rows = list(reversed(ranked_rows[-3:]))

    for index, row in enumerate(top_rows, start=1):
        value = row.clientes_nuevos_real_mtd or 0

        alerts.append(
            TrackAlertCandidate(
                track_date=track_date,
                sucursal_canon=row.sucursal_canon,
                alert_code="TOP_CLIENTES_NUEVOS_MTD",
                severity="SUCCESS",
                title=f"Top {index} nacional en clientes nuevos",
                message=(
                    f"{row.sucursal_canon} está en posición {index} nacional "
                    f"por clientes nuevos acumulados del mes."
                ),
                metric_value=Decimal(value),
                ranking_position=index,
                metadata_json={
                    "metric": "clientes_nuevos_real_mtd",
                    "generation_mode": row.generation_mode,
                    "total_branches": len(ranked_rows),
                    "eligibility_rule": "meta_faycgo_mes > 0",
                },
            )
        )

    total = len(ranked_rows)
    for offset, row in enumerate(bottom_rows, start=0):
        position = total - offset
        value = row.clientes_nuevos_real_mtd or 0

        alerts.append(
            TrackAlertCandidate(
                track_date=track_date,
                sucursal_canon=row.sucursal_canon,
                alert_code="BOTTOM_CLIENTES_NUEVOS_MTD",
                severity="WARNING",
                title=f"Riesgo: posición {position} nacional en clientes nuevos",
                message=(
                    f"{row.sucursal_canon} está en posición {position} de {total} "
                    f"por clientes nuevos acumulados del mes."
                ),
                metric_value=Decimal(value),
                ranking_position=position,
                metadata_json={
                    "metric": "clientes_nuevos_real_mtd",
                    "generation_mode": row.generation_mode,
                    "total_branches": total,
                    "eligibility_rule": "meta_faycgo_mes > 0",
                },
            )
        )

    return alerts
def _has_faycgo_target(row: TrackDailyMartORM) -> bool:
    return Decimal(row.meta_faycgo_mes or 0) > 0