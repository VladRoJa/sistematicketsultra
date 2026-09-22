# backend/app/services/maintenance_preventive_service.py

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Callable
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func

from app.extensions import db
from app.models.catalogos import CatalogoClasificacion
from app.models.inventario import InventarioGeneral, InventarioSucursal
from app.models.maintenance_preventive import (
    MaintenanceCrewORM,
    MaintenancePersonnelORM,
    MaintenancePreventiveBatchORM,
    MaintenancePreventiveItemORM,
    MaintenancePreventiveOccurrenceORM,
    MaintenancePreventiveScheduleORM,
)
from app.models.sucursal_model import Sucursal
from app.models.suite_governance import (
    SuiteRegionORM,
    SuiteSucursalRegionAssignmentORM,
)
from app.models.ticket_model import Ticket
from app.utils.sucursal_audience import (
    SUCURSAL_AUDIENCE_OPERATIONAL,
    apply_selectable_sucursal_catalog,
)
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


def _schedule_key() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"PMR-{stamp}-{uuid4().hex[:10].upper()}"


def _repeat_enabled_input(value) -> str | None:
    if isinstance(value, bool):
        return "SI" if value else "NO"
    return _clean(value) or None


def _parse_repeat_enabled(value) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False

    normalized = _normalize_key(value)
    if normalized in {"1", "TRUE", "SI", "SÍ", "YES"}:
        return True
    if normalized in {"0", "FALSE", "NO"}:
        return False

    raise MaintenancePreventiveError(
        "repeat_enabled debe ser verdadero o falso."
    )


def _parse_workday_interval(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise MaintenancePreventiveError(
            "repeat_interval_workdays debe ser un entero positivo."
        ) from exc

    if parsed <= 0:
        raise MaintenancePreventiveError(
            "repeat_interval_workdays debe ser mayor a cero."
        )
    return parsed


def add_workdays(start_date: date, workdays: int) -> date:
    """Suma días hábiles contando únicamente lunes a viernes."""
    if not isinstance(start_date, date):
        raise MaintenancePreventiveError("start_date debe ser una fecha.")

    try:
        remaining = int(workdays)
    except (TypeError, ValueError) as exc:
        raise MaintenancePreventiveError(
            "workdays debe ser un entero positivo."
        ) from exc

    if remaining <= 0:
        raise MaintenancePreventiveError(
            "workdays debe ser mayor a cero."
        )

    result = start_date
    while remaining:
        result += timedelta(days=1)
        if result.weekday() < 5:
            remaining -= 1

    return result


def assert_import_hash_available(source_sha256: str) -> None:
    sha = _clean(source_sha256).lower()
    if not sha:
        raise MaintenancePreventiveError(
            "No se pudo calcular la huella del archivo."
        )

    existing = (
        MaintenancePreventiveBatchORM.query
        .filter(
            func.lower(MaintenancePreventiveBatchORM.source_sha256) == sha,
            MaintenancePreventiveBatchORM.status.in_(
                ("BORRADOR", "PUBLICADO")
            ),
        )
        .order_by(MaintenancePreventiveBatchORM.id.desc())
        .first()
    )

    if existing is not None:
        raise MaintenancePreventiveStateError(
            "Este archivo ya fue cargado en un lote preventivo activo."
        )


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


def listar_cuadrillas(user) -> list[dict]:
    _assert_can_configure(user)

    crews = (
        MaintenanceCrewORM.query
        .order_by(
            MaintenanceCrewORM.activo.desc(),
            MaintenanceCrewORM.nombre.asc(),
        )
        .all()
    )

    return [
        {
            "id": int(crew.id),
            "nombre": str(crew.nombre),
            "region_id": crew.region_id,
            "region": (
                str(crew.region.region_label)
                if crew.region is not None
                else None
            ),
            "activo": bool(crew.activo),
        }
        for crew in crews
    ]


def crear_cuadrilla(user, payload: dict) -> MaintenanceCrewORM:
    _assert_can_configure(user)

    nombre = _clean((payload or {}).get("nombre"))
    if not nombre:
        raise MaintenancePreventiveError("nombre es obligatorio.")

    region_id = (payload or {}).get("region_id")
    if region_id not in (None, ""):
        try:
            region_id = int(region_id)
        except (TypeError, ValueError) as exc:
            raise MaintenancePreventiveError("region_id inválido.") from exc

        region = db.session.get(SuiteRegionORM, region_id)
        if region is None or not bool(region.is_active):
            raise MaintenancePreventiveError(
                "La región indicada no existe o está inactiva."
            )
    else:
        region_id = None

    crew = MaintenanceCrewORM(
        nombre=nombre,
        region_id=region_id,
        activo=True,
    )
    db.session.add(crew)
    db.session.flush()
    return crew


def actualizar_cuadrilla(
    crew_id: int,
    user,
    payload: dict,
) -> MaintenanceCrewORM:
    _assert_can_configure(user)

    crew = db.session.get(MaintenanceCrewORM, int(crew_id))
    if crew is None:
        raise MaintenancePreventiveNotFoundError(
            "Cuadrilla no encontrada."
        )

    if "nombre" in payload:
        nombre = _clean(payload.get("nombre"))
        if not nombre:
            raise MaintenancePreventiveError("nombre es obligatorio.")
        crew.nombre = nombre

    if "region_id" in payload:
        region_id = payload.get("region_id")
        if region_id in (None, ""):
            crew.region_id = None
        else:
            try:
                region_id = int(region_id)
            except (TypeError, ValueError) as exc:
                raise MaintenancePreventiveError(
                    "region_id inválido."
                ) from exc

            region = db.session.get(SuiteRegionORM, region_id)
            if region is None or not bool(region.is_active):
                raise MaintenancePreventiveError(
                    "La región indicada no existe o está inactiva."
                )
            crew.region_id = region_id

    if "activo" in payload:
        crew.activo = bool(payload.get("activo"))

    db.session.flush()
    return crew


def listar_personal_mantenimiento(user) -> dict:
    _assert_can_configure(user)

    personnel = (
        MaintenancePersonnelORM.query
        .order_by(
            MaintenancePersonnelORM.activo.desc(),
            MaintenancePersonnelORM.id.asc(),
        )
        .all()
    )
    candidates = (
        UserORM.query
        .filter(UserORM.department_id == MAINTENANCE_DEPARTMENT_ID)
        .order_by(UserORM.username.asc())
        .all()
    )
    regions = (
        SuiteRegionORM.query
        .filter(SuiteRegionORM.is_active.is_(True))
        .order_by(SuiteRegionORM.region_label.asc())
        .all()
    )

    return {
        "personnel": [
            {
                "id": int(row.id),
                "user_id": int(row.user.id),
                "username": str(row.user.username),
                "rol": str(row.user.rol or ""),
                "crew_id": row.crew_id,
                "crew": (
                    str(row.crew.nombre) if row.crew is not None else None
                ),
                "region_id": (
                    row.crew.region_id if row.crew is not None else None
                ),
                "activo": bool(row.activo),
            }
            for row in personnel
        ],
        "candidates": [
            {
                "user_id": int(candidate.id),
                "username": str(candidate.username),
                "rol": str(candidate.rol or ""),
            }
            for candidate in candidates
        ],
        "crews": listar_cuadrillas(user),
        "regions": [
            {
                "id": int(region.id),
                "key": str(region.region_key),
                "label": str(region.region_label),
            }
            for region in regions
        ],
    }


def guardar_personal_mantenimiento(
    user,
    payload: dict,
    *,
    personnel_id: int | None = None,
) -> MaintenancePersonnelORM:
    _assert_can_configure(user)

    if personnel_id is None:
        try:
            user_id = int((payload or {}).get("user_id"))
        except (TypeError, ValueError) as exc:
            raise MaintenancePreventiveError("user_id inválido.") from exc

        target_user = db.session.get(UserORM, user_id)
        if target_user is None:
            raise MaintenancePreventiveError("Usuario no encontrado.")
        if int(target_user.department_id or 0) != MAINTENANCE_DEPARTMENT_ID:
            raise MaintenancePreventiveError(
                "El usuario no pertenece al departamento de Mantenimiento."
            )

        existing = (
            MaintenancePersonnelORM.query
            .filter(MaintenancePersonnelORM.user_id == user_id)
            .first()
        )
        if existing is not None:
            raise MaintenancePreventiveStateError(
                "El usuario ya existe en el catálogo de personal."
            )

        row = MaintenancePersonnelORM(
            user_id=user_id,
            activo=True,
        )
        db.session.add(row)
    else:
        row = db.session.get(
            MaintenancePersonnelORM,
            int(personnel_id),
        )
        if row is None:
            raise MaintenancePreventiveNotFoundError(
                "Personal de Mantenimiento no encontrado."
            )

    if "crew_id" in payload:
        crew_id = payload.get("crew_id")
        if crew_id in (None, ""):
            row.crew_id = None
        else:
            try:
                crew_id = int(crew_id)
            except (TypeError, ValueError) as exc:
                raise MaintenancePreventiveError(
                    "crew_id inválido."
                ) from exc

            crew = db.session.get(MaintenanceCrewORM, crew_id)
            if crew is None or not bool(crew.activo):
                raise MaintenancePreventiveError(
                    "La cuadrilla indicada no existe o está inactiva."
                )
            row.crew_id = crew_id

    if "activo" in payload:
        row.activo = bool(payload.get("activo"))

    db.session.flush()
    return row


def _classification_path(
    classification: CatalogoClasificacion | None,
) -> list[CatalogoClasificacion]:
    path: list[CatalogoClasificacion] = []
    current = classification
    visited: set[int] = set()

    while current is not None:
        try:
            current_id = int(current.id)
        except (TypeError, ValueError):
            break

        if current_id in visited:
            break

        visited.add(current_id)
        path.insert(0, current)
        current = getattr(current, "padre", None)

    return path


def _is_building_classification(
    classification: CatalogoClasificacion | None,
) -> bool:
    if classification is None:
        return False

    if not bool(getattr(classification, "activo", False)):
        return False

    try:
        if int(classification.departamento_id) != MAINTENANCE_DEPARTMENT_ID:
            return False
    except (TypeError, ValueError):
        return False

    path = _classification_path(classification)
    normalized = [
        _normalize_key(getattr(node, "nombre", ""))
        for node in path
    ]

    return (
        len(normalized) >= 3
        and normalized[0] == "MANTENIMIENTO"
        and normalized[1] == "EDIFICIO"
    )


def _building_classification_label(
    classification: CatalogoClasificacion,
) -> str:
    path = _classification_path(classification)
    labels = [
        _clean(getattr(node, "nombre", ""))
        for node in path[2:]
        if _clean(getattr(node, "nombre", ""))
    ]
    return " > ".join(labels)


def listar_clasificaciones_edificio() -> list[CatalogoClasificacion]:
    rows = (
        CatalogoClasificacion.query
        .filter(
            CatalogoClasificacion.departamento_id
            == MAINTENANCE_DEPARTMENT_ID,
            CatalogoClasificacion.activo.is_(True),
        )
        .order_by(
            CatalogoClasificacion.nivel.asc(),
            CatalogoClasificacion.nombre.asc(),
            CatalogoClasificacion.id.asc(),
        )
        .all()
    )

    return [
        row
        for row in rows
        if _is_building_classification(row)
    ]


def _resolve_building_classification(
    value,
) -> CatalogoClasificacion | None:
    raw = _clean(value)
    if not raw:
        return None

    if raw.isdigit():
        row = db.session.get(CatalogoClasificacion, int(raw))
        return row if _is_building_classification(row) else None

    normalized = _normalize_key(raw)
    matches: list[CatalogoClasificacion] = []

    for row in listar_clasificaciones_edificio():
        path_label = _building_classification_label(row)
        full_path = " > ".join(
            _clean(getattr(node, "nombre", ""))
            for node in _classification_path(row)
        )
        candidates = {
            _normalize_key(getattr(row, "nombre", "")),
            _normalize_key(path_label),
            _normalize_key(full_path),
        }
        if normalized in candidates:
            matches.append(row)

    if len(matches) > 1:
        raise MaintenancePreventiveError(
            "La clasificación de Edificio es ambigua; usa su ID o jerarquía."
        )

    return matches[0] if matches else None


def listar_contexto_programacion(user) -> dict:
    _assert_can_configure(user)

    branch_query = apply_selectable_sucursal_catalog(
        Sucursal.query,
        audience=SUCURSAL_AUDIENCE_OPERATIONAL,
    )

    if _role(user) not in {
        "ADMIN",
        "ADMINISTRADOR",
        "SUPER_ADMIN",
        "MANTENIMIENTO",
    }:
        allowed = sorted(_allowed_branch_ids(user))
        if not allowed:
            branches = []
        else:
            branches = (
                branch_query
                .filter(Sucursal.sucursal_id.in_(allowed))
                .order_by(Sucursal.sucursal.asc())
                .all()
            )
    else:
        branches = (
            branch_query
            .order_by(Sucursal.sucursal.asc())
            .all()
        )

    personnel_rows = (
        MaintenancePersonnelORM.query
        .join(
            UserORM,
            UserORM.id == MaintenancePersonnelORM.user_id,
        )
        .filter(
            MaintenancePersonnelORM.activo.is_(True),
            UserORM.department_id == MAINTENANCE_DEPARTMENT_ID,
        )
        .order_by(UserORM.username.asc())
        .all()
    )

    return {
        "sucursales": [
            {
                "id": int(branch.sucursal_id),
                "nombre": str(branch.sucursal),
                "is_demo": bool(getattr(branch, "is_demo", False)),
            }
            for branch in branches
        ],
        "building_classifications": [
            {
                "id": int(classification.id),
                "nombre": str(classification.nombre),
                "label": _building_classification_label(classification),
                "nivel": int(classification.nivel or 0),
            }
            for classification in listar_clasificaciones_edificio()
        ],
        "responsables": [
            {
                "personnel_id": int(personnel.id),
                "user_id": int(personnel.user.id),
                "username": str(personnel.user.username),
                "rol": str(personnel.user.rol or ""),
                "crew_id": personnel.crew_id,
                "crew": (
                    str(personnel.crew.nombre)
                    if personnel.crew is not None
                    else None
                ),
                "region_id": (
                    personnel.crew.region_id
                    if personnel.crew is not None
                    else None
                ),
            }
            for personnel in personnel_rows
        ],
    }


def listar_equipos_programables(user, branch_id: int) -> list[dict]:
    _assert_can_configure(user)

    try:
        branch_id = int(branch_id)
    except (TypeError, ValueError) as exc:
        raise MaintenancePreventiveError(
            "branch_id inválido."
        ) from exc

    if not _can_manage_branch(user, branch_id):
        raise MaintenancePreventiveAuthorizationError(
            "No tienes acceso a esta sucursal."
        )

    rows = (
        db.session.query(InventarioGeneral)
        .join(
            InventarioSucursal,
            InventarioSucursal.inventario_id == InventarioGeneral.id,
        )
        .filter(
            InventarioSucursal.sucursal_id == branch_id,
            InventarioSucursal.stock > 0,
            InventarioGeneral.codigo_interno.isnot(None),
            func.lower(InventarioGeneral.tipo) == "aparatos",
        )
        .order_by(
            InventarioGeneral.familia_equipo_id.asc().nullslast(),
            InventarioGeneral.nombre.asc(),
            InventarioGeneral.codigo_interno.asc(),
        )
        .all()
    )

    return [
        {
            "inventario_id": int(item.id),
            "codigo_interno": str(item.codigo_interno),
            "nombre": str(item.nombre or ""),
            "marca": str(item.marca or ""),
            "familia_equipo_id": item.familia_equipo_id,
            "familia": (
                {
                    "id": int(item.familia_equipo.id),
                    "key": str(item.familia_equipo.key),
                    "nombre": str(item.familia_equipo.nombre),
                }
                if item.familia_equipo is not None
                else None
            ),
        }
        for item in rows
    ]


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
            target_type_input=_clean(
                raw_row.get("target_type")
                or raw_row.get("tipo_objetivo")
                or raw_row.get("tipo")
                or "EQUIPO"
            ) or "EQUIPO",
            sucursal_input=sucursal_input or None,
            codigo_equipo_input=_clean(
                raw_row.get("codigo_equipo")
                or raw_row.get("codigo_equipo_input")
            ) or None,
            building_classification_input=_clean(
                raw_row.get("building_classification")
                or raw_row.get("building_classification_id")
                or raw_row.get("clasificacion_edificio")
                or raw_row.get("clasificacion_edificio_id")
            ) or None,
            responsable_input=_clean(
                raw_row.get("responsable")
                or raw_row.get("responsable_input")
            ) or None,
            fecha_programada_input=_clean(
                raw_row.get("fecha_programada")
                or raw_row.get("fecha_programada_input")
            ) or None,
            repeat_enabled_input=_repeat_enabled_input(
                raw_row.get("repeat_enabled")
                if "repeat_enabled" in raw_row
                else raw_row.get("se_repite")
            ),
            repeat_interval_workdays_input=_clean(
                raw_row.get("repeat_interval_workdays")
                if "repeat_interval_workdays" in raw_row
                else raw_row.get("cada_dias_habiles")
            ) or None,
            repeat_enabled=False,
            repeat_interval_workdays=None,
            actividad=_clean(raw_row.get("actividad")) or None,
            observaciones=_clean(raw_row.get("observaciones")) or None,
            validation_status="PENDIENTE",
            validation_errors=None,
        )
        db.session.add(item)
        batch.items.append(item)
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

    if (
        "target_type" in payload
        or "tipo_objetivo" in payload
        or "tipo" in payload
    ):
        item.target_type_input = _clean(
            payload.get("target_type")
            or payload.get("tipo_objetivo")
            or payload.get("tipo")
        ) or None

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

    if (
        "building_classification" in payload
        or "building_classification_id" in payload
        or "clasificacion_edificio" in payload
        or "clasificacion_edificio_id" in payload
    ):
        item.building_classification_input = _clean(
            payload.get("building_classification")
            or payload.get("building_classification_id")
            or payload.get("clasificacion_edificio")
            or payload.get("clasificacion_edificio_id")
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

    if "repeat_enabled" in payload or "se_repite" in payload:
        item.repeat_enabled_input = _repeat_enabled_input(
            payload.get("repeat_enabled")
            if "repeat_enabled" in payload
            else payload.get("se_repite")
        )

    if (
        "repeat_interval_workdays" in payload
        or "cada_dias_habiles" in payload
    ):
        item.repeat_interval_workdays_input = _clean(
            payload.get("repeat_interval_workdays")
            if "repeat_interval_workdays" in payload
            else payload.get("cada_dias_habiles")
        ) or None


    if "actividad" in payload:
        item.actividad = _clean(payload.get("actividad")) or None

    if "observaciones" in payload:
        item.observaciones = _clean(payload.get("observaciones")) or None

    # Cualquier corrección invalida la resolución previa.
    item.target_type = None
    item.sucursal_id = None
    item.inventario_id = None
    item.building_classification_id = None
    item.responsable_user_id = None
    item.fecha_programada = None
    item.repeat_enabled = False
    item.repeat_interval_workdays = None
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


BUSINESS_TZ = ZoneInfo("America/Tijuana")
MAINTENANCE_DEPARTMENT_ID = 1


def _programmed_datetime_utc(programmed_date: date) -> datetime:
    local_dt = datetime.combine(
        programmed_date,
        time(hour=7),
        tzinfo=BUSINESS_TZ,
    )
    return local_dt.astimezone(timezone.utc)


def _published_duplicate_exists(
    item: MaintenancePreventiveItemORM,
) -> bool:
    target_type = _normalize_key(
        getattr(item, "target_type", None) or "EQUIPO"
    )

    query = MaintenancePreventiveItemORM.query.filter(
        MaintenancePreventiveItemORM.id != item.id,
        MaintenancePreventiveItemORM.ticket_id.isnot(None),
        MaintenancePreventiveItemORM.sucursal_id == item.sucursal_id,
        MaintenancePreventiveItemORM.fecha_programada == item.fecha_programada,
        MaintenancePreventiveItemORM.target_type == target_type,
    )

    if target_type == "EQUIPO":
        query = query.filter(
            MaintenancePreventiveItemORM.inventario_id
            == item.inventario_id
        )
    elif target_type == "EDIFICIO":
        query = query.filter(
            MaintenancePreventiveItemORM.building_classification_id
            == item.building_classification_id
        )
    else:
        return False

    return query.first() is not None


def publicar_lote_preventivo(
    batch_id: int,
    user,
) -> list[Ticket]:
    batch = _get_batch(batch_id)
    _assert_batch_manageable(user, batch)

    if batch.status != "BORRADOR":
        raise MaintenancePreventiveStateError(
            "Solo se pueden publicar lotes en BORRADOR."
        )

    items = list(batch.items or [])
    if not items:
        raise MaintenancePreventiveStateError(
            "El lote no contiene renglones para publicar."
        )

    not_valid = [
        item
        for item in items
        if item.validation_status != "VALIDO"
    ]
    if not_valid:
        raise MaintenancePreventiveStateError(
            "El lote contiene renglones pendientes o con error; "
            "debe validarse completamente antes de publicar."
        )

    created_tickets: list[Ticket] = []

    for item in items:
        if item.ticket_id is not None:
            raise MaintenancePreventiveStateError(
                "El lote contiene un renglón que ya generó ticket."
            )

        target_type = _normalize_key(
            getattr(item, "target_type", None)
        )
        if (
            item.sucursal_id is None
            or item.responsable_user_id is None
            or item.fecha_programada is None
            or not _clean(item.actividad)
            or target_type not in {"EQUIPO", "EDIFICIO"}
        ):
            raise MaintenancePreventiveStateError(
                "Un renglón marcado como válido no tiene resolución completa."
            )

        if (
            target_type == "EQUIPO"
            and item.inventario_id is None
        ) or (
            target_type == "EDIFICIO"
            and item.building_classification_id is None
        ):
            raise MaintenancePreventiveStateError(
                "Un renglón marcado como válido no tiene objetivo resuelto."
            )

        if not _can_manage_branch(user, item.sucursal_id):
            raise MaintenancePreventiveAuthorizationError(
                "El lote contiene una sucursal fuera de tu alcance."
            )

        if _published_duplicate_exists(item):
            raise MaintenancePreventiveStateError(
                "Ya existe un preventivo publicado para el mismo objetivo "
                "y fecha."
            )

        responsible = db.session.get(
            UserORM,
            int(item.responsable_user_id),
        )
        if responsible is None:
            raise MaintenancePreventiveStateError(
                "El responsable dejó de existir antes de publicar."
            )

        inventory = None
        building = None

        if target_type == "EQUIPO":
            inventory = db.session.get(
                InventarioGeneral,
                int(item.inventario_id),
            )
            if inventory is None:
                raise MaintenancePreventiveStateError(
                    "El equipo dejó de existir antes de publicar."
                )
            ticket_classification_id = None
            ticket_inventory_id = int(item.inventario_id)
            ticket_equipment_label = getattr(
                inventory,
                "nombre",
                None,
            )
        else:
            building = db.session.get(
                CatalogoClasificacion,
                int(item.building_classification_id),
            )
            if not _is_building_classification(building):
                raise MaintenancePreventiveStateError(
                    "La clasificación de Edificio dejó de ser válida."
                )
            ticket_classification_id = int(building.id)
            ticket_inventory_id = None
            ticket_equipment_label = _building_classification_label(
                building
            )

        programmed_at = _programmed_datetime_utc(item.fecha_programada)

        ticket = Ticket.create_ticket(
            descripcion=_clean(item.actividad),
            username=str(user.username),
            sucursal_id=int(user.sucursal_id),
            sucursal_id_destino=int(item.sucursal_id),
            departamento_id=MAINTENANCE_DEPARTMENT_ID,
            criticidad=1,
            clasificacion_id=ticket_classification_id,
            aparato_id=ticket_inventory_id,
            problema_detectado=None,
            necesita_refaccion=False,
            descripcion_refaccion=None,
            ubicacion=None,
            equipo=ticket_equipment_label,
            estado="abierto",
            requiere_aprobacion=False,
            tipo_mantenimiento="PREVENTIVO",
            maintenance_target_type=target_type,
            fecha_programada_original=programmed_at,
            fecha_programada_actual=programmed_at,
            commit=False,
        )

        ticket.asignado_a = str(responsible.username)
        if inventory is not None:
            ticket.familia_equipo_id = getattr(
                inventory,
                "familia_equipo_id",
                None,
            )

        item.ticket_id = ticket.id

        if bool(getattr(item, "repeat_enabled", False)):
            interval = _parse_workday_interval(
                getattr(item, "repeat_interval_workdays", None)
            )
            if interval is None:
                raise MaintenancePreventiveStateError(
                    "Un preventivo recurrente no tiene intervalo válido."
                )
            if item.fecha_programada.weekday() >= 5:
                raise MaintenancePreventiveStateError(
                    "La fecha inicial recurrente debe ser de lunes a viernes."
                )

            schedule = MaintenancePreventiveScheduleORM(
                schedule_key=_schedule_key(),
                target_type=target_type,
                sucursal_id=int(item.sucursal_id),
                inventario_id=(
                    int(item.inventario_id)
                    if target_type == "EQUIPO"
                    else None
                ),
                building_classification_id=(
                    int(item.building_classification_id)
                    if target_type == "EDIFICIO"
                    else None
                ),
                responsable_user_id=int(item.responsable_user_id),
                actividad=_clean(item.actividad),
                observaciones=_clean(item.observaciones) or None,
                repeat_interval_workdays=interval,
                start_date=item.fecha_programada,
                next_scheduled_date=add_workdays(
                    item.fecha_programada,
                    interval,
                ),
                active=True,
                created_by_user_id=int(user.id),
            )
            db.session.add(schedule)
            item.schedule = schedule

            occurrence = MaintenancePreventiveOccurrenceORM(
                schedule=schedule,
                scheduled_date=item.fecha_programada,
                ticket_id=ticket.id,
            )
            db.session.add(occurrence)

        created_tickets.append(ticket)

    batch.status = "PUBLICADO"
    batch.published_by_user_id = int(user.id)
    batch.published_at = datetime.now(timezone.utc)

    db.session.flush()
    return created_tickets


def _find_schedule_occurrence(
    schedule_id: int,
    scheduled_date: date,
) -> MaintenancePreventiveOccurrenceORM | None:
    return (
        MaintenancePreventiveOccurrenceORM.query
        .filter(
            MaintenancePreventiveOccurrenceORM.schedule_id
            == int(schedule_id),
            MaintenancePreventiveOccurrenceORM.scheduled_date
            == scheduled_date,
        )
        .first()
    )


def materializar_programacion_recurrente(
    schedule: MaintenancePreventiveScheduleORM,
    *,
    through_date: date,
    occurrence_lookup: Callable = _find_schedule_occurrence,
) -> dict:
    """Genera como máximo una ocurrencia pendiente de una programación."""
    if schedule is None or not bool(schedule.active):
        return {
            "generated": False,
            "reason": "inactive",
            "ticket_id": None,
        }

    due_date = schedule.next_scheduled_date
    if due_date is None or due_date > through_date:
        return {
            "generated": False,
            "reason": "not_due",
            "ticket_id": None,
        }

    interval = _parse_workday_interval(
        schedule.repeat_interval_workdays
    )
    if interval is None:
        raise MaintenancePreventiveStateError(
            "La programación recurrente no tiene intervalo válido."
        )

    if due_date.weekday() >= 5:
        raise MaintenancePreventiveStateError(
            "La próxima fecha recurrente debe ser de lunes a viernes."
        )

    existing = occurrence_lookup(int(schedule.id), due_date)
    if existing is not None:
        schedule.next_scheduled_date = add_workdays(
            due_date,
            interval,
        )
        return {
            "generated": False,
            "reason": "already_exists",
            "ticket_id": existing.ticket_id,
            "scheduled_date": due_date.isoformat(),
            "next_scheduled_date": (
                schedule.next_scheduled_date.isoformat()
            ),
        }

    target_type = _normalize_key(schedule.target_type or "EQUIPO")
    if target_type not in {"EQUIPO", "EDIFICIO"}:
        raise MaintenancePreventiveStateError(
            "La programación recurrente tiene un tipo de objetivo inválido."
        )

    inventory = None
    building = None

    if target_type == "EQUIPO":
        inventory = db.session.get(
            InventarioGeneral,
            int(schedule.inventario_id or 0),
        )
        if inventory is None:
            raise MaintenancePreventiveStateError(
                "El equipo de la programación recurrente no existe."
            )
        ticket_classification_id = None
        ticket_inventory_id = int(schedule.inventario_id)
        ticket_equipment_label = getattr(inventory, "nombre", None)
    else:
        building = db.session.get(
            CatalogoClasificacion,
            int(schedule.building_classification_id or 0),
        )
        if not _is_building_classification(building):
            raise MaintenancePreventiveStateError(
                "La clasificación de Edificio de la programación "
                "recurrente ya no es válida."
            )
        ticket_classification_id = int(building.id)
        ticket_inventory_id = None
        ticket_equipment_label = _building_classification_label(building)

    responsible = db.session.get(
        UserORM,
        int(schedule.responsable_user_id or 0),
    )
    if responsible is None:
        raise MaintenancePreventiveStateError(
            "El responsable de la programación recurrente no existe."
        )

    creator = None
    if schedule.created_by_user_id is not None:
        creator = db.session.get(
            UserORM,
            int(schedule.created_by_user_id),
        )

    creator_username = (
        _clean(getattr(creator, "username", None))
        or "SISTEMA_PM"
    )
    try:
        creator_branch_id = int(
            getattr(creator, "sucursal_id", None)
            or schedule.sucursal_id
        )
    except (TypeError, ValueError):
        creator_branch_id = int(schedule.sucursal_id)

    programmed_at = _programmed_datetime_utc(due_date)
    ticket = Ticket.create_ticket(
        descripcion=_clean(schedule.actividad),
        username=creator_username,
        sucursal_id=creator_branch_id,
        sucursal_id_destino=int(schedule.sucursal_id),
        departamento_id=MAINTENANCE_DEPARTMENT_ID,
        criticidad=1,
        clasificacion_id=ticket_classification_id,
        aparato_id=ticket_inventory_id,
        problema_detectado=None,
        necesita_refaccion=False,
        descripcion_refaccion=None,
        ubicacion=None,
        equipo=ticket_equipment_label,
        estado="abierto",
        requiere_aprobacion=False,
        tipo_mantenimiento="PREVENTIVO",
        maintenance_target_type=target_type,
        fecha_programada_original=programmed_at,
        fecha_programada_actual=programmed_at,
        commit=False,
    )
    ticket.asignado_a = str(responsible.username)
    if inventory is not None:
        ticket.familia_equipo_id = getattr(
            inventory,
            "familia_equipo_id",
            None,
        )

    occurrence = MaintenancePreventiveOccurrenceORM(
        schedule_id=int(schedule.id),
        scheduled_date=due_date,
        ticket_id=int(ticket.id),
    )
    db.session.add(occurrence)

    schedule.next_scheduled_date = add_workdays(
        due_date,
        interval,
    )

    return {
        "generated": True,
        "reason": "generated",
        "ticket_id": int(ticket.id),
        "scheduled_date": due_date.isoformat(),
        "next_scheduled_date": schedule.next_scheduled_date.isoformat(),
    }


def materializar_programaciones_recurrentes(
    *,
    through_date: date | None = None,
    limit: int = 500,
) -> dict:
    """Materializa una sola ocurrencia por serie activa y ejecución."""
    target_date = through_date or datetime.now(BUSINESS_TZ).date()

    try:
        row_limit = int(limit)
    except (TypeError, ValueError) as exc:
        raise MaintenancePreventiveError(
            "limit debe ser un entero positivo."
        ) from exc
    if row_limit <= 0:
        raise MaintenancePreventiveError(
            "limit debe ser mayor a cero."
        )

    schedules = (
        MaintenancePreventiveScheduleORM.query
        .filter(
            MaintenancePreventiveScheduleORM.active.is_(True),
            MaintenancePreventiveScheduleORM.next_scheduled_date
            <= target_date,
        )
        .order_by(
            MaintenancePreventiveScheduleORM.next_scheduled_date.asc(),
            MaintenancePreventiveScheduleORM.id.asc(),
        )
        .limit(row_limit)
        .with_for_update(skip_locked=True)
        .all()
    )

    generated = 0
    existing = 0
    errors: list[dict] = []
    results: list[dict] = []

    for schedule in schedules:
        try:
            result = materializar_programacion_recurrente(
                schedule,
                through_date=target_date,
            )
            results.append(
                {
                    "schedule_id": int(schedule.id),
                    **result,
                }
            )
            if result.get("generated"):
                generated += 1
            elif result.get("reason") == "already_exists":
                existing += 1
        except MaintenancePreventiveError as exc:
            errors.append(
                {
                    "schedule_id": int(schedule.id),
                    "error": str(exc),
                }
            )

    db.session.flush()

    return {
        "through_date": target_date.isoformat(),
        "considered": len(schedules),
        "generated": generated,
        "already_existing": existing,
        "errors": errors,
        "results": results,
    }


def serializar_item(item: MaintenancePreventiveItemORM) -> dict:
    return {
        "id": item.id,
        "batch_id": item.batch_id,
        "source_row_number": item.source_row_number,
        "target_type_input": (
            getattr(item, "target_type_input", None)
            or getattr(item, "target_type", None)
            or "EQUIPO"
        ),
        "sucursal_input": item.sucursal_input,
        "codigo_equipo_input": item.codigo_equipo_input,
        "building_classification_input": getattr(
            item,
            "building_classification_input",
            None,
        ),
        "responsable_input": item.responsable_input,
        "fecha_programada_input": item.fecha_programada_input,
        "repeat_enabled_input": (
            getattr(item, "repeat_enabled_input", None)
            or (
                "SI"
                if bool(getattr(item, "repeat_enabled", False))
                else "NO"
            )
        ),
        "repeat_interval_workdays_input": (
            getattr(item, "repeat_interval_workdays_input", None)
            or (
                str(item.repeat_interval_workdays)
                if getattr(item, "repeat_interval_workdays", None)
                is not None
                else None
            )
        ),
        "target_type": getattr(item, "target_type", None),
        "sucursal_id": item.sucursal_id,
        "inventario_id": item.inventario_id,
        "building_classification_id": getattr(
            item,
            "building_classification_id",
            None,
        ),
        "building_classification": (
            {
                "id": int(item.building_classification.id),
                "nombre": str(item.building_classification.nombre),
                "label": _building_classification_label(
                    item.building_classification
                ),
            }
            if getattr(item, "building_classification", None) is not None
            else None
        ),
        "responsable_user_id": item.responsable_user_id,
        "fecha_programada": (
            item.fecha_programada.isoformat()
            if item.fecha_programada
            else None
        ),
        "repeat_enabled": bool(
            getattr(item, "repeat_enabled", False)
        ),
        "repeat_interval_workdays": getattr(
            item,
            "repeat_interval_workdays",
            None,
        ),
        "schedule_id": getattr(item, "schedule_id", None),
        "next_scheduled_date": (
            item.schedule.next_scheduled_date.isoformat()
            if getattr(item, "schedule", None) is not None
            and item.schedule.next_scheduled_date is not None
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

    for date_format in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, date_format).date()
        except ValueError:
            continue

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


def _active_personnel_for_user(
    user: UserORM | None,
) -> MaintenancePersonnelORM | None:
    if user is None:
        return None

    return (
        MaintenancePersonnelORM.query
        .filter(
            MaintenancePersonnelORM.user_id == int(user.id),
            MaintenancePersonnelORM.activo.is_(True),
        )
        .first()
    )


def _validate_responsable_catalog(
    user: UserORM | None,
    *,
    branch_id: int | None = None,
) -> tuple[bool, str | None]:
    if user is None:
        return False, "Responsable inexistente en Suite."

    try:
        if int(getattr(user, "department_id", 0) or 0) != 1:
            return (
                False,
                "El responsable no pertenece al departamento de Mantenimiento.",
            )
    except (TypeError, ValueError):
        return (
            False,
            "El responsable no pertenece al departamento de Mantenimiento.",
        )

    personnel = _active_personnel_for_user(user)
    if personnel is None:
        return (
            False,
            "El responsable no está activo en el catálogo de personal de Mantenimiento.",
        )

    crew = personnel.crew
    if (
        branch_id is None
        or crew is None
        or not bool(crew.activo)
        or crew.region_id is None
    ):
        return True, None

    branch_assignment = (
        SuiteSucursalRegionAssignmentORM.query
        .filter(
            SuiteSucursalRegionAssignmentORM.sucursal_id == int(branch_id),
            SuiteSucursalRegionAssignmentORM.is_current.is_(True),
        )
        .order_by(SuiteSucursalRegionAssignmentORM.id.desc())
        .first()
    )

    if branch_assignment is None:
        return (
            False,
            "La sucursal no tiene una región operativa vigente.",
        )

    if int(branch_assignment.region_id) != int(crew.region_id):
        return (
            False,
            "El responsable pertenece a una cuadrilla de otra región.",
        )

    return True, None


def _item_duplicate_key(item: MaintenancePreventiveItemORM):
    if item.sucursal_id is None or item.fecha_programada is None:
        return None

    target_type = _normalize_key(
        getattr(item, "target_type", None) or "EQUIPO"
    )

    if target_type == "EQUIPO":
        target_id = getattr(item, "inventario_id", None)
    elif target_type == "EDIFICIO":
        target_id = getattr(item, "building_classification_id", None)
    else:
        return None

    if target_id is None:
        return None

    return (
        int(item.sucursal_id),
        target_type,
        int(target_id),
        item.fecha_programada.isoformat(),
    )


def validar_item_borrador(
    item: MaintenancePreventiveItemORM,
    *,
    seen_keys: set | None = None,
    actor=None,
    resolve_sucursal: Callable = _resolve_sucursal,
    resolve_equipo: Callable = _resolve_equipo_by_code,
    equipo_asignado: Callable = _equipo_asignado_a_sucursal,
    resolve_building: Callable = _resolve_building_classification,
    resolve_responsable: Callable = _resolve_responsable,
    validate_responsable: Callable = _validate_responsable_catalog,
) -> list[str]:
    """Resuelve y valida un renglón sin borrarlo si contiene errores."""

    seen_keys = seen_keys if seen_keys is not None else set()
    errors: list[str] = []

    # Cada nueva validación parte de los datos de entrada; evita conservar IDs
    # viejos después de corregir una fila.
    item.target_type = None
    item.sucursal_id = None
    item.inventario_id = None
    item.building_classification_id = None
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

    raw_target_type = _normalize_key(
        getattr(item, "target_type_input", None) or "EQUIPO"
    )
    target_aliases = {
        "EQUIPO": "EQUIPO",
        "APARATO": "EQUIPO",
        "APARATOS": "EQUIPO",
        "EDIFICIO": "EDIFICIO",
    }
    target_type = target_aliases.get(raw_target_type)

    if target_type is None:
        errors.append("Tipo debe ser Equipo o Edificio.")
    else:
        item.target_type = target_type

    if target_type == "EQUIPO":
        if _clean(getattr(item, "building_classification_input", None)):
            errors.append(
                "La clasificación de Edificio no aplica a un preventivo de Equipo."
            )

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
                errors.append(
                    "El código no corresponde a un equipo de Aparatos."
                )

        if item.sucursal_id is not None and item.inventario_id is not None:
            if not equipo_asignado(item.inventario_id, item.sucursal_id):
                errors.append(
                    "El equipo no está asignado actualmente a la sucursal indicada."
                )

    elif target_type == "EDIFICIO":
        if _clean(item.codigo_equipo_input):
            errors.append(
                "Código equipo no aplica a un preventivo de Edificio."
            )

        try:
            building = resolve_building(
                getattr(item, "building_classification_input", None)
            )
        except MaintenancePreventiveError as exc:
            building = None
            errors.append(str(exc))

        if building is None:
            if _clean(
                getattr(item, "building_classification_input", None)
            ):
                errors.append(
                    "Clasificación de Edificio inexistente o inválida."
                )
            else:
                errors.append("Clasificación de Edificio vacía.")
        else:
            item.building_classification_id = int(building.id)

    responsable = resolve_responsable(item.responsable_input)
    if responsable is None:
        if _clean(item.responsable_input):
            errors.append("Responsable inexistente en Suite.")
        else:
            errors.append("Responsable vacío.")
    else:
        valid_responsable, responsible_error = validate_responsable(
            responsable,
            branch_id=item.sucursal_id,
        )
        if not valid_responsable:
            errors.append(
                responsible_error
                or "Responsable inválido para programación preventiva."
            )
        else:
            item.responsable_user_id = int(responsable.id)

    parsed_date = _parse_programmed_date(item.fecha_programada_input)
    if parsed_date is None:
        errors.append(
            "Fecha programada inválida; usa formato DD/MM/AAAA."
        )
    else:
        item.fecha_programada = parsed_date

    raw_repeat = getattr(item, "repeat_enabled_input", None)
    if raw_repeat in (None, ""):
        repeat_enabled = bool(
            getattr(item, "repeat_enabled", False)
        )
        repeat_input_valid = True
    else:
        try:
            repeat_enabled = _parse_repeat_enabled(raw_repeat)
            repeat_input_valid = True
        except MaintenancePreventiveError:
            repeat_enabled = False
            repeat_input_valid = False
            errors.append("Se repite debe ser Sí o No.")

    item.repeat_enabled = repeat_enabled

    interval_input = getattr(
        item,
        "repeat_interval_workdays_input",
        None,
    )
    if interval_input in (None, ""):
        interval_input = getattr(
            item,
            "repeat_interval_workdays",
            None,
        )

    if repeat_enabled:
        try:
            interval = _parse_workday_interval(interval_input)
        except MaintenancePreventiveError:
            interval = None
            errors.append(
                "La repetición requiere un intervalo de días hábiles "
                "mayor a cero."
            )

        if (
            item.fecha_programada is not None
            and item.fecha_programada.weekday() >= 5
        ):
            errors.append(
                "La fecha inicial de un preventivo recurrente debe ser "
                "de lunes a viernes."
            )

        item.repeat_interval_workdays = interval
    else:
        if repeat_input_valid and _clean(interval_input):
            errors.append(
                "El intervalo de días hábiles solo aplica cuando "
                "Se repite es Sí."
            )
        item.repeat_interval_workdays = None

    item.actividad = _clean(item.actividad) or None
    if item.actividad is None:
        errors.append("Actividad preventiva vacía.")

    duplicate_key = _item_duplicate_key(item)
    if duplicate_key is not None:
        if duplicate_key in seen_keys:
            errors.append(
                "El mismo objetivo ya está programado para esa fecha "
                "dentro del mismo lote."
            )
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
