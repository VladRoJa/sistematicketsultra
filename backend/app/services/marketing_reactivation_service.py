"""Lectura operativa para Reactivación de socios en Marketing.

Esta capa expone fuentes disponibles y enriquece el resultado del
resolver de reactivación. No clasifica candidatos ni escribe datos.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.extensions import db
from app.models import MarketingIventasSyncRunORM
from app.models.warehouse import (
    SociosVencidosSnapshotORM,
    SociosVencidosSnapshotRowORM,
)
from app.warehouse.services.socios_vencidos_reactivation_candidate_resolver import (
    SociosVencidosReactivationCandidateResolverError,
    resolve_socios_vencidos_reactivation_candidates,
)


def _session_or_default(session: Any | None):
    return session if session is not None else db.session


def list_marketing_reactivation_sources(
    *,
    session: Any | None = None,
) -> dict[str, list[dict[str, object]]]:
    """Lista cortes vencidos y runs iVentas canónicos disponibles."""

    active_session = _session_or_default(session)

    vencidos_snapshots = (
        active_session.query(SociosVencidosSnapshotORM)
        .order_by(
            SociosVencidosSnapshotORM.date_to.desc(),
            SociosVencidosSnapshotORM.id.desc(),
        )
        .all()
    )

    iventas_runs = (
        active_session.query(MarketingIventasSyncRunORM)
        .filter(
            MarketingIventasSyncRunORM.status == "COMPLETED",
            MarketingIventasSyncRunORM.is_canonical.is_(True),
        )
        .order_by(
            MarketingIventasSyncRunORM.date_to.desc(),
            MarketingIventasSyncRunORM.id.desc(),
        )
        .all()
    )

    return {
        "vencidos_snapshots": [
            {
                "id": int(snapshot.id),
                "date_from": _serialize_date(snapshot.date_from),
                "date_to": _serialize_date(snapshot.date_to),
                # El modelo estructurado de Socios Vencidos no
                # persiste snapshot_kind. No se infiere desde otro campo.
                "snapshot_kind": None,
                "row_count": int(snapshot.row_count_valid),
            }
            for snapshot in vencidos_snapshots
        ],
        "iventas_periods": [
            {
                "period_key": str(run.period_key),
                "sync_run_id": int(run.id),
                "date_from": _serialize_date(run.date_from),
                "date_to": _serialize_date(run.date_to),
                "contacts_unique": int(run.contacts_unique),
            }
            for run in iventas_runs
        ],
    }


def build_marketing_reactivation_candidates(
    *,
    vencidos_snapshot_id: int,
    iventas_period_key: str,
    session: Any | None = None,
) -> dict[str, object]:
    """Resuelve y enriquece candidatos sin modificar persistencia."""

    active_session = _session_or_default(session)
    result = resolve_socios_vencidos_reactivation_candidates(
        vencidos_snapshot_id=vencidos_snapshot_id,
        iventas_period_key=iventas_period_key,
        activos_snapshot_id=None,
        session=active_session,
    )

    row_ids = tuple(
        sorted(int(candidate.vencido_row_id) for candidate in result.rows)
    )

    vencido_rows = []
    if row_ids:
        vencido_rows = (
            active_session.query(SociosVencidosSnapshotRowORM)
            .filter(
                SociosVencidosSnapshotRowORM.snapshot_id
                == int(result.vencidos_snapshot_id),
                SociosVencidosSnapshotRowORM.id.in_(row_ids),
            )
            .all()
        )

    vencido_rows_by_id = {
        int(row.id): row
        for row in vencido_rows
    }
    missing_row_ids = set(row_ids) - vencido_rows_by_id.keys()
    if missing_row_ids:
        raise SociosVencidosReactivationCandidateResolverError(
            "No se pudieron enriquecer filas del snapshot de vencidos: "
            f"{sorted(missing_row_ids)}."
        )

    return {
        "sources": {
            "vencidos_snapshot_id": int(result.vencidos_snapshot_id),
            "activos_snapshot_id": int(result.activos_snapshot_id),
            "iventas_sync_run_id": int(result.iventas_sync_run_id),
            "iventas_period_key": str(result.iventas_period_key),
        },
        "summary": {
            "total_rows": int(result.total_rows),
            "status_counts": dict(result.status_counts),
            "reason_counts": dict(result.reason_counts),
        },
        "rows": [
            _serialize_candidate(
                candidate=candidate,
                vencido_row=vencido_rows_by_id[
                    int(candidate.vencido_row_id)
                ],
            )
            for candidate in result.rows
        ],
    }


def _serialize_candidate(
    *,
    candidate: Any,
    vencido_row: Any,
) -> dict[str, object]:
    return {
        "vencido_row_id": int(candidate.vencido_row_id),
        "pin": str(vencido_row.pin),
        "nombre": vencido_row.nombre,
        "sucursal": vencido_row.sucursal_raw,
        "telefono": vencido_row.telefono_raw,
        "correo": vencido_row.correo_raw,
        "fecha_vencimiento": _serialize_date(
            vencido_row.fecha_vencimiento_date
        ),
        "fecha_ultimo_pago": _serialize_optional_date(
            vencido_row.fecha_ultimo_pago_local
        ),
        "tarifa": vencido_row.tarifa,
        "adeudo": _serialize_optional_decimal(vencido_row.adeudo),
        "status": str(candidate.status),
        "reason": str(candidate.reason),
        "active_status": str(candidate.active_status),
        "active_id_socio": candidate.active_id_socio,
        "iventas_contact_id": candidate.iventas_contact_id,
        "latest_outbound_at_utc": _serialize_optional_aware_datetime(
            candidate.latest_outbound_at_utc
        ),
    }


def _serialize_date(value: date | datetime) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value.isoformat()


def _serialize_optional_date(value: date | datetime | None) -> str | None:
    return None if value is None else _serialize_date(value)


def _serialize_optional_decimal(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _serialize_optional_aware_datetime(
    value: datetime | None,
) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise SociosVencidosReactivationCandidateResolverError(
            "latest_outbound_at_utc debe incluir zona horaria."
        )
    return value.isoformat()
