"""Consulta acotada de IDs de socio para ligas de pago en Contact Center.

Usa únicamente snapshots canónicos: padrón activo y altas históricas.
Los padrones de vencidos no contienen ID socio y no se infiere por PIN.
"""
from __future__ import annotations

import re
from datetime import date

from sqlalchemy import func, or_

from app.extensions import db
from app.models.warehouse import (
    SociosActivosSnapshotRowORM,
    VentasNuevosSociosDetalleSnapshotORM,
    VentasNuevosSociosDetalleSnapshotRowORM,
)
from app.services.contact_center_service import ContactCenterValidationError
from app.services.marketing_phone import normalize_member_phone, normalize_phone
from app.warehouse.services.socios_activos_snapshot_resolver import (
    resolve_latest_canonical_socios_activos_snapshot,
)


PAYMENT_URL_BASE = "https://pago.ultragym.com.mx?sid="
MAX_RESULTS = 20
MAX_SOURCE_ROWS = 250
_ID_PATTERN = re.compile(r"([0-9]+)(?:\.0+)?\Z")
_PHONE_INPUT_PATTERN = re.compile(r"\+?[0-9\s().-]+\Z")


def _valid_member_id(value: object) -> str | None:
    raw = str(value or "").strip()
    match = _ID_PATTERN.fullmatch(raw)
    if not match or not any(character != "0" for character in match.group(1)):
        return None
    return match.group(1)


def _search_term(value: object) -> tuple[str, str]:
    term = str(value or "").strip()
    if not 3 <= len(term) <= 80:
        raise ContactCenterValidationError(
            "Escribe entre 3 y 80 caracteres de nombre, PIN o teléfono."
        )
    if _PHONE_INPUT_PATTERN.fullmatch(term):
        phone = normalize_phone(term)
        if phone is not None:
            return phone, "PHONE"
    if term.isdecimal():
        return term, "PIN"
    return term, "NAME"


def _escaped_like(term: str) -> str:
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _phone_filter(
    phone_column, lada_column, phone_mx10: str, *, digits_stored: bool = False
):
    """SQL acotado a números completos; verifica después el MX10 de cada fila."""
    valid_forms = (phone_mx10, f"52{phone_mx10}", f"521{phone_mx10}")
    digits = (
        func.coalesce(phone_column, "")
        if digits_stored
        else func.regexp_replace(
            func.coalesce(phone_column, ""), r"[^0-9]", "", "g"
        )
    )
    lada_digits = func.regexp_replace(
        func.coalesce(lada_column, ""), r"[^0-9]", "", "g"
    )
    return or_(
        digits.in_(valid_forms),
        func.concat(lada_digits, digits).in_(valid_forms),
    )


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
    """Ordena activos antes que altas históricas, sin cruzar identidades."""
    term, kind = _search_term(query)
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
        if kind == "PIN":
            active_query = active_query.filter(
                SociosActivosSnapshotRowORM.pin == term
            )
        elif kind == "PHONE":
            active_query = active_query.filter(
                _phone_filter(
                    SociosActivosSnapshotRowORM.telefono_digits,
                    SociosActivosSnapshotRowORM.lada_raw,
                    term,
                    digits_stored=True,
                )
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
            if kind == "PHONE" and normalize_member_phone(
                lada=row.lada_raw, telefono=row.telefono_raw
            ) != term:
                continue
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
    if kind == "PIN":
        historical_query = historical_query.filter(
            VentasNuevosSociosDetalleSnapshotRowORM.pin == term
        )
    elif kind == "PHONE":
        historical_query = historical_query.filter(
            _phone_filter(
                VentasNuevosSociosDetalleSnapshotRowORM.telefono,
                VentasNuevosSociosDetalleSnapshotRowORM.lada,
                term,
            )
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
        if kind == "PHONE" and normalize_member_phone(
            lada=row.lada, telefono=row.telefono
        ) != term:
            continue
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
