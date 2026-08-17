from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import re
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.marketing import MarketingMonthlyInputORM
from app.models.sucursal_model import Sucursal


ALLOWED_INPUT_FIELDS = frozenset(
    {
        "month",
        "notes",
    }
)


class MarketingInputValidationError(ValueError):
    pass


class MarketingInputConflictError(RuntimeError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_month(value: Any) -> date:
    raw_value = str(value or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}", raw_value):
        raise MarketingInputValidationError(
            "month es obligatorio y debe usar formato YYYY-MM."
        )

    try:
        return datetime.strptime(
            raw_value,
            "%Y-%m",
        ).date()
    except ValueError as exc:
        raise MarketingInputValidationError(
            "month no representa un mes válido."
        ) from exc


def validate_input_payload(
    payload: Any,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise MarketingInputValidationError(
            "El payload JSON debe ser un objeto."
        )

    unknown_fields = sorted(
        set(payload) - ALLOWED_INPUT_FIELDS
    )
    if unknown_fields:
        raise MarketingInputValidationError(
            "Campos no permitidos: "
            + ", ".join(unknown_fields)
            + "."
        )

    if "month" not in payload:
        raise MarketingInputValidationError(
            "Campos obligatorios faltantes: month."
        )

    notes = payload.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise MarketingInputValidationError(
            "notes debe ser texto o null."
        )

    return {
        "month_start": parse_month(payload.get("month")),
        "notes": (
            str(notes).strip() or None
            if notes is not None
            else None
        ),
    }


def _branch_exists(sucursal_id: int) -> bool:
    return (
        Sucursal.query.filter_by(
            sucursal_id=sucursal_id
        ).first()
        is not None
    )


def _find_monthly_input(
    *,
    month_start: date,
    sucursal_id: int,
) -> MarketingMonthlyInputORM | None:
    return MarketingMonthlyInputORM.query.filter_by(
        month_start=month_start,
        sucursal_id=sucursal_id,
    ).first()


def serialize_marketing_input(
    row: MarketingMonthlyInputORM,
) -> dict[str, Any]:
    return {
        "id": row.id,
        "month": row.month_start.strftime("%Y-%m"),
        "sucursal_id": row.sucursal_id,
        "notes": row.notes,
        "created_by_user_id": row.created_by_user_id,
        "updated_by_user_id": row.updated_by_user_id,
        "created_at": (
            row.created_at.isoformat()
            if row.created_at is not None
            else None
        ),
        "updated_at": (
            row.updated_at.isoformat()
            if row.updated_at is not None
            else None
        ),
    }


def upsert_marketing_input(
    *,
    month_start: date,
    sucursal_id: int,
    notes: str | None,
    user_id: int | None,
) -> tuple[MarketingMonthlyInputORM, bool]:
    if not _branch_exists(sucursal_id):
        raise MarketingInputValidationError(
            "La sucursal indicada no existe."
        )

    existing = _find_monthly_input(
        month_start=month_start,
        sucursal_id=sucursal_id,
    )
    now = _utc_now()
    created = existing is None

    if existing is None:
        existing = MarketingMonthlyInputORM(
            month_start=month_start,
            sucursal_id=sucursal_id,
            # Columna histórica no nula. La inversión funcional
            # proviene exclusivamente del snapshot canónico Meta.
            investment=Decimal("0"),
            # Columna histórica no nula. Ya no forma parte
            # del contrato ni de los cálculos del dashboard.
            leads=0,
            notes=notes,
            created_by_user_id=user_id,
            updated_by_user_id=user_id,
            created_at=now,
            updated_at=now,
        )
        db.session.add(existing)
    else:
        existing.notes = notes
        existing.updated_by_user_id = user_id
        existing.updated_at = now

    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise MarketingInputConflictError(
            "Conflicto al guardar el input mensual."
        ) from exc

    return existing, created


def list_marketing_inputs(
    *,
    month_start: date,
    branch_ids: tuple[int, ...],
) -> list[MarketingMonthlyInputORM]:
    if not branch_ids:
        return []

    return (
        MarketingMonthlyInputORM.query.filter(
            MarketingMonthlyInputORM.month_start
            == month_start,
            MarketingMonthlyInputORM.sucursal_id.in_(
                branch_ids
            ),
        )
        .order_by(
            MarketingMonthlyInputORM.sucursal_id.asc()
        )
        .all()
    )
