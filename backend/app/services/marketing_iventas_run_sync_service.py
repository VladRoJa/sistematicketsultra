"""Orquestador de corrida completa iVentas Contactos V1.

Responsabilidades:

- leer dinámicamente aliases activos iventas_family;
- validar todos los aliases antes del primer request HTTP;
- crear el sync_run RUNNING;
- ejecutar cada branch de forma secuencial;
- continuar ante fallas operativas conocidas de una branch;
- reconstruir counters desde PostgreSQL;
- decidir COMPLETED / PARTIAL / FAILED;
- delegar canonicalidad al lifecycle.

No implementa:

- endpoint Flask;
- scheduler;
- definición de lead;
- Meta Ads;
- contacto -> visita;
- retry parcial dentro del mismo run.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import logging
from typing import Any

from app.extensions import db
from app.integrations.iventas.client import (
    IventasClient,
    IventasClientError,
)
from app.models.warehouse import (
    TrackBranchAliasORM,
)
from app.services.marketing_iventas_branch_service import (
    IVENTAS_ALIAS_SOURCE_FAMILY,
    MarketingIventasBranchResolution,
    MarketingIventasBranchResolutionError,
    resolve_iventas_branch,
)
from app.services.marketing_iventas_branch_sync_service import (
    MarketingIventasBranchSyncError,
    sync_iventas_branch_pages,
)
from app.services.marketing_iventas_persistence_service import (
    create_iventas_sync_run_running,
)
from app.services.marketing_iventas_run_counters_service import (
    read_iventas_stored_run_counters,
)
from app.services.marketing_iventas_run_lifecycle_service import (
    MarketingIventasRunCounters,
    SYNC_STATUS_COMPLETED,
    SYNC_STATUS_FAILED,
    SYNC_STATUS_PARTIAL,
    finalize_iventas_sync_run,
)
from app.services.marketing_iventas_service import (
    build_iventas_utc_period,
)


logger = logging.getLogger(__name__)


IVENTAS_V1_EXPECTED_BRANCH_COUNT = 26


class MarketingIventasRunSyncError(
    RuntimeError
):
    """Inconsistencia propia del orquestador."""


@dataclass(frozen=True)
class MarketingIventasRunBranchFailure:
    branch_code: str
    error_type: str


@dataclass(frozen=True)
class MarketingIventasRunSyncResult:
    sync_run_id: int
    period_key: str
    status: str
    is_canonical: bool

    branches_requested: int
    branches_completed: int
    branches_failed: int

    aliases_resolved: int
    aliases_unresolved: int

    failed_branches: tuple[
        MarketingIventasRunBranchFailure,
        ...,
    ]

    replaced_canonical_run_id: int | None


_OPERATIONAL_BRANCH_ERRORS = (
    IventasClientError,
    MarketingIventasBranchSyncError,
    MarketingIventasBranchResolutionError,
)


def _session_or_default(
    session: Any | None,
):
    return (
        session
        if session is not None
        else db.session
    )


def _validate_positive_int(
    value: Any,
    *,
    field_name: str,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise ValueError(
            f"{field_name} debe ser "
            "un entero positivo."
        )

    return value


def _validate_period_key(
    period_key: Any,
) -> str:
    value = str(
        period_key or ""
    ).strip()

    if not value:
        raise ValueError(
            "period_key no puede estar vacío."
        )

    if len(value) > 64:
        raise ValueError(
            "period_key excede 64 caracteres."
        )

    return value


def _load_active_iventas_branch_codes(
    *,
    session: Any,
) -> tuple[str, ...]:
    rows = (
        session.query(
            TrackBranchAliasORM
        )
        .filter(
            TrackBranchAliasORM.source_family
            == IVENTAS_ALIAS_SOURCE_FAMILY,
            TrackBranchAliasORM.is_active
            .is_(True),
        )
        .order_by(
            TrackBranchAliasORM.raw_branch_name
        )
        .all()
    )

    branch_codes = tuple(
        str(
            row.raw_branch_name or ""
        ).strip()
        for row in rows
    )

    if not branch_codes:
        raise MarketingIventasRunSyncError(
            "No existen aliases activos "
            "iventas_family."
        )

    if any(
        not branch_code
        for branch_code in branch_codes
    ):
        raise MarketingIventasRunSyncError(
            "Existe un alias iVentas activo "
            "sin raw_branch_name válido."
        )

    if (
        len(set(branch_codes))
        != len(branch_codes)
    ):
        raise MarketingIventasRunSyncError(
            "Existen códigos iVentas "
            "duplicados entre aliases activos."
        )

    if (
        len(branch_codes)
        != IVENTAS_V1_EXPECTED_BRANCH_COUNT
    ):
        raise MarketingIventasRunSyncError(
            "iVentas Contactos V1 requiere "
            f"{IVENTAS_V1_EXPECTED_BRANCH_COUNT} "
            "aliases activos iventas_family; "
            f"se encontraron {len(branch_codes)}."
        )

    return branch_codes


def _pre_resolve_branches(
    branch_codes: tuple[str, ...],
) -> tuple[
    tuple[MarketingIventasBranchResolution, ...],
    tuple[MarketingIventasRunBranchFailure, ...],
]:
    resolved: list[
        MarketingIventasBranchResolution
    ] = []

    failures: list[
        MarketingIventasRunBranchFailure
    ] = []

    for branch_code in branch_codes:
        try:
            resolution = resolve_iventas_branch(
                branch_code
            )

        except MarketingIventasBranchResolutionError:
            failures.append(
                MarketingIventasRunBranchFailure(
                    branch_code=branch_code,
                    error_type=(
                        "MarketingIventasBranchResolutionError"
                    ),
                )
            )
            continue

        if resolution is None:
            failures.append(
                MarketingIventasRunBranchFailure(
                    branch_code=branch_code,
                    error_type="ALIAS_UNRESOLVED",
                )
            )
            continue

        resolved.append(
            resolution
        )

    # --------------------------------------------------------
    # Un destino Suite no debe corresponder a varios códigos
    # activos iVentas dentro de la misma corrida.
    # --------------------------------------------------------

    by_sucursal_id: dict[
        int,
        list[
            MarketingIventasBranchResolution
        ],
    ] = {}

    for resolution in resolved:
        by_sucursal_id.setdefault(
            resolution.sucursal_id,
            [],
        ).append(
            resolution
        )

    ambiguous_codes = {
        resolution.branch_code
        for group in by_sucursal_id.values()
        if len(group) > 1
        for resolution in group
    }

    if ambiguous_codes:
        clean_resolved = []

        for resolution in resolved:
            if (
                resolution.branch_code
                in ambiguous_codes
            ):
                failures.append(
                    MarketingIventasRunBranchFailure(
                        branch_code=(
                            resolution.branch_code
                        ),
                        error_type=(
                            "ALIAS_AMBIGUOUS_DESTINATION"
                        ),
                    )
                )
            else:
                clean_resolved.append(
                    resolution
                )

        resolved = clean_resolved

    resolved.sort(
        key=lambda item: (
            item.sucursal_id,
            item.branch_code,
        )
    )

    failures.sort(
        key=lambda item: item.branch_code
    )

    return (
        tuple(resolved),
        tuple(failures),
    )


def _build_run_counters(
    *,
    branches_completed: int,
    branches_failed: int,
    aliases_resolved: int,
    aliases_unresolved: int,
    stored: Any,
) -> MarketingIventasRunCounters:
    return MarketingIventasRunCounters(
        branches_completed=branches_completed,
        branches_failed=branches_failed,
        contacts_received=(
            stored.contacts_received
        ),
        contacts_unique=(
            stored.contacts_unique
        ),
        contacts_with_phone=(
            stored.contacts_with_phone
        ),
        contacts_mx10_matchable=(
            stored.contacts_mx10_matchable
        ),
        contacts_non_mx_or_unresolved=(
            stored.contacts_non_mx_or_unresolved
        ),
        contacts_with_first_message=(
            stored.contacts_with_first_message
        ),
        contacts_with_any_tag=(
            stored.contacts_with_any_tag
        ),
        contacts_with_meta_ad_tag=(
            stored.contacts_with_meta_ad_tag
        ),
        contacts_with_multiple_meta_ad_tags=(
            stored
            .contacts_with_multiple_meta_ad_tags
        ),
        aliases_resolved=aliases_resolved,
        aliases_unresolved=aliases_unresolved,
    )


def _determine_terminal_status(
    *,
    branches_requested: int,
    branches_completed: int,
    branches_failed: int,
    aliases_unresolved: int,
) -> str:
    if (
        branches_completed
        + branches_failed
        != branches_requested
    ):
        raise MarketingIventasRunSyncError(
            "La contabilidad de branches "
            "no cubre branches_requested."
        )

    if (
        aliases_unresolved == 0
        and branches_completed
        == branches_requested
        and branches_failed == 0
    ):
        return SYNC_STATUS_COMPLETED

    if branches_completed > 0:
        return SYNC_STATUS_PARTIAL

    return SYNC_STATUS_FAILED


def sync_iventas_full_run(
    *,
    period_key: str,
    date_from: date,
    date_to: date,
    client: Any | None = None,
    page_limit: int = 100,
    max_pages: int = 10000,
    make_canonical_on_completed: bool = True,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    session: Any | None = None,
) -> MarketingIventasRunSyncResult:
    """Ejecuta una extracción completa de aliases iVentas activos.

    Fallas operativas conocidas de una branch:

    - IventasClientError;
    - MarketingIventasBranchSyncError;
    - MarketingIventasBranchResolutionError.

    Esas fallas se contabilizan y la corrida continúa.

    Excepciones inesperadas NO se convierten artificialmente
    en PARTIAL/FAILED. Se propagan para no ocultar bugs,
    inconsistencias ORM o errores de programación.
    """

    period_key_value = _validate_period_key(
        period_key
    )

    _validate_positive_int(
        page_limit,
        field_name="page_limit",
    )

    if page_limit > 100:
        raise ValueError(
            "page_limit no puede superar 100."
        )

    _validate_positive_int(
        max_pages,
        field_name="max_pages",
    )

    if not isinstance(
        make_canonical_on_completed,
        bool,
    ):
        raise TypeError(
            "make_canonical_on_completed "
            "debe ser bool."
        )

    utc_period = build_iventas_utc_period(
        date_from=date_from,
        date_to=date_to,
    )

    session_value = _session_or_default(
        session
    )

    # ========================================================
    # 1. ALIASES DINÁMICOS
    # ========================================================

    branch_codes = (
        _load_active_iventas_branch_codes(
            session=session_value
        )
    )

    branches_requested = len(
        branch_codes
    )

    # ========================================================
    # 2. PRE-RESOLVER TODOS ANTES DE HTTP
    # ========================================================

    (
        resolutions,
        alias_failures,
    ) = _pre_resolve_branches(
        branch_codes
    )

    aliases_resolved = len(
        resolutions
    )

    aliases_unresolved = (
        branches_requested
        - aliases_resolved
    )

    if (
        aliases_resolved
        + aliases_unresolved
        != branches_requested
    ):
        raise MarketingIventasRunSyncError(
            "La contabilidad de aliases "
            "no cubre branches_requested."
        )

    # --------------------------------------------------------
    # Si aliases están completos, validar configuración del
    # cliente ANTES de crear el run.
    # --------------------------------------------------------

    client_value = client

    if (
        aliases_unresolved == 0
        and client_value is None
    ):
        client_value = IventasClient()

    # ========================================================
    # 3. CREAR RUN
    # ========================================================

    run = create_iventas_sync_run_running(
        period_key=period_key_value,
        date_from=date_from,
        date_to=date_to,
        branches_requested=branches_requested,
        started_at=started_at,
        session=session_value,
    )

    if run.id is None:
        raise MarketingIventasRunSyncError(
            "sync_run creado sin id."
        )

    sync_run_id = int(
        run.id
    )

    # ========================================================
    # 4. ALIAS INCOMPLETO = FAILED SIN HTTP
    # ========================================================

    if aliases_unresolved > 0:
        stored = (
            read_iventas_stored_run_counters(
                sync_run_id=sync_run_id,
                session=session_value,
            )
        )

        counters = _build_run_counters(
            branches_completed=0,
            branches_failed=branches_requested,
            aliases_resolved=aliases_resolved,
            aliases_unresolved=aliases_unresolved,
            stored=stored,
        )

        finalized = finalize_iventas_sync_run(
            sync_run_id=sync_run_id,
            status=SYNC_STATUS_FAILED,
            counters=counters,
            make_canonical=False,
            finished_at=finished_at,
            session=session_value,
        )

        return MarketingIventasRunSyncResult(
            sync_run_id=sync_run_id,
            period_key=period_key_value,
            status=finalized.status,
            is_canonical=(
                finalized.is_canonical
            ),
            branches_requested=(
                branches_requested
            ),
            branches_completed=0,
            branches_failed=(
                branches_requested
            ),
            aliases_resolved=(
                aliases_resolved
            ),
            aliases_unresolved=(
                aliases_unresolved
            ),
            failed_branches=(
                alias_failures
            ),
            replaced_canonical_run_id=(
                finalized
                .replaced_canonical_run_id
            ),
        )

    # ========================================================
    # 5. EJECUTAR BRANCHES
    # ========================================================

    branches_completed = 0
    branches_failed = 0

    operational_failures: list[
        MarketingIventasRunBranchFailure
    ] = []

    for resolution in resolutions:
        try:
            sync_iventas_branch_pages(
                sync_run_id=sync_run_id,
                branch_code=(
                    resolution.branch_code
                ),
                from_utc=(
                    utc_period.from_iso_z
                ),
                to_utc=(
                    utc_period.to_iso_z
                ),
                client=client_value,
                page_limit=page_limit,
                max_pages=max_pages,
                session=session_value,
            )

        except _OPERATIONAL_BRANCH_ERRORS as exc:
            # Puede existir evidencia ya COMMITeada por
            # raw-first. Solo limpiamos la transacción
            # actualmente fallida/no confirmada.
            session_value.rollback()

            branches_failed += 1

            failure = (
                MarketingIventasRunBranchFailure(
                    branch_code=(
                        resolution.branch_code
                    ),
                    error_type=(
                        exc.__class__.__name__
                    ),
                )
            )

            operational_failures.append(
                failure
            )

            logger.warning(
                "iVentas branch failed "
                "run=%s branch=%s error_type=%s",
                sync_run_id,
                resolution.branch_code,
                failure.error_type,
            )

            continue

        except Exception as unexpected_exc:
            # No ocultar bugs o inconsistencias no
            # clasificadas como falla operacional.
            #
            # El run ya fue COMMITeado como RUNNING antes
            # del primer HTTP. Cerramos el snapshot como
            # FAILED con la evidencia realmente persistida,
            # pero después propagamos la excepción original.
            session_value.rollback()

            logger.exception(
                "iVentas unexpected branch failure "
                "run=%s branch=%s error_type=%s",
                sync_run_id,
                resolution.branch_code,
                unexpected_exc.__class__.__name__,
            )

            try:
                stored = (
                    read_iventas_stored_run_counters(
                        sync_run_id=sync_run_id,
                        session=session_value,
                    )
                )

                aborted_branches_failed = (
                    branches_requested
                    - branches_completed
                )

                abort_counters = _build_run_counters(
                    branches_completed=(
                        branches_completed
                    ),
                    branches_failed=(
                        aborted_branches_failed
                    ),
                    aliases_resolved=(
                        aliases_resolved
                    ),
                    aliases_unresolved=0,
                    stored=stored,
                )

                finalize_iventas_sync_run(
                    sync_run_id=sync_run_id,
                    status=SYNC_STATUS_FAILED,
                    counters=abort_counters,
                    make_canonical=False,
                    finished_at=finished_at,
                    session=session_value,
                )

            except Exception:
                # El cleanup nunca debe esconder la
                # excepción original que abortó el run.
                session_value.rollback()

                logger.exception(
                    "iVentas failed to finalize "
                    "aborted run=%s after "
                    "unexpected error_type=%s",
                    sync_run_id,
                    unexpected_exc
                    .__class__.__name__,
                )

            raise

        branches_completed += 1

    if (
        branches_completed
        + branches_failed
        != branches_requested
    ):
        raise MarketingIventasRunSyncError(
            "La ejecución no contabilizó "
            "todas las branches solicitadas."
        )

    # ========================================================
    # 6. RECONSTRUIR COUNTERS DESDE POSTGRES
    # ========================================================

    stored = (
        read_iventas_stored_run_counters(
            sync_run_id=sync_run_id,
            session=session_value,
        )
    )

    # ========================================================
    # 7. STATUS TERMINAL
    # ========================================================

    status = _determine_terminal_status(
        branches_requested=(
            branches_requested
        ),
        branches_completed=(
            branches_completed
        ),
        branches_failed=(
            branches_failed
        ),
        aliases_unresolved=0,
    )

    counters = _build_run_counters(
        branches_completed=(
            branches_completed
        ),
        branches_failed=(
            branches_failed
        ),
        aliases_resolved=(
            aliases_resolved
        ),
        aliases_unresolved=0,
        stored=stored,
    )

    make_canonical = (
        status == SYNC_STATUS_COMPLETED
        and make_canonical_on_completed
    )

    # ========================================================
    # 8. LIFECYCLE
    # ========================================================

    finalized = finalize_iventas_sync_run(
        sync_run_id=sync_run_id,
        status=status,
        counters=counters,
        make_canonical=make_canonical,
        finished_at=finished_at,
        session=session_value,
    )

    failures = tuple(
        sorted(
            operational_failures,
            key=lambda item: (
                item.branch_code
            ),
        )
    )

    return MarketingIventasRunSyncResult(
        sync_run_id=sync_run_id,
        period_key=period_key_value,
        status=finalized.status,
        is_canonical=(
            finalized.is_canonical
        ),
        branches_requested=(
            branches_requested
        ),
        branches_completed=(
            branches_completed
        ),
        branches_failed=(
            branches_failed
        ),
        aliases_resolved=(
            aliases_resolved
        ),
        aliases_unresolved=0,
        failed_branches=failures,
        replaced_canonical_run_id=(
            finalized
            .replaced_canonical_run_id
        ),
    )
