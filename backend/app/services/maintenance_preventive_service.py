# backend/app/services/maintenance_preventive_service.py

from __future__ import annotations

from datetime import date, datetime
from typing import Callable

from sqlalchemy import func

from app.extensions import db
from app.models.inventario import InventarioGeneral, InventarioSucursal
from app.models.maintenance_preventive import (
    MaintenancePreventiveBatchORM,
    MaintenancePreventiveItemORM,
)
from app.models.sucursal_model import Sucursal
from app.models.user_model import UserORM


class MaintenancePreventiveError(ValueError):
    pass


class MaintenancePreventiveNotFoundError(MaintenancePreventiveError):
    pass


class MaintenancePreventiveStateError(MaintenancePreventiveError):
    pass


def _clean(value) -> str:
    return str(value or "").strip()


def _normalize_key(value) -> str:
    return " ".join(_clean(value).upper().split())


def _resolve_sucursal(value) -> Sucursal | None:
    raw = _clean(value)
    if not raw:
        return None

    if raw.isdigit():
        return Sucursal.query.filter_by(sucursal_id=int(raw)).first()

    return (
        Sucursal.query
        .filter(
            func.lower(func.trim(Sucursal.sucursal))
            == raw.casefold()
        )
        .first()
    )


def _resolve_equipo_by_code(value) -> InventarioGeneral | None:
    code = _normalize_key(value)
    if not code:
        return None

    matches = (
        InventarioGeneral.query
        .filter(
            func.upper(func.trim(InventarioGeneral.codigo_interno))
            == code
        )
        .limit(2)
        .all()
    )

    if len(matches) > 1:
        raise MaintenancePreventiveError(
            f"El código de equipo {code} está duplicado en Inventario."
        )

    return matches[0] if matches else None


def _resolve_responsable(value) -> UserORM | None:
    raw = _clean(value)
    if not raw:
        return None

    return (
        UserORM.query
        .filter(func.lower(UserORM.username) == raw.casefold())
        .first()
    )


def _parse_programmed_date(value) -> date | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    raw = _clean(value)
    if not raw:
        return None

    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _equipo_asignado_a_sucursal(
    inventario_id: int,
    sucursal_id: int,
) -> bool:
    row = (
        InventarioSucursal.query
        .filter(
            InventarioSucursal.inventario_id == inventario_id,
            InventarioSucursal.sucursal_id == sucursal_id,
            InventarioSucursal.stock > 0,
        )
        .first()
    )
    return row is not None


def _validate_responsable_mantenimiento(user: UserORM | None) -> bool:
    if user is None:
        return False

    try:
        return int(getattr(user, "department_id", 0) or 0) == 1
    except (TypeError, ValueError):
        return False


def _item_duplicate_key(item: MaintenancePreventiveItemORM):
    if (
        item.sucursal_id is None
        or item.inventario_id is None
        or item.fecha_programada is None
        or not _clean(item.actividad)
    ):
        return None

    return (
        int(item.sucursal_id),
        int(item.inventario_id),
        item.fecha_programada.isoformat(),
        _normalize_key(item.actividad),
    )


def validar_item_borrador(
    item: MaintenancePreventiveItemORM,
    *,
    seen_keys: set | None = None,
    resolve_sucursal: Callable = _resolve_sucursal,
    resolve_equipo: Callable = _resolve_equipo_by_code,
    equipo_asignado: Callable = _equipo_asignado_a_sucursal,
    resolve_responsable: Callable = _resolve_responsable,
) -> list[str]:
    """Resuelve y valida un renglón sin borrarlo si contiene errores."""

    seen_keys = seen_keys if seen_keys is not None else set()
    errors: list[str] = []

    # Cada nueva validación parte de los datos de entrada; evita conservar IDs
    # viejos después de corregir una fila.
    item.sucursal_id = None
    item.inventario_id = None
    item.responsable_user_id = None
    item.fecha_programada = None

    sucursal = resolve_sucursal(item.sucursal_input)
    if sucursal is None:
        errors.append("Sucursal inexistente o vacía.")
    else:
        item.sucursal_id = int(sucursal.sucursal_id)

    try:
        equipo = resolve_equipo(item.codigo_equipo_input)
    except MaintenancePreventiveError as exc:
        equipo = None
        errors.append(str(exc))

    if equipo is None:
        if _clean(item.codigo_equipo_input):
            if not any("duplicado" in error.lower() for error in errors):
                errors.append("Código de equipo inexistente.")
        else:
            errors.append("Código de equipo vacío.")
    else:
        item.inventario_id = int(equipo.id)

        if _normalize_key(getattr(equipo, "tipo", "")) != "APARATOS":
            errors.append("El código no corresponde a un equipo de Aparatos.")

    if item.sucursal_id is not None and item.inventario_id is not None:
        if not equipo_asignado(item.inventario_id, item.sucursal_id):
            errors.append(
                "El equipo no está asignado actualmente a la sucursal indicada."
            )

    responsable = resolve_responsable(item.responsable_input)
    if responsable is None:
        if _clean(item.responsable_input):
            errors.append("Responsable inexistente en Suite.")
        else:
            errors.append("Responsable vacío.")
    elif not _validate_responsable_mantenimiento(responsable):
        errors.append("El responsable no pertenece al departamento de Mantenimiento.")
    else:
        item.responsable_user_id = int(responsable.id)

    parsed_date = _parse_programmed_date(item.fecha_programada_input)
    if parsed_date is None:
        errors.append(
            "Fecha programada inválida; se requiere formato YYYY-MM-DD."
        )
    else:
        item.fecha_programada = parsed_date

    item.actividad = _clean(item.actividad) or None
    if item.actividad is None:
        errors.append("Actividad preventiva vacía.")

    duplicate_key = _item_duplicate_key(item)
    if duplicate_key is not None:
        if duplicate_key in seen_keys:
            errors.append("Renglón duplicado dentro del mismo lote.")
        else:
            seen_keys.add(duplicate_key)

    item.validation_errors = errors or None
    item.validation_status = "ERROR" if errors else "VALIDO"

    return errors


def validar_lote_preventivo(batch_id: int) -> dict:
    batch = db.session.get(MaintenancePreventiveBatchORM, int(batch_id))
    if batch is None:
        raise MaintenancePreventiveNotFoundError(
            "Lote preventivo no encontrado."
        )

    if batch.status != "BORRADOR":
        raise MaintenancePreventiveStateError(
            "Solo se pueden validar lotes en BORRADOR."
        )

    items = list(batch.items or [])
    if not items:
        raise MaintenancePreventiveStateError(
            "El lote no contiene renglones para validar."
        )

    seen_keys: set = set()
    valid = 0
    invalid = 0

    for item in items:
        errors = validar_item_borrador(
            item,
            seen_keys=seen_keys,
        )
        if errors:
            invalid += 1
        else:
            valid += 1

    db.session.flush()

    return {
        "batch_id": batch.id,
        "total": len(items),
        "validos": valid,
        "errores": invalid,
        "publicable": invalid == 0 and valid > 0,
    }
