"""Ciclo de vida de marketing_iventas_sync_runs.

Responsabilidades:

- finalizar un run RUNNING;
- persistir sus contadores finales;
- opcionalmente convertir un COMPLETED válido en canónico;
- reemplazar el canónico anterior del mismo period_key
  dentro de la misma transacción.

No realiza HTTP.
No resuelve aliases.
No persiste raw pages.
No persiste contactos/tags.
No decide por sí mismo si un error operativo es PARTIAL o FAILED.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.extensions import db
from app.models import MarketingIventasSyncRunORM


SYNC_STATUS_RUNNING = "RUNNING"
SYNC_STATUS_COMPLETED = "COMPLETED"
SYNC_STATUS_PARTIAL = "PARTIAL"
SYNC_STATUS_FAILED = "FAILED"

TERMINAL_STATUSES = frozenset(
    {
        SYNC_STATUS_COMPLETED,
        SYNC_STATUS_PARTIAL,
        SYNC_STATUS_FAILED,
    }
)


class MarketingIventasRunLifecycleError(
    RuntimeError
):
    """Inconsistencia al finalizar un sync_run iVentas."""


@dataclass(frozen=True)
class MarketingIventasRunCounters:
    branches_completed: int
    branches_failed: int

    contacts_received: int
    contacts_unique: int
    contacts_with_phone: int
    contacts_mx10_matchable: int
    contacts_non_mx_or_unresolved: int
    contacts_with_first_message: int
    contacts_with_any_tag: int
    contacts_with_meta_ad_tag: int
    contacts_with_multiple_meta_ad_tags: int

    aliases_resolved: int
    aliases_unresolved: int


@dataclass(frozen=True)
class MarketingIventasFinalizeResult:
    sync_run_id: int
    period_key: str
    status: str
    is_canonical: bool
    replaced_canonical_run_id: int | None
    was_already_finalized: bool


_COUNTER_FIELDS = (
    "branches_completed",
    "branches_failed",
    "contacts_received",
    "contacts_unique",
    "contacts_with_phone",
    "contacts_mx10_matchable",
    "contacts_non_mx_or_unresolved",
    "contacts_with_first_message",
    "contacts_with_any_tag",
    "contacts_with_meta_ad_tag",
    "contacts_with_multiple_meta_ad_tags",
    "aliases_resolved",
    "aliases_unresolved",
)


def _utc_now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def _session_or_default(
    session: Any | None,
):
    return (
        session
        if session is not None
        else db.session
    )


def _validate_finished_at(
    finished_at: datetime,
) -> None:
    if (
        finished_at.tzinfo is None
        or finished_at.utcoffset() is None
    ):
        raise ValueError(
            "finished_at debe tener timezone."
        )


def _validate_counters(
    *,
    counters: MarketingIventasRunCounters,
    branches_requested: int,
) -> None:
    if not isinstance(
        counters,
        MarketingIventasRunCounters,
    ):
        raise TypeError(
            "counters debe ser "
            "MarketingIventasRunCounters."
        )

    for field_name in _COUNTER_FIELDS:
        value = getattr(
            counters,
            field_name,
        )

        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
        ):
            raise ValueError(
                f"{field_name} debe ser "
                "un entero no negativo."
            )

    if (
        counters.branches_completed
        + counters.branches_failed
        > branches_requested
    ):
        raise ValueError(
            "branches_completed + branches_failed "
            "no puede superar branches_requested."
        )

    if (
        counters.aliases_resolved
        > branches_requested
    ):
        raise ValueError(
            "aliases_resolved no puede superar "
            "branches_requested."
        )

    if (
        counters.aliases_unresolved
        > branches_requested
    ):
        raise ValueError(
            "aliases_unresolved no puede superar "
            "branches_requested."
        )

    if (
        counters.contacts_unique
        > counters.contacts_received
    ):
        raise ValueError(
            "contacts_unique no puede superar "
            "contacts_received."
        )

    if (
        counters.contacts_with_phone
        > counters.contacts_unique
    ):
        raise ValueError(
            "contacts_with_phone no puede superar "
            "contacts_unique."
        )

    if (
        counters.contacts_mx10_matchable
        > counters.contacts_with_phone
    ):
        raise ValueError(
            "contacts_mx10_matchable no puede superar "
            "contacts_with_phone."
        )

    if (
        counters.contacts_non_mx_or_unresolved
        > counters.contacts_unique
    ):
        raise ValueError(
            "contacts_non_mx_or_unresolved no puede "
            "superar contacts_unique."
        )

    if (
        counters.contacts_with_first_message
        > counters.contacts_unique
    ):
        raise ValueError(
            "contacts_with_first_message no puede "
            "superar contacts_unique."
        )

    if (
        counters.contacts_with_any_tag
        > counters.contacts_unique
    ):
        raise ValueError(
            "contacts_with_any_tag no puede superar "
            "contacts_unique."
        )

    if (
        counters.contacts_with_meta_ad_tag
        > counters.contacts_with_any_tag
    ):
        raise ValueError(
            "contacts_with_meta_ad_tag no puede "
            "superar contacts_with_any_tag."
        )

    if (
        counters.contacts_with_multiple_meta_ad_tags
        > counters.contacts_with_meta_ad_tag
    ):
        raise ValueError(
            "contacts_with_multiple_meta_ad_tags "
            "no puede superar "
            "contacts_with_meta_ad_tag."
        )


def _validate_completed_run(
    *,
    branches_requested: int,
    counters: MarketingIventasRunCounters,
) -> None:
    if (
        counters.branches_completed
        != branches_requested
    ):
        raise MarketingIventasRunLifecycleError(
            "COMPLETED requiere que todas las "
            "sucursales solicitadas estén completadas."
        )

    if counters.branches_failed != 0:
        raise MarketingIventasRunLifecycleError(
            "COMPLETED requiere "
            "branches_failed = 0."
        )

    if (
        counters.aliases_resolved
        != branches_requested
    ):
        raise MarketingIventasRunLifecycleError(
            "COMPLETED requiere que todos los "
            "aliases estén resueltos."
        )

    if counters.aliases_unresolved != 0:
        raise MarketingIventasRunLifecycleError(
            "COMPLETED requiere "
            "aliases_unresolved = 0."
        )


def _apply_counters(
    *,
    run: MarketingIventasSyncRunORM,
    counters: MarketingIventasRunCounters,
) -> None:
    for field_name in _COUNTER_FIELDS:
        setattr(
            run,
            field_name,
            getattr(
                counters,
                field_name,
            ),
        )


def _matches_terminal_state(
    *,
    run: MarketingIventasSyncRunORM,
    status: str,
    counters: MarketingIventasRunCounters,
    make_canonical: bool,
) -> bool:
    if run.status != status:
        return False

    if bool(
        run.is_canonical
    ) != make_canonical:
        return False

    if run.finished_at is None:
        return False

    for field_name in _COUNTER_FIELDS:
        if getattr(
            run,
            field_name,
        ) != getattr(
            counters,
            field_name,
        ):
            return False

    return True


def finalize_iventas_sync_run(
    *,
    sync_run_id: int,
    status: str,
    counters: MarketingIventasRunCounters,
    make_canonical: bool = False,
    finished_at: datetime | None = None,
    session: Any | None = None,
) -> MarketingIventasFinalizeResult:
    """Finaliza un sync_run y opcionalmente lo hace canónico.

    Canonical replacement:

        canonical anterior -> False
        FLUSH
        run actual -> COMPLETED + canonical
        COMMIT

    Todo ocurre dentro de una sola transacción.

    Si el run ya fue finalizado exactamente con el mismo estado,
    counters y canonicalidad, la llamada es idempotente.
    """

    if (
        isinstance(sync_run_id, bool)
        or not isinstance(sync_run_id, int)
        or sync_run_id <= 0
    ):
        raise ValueError(
            "sync_run_id debe ser "
            "un entero positivo."
        )

    status_value = str(
        status or ""
    ).strip().upper()

    if status_value not in TERMINAL_STATUSES:
        raise ValueError(
            "status debe ser COMPLETED, "
            "PARTIAL o FAILED."
        )

    if not isinstance(
        make_canonical,
        bool,
    ):
        raise TypeError(
            "make_canonical debe ser bool."
        )

    finished = (
        finished_at
        if finished_at is not None
        else _utc_now()
    )

    _validate_finished_at(
        finished
    )

    session_value = _session_or_default(
        session
    )

    replaced_canonical_run_id = None

    try:
        run = session_value.get(
            MarketingIventasSyncRunORM,
            sync_run_id,
        )

        if run is None:
            raise MarketingIventasRunLifecycleError(
                "No existe el sync_run indicado."
            )

        branches_requested = int(
            run.branches_requested
        )

        if branches_requested <= 0:
            raise MarketingIventasRunLifecycleError(
                "El sync_run no tiene "
                "branches_requested válido."
            )

        _validate_counters(
            counters=counters,
            branches_requested=(
                branches_requested
            ),
        )

        if (
            run.started_at is None
            or run.started_at.tzinfo is None
            or run.started_at.utcoffset()
            is None
        ):
            raise MarketingIventasRunLifecycleError(
                "started_at del run debe "
                "tener timezone."
            )

        if finished < run.started_at:
            raise ValueError(
                "finished_at no puede ser "
                "anterior a started_at."
            )

        if status_value == SYNC_STATUS_COMPLETED:
            _validate_completed_run(
                branches_requested=(
                    branches_requested
                ),
                counters=counters,
            )

        if make_canonical:
            if (
                status_value
                != SYNC_STATUS_COMPLETED
            ):
                raise MarketingIventasRunLifecycleError(
                    "Solo un run COMPLETED puede "
                    "convertirse en canónico."
                )

            # Repetimos explícitamente la validación de
            # elegibilidad. La DB también tiene su CHECK,
            # pero el service no depende solo de él.
            _validate_completed_run(
                branches_requested=(
                    branches_requested
                ),
                counters=counters,
            )

        if run.status != SYNC_STATUS_RUNNING:
            if _matches_terminal_state(
                run=run,
                status=status_value,
                counters=counters,
                make_canonical=make_canonical,
            ):
                return MarketingIventasFinalizeResult(
                    sync_run_id=int(
                        run.id
                    ),
                    period_key=(
                        run.period_key
                    ),
                    status=run.status,
                    is_canonical=bool(
                        run.is_canonical
                    ),
                    replaced_canonical_run_id=None,
                    was_already_finalized=True,
                )

            raise MarketingIventasRunLifecycleError(
                "El sync_run ya fue finalizado "
                "con un estado diferente."
            )

        if make_canonical:
            canonical_rows = (
                session_value.query(
                    MarketingIventasSyncRunORM
                )
                .filter_by(
                    period_key=run.period_key,
                    is_canonical=True,
                )
                .all()
            )

            previous_rows = [
                row
                for row in canonical_rows
                if int(row.id)
                != int(run.id)
            ]

            if len(previous_rows) > 1:
                raise MarketingIventasRunLifecycleError(
                    "Existe más de un canónico previo "
                    "para el mismo period_key."
                )

            if previous_rows:
                previous = previous_rows[0]

                previous.is_canonical = False

                replaced_canonical_run_id = int(
                    previous.id
                )

                # Este flush es intencional.
                # El índice parcial UNIQUE de PostgreSQL
                # exige retirar primero el canónico previo.
                # Todavía NO hay commit.
                session_value.flush()

        _apply_counters(
            run=run,
            counters=counters,
        )

        run.status = status_value
        run.finished_at = finished
        run.is_canonical = make_canonical

        session_value.commit()

        return MarketingIventasFinalizeResult(
            sync_run_id=int(
                run.id
            ),
            period_key=run.period_key,
            status=run.status,
            is_canonical=bool(
                run.is_canonical
            ),
            replaced_canonical_run_id=(
                replaced_canonical_run_id
            ),
            was_already_finalized=False,
        )

    except Exception:
        session_value.rollback()
        raise
