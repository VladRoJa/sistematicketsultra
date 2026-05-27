# backend/app/warehouse/services/planning_targets_service.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from app.extensions import db
from app.models import (
    PlanningModelConfigORM,
    PlanningTargetApprovalEventORM,
    PlanningTargetBatchORM,
    PlanningTargetBranchRowORM,
)
from app.models.warehouse import TrackBranchCatalogORM


class PlanningTargetsServiceError(RuntimeError):
    """Error base para servicios de Planeación Comercial / Metas."""


@dataclass(slots=True)
class CreatePlanningModelConfigCommand:
    name: str
    version: int
    created_by_user_id: int | None = None
    description: str | None = None
    trend_window_months: int = 3
    trend_closed_months_only: bool = True
    arpu_strategy: str = "PROMEDIO_3M"
    bajas_strategy: str = "PROMEDIO_HISTORICO_SUCURSAL"
    reactivaciones_strategy: str = "PROMEDIO_HISTORICO_SUCURSAL"
    domiciliados_strategy: str = "PORCENTAJE_CLIENTES_NUEVOS"
    aggregators_strategy: str = "SEPARADAS_SOLO_INGRESO"
    new_branch_strategy: str = "PROMEDIO_REGIONAL"
    risk_rules_json: dict[str, Any] | None = None
    parameters_json: dict[str, Any] | None = None
    notes: str | None = None

@dataclass(slots=True)
class CreatePlanningTargetBatchCommand:
    target_month: date
    version: int
    created_by_user_id: int | None = None
    model_config_id: int | None = None
    source_upload_id: int | None = None
    scope: str = "MONTHLY_BATCH"
    source_type: str = "MANUAL"
    scenario_base: str | None = None
    notes: str | None = None

@dataclass(slots=True)
class AddPlanningTargetBranchRowCommand:
    batch_id: int
    sucursal_canon: str

    m2_sin_circulaciones: Decimal
    usuarios_inicio_mes: int
    proyeccion_usuarios_cierre_mes: int

    meta_faycgo_mes: Decimal
    meta_clientes_nuevos_mes: int
    meta_reactivaciones_mes: int
    meta_bajas_mes: int
    meta_nuevos_domiciliados_mes: int
    meta_arpu_mes: Decimal
    meta_venta_tienda_mes: Decimal

    ingreso_agregadoras_estimado: Decimal | None = None
    usuarios_agregadoras_estimado: int | None = None

    scenario_used: str | None = None
    trend_classification: str | None = None
    risk_level: str | None = None
    status: str = "PROPUESTA"
    previous_branch_row_id: int | None = None
    notes: str | None = None

@dataclass(slots=True)
class SubmitPlanningTargetBatchCommand:
    batch_id: int
    submitted_by_user_id: int | None = None
    actor_username_snapshot: str | None = None
    comment: str | None = None

@dataclass(slots=True)
class ApprovePlanningTargetBatchCommand:
    batch_id: int
    approved_by_user_id: int | None = None
    actor_username_snapshot: str | None = None
    comment: str | None = None

@dataclass(slots=True)
class RejectPlanningTargetBatchCommand:
    batch_id: int
    rejected_by_user_id: int | None = None
    actor_username_snapshot: str | None = None
    comment: str | None = None

def _ensure_text(value: Any, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise PlanningTargetsServiceError(
            f"El campo {field_name!r} es obligatorio."
        )
    return normalized


def _ensure_optional_text(value: Any) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip()
    return normalized or None

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

def _ensure_positive_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise PlanningTargetsServiceError(
            f"El campo {field_name!r} no puede ser bool."
        )

    try:
        normalized = int(value)
    except Exception as exc:
        raise PlanningTargetsServiceError(
            f"No se pudo convertir a int el campo {field_name!r}: {value!r}"
        ) from exc

    if normalized <= 0:
        raise PlanningTargetsServiceError(
            f"El campo {field_name!r} debe ser mayor a 0."
        )

    return normalized

def _ensure_non_negative_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise PlanningTargetsServiceError(
            f"El campo {field_name!r} no puede ser bool."
        )

    try:
        normalized = int(value)
    except Exception as exc:
        raise PlanningTargetsServiceError(
            f"No se pudo convertir a int el campo {field_name!r}: {value!r}"
        ) from exc

    if normalized < 0:
        raise PlanningTargetsServiceError(
            f"El campo {field_name!r} no puede ser negativo."
        )

    return normalized


def _ensure_optional_non_negative_int(
    value: Any,
    *,
    field_name: str,
) -> int | None:
    if value is None:
        return None

    return _ensure_non_negative_int(value, field_name=field_name)


def _ensure_non_negative_decimal(value: Any, *, field_name: str) -> Decimal:
    try:
        normalized = Decimal(str(value))
    except Exception as exc:
        raise PlanningTargetsServiceError(
            f"No se pudo convertir a Decimal el campo {field_name!r}: {value!r}"
        ) from exc

    if normalized < 0:
        raise PlanningTargetsServiceError(
            f"El campo {field_name!r} no puede ser negativo."
        )

    return normalized


def _ensure_optional_non_negative_decimal(
    value: Any,
    *,
    field_name: str,
) -> Decimal | None:
    if value is None:
        return None

    return _ensure_non_negative_decimal(value, field_name=field_name)

def _ensure_date(value: Any, *, field_name: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except Exception as exc:
            raise PlanningTargetsServiceError(
                f"No se pudo convertir a date el campo {field_name!r}: {value!r}"
            ) from exc

    raise PlanningTargetsServiceError(
        f"Valor inválido para {field_name!r}: {value!r}"
    )


def _normalize_target_month(value: Any) -> date:
    month_date = _ensure_date(value, field_name="target_month")
    return month_date.replace(day=1)


def _ensure_optional_positive_int(
    value: Any,
    *,
    field_name: str,
) -> int | None:
    if value is None:
        return None

    return _ensure_positive_int(value, field_name=field_name)

def _ensure_optional_user_id(value: Any, *, field_name: str) -> int | None:
    if value is None:
        return None

    if isinstance(value, bool):
        raise PlanningTargetsServiceError(
            f"El campo {field_name!r} no puede ser bool."
        )

    try:
        normalized = int(value)
    except Exception as exc:
        raise PlanningTargetsServiceError(
            f"No se pudo convertir a int el campo {field_name!r}: {value!r}"
        ) from exc

    if normalized <= 0:
        raise PlanningTargetsServiceError(
            f"El campo {field_name!r} debe ser mayor a 0."
        )

    return normalized


def _ensure_optional_dict(
    value: Any,
    *,
    field_name: str,
) -> dict[str, Any] | None:
    if value is None:
        return None

    if not isinstance(value, dict):
        raise PlanningTargetsServiceError(
            f"El campo {field_name!r} debe ser dict o None."
        )

    return value


def _ensure_model_config_version_available(
    *,
    name: str,
    version: int,
) -> None:
    existing = PlanningModelConfigORM.query.filter_by(
        name=name,
        version=version,
    ).first()

    if existing is not None:
        raise PlanningTargetsServiceError(
            f"Ya existe una configuración de modelo con name={name!r} "
            f"y version={version!r}."
        )

def _ensure_model_config_exists(model_config_id: int | None) -> None:
    if model_config_id is None:
        return

    exists = PlanningModelConfigORM.query.get(model_config_id)

    if exists is None:
        raise PlanningTargetsServiceError(
            f"No existe planning_model_configs.id={model_config_id!r}."
        )


def _ensure_target_batch_version_available(
    *,
    target_month: date,
    version: int,
) -> None:
    existing = PlanningTargetBatchORM.query.filter_by(
        target_month=target_month,
        version=version,
    ).first()

    if existing is not None:
        raise PlanningTargetsServiceError(
            f"Ya existe un batch con target_month={target_month.isoformat()!r} "
            f"y version={version!r}."
        )

def _get_target_batch(batch_id: int) -> PlanningTargetBatchORM:
    normalized_batch_id = _ensure_positive_int(
        batch_id,
        field_name="batch_id",
    )

    batch = PlanningTargetBatchORM.query.get(normalized_batch_id)

    if batch is None:
        raise PlanningTargetsServiceError(
            f"No existe planning_target_batches.id={normalized_batch_id!r}."
        )

    return batch


def _ensure_branch_exists(sucursal_canon: str) -> str:
    normalized = _ensure_text(
        sucursal_canon,
        field_name="sucursal_canon",
    )

    exists = TrackBranchCatalogORM.query.filter_by(
        sucursal_canon=normalized,
    ).first()

    if exists is None:
        raise PlanningTargetsServiceError(
            f"La sucursal_canon no existe en track_branch_catalog: {normalized!r}."
        )

    return normalized


def _ensure_branch_row_available(
    *,
    batch_id: int,
    sucursal_canon: str,
) -> None:
    existing = PlanningTargetBranchRowORM.query.filter_by(
        batch_id=batch_id,
        sucursal_canon=sucursal_canon,
    ).first()

    if existing is not None:
        raise PlanningTargetsServiceError(
            f"Ya existe una fila para batch_id={batch_id!r} "
            f"y sucursal_canon={sucursal_canon!r}."
        )


def _ensure_previous_branch_row_exists(
    previous_branch_row_id: int | None,
) -> None:
    if previous_branch_row_id is None:
        return

    normalized_id = _ensure_positive_int(
        previous_branch_row_id,
        field_name="previous_branch_row_id",
    )

    exists = PlanningTargetBranchRowORM.query.get(normalized_id)

    if exists is None:
        raise PlanningTargetsServiceError(
            f"No existe planning_target_branch_rows.id={normalized_id!r}."
        )

def _ensure_batch_can_submit(batch: PlanningTargetBatchORM) -> None:
    allowed_statuses = {"BORRADOR", "PROPUESTA"}

    if batch.status not in allowed_statuses:
        raise PlanningTargetsServiceError(
            f"El batch id={batch.id!r} no puede enviarse a revisión "
            f"desde status={batch.status!r}."
        )

    if not batch.branch_rows:
        raise PlanningTargetsServiceError(
            f"El batch id={batch.id!r} no puede enviarse a revisión "
            "porque no tiene filas por sucursal."
        )

def _ensure_batch_can_approve(batch: PlanningTargetBatchORM) -> None:
    if batch.status != "EN_REVISION":
        raise PlanningTargetsServiceError(
            f"El batch id={batch.id!r} no puede aprobarse "
            f"desde status={batch.status!r}."
        )

    if not batch.branch_rows:
        raise PlanningTargetsServiceError(
            f"El batch id={batch.id!r} no puede aprobarse "
            "porque no tiene filas por sucursal."
        )

def _ensure_batch_can_reject(batch: PlanningTargetBatchORM) -> None:
    if batch.status != "EN_REVISION":
        raise PlanningTargetsServiceError(
            f"El batch id={batch.id!r} no puede rechazarse "
            f"desde status={batch.status!r}."
        )


def _ensure_required_comment(value: Any, *, field_name: str) -> str:
    normalized = _ensure_text(value, field_name=field_name)

    if len(normalized) < 5:
        raise PlanningTargetsServiceError(
            f"El campo {field_name!r} debe tener al menos 5 caracteres."
        )

    return normalized

def _serialize_decimal(value: Any) -> str | None:
    if value is None:
        return None

    return str(value)


def _serialize_datetime(value: Any) -> str | None:
    if value is None:
        return None

    return value.isoformat()

def create_model_config(
    command: CreatePlanningModelConfigCommand,
) -> dict[str, Any]:
    if not isinstance(command, CreatePlanningModelConfigCommand):
        raise PlanningTargetsServiceError(
            "command debe ser instancia de CreatePlanningModelConfigCommand."
        )

    name = _ensure_text(command.name, field_name="name")
    version = _ensure_positive_int(command.version, field_name="version")

    _ensure_model_config_version_available(name=name, version=version)

    row = PlanningModelConfigORM(
        name=name,
        version=version,
        status="BORRADOR",
        description=_ensure_optional_text(command.description),
        trend_window_months=_ensure_positive_int(
            command.trend_window_months,
            field_name="trend_window_months",
        ),
        trend_closed_months_only=bool(command.trend_closed_months_only),
        arpu_strategy=_ensure_text(
            command.arpu_strategy,
            field_name="arpu_strategy",
        ),
        bajas_strategy=_ensure_text(
            command.bajas_strategy,
            field_name="bajas_strategy",
        ),
        reactivaciones_strategy=_ensure_text(
            command.reactivaciones_strategy,
            field_name="reactivaciones_strategy",
        ),
        domiciliados_strategy=_ensure_text(
            command.domiciliados_strategy,
            field_name="domiciliados_strategy",
        ),
        aggregators_strategy=_ensure_text(
            command.aggregators_strategy,
            field_name="aggregators_strategy",
        ),
        new_branch_strategy=_ensure_text(
            command.new_branch_strategy,
            field_name="new_branch_strategy",
        ),
        risk_rules_json=_ensure_optional_dict(
            command.risk_rules_json,
            field_name="risk_rules_json",
        ),
        parameters_json=_ensure_optional_dict(
            command.parameters_json,
            field_name="parameters_json",
        ),
        created_by_user_id=_ensure_optional_user_id(
            command.created_by_user_id,
            field_name="created_by_user_id",
        ),
        notes=_ensure_optional_text(command.notes),
    )

    db.session.add(row)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return {
        "status": "created",
        "id": row.id,
        "name": row.name,
        "version": row.version,
        "model_status": row.status,
    }
    
def create_target_batch(
    command: CreatePlanningTargetBatchCommand,
) -> dict[str, Any]:
    if not isinstance(command, CreatePlanningTargetBatchCommand):
        raise PlanningTargetsServiceError(
            "command debe ser instancia de CreatePlanningTargetBatchCommand."
        )

    target_month = _normalize_target_month(command.target_month)
    version = _ensure_positive_int(command.version, field_name="version")
    model_config_id = _ensure_optional_positive_int(
        command.model_config_id,
        field_name="model_config_id",
    )
    source_upload_id = _ensure_optional_positive_int(
        command.source_upload_id,
        field_name="source_upload_id",
    )

    _ensure_model_config_exists(model_config_id)
    _ensure_target_batch_version_available(
        target_month=target_month,
        version=version,
    )

    row = PlanningTargetBatchORM(
        target_month=target_month,
        version=version,
        status="BORRADOR",
        scope=_ensure_text(command.scope, field_name="scope"),
        source_type=_ensure_text(command.source_type, field_name="source_type"),
        source_upload_id=source_upload_id,
        model_config_id=model_config_id,
        scenario_base=_ensure_optional_text(command.scenario_base),
        created_by_user_id=_ensure_optional_user_id(
            command.created_by_user_id,
            field_name="created_by_user_id",
        ),
        notes=_ensure_optional_text(command.notes),
    )

    db.session.add(row)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return {
        "status": "created",
        "id": row.id,
        "target_month": row.target_month.isoformat(),
        "version": row.version,
        "batch_status": row.status,
        "scope": row.scope,
        "source_type": row.source_type,
        "model_config_id": row.model_config_id,
    }
    
def add_branch_row_to_batch(
    command: AddPlanningTargetBranchRowCommand,
) -> dict[str, Any]:
    if not isinstance(command, AddPlanningTargetBranchRowCommand):
        raise PlanningTargetsServiceError(
            "command debe ser instancia de AddPlanningTargetBranchRowCommand."
        )

    batch = _get_target_batch(command.batch_id)
    sucursal_canon = _ensure_branch_exists(command.sucursal_canon)

    _ensure_branch_row_available(
        batch_id=batch.id,
        sucursal_canon=sucursal_canon,
    )

    previous_branch_row_id = _ensure_optional_positive_int(
        command.previous_branch_row_id,
        field_name="previous_branch_row_id",
    )
    _ensure_previous_branch_row_exists(previous_branch_row_id)

    row = PlanningTargetBranchRowORM(
        batch_id=batch.id,
        target_month=batch.target_month,
        sucursal_canon=sucursal_canon,
        m2_sin_circulaciones=_ensure_non_negative_decimal(
            command.m2_sin_circulaciones,
            field_name="m2_sin_circulaciones",
        ),
        usuarios_inicio_mes=_ensure_non_negative_int(
            command.usuarios_inicio_mes,
            field_name="usuarios_inicio_mes",
        ),
        proyeccion_usuarios_cierre_mes=_ensure_non_negative_int(
            command.proyeccion_usuarios_cierre_mes,
            field_name="proyeccion_usuarios_cierre_mes",
        ),
        meta_faycgo_mes=_ensure_non_negative_decimal(
            command.meta_faycgo_mes,
            field_name="meta_faycgo_mes",
        ),
        meta_clientes_nuevos_mes=_ensure_non_negative_int(
            command.meta_clientes_nuevos_mes,
            field_name="meta_clientes_nuevos_mes",
        ),
        meta_reactivaciones_mes=_ensure_non_negative_int(
            command.meta_reactivaciones_mes,
            field_name="meta_reactivaciones_mes",
        ),
        meta_bajas_mes=_ensure_non_negative_int(
            command.meta_bajas_mes,
            field_name="meta_bajas_mes",
        ),
        meta_nuevos_domiciliados_mes=_ensure_non_negative_int(
            command.meta_nuevos_domiciliados_mes,
            field_name="meta_nuevos_domiciliados_mes",
        ),
        meta_arpu_mes=_ensure_non_negative_decimal(
            command.meta_arpu_mes,
            field_name="meta_arpu_mes",
        ),
        meta_venta_tienda_mes=_ensure_non_negative_decimal(
            command.meta_venta_tienda_mes,
            field_name="meta_venta_tienda_mes",
        ),
        ingreso_agregadoras_estimado=_ensure_optional_non_negative_decimal(
            command.ingreso_agregadoras_estimado,
            field_name="ingreso_agregadoras_estimado",
        ),
        usuarios_agregadoras_estimado=_ensure_optional_non_negative_int(
            command.usuarios_agregadoras_estimado,
            field_name="usuarios_agregadoras_estimado",
        ),
        scenario_used=_ensure_optional_text(command.scenario_used),
        trend_classification=_ensure_optional_text(command.trend_classification),
        risk_level=_ensure_optional_text(command.risk_level),
        status=_ensure_text(command.status, field_name="status"),
        previous_branch_row_id=previous_branch_row_id,
        notes=_ensure_optional_text(command.notes),
    )

    db.session.add(row)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return {
        "status": "created",
        "id": row.id,
        "batch_id": row.batch_id,
        "target_month": row.target_month.isoformat(),
        "sucursal_canon": row.sucursal_canon,
        "row_status": row.status,
        "meta_faycgo_mes": str(row.meta_faycgo_mes),
    }    
    
def get_batch_detail(batch_id: int) -> dict[str, Any]:
    batch = _get_target_batch(batch_id)

    model_config = batch.model_config

    return {
        "id": batch.id,
        "target_month": batch.target_month.isoformat(),
        "version": batch.version,
        "status": batch.status,
        "scope": batch.scope,
        "source_type": batch.source_type,
        "source_upload_id": batch.source_upload_id,
        "scenario_base": batch.scenario_base,
        "published_at": _serialize_datetime(batch.published_at),
        "is_canonical": batch.is_canonical,
        "notes": batch.notes,
        "created_by_user_id": batch.created_by_user_id,
        "created_at": _serialize_datetime(batch.created_at),
        "updated_at": _serialize_datetime(batch.updated_at),
        "model_config": None
        if model_config is None
        else {
            "id": model_config.id,
            "name": model_config.name,
            "version": model_config.version,
            "status": model_config.status,
            "trend_window_months": model_config.trend_window_months,
            "trend_closed_months_only": model_config.trend_closed_months_only,
            "arpu_strategy": model_config.arpu_strategy,
            "bajas_strategy": model_config.bajas_strategy,
            "reactivaciones_strategy": model_config.reactivaciones_strategy,
            "domiciliados_strategy": model_config.domiciliados_strategy,
            "aggregators_strategy": model_config.aggregators_strategy,
            "new_branch_strategy": model_config.new_branch_strategy,
            "risk_rules_json": model_config.risk_rules_json,
            "parameters_json": model_config.parameters_json,
        },
        "branch_rows": [
            {
                "id": row.id,
                "batch_id": row.batch_id,
                "target_month": row.target_month.isoformat(),
                "sucursal_canon": row.sucursal_canon,
                "m2_sin_circulaciones": _serialize_decimal(
                    row.m2_sin_circulaciones
                ),
                "usuarios_inicio_mes": row.usuarios_inicio_mes,
                "proyeccion_usuarios_cierre_mes": row.proyeccion_usuarios_cierre_mes,
                "meta_faycgo_mes": _serialize_decimal(row.meta_faycgo_mes),
                "meta_clientes_nuevos_mes": row.meta_clientes_nuevos_mes,
                "meta_reactivaciones_mes": row.meta_reactivaciones_mes,
                "meta_bajas_mes": row.meta_bajas_mes,
                "meta_nuevos_domiciliados_mes": row.meta_nuevos_domiciliados_mes,
                "meta_arpu_mes": _serialize_decimal(row.meta_arpu_mes),
                "meta_venta_tienda_mes": _serialize_decimal(
                    row.meta_venta_tienda_mes
                ),
                "ingreso_agregadoras_estimado": _serialize_decimal(
                    row.ingreso_agregadoras_estimado
                ),
                "usuarios_agregadoras_estimado": row.usuarios_agregadoras_estimado,
                "scenario_used": row.scenario_used,
                "trend_classification": row.trend_classification,
                "risk_level": row.risk_level,
                "status": row.status,
                "previous_branch_row_id": row.previous_branch_row_id,
                "published_track_monthly_target_id": (
                    row.published_track_monthly_target_id
                ),
                "notes": row.notes,
                "created_at": _serialize_datetime(row.created_at),
                "updated_at": _serialize_datetime(row.updated_at),
                "adjustments": [
                    {
                        "id": adjustment.id,
                        "variable_key": adjustment.variable_key,
                        "adjustment_value": _serialize_decimal(
                            adjustment.adjustment_value
                        ),
                        "adjustment_type": adjustment.adjustment_type,
                        "driver_type": adjustment.driver_type,
                        "justification": adjustment.justification,
                        "created_by_user_id": adjustment.created_by_user_id,
                        "created_at": _serialize_datetime(adjustment.created_at),
                        "updated_at": _serialize_datetime(adjustment.updated_at),
                    }
                    for adjustment in row.adjustments
                ],
            }
            for row in batch.branch_rows
        ],
        "approval_events": [
            {
                "id": event.id,
                "event_type": event.event_type,
                "from_status": event.from_status,
                "to_status": event.to_status,
                "actor_user_id": event.actor_user_id,
                "actor_username_snapshot": event.actor_username_snapshot,
                "comment": event.comment,
                "metadata_json": event.metadata_json,
                "created_at": _serialize_datetime(event.created_at),
                "branch_row_id": event.branch_row_id,
            }
            for event in batch.approval_events
        ],
    }
    
def list_model_configs(
    *,
    status: str | None = None,
) -> dict[str, Any]:
    query = PlanningModelConfigORM.query

    normalized_status = _ensure_optional_text(status)
    if normalized_status is not None:
        query = query.filter_by(status=normalized_status)

    rows = (
        query
        .order_by(
            PlanningModelConfigORM.name.asc(),
            PlanningModelConfigORM.version.desc(),
            PlanningModelConfigORM.id.desc(),
        )
        .all()
    )

    return {
        "status": "ok",
        "items": [
            {
                "id": row.id,
                "name": row.name,
                "version": row.version,
                "model_status": row.status,
                "description": row.description,
                "trend_window_months": row.trend_window_months,
                "trend_closed_months_only": row.trend_closed_months_only,
                "arpu_strategy": row.arpu_strategy,
                "bajas_strategy": row.bajas_strategy,
                "reactivaciones_strategy": row.reactivaciones_strategy,
                "domiciliados_strategy": row.domiciliados_strategy,
                "aggregators_strategy": row.aggregators_strategy,
                "new_branch_strategy": row.new_branch_strategy,
                "risk_rules_json": row.risk_rules_json,
                "parameters_json": row.parameters_json,
                "created_by_user_id": row.created_by_user_id,
                "activated_by_user_id": row.activated_by_user_id,
                "activated_at": _serialize_datetime(row.activated_at),
                "replaced_by_config_id": row.replaced_by_config_id,
                "notes": row.notes,
                "created_at": _serialize_datetime(row.created_at),
                "updated_at": _serialize_datetime(row.updated_at),
            }
            for row in rows
        ],
    }
    
def list_target_batches(
    *,
    target_month: Any = None,
    status: str | None = None,
) -> dict[str, Any]:
    query = PlanningTargetBatchORM.query

    if target_month is not None:
        normalized_target_month = _normalize_target_month(target_month)
        query = query.filter_by(target_month=normalized_target_month)

    normalized_status = _ensure_optional_text(status)
    if normalized_status is not None:
        query = query.filter_by(status=normalized_status)

    rows = (
        query
        .order_by(
            PlanningTargetBatchORM.target_month.desc(),
            PlanningTargetBatchORM.version.desc(),
            PlanningTargetBatchORM.id.desc(),
        )
        .all()
    )

    return {
        "status": "ok",
        "items": [
            {
                "id": row.id,
                "target_month": row.target_month.isoformat(),
                "version": row.version,
                "batch_status": row.status,
                "scope": row.scope,
                "source_type": row.source_type,
                "source_upload_id": row.source_upload_id,
                "model_config_id": row.model_config_id,
                "model_config": None
                if row.model_config is None
                else {
                    "id": row.model_config.id,
                    "name": row.model_config.name,
                    "version": row.model_config.version,
                    "status": row.model_config.status,
                },
                "scenario_base": row.scenario_base,
                "proposed_by_user_id": row.proposed_by_user_id,
                "proposed_at": _serialize_datetime(row.proposed_at),
                "approved_by_user_id": row.approved_by_user_id,
                "approved_at": _serialize_datetime(row.approved_at),
                "rejected_by_user_id": row.rejected_by_user_id,
                "rejected_at": _serialize_datetime(row.rejected_at),
                "rejection_comment": row.rejection_comment,
                "published_at": _serialize_datetime(row.published_at),
                "is_canonical": row.is_canonical,
                "notes": row.notes,
                "created_by_user_id": row.created_by_user_id,
                "created_at": _serialize_datetime(row.created_at),
                "updated_at": _serialize_datetime(row.updated_at),
                "branch_rows_count": len(row.branch_rows),
            }
            for row in rows
        ],
    }
    
def submit_target_batch(
    command: SubmitPlanningTargetBatchCommand,
) -> dict[str, Any]:
    if not isinstance(command, SubmitPlanningTargetBatchCommand):
        raise PlanningTargetsServiceError(
            "command debe ser instancia de SubmitPlanningTargetBatchCommand."
        )

    batch = _get_target_batch(command.batch_id)
    _ensure_batch_can_submit(batch)

    submitted_by_user_id = _ensure_optional_user_id(
        command.submitted_by_user_id,
        field_name="submitted_by_user_id",
    )

    previous_status = batch.status
    now = _utc_now()

    batch.status = "EN_REVISION"
    batch.proposed_by_user_id = submitted_by_user_id
    batch.proposed_at = now

    event = PlanningTargetApprovalEventORM(
        batch_id=batch.id,
        branch_row_id=None,
        event_type="SUBMITTED",
        from_status=previous_status,
        to_status=batch.status,
        actor_user_id=submitted_by_user_id,
        actor_username_snapshot=_ensure_optional_text(
            command.actor_username_snapshot
        ),
        comment=_ensure_optional_text(command.comment),
        metadata_json={
            "branch_rows_count": len(batch.branch_rows),
            "target_month": batch.target_month.isoformat(),
            "version": batch.version,
        },
    )

    db.session.add(event)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return {
        "status": "submitted",
        "id": batch.id,
        "target_month": batch.target_month.isoformat(),
        "version": batch.version,
        "previous_status": previous_status,
        "batch_status": batch.status,
        "proposed_by_user_id": batch.proposed_by_user_id,
        "proposed_at": _serialize_datetime(batch.proposed_at),
        "event_id": event.id,
    }
    
def approve_target_batch(
    command: ApprovePlanningTargetBatchCommand,
) -> dict[str, Any]:
    if not isinstance(command, ApprovePlanningTargetBatchCommand):
        raise PlanningTargetsServiceError(
            "command debe ser instancia de ApprovePlanningTargetBatchCommand."
        )

    batch = _get_target_batch(command.batch_id)
    _ensure_batch_can_approve(batch)

    approved_by_user_id = _ensure_optional_user_id(
        command.approved_by_user_id,
        field_name="approved_by_user_id",
    )

    previous_status = batch.status
    now = _utc_now()

    batch.status = "APROBADA"
    batch.approved_by_user_id = approved_by_user_id
    batch.approved_at = now

    for row in batch.branch_rows:
        row.status = "APROBADA"

    event = PlanningTargetApprovalEventORM(
        batch_id=batch.id,
        branch_row_id=None,
        event_type="APPROVED",
        from_status=previous_status,
        to_status=batch.status,
        actor_user_id=approved_by_user_id,
        actor_username_snapshot=_ensure_optional_text(
            command.actor_username_snapshot
        ),
        comment=_ensure_optional_text(command.comment),
        metadata_json={
            "branch_rows_count": len(batch.branch_rows),
            "target_month": batch.target_month.isoformat(),
            "version": batch.version,
        },
    )

    db.session.add(event)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return {
        "status": "approved",
        "id": batch.id,
        "target_month": batch.target_month.isoformat(),
        "version": batch.version,
        "previous_status": previous_status,
        "batch_status": batch.status,
        "approved_by_user_id": batch.approved_by_user_id,
        "approved_at": _serialize_datetime(batch.approved_at),
        "event_id": event.id,
    }
    
def reject_target_batch(
    command: RejectPlanningTargetBatchCommand,
) -> dict[str, Any]:
    if not isinstance(command, RejectPlanningTargetBatchCommand):
        raise PlanningTargetsServiceError(
            "command debe ser instancia de RejectPlanningTargetBatchCommand."
        )

    batch = _get_target_batch(command.batch_id)
    _ensure_batch_can_reject(batch)

    rejected_by_user_id = _ensure_optional_user_id(
        command.rejected_by_user_id,
        field_name="rejected_by_user_id",
    )
    rejection_comment = _ensure_required_comment(
        command.comment,
        field_name="comment",
    )

    previous_status = batch.status
    now = _utc_now()

    batch.status = "RECHAZADA"
    batch.rejected_by_user_id = rejected_by_user_id
    batch.rejected_at = now
    batch.rejection_comment = rejection_comment

    for row in batch.branch_rows:
        row.status = "RECHAZADA"

    event = PlanningTargetApprovalEventORM(
        batch_id=batch.id,
        branch_row_id=None,
        event_type="REJECTED",
        from_status=previous_status,
        to_status=batch.status,
        actor_user_id=rejected_by_user_id,
        actor_username_snapshot=_ensure_optional_text(
            command.actor_username_snapshot
        ),
        comment=rejection_comment,
        metadata_json={
            "branch_rows_count": len(batch.branch_rows),
            "target_month": batch.target_month.isoformat(),
            "version": batch.version,
        },
    )

    db.session.add(event)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return {
        "status": "rejected",
        "id": batch.id,
        "target_month": batch.target_month.isoformat(),
        "version": batch.version,
        "previous_status": previous_status,
        "batch_status": batch.status,
        "rejected_by_user_id": batch.rejected_by_user_id,
        "rejected_at": _serialize_datetime(batch.rejected_at),
        "rejection_comment": batch.rejection_comment,
        "event_id": event.id,
    }