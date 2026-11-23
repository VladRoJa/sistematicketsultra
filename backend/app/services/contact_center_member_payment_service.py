"""Consulta acotada de IDs de socio para ligas de pago en Contact Center.

Usa únicamente snapshots canónicos: padrón activo y altas históricas.
Los padrones de vencidos no contienen ID socio y no se infiere por PIN.
"""
from __future__ import annotations

import re
from datetime import date

from sqlalchemy import func

from app.extensions import db
from app.models.warehouse import (
    SociosActivosSnapshotRowORM,
    VentasNuevosSociosDetalleSnapshotORM,
    VentasNuevosSociosDetalleSnapshotRowORM,
)
from app.services.contact_center_service import ContactCenterValidationError
from app.warehouse.services.socios_activos_snapshot_resolver import (
    resolve_latest_canonical_socios_activos_snapshot,
)


PAYMENT_URL_BASE = "https://pago.ultragym.com.mx?sid="
MAX_RESULTS = 20
MAX_SOURCE_ROWS = 250
_ID_PATTERN = re.compile(r"([0-9]+)(?:\.0+)?\Z")


def _valid_member_id(value: object) -> str | None:
    raw = str(value or "").strip()
    match = _ID_PATTERN.fullmatch(raw)
    if not match or not any(character != "0" for character in match.group(1)):
        return None
    return match.group(1)


def _search_term(value: object) -> tuple[str, bool]:
    term = str(value or "").strip()
    if not 3 <= len(term) <= 80:
        raise ContactCenterValidationError(
            "Escribe al menos 3 caracteres de nombre o PIN (máximo 80)."
        )
    return term, term.isdecimal()


def _escaped_like(term: str) -> str:
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _member_payload(
    *, member_id: object, name: object, pin: object, branch: object, source: str
) -> dict | None:
    normalized_id = _valid_member_id(member_id)
    if normalized_id is None:
        return None
    return {
        "member_id": normalized_id,
        "name": str(name or "").strip() or "Sin nombre",
        "pin": str(pin or "").strip(),
        "branch": str(branch or "").strip(),
        "source": source,
        "payment_url": f"{PAYMENT_URL_BASE}{normalized_id}",
    }


def _add_unique(results: list[dict], seen: set[str], payload: dict | None) -> None:
    if payload is None:
        return
    member_id = payload["member_id"]
    if member_id not in seen:
        results.append(payload)
        seen.add(member_id)


def search_contact_center_member_payments(
    query: object, *, session=None
) -> list[dict]:
    """Ordena activos antes que altas históricas, sin mezclar IDs por nombre/PIN."""
    term, by_pin = _search_term(query)
    active_session = session if session is not None else db.session
    results: list[dict] = []
    seen: set[str] = set()

    active_snapshot = resolve_latest_canonical_socios_activos_snapshot(
        minimum_cutoff_date=date.min,
        session=active_session,
    )
    if active_snapshot is not None:
        active_query = active_session.query(SociosActivosSnapshotRowORM).filter(
            SociosActivosSnapshotRowORM.snapshot_id == int(active_snapshot.id)
        )
        if by_pin:
            active_query = active_query.filter(
                SociosActivosSnapshotRowORM.pin == term
            )
        else:
            active_query = active_query.filter(
                SociosActivosSnapshotRowORM.nombre.ilike(
                    _escaped_like(term), escape="\\"
                )
            )
        for row in (
            active_query.order_by(
                SociosActivosSnapshotRowORM.nombre.asc(),
                SociosActivosSnapshotRowORM.id.asc(),
            )
            .limit(MAX_SOURCE_ROWS)
            .all()
        ):
            _add_unique(
                results,
                seen,
                _member_payload(
                    member_id=row.id_socio,
                    name=row.nombre,
                    pin=row.pin,
                    branch=row.sucursal_raw,
                    source="ACTIVO",
                ),
            )
            if len(results) >= MAX_RESULTS:
                return results

    historic_name = func.concat_ws(
        " ",
        VentasNuevosSociosDetalleSnapshotRowORM.nombre,
        VentasNuevosSociosDetalleSnapshotRowORM.apellido_paterno,
        VentasNuevosSociosDetalleSnapshotRowORM.apellido_materno,
    )
    historical_query = (
        active_session.query(VentasNuevosSociosDetalleSnapshotRowORM)
        .join(
            VentasNuevosSociosDetalleSnapshotORM,
            VentasNuevosSociosDetalleSnapshotRowORM.snapshot_id
            == VentasNuevosSociosDetalleSnapshotORM.id,
        )
        .filter(
            VentasNuevosSociosDetalleSnapshotORM.report_type_key
            == "ventas_nuevos_socios_detalle",
            VentasNuevosSociosDetalleSnapshotORM.snapshot_kind == "month_to_date",
            VentasNuevosSociosDetalleSnapshotORM.is_canonical.is_(True),
        )
    )
    if by_pin:
        historical_query = historical_query.filter(
            VentasNuevosSociosDetalleSnapshotRowORM.pin == term
        )
    else:
        historical_query = historical_query.filter(
            historic_name.ilike(_escaped_like(term), escape="\\")
        )

    for row in (
        historical_query.order_by(
            VentasNuevosSociosDetalleSnapshotORM.business_date.desc(),
            VentasNuevosSociosDetalleSnapshotORM.captured_at.desc(),
            VentasNuevosSociosDetalleSnapshotRowORM.id.desc(),
        )
        .limit(MAX_SOURCE_ROWS)
        .all()
    ):
        full_name = " ".join(
            str(value).strip()
            for value in (row.nombre, row.apellido_paterno, row.apellido_materno)
            if value
        )
        _add_unique(
            results,
            seen,
            _member_payload(
                member_id=row.id_socio,
                name=full_name,
                pin=row.pin,
                branch=row.sucursal_raw,
                source="HISTORICO_ALTAS",
            ),
        )
        if len(results) >= MAX_RESULTS:
            break
    return results
