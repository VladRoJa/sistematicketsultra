"""Orquestación de una sucursal iVentas completa.

Secuencia obligatoria por página:

    HTTP raw
    -> COMMIT raw
    -> parse
    -> COMMIT metadata
    -> normalize
    -> COMMIT contacts/tags
    -> cursor siguiente

Este módulo NO:
- crea sync_runs;
- finaliza sync_runs;
- decide COMPLETED/PARTIAL/FAILED;
- reemplaza canonicalidad;
- recorre las 26 sucursales.

V1 solo acepta una sucursal que todavía no tenga raw pages
dentro del run. Resume/retry de sucursal parcial se diseñará
por separado para no mezclar snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.extensions import db
from app.integrations.iventas import IventasClient
from app.models import (
    MarketingIventasRawPageORM,
    MarketingIventasSyncRunORM,
)
from app.services.marketing_iventas_branch_service import (
    resolve_iventas_branch,
)
from app.services.marketing_iventas_persistence_service import (
    apply_iventas_raw_page_parse_metadata,
    persist_iventas_raw_page_pre_parse,
)
from app.services.marketing_iventas_service import (
    normalize_iventas_contact,
)
from app.services.marketing_iventas_structured_persistence_service import (
    persist_iventas_normalized_page,
)


SYNC_STATUS_RUNNING = "RUNNING"


class MarketingIventasBranchSyncError(
    RuntimeError
):
    """Inconsistencia durante sync de una sucursal iVentas."""


@dataclass(frozen=True)
class MarketingIventasBranchSyncResult:
    sync_run_id: int
    branch_code: str
    sucursal_canon: str
    sucursal_id: int

    pages_processed: int
    contacts_received: int
    contacts_created: int
    contacts_existing: int
    tags_created: int


def _session_or_default(
    session: Any | None,
):
    return (
        session
        if session is not None
        else db.session
    )


def _utc_now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def sync_iventas_branch_pages(
    *,
    sync_run_id: int,
    branch_code: str,
    from_utc: str,
    to_utc: str,
    client: IventasClient,
    page_limit: int = 100,
    max_pages: int = 10000,
    session: Any | None = None,
) -> MarketingIventasBranchSyncResult:
    """Sincroniza todas las páginas de una sola sucursal.

    Cada raw page se confirma antes de intentar parsearla.

    V1 exige que la sucursal no tenga raw pages previas
    dentro de este run. Esto evita hacer un nuevo request
    contra una fuente mutable y mezclarlo silenciosamente
    con una extracción parcial previa.
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

    branch_value = str(
        branch_code or ""
    ).strip()

    if not branch_value:
        raise ValueError(
            "branch_code no puede estar vacío."
        )

    from_value = str(
        from_utc or ""
    ).strip()

    to_value = str(
        to_utc or ""
    ).strip()

    if not from_value:
        raise ValueError(
            "from_utc no puede estar vacío."
        )

    if not to_value:
        raise ValueError(
            "to_utc no puede estar vacío."
        )

    if (
        isinstance(page_limit, bool)
        or not isinstance(page_limit, int)
        or page_limit <= 0
    ):
        raise ValueError(
            "page_limit debe ser "
            "un entero positivo."
        )

    if (
        isinstance(max_pages, bool)
        or not isinstance(max_pages, int)
        or max_pages <= 0
    ):
        raise ValueError(
            "max_pages debe ser "
            "un entero positivo."
        )

    if client is None:
        raise TypeError(
            "client es requerido."
        )

    session_value = _session_or_default(
        session
    )

    # ========================================================
    # PRECONDICION RUN
    # ========================================================

    run = session_value.get(
        MarketingIventasSyncRunORM,
        sync_run_id,
    )

    if run is None:
        raise MarketingIventasBranchSyncError(
            "No existe el sync_run indicado."
        )

    if run.status != SYNC_STATUS_RUNNING:
        raise MarketingIventasBranchSyncError(
            "La sucursal solo puede sincronizarse "
            "dentro de un run RUNNING."
        )

    # ========================================================
    # RESOLVER SUCURSAL
    # ========================================================

    resolution = resolve_iventas_branch(
        branch_value
    )

    if resolution is None:
        raise MarketingIventasBranchSyncError(
            "branch_code no resolvió mediante "
            "iventas_family."
        )

    canonical_branch_code = (
        resolution.branch_code
    )

    # ========================================================
    # V1 = SOLO BRANCH FRESCA
    # ========================================================

    existing_raw = (
        session_value.query(
            MarketingIventasRawPageORM
        )
        .filter_by(
            sync_run_id=sync_run_id,
            branch_code=canonical_branch_code,
        )
        .first()
    )

    if existing_raw is not None:
        raise MarketingIventasBranchSyncError(
            "La sucursal ya tiene raw pages "
            "dentro de este run. "
            "Resume/retry parcial no está "
            "habilitado en esta versión."
        )

    # ========================================================
    # PAGINACION
    # ========================================================

    page_number = 1
    cursor = None

    seen_request_cursors = {
        None
    }

    pages_processed = 0
    contacts_received = 0
    contacts_created = 0
    contacts_existing = 0
    tags_created = 0

    while True:

        if page_number > max_pages:
            raise MarketingIventasBranchSyncError(
                "Se alcanzó max_pages antes "
                "de terminar la paginación."
            )

        # ----------------------------------------------------
        # 1. HTTP RAW
        # ----------------------------------------------------

        raw_response = client.request_page_raw(
            branch=canonical_branch_code,
            from_utc=from_value,
            to_utc=to_value,
            limit=page_limit,
            cursor=cursor,
        )

        # ----------------------------------------------------
        # 2. COMMIT RAW PRE-PARSE
        # ----------------------------------------------------

        raw_row = persist_iventas_raw_page_pre_parse(
            sync_run_id=sync_run_id,
            branch_code=canonical_branch_code,
            page_number=page_number,
            raw_response=raw_response,
            received_at=_utc_now(),
            session=session_value,
        )

        if raw_row.id is None:
            raise MarketingIventasBranchSyncError(
                "Raw page persistida sin id."
            )

        # ----------------------------------------------------
        # 3. PARSE
        # ----------------------------------------------------

        page = client.parse_page(
            raw_response
        )

        # ----------------------------------------------------
        # 4. COMMIT METADATA DEL RAW
        # ----------------------------------------------------

        apply_iventas_raw_page_parse_metadata(
            raw_page_id=int(
                raw_row.id
            ),
            page=page,
            session=session_value,
        )

        # ----------------------------------------------------
        # 5. NORMALIZE
        # ----------------------------------------------------

        normalized_contacts = tuple(
            normalize_iventas_contact(
                contact=contact,
                branch_code=canonical_branch_code,
                sucursal_id=resolution.sucursal_id,
            )
            for contact in page.contacts
        )

        # ----------------------------------------------------
        # 6. COMMIT CONTACTS + TAGS
        # ----------------------------------------------------

        observed_at = raw_row.received_at

        if (
            observed_at is None
            or observed_at.tzinfo is None
            or observed_at.utcoffset() is None
        ):
            raise MarketingIventasBranchSyncError(
                "received_at del raw debe "
                "tener timezone."
            )

        structured_result = (
            persist_iventas_normalized_page(
                sync_run_id=sync_run_id,
                contacts=normalized_contacts,
                observed_at=observed_at,
                session=session_value,
            )
        )

        # ----------------------------------------------------
        # 7. CONTADORES BRANCH
        # ----------------------------------------------------

        pages_processed += 1

        contacts_received += len(
            page.contacts
        )

        contacts_created += (
            structured_result.contacts_created
        )

        contacts_existing += (
            structured_result.contacts_existing
        )

        tags_created += (
            structured_result.tags_created
        )

        # ----------------------------------------------------
        # 8. TERMINAR O CONTINUAR
        # ----------------------------------------------------

        if not page.has_more:
            break

        next_cursor = page.next_cursor

        if (
            next_cursor is None
            or not str(next_cursor).strip()
        ):
            raise MarketingIventasBranchSyncError(
                "iVentas indicó has_more=True "
                "sin next_cursor."
            )

        if next_cursor == cursor:
            raise MarketingIventasBranchSyncError(
                "iVentas devolvió el mismo cursor "
                "de la página actual."
            )

        if next_cursor in seen_request_cursors:
            raise MarketingIventasBranchSyncError(
                "iVentas repitió un cursor ya "
                "utilizado durante la paginación."
            )

        seen_request_cursors.add(
            next_cursor
        )

        cursor = next_cursor
        page_number += 1

    return MarketingIventasBranchSyncResult(
        sync_run_id=sync_run_id,
        branch_code=canonical_branch_code,
        sucursal_canon=(
            resolution.sucursal_canon
        ),
        sucursal_id=(
            resolution.sucursal_id
        ),
        pages_processed=pages_processed,
        contacts_received=contacts_received,
        contacts_created=contacts_created,
        contacts_existing=contacts_existing,
        tags_created=tags_created,
    )
