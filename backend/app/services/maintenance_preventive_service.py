# backend/app/services/maintenance_preventive_service.py

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Callable
from uuid import uuid4

from sqlalchemy import func

from app.extensions import db
from app.models.inventario import InventarioGeneral, InventarioSucursal
from app.models.maintenance_preventive import (
    MaintenancePreventiveBatchORM,
    MaintenancePreventiveItemORM,
)
from app.models.sucursal_model import Sucursal
from app.models.user_model import UserORM
from app.utils.pm_permissions import can_pm_configure


class MaintenancePreventiveError(ValueError):
    pass


class MaintenancePreventiveAuthorizationError(MaintenancePreventiveError):
    pass


class MaintenancePreventiveNotFoundError(MaintenancePreventiveError):
    pass


class MaintenancePreventiveStateError(MaintenancePreventiveError):
    pass


def _clean(value) -> str:
    return str(value or "").strip()


def _normalize_key(value) -> str:
    return " ".join(_clean(value).upper().split())


def _role(user) -> str:
    return _normalize_key(getattr(user, "rol", ""))


def _assert_can_configure(user) -> None:
    if not user or not can_pm_configure(user):
        raise MaintenancePreventiveAuthorizationError(
            "No tienes permiso para configurar programación preventiva."
        )


def _allowed_branch_ids(user) -> set[int]:
    result: set[int] = set()

    for value in (getattr(user, "sucursales_ids", None) or []):
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            result.add(parsed)

    try:
        primary = int(getattr(user, "sucursal_id", 0) or 0)
    except (TypeError, ValueError):
        primary = 0

    if primary > 0:
        result.add(primary)

    return result


def _can_manage_branch(user, branch_id: int) -> bool:
    role = _role(user)

    if role in {"ADMIN", "ADMINISTRADOR", "SUPER_ADMIN", "MANTENIMIENTO"}:
        return True

    try:
        target = int(branch_id)
    except (TypeError, ValueError):
        return False

    return target in _allowed_branch_ids(user)


def _parse_optional_date(value, field_name: str) -> date | None:
    if value in (None, ""):
        return None

    parsed = _parse_programmed_date(value)
    if parsed is None:
        raise MaintenancePreventiveError(
            f"{field_name} debe tener formato YYYY-MM-DD."
        )
    return parsed


def _batch_key() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"PM-{stamp}-{uuid4().hex[:8].upper()}"


def crear_lote_preventivo(user, payload: dict) -> MaintenancePreventiveBatchORM:
    _assert_can_configure(user)

    if not isinstance(payload, dict):
        raise MaintenancePreventiveError("El cuerpo del lote es inválido.")

    nombre = _clean(payload.get("nombre"))
    if not nombre:
        raise MaintenancePreventiveError("nombre es obligatorio.")

    source_type = _normalize_key(payload.get("source_type") or "MANUAL")
    if source_type not in {"MANUAL", "ARCHIVO"}:
        raise MaintenancePreventiveError(
            "source_type debe ser MANUAL o ARCHIVO."
        )

    period_start = _parse_optional_date(
        payload.get("period_start"),
        "period_start",
    )
    period_end = _parse_optional_date(
        payload.get("period_end"),
        "period_end",
    )

    if period_start and period_end and period_start > period_end:
        raise MaintenancePreventiveError(
            "period_start no puede ser mayor que period_end."
        )

    batch = MaintenancePreventiveBatchORM(
        batch_key=_batch_key(),
        nombre=nombre,
        source_type=source_type,
        status="BORRADOR",
        period_start=period_start,
        period_end=period_end,
        source_filename=_clean(payload.get("source_filename")) or None,
        source_sha256=_clean(payload.get("source_sha256")) or None,
        notes=_clean(payload.get("notes")) or None,
        created_by_user_id=int(user.id),
    )
    db.session.add(batch)
    db.session.flush()
    return batch


def _get_batch(batch_id: int) -> MaintenancePreventiveBatchORM:
    batch = db.session.get(MaintenancePreventiveBatchORM, int(batch_id))
    if batch is None:
        raise MaintenancePreventiveNotFoundError(
            "Lote preventivo no encontrado."
        )
    return batch


def _assert_batch_manageable(user, batch: MaintenancePreventiveBatchORM) -> None:
    _assert_can_configure(user)

    role = _role(user)
    if role in {"ADMIN", "ADMINISTRADOR", "SUPER_ADMIN", "MANTENIMIENTO"}:
        return

    if int(batch.created_by_user_id or 0) != int(user.id):
        raise MaintenancePreventiveAuthorizationError(
            "No tienes acceso de edición a este lote preventivo."
        )


def obtener_lote_preventivo(
    batch_id: int,
    user,
) -> MaintenancePreventiveBatchORM:
    batch = _get_batch(batch_id)
    _assert_batch_manageable(user, batch)
    return batch


def listar_lotes_preventivos(user) -> list[MaintenancePreventiveBatchORM]:
    _assert_can_configure(user)

    query = MaintenancePreventiveBatchORM.query

    if _role(user) not in {
        "ADMIN",
        "ADMINISTRADOR",
        "SUPER_ADMIN",
        "MANTENIMIENTO",
    }:
        query = query.filter(
            MaintenancePreventiveBatchORM.created_by_user_id == int(user.id)
        )

    return (
        query
        .order_by(
            MaintenancePreventiveBatchORM.created_at.desc(),
            MaintenancePreventiveBatchORM.id.desc(),
        )
        .all()
    )


def agregar_renglones_lote(
    batch_id: int,
    user,
    rows: list[dict],
) -> list[MaintenancePreventiveItemORM]:
    batch = _get_batch(batch_id)
    _assert_batch_manageable(user, batch)

    if batch.status != "BORRADOR":
        raise MaintenancePreventiveStateError(
            "Solo se pueden editar lotes en BORRADOR."
        )

    if not isinstance(rows, list) or not rows:
        raise MaintenancePreventiveError(
            "items debe ser una lista no vacía."
        )

    existing_rows = [
        int(item.source_row_number)
        for item in (batch.items or [])
        if item.source_row_number is not None
    ]
    next_row_number = max(existing_rows, default=0) + 1

    created: list[MaintenancePreventiveItemORM] = []

    for offset, raw_row in enumerate(rows):
        if not isinstance(raw_row, dict):
            raise MaintenancePreventiveError(
                f"El renglón {offset + 1} es inválido."
            )

        source_row_number = raw_row.get("source_row_number")
        try:
            source_row_number = (
                int(source_row_number)
                if source_row_number is not None
                else next_row_number + offset
            )
        except (TypeError, ValueError):
            raise MaintenancePreventiveError(
                f"source_row_number inválido en renglón {offset + 1}."
            )

        sucursal_input = _clean(
            raw_row.get("sucursal")
            or raw_row.get("sucursal_input")
            or raw_row.get("sucursal_id")
        )

        # Si la sucursal ya es resoluble, el backend aplica scope antes de
        # persistir. Una sucursal inexistente sí se guarda para que validación
        # muestre el error correspondiente.
        branch = _resolve_sucursal(sucursal_input)
        if branch is not None and not _can_manage_branch(
            user,
            int(branch.sucursal_id),
        ):
            raise MaintenancePreventiveAuthorizationError(
                f"No tienes acceso a la sucursal {sucursal_input}."
            )

        item = MaintenancePreventiveItemORM(
            batch_id=batch.id,
            source_row_number=source_row_number,
            sucursal_input=sucursal_input or None,
            codigo_equipo_input=_clean(
                raw_row.get("codigo_equipo")
                or raw_row.get("codigo_equipo_input")
            ) or None,
            responsable_input=_clean(
                raw_row.get("responsable")
                or raw_row.get("responsable_input")
            ) or None,
            fecha_programada_input=_clean(
                raw_row.get("fecha_programada")
                or raw_row.get("fecha_programada_input")
            ) or None,
            actividad=_clean(raw_row.get("actividad")) or None,
            observaciones=_clean(raw_row.get("observaciones")) or None,
            validation_status="PENDIENTE",
            validation_errors=None,
        )
        db.session.add(item)
        created.append(item)

    db.session.flush()
    return created


def _get_item_in_batch(
    batch: MaintenancePreventiveBatchORM,
    item_id: int,
) -> MaintenancePreventiveItemORM:
    item = db.session.get(MaintenancePreventiveItemORM, int(item_id))
    if item is None or int(item.batch_id) != int(batch.id):
        raise MaintenancePreventiveNotFoundError(
            "Renglón preventivo no encontrado en el lote."
        )
    return item


def actualizar_renglon_lote(
    batch_id: int,
    item_id: int,
    user,
    payload: dict,
) -> MaintenancePreventiveItemORM:
    batch = _get_batch(batch_id)
    _assert_batch_manageable(user, batch)

    if batch.status != "BORRADOR":
        raise MaintenancePreventiveStateError(
            "Solo se pueden editar lotes en BORRADOR."
        )

    if not isinstance(payload, dict):
        raise MaintenancePreventiveError("El cuerpo del renglón es inválido.")

    item = _get_item_in_batch(batch, item_id)

    if "sucursal" in payload or "sucursal_input" in payload or "sucursal_id" in payload:
        sucursal_input = _clean(
            payload.get("sucursal")
            or payload.get("sucursal_input")
            or payload.get("sucursal_id")
        )
        branch = _resolve_sucursal(sucursal_input)
        if branch is not None and not _can_manage_branch(
            user,
            int(branch.sucursal_id),
        ):
            raise MaintenancePreventiveAuthorizationError(
                f"No tienes acceso a la sucursal {sucursal_input}."
            )
        item.sucursal_input = sucursal_input or None

    if "codigo_equipo" in payload or "codigo_equipo_input" in payload:
        item.codigo_equipo_input = _clean(
            payload.get("codigo_equipo")
            or payload.get("codigo_equipo_input")
        ) or None

    if "responsable" in payload or "responsable_input" in payload:
        item.responsable_input = _clean(
            payload.get("responsable")
            or payload.get("responsable_input")
        ) or None

    if "fecha_programada" in payload or "fecha_programada_input" in payload:
        item.fecha_programada_input = _clean(
            payload.get("fecha_programada")
            or payload.get("fecha_programada_input")
        ) or None

    if "actividad" in payload:
        item.actividad = _clean(payload.get("actividad")) or None

    if "observaciones" in payload:
        item.observaciones = _clean(payload.get("observaciones")) or None

    # Cualquier corrección invalida la resolución previa.
    item.sucursal_id = None
    item.inventario_id = None
    item.responsable_user_id = None
    item.fecha_programada = None
    item.validation_status = "PENDIENTE"
    item.validation_errors = None

    db.session.flush()
    return item


def eliminar_renglon_lote(
    batch_id: int,
    item_id: int,
    user,
) -> None:
    batch = _get_batch(batch_id)
    _assert_batch_manageable(user, batch)

    if batch.status != "BORRADOR":
        raise MaintenancePreventiveStateError(
            "Solo se pueden editar lotes en BORRADOR."
        )

    item = _get_item_in_batch(batch, item_id)

    if item.ticket_id is not None:
        raise MaintenancePreventiveStateError(
            "No se puede eliminar un renglón que ya generó ticket."
        )

    db.session.delete(item)
    db.session.flush()


def serializar_item(item: MaintenancePreventiveItemORM) -> dict:
    return {
        "id": item.id,
        "batch_id": item.batch_id,
        "source_row_number": item.source_row_number,
        "sucursal_input": item.sucursal_input,
        "codigo_equipo_input": item.codigo_equipo_input,
        "responsable_input": item.responsable_input,
        "fecha_programada_input": item.fecha_programada_input,
        "sucursal_id": item.sucursal_id,
        "inventario_id": item.inventario_id,
        "responsable_user_id": item.responsable_user_id,
        "fecha_programada": (
            item.fecha_programada.isoformat()
            if item.fecha_programada
            else None
        ),
        "actividad": item.actividad,
        "observaciones": item.observaciones,
        "validation_status": item.validation_status,
        "validation_errors": item.validation_errors or [],
        "ticket_id": item.ticket_id,
    }


def serializar_lote(batch: MaintenancePreventiveBatchORM) -> dict:
    return {
        "id": batch.id,
        "batch_key": batch.batch_key,
        "nombre": batch.nombre,
        "source_type": batch.source_type,
        "status": batch.status,
        "period_start": (
            batch.period_start.isoformat() if batch.period_start else None
        ),
        "period_end": (
            batch.period_end.isoformat() if batch.period_end else None
        ),
        "source_filename": batch.source_filename,
        "source_sha256": batch.source_sha256,
        "notes": batch.notes,
        "created_by_user_id": batch.created_by_user_id,
        "published_by_user_id": batch.published_by_user_id,
        "published_at": (
            batch.published_at.isoformat() if batch.published_at else None
        ),
        "items": [
            serializar_item(item)
            for item in (batch.items or [])
        ],
    }


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
    actor=None,
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
        if actor is not None and not _can_manage_branch(
            actor,
            item.sucursal_id,
        ):
            errors.append("No tienes acceso a la sucursal indicada.")

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


def validar_lote_preventivo(batch_id: int, user=None) -> dict:
    batch = _get_batch(batch_id)

    if user is not None:
        _assert_batch_manageable(user, batch)

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
            actor=user,
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
