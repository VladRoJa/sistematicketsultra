from __future__ import annotations

from datetime import date, datetime, time, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.purchase_requisition import (
    PurchaseRequisitionCategory,
    PurchaseRequisitionEventORM,
    PurchaseRequisitionEventType,
    PurchaseRequisitionItemORM,
    PurchaseRequisitionORM,
    PurchaseRequisitionPriority,
    PurchaseRequisitionReason,
    PurchaseRequisitionStatus,
)
from app.models.sucursal_model import Sucursal
from app.utils.purchase_requisition_permissions import (
    PurchaseRequisitionAuthorizationError,
    assigned_branch_ids,
    can_create_for_branch,
    can_purchase_requisition_create,
    can_purchase_requisition_view,
    has_global_purchase_requisition_read,
    normalize_role,
    MAINTENANCE_ROLES,
)


BUSINESS_TZ = ZoneInfo("America/Tijuana")


class PurchaseRequisitionValidationError(ValueError):
    pass


class PurchaseRequisitionNotFoundError(LookupError):
    pass


def _session(session: Session | None):
    return session if session is not None else db.session


def _required_text(value: object, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise PurchaseRequisitionValidationError(
            f"{field} es obligatorio."
        )
    return normalized


def _optional_text(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _positive_int(value: object, field: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise PurchaseRequisitionValidationError(
            f"{field} debe ser entero."
        ) from exc
    if parsed <= 0:
        raise PurchaseRequisitionValidationError(
            f"{field} debe ser mayor que cero."
        )
    return parsed


def _validate_choice(
    value: object,
    field: str,
    allowed: tuple[str, ...],
    *,
    default: str | None = None,
) -> str:
    normalized = str(value or default or "").strip().upper()
    if normalized not in allowed:
        raise PurchaseRequisitionValidationError(
            f"{field} inválido."
        )
    return normalized


def _resolve_branch_id(payload: dict, actor) -> int:
    raw_value = payload.get("sucursal_id")
    if raw_value in (None, ""):
        raw_value = getattr(actor, "sucursal_id", None)

    branch_id = _positive_int(raw_value, "sucursal_id")
    if not can_create_for_branch(actor, branch_id):
        raise PurchaseRequisitionAuthorizationError(
            "No puedes crear requisiciones para esa sucursal."
        )
    return branch_id


def _assert_branch_exists(session, branch_id: int) -> None:
    exists = session.execute(
        select(Sucursal.sucursal_id).where(
            Sucursal.sucursal_id == branch_id
        )
    ).scalar_one_or_none()
    if exists is None:
        raise PurchaseRequisitionValidationError(
            "La sucursal seleccionada no existe."
        )


def _parse_items(raw_items: object) -> list[dict]:
    if not isinstance(raw_items, list) or not raw_items:
        raise PurchaseRequisitionValidationError(
            "La requisición requiere al menos una partida."
        )

    rows: list[dict] = []
    for index, raw in enumerate(raw_items, start=1):
        if not isinstance(raw, dict):
            raise PurchaseRequisitionValidationError(
                f"La partida {index} es inválida."
            )
        rows.append({
            "item_description": _required_text(
                raw.get("item_description"),
                f"items[{index}].item_description",
            ),
            "quantity": _positive_int(
                raw.get("quantity"),
                f"items[{index}].quantity",
            ),
            "notes": _optional_text(raw.get("notes")),
        })
    return rows


def _temporary_public_id() -> str:
    return f"TMP-{uuid4().hex[:28]}"


def _next_public_id(requisition_id: int) -> str:
    year = datetime.now(BUSINESS_TZ).year
    return f"RQ-{year}-{int(requisition_id):06d}"


def create_purchase_requisition(
    payload: dict,
    actor,
    *,
    session: Session | None = None,
) -> PurchaseRequisitionORM:
    if not can_purchase_requisition_create(actor):
        raise PurchaseRequisitionAuthorizationError(
            "El usuario no puede crear requisiciones."
        )
    if not isinstance(payload, dict):
        raise PurchaseRequisitionValidationError(
            "Payload inválido."
        )

    target_session = _session(session)
    branch_id = _resolve_branch_id(payload, actor)
    _assert_branch_exists(target_session, branch_id)

    category = _validate_choice(
        payload.get("category"),
        "category",
        PurchaseRequisitionCategory.ALL,
        default=PurchaseRequisitionCategory.GYM_EQUIPMENT,
    )
    reason = _validate_choice(
        payload.get("reason"),
        "reason",
        PurchaseRequisitionReason.ALL,
    )
    priority = _validate_choice(
        payload.get("priority"),
        "priority",
        PurchaseRequisitionPriority.ALL,
        default=PurchaseRequisitionPriority.NORMAL,
    )
    justification = _required_text(
        payload.get("justification"),
        "justification",
    )
    items = _parse_items(payload.get("items"))

    requisition = PurchaseRequisitionORM(
        public_id=_temporary_public_id(),
        sucursal_id=branch_id,
        created_by_user_id=int(actor.id),
        category=category,
        reason=reason,
        justification=justification,
        priority=priority,
        status=PurchaseRequisitionStatus.PENDING_REVIEW,
    )
    target_session.add(requisition)
    target_session.flush()

    requisition.public_id = _next_public_id(requisition.id)

    for item in items:
        requisition.items.append(
            PurchaseRequisitionItemORM(**item)
        )

    requisition.events.append(
        PurchaseRequisitionEventORM(
            event_type=PurchaseRequisitionEventType.CREATED,
            actor_user_id=int(actor.id),
            from_status=None,
            to_status=PurchaseRequisitionStatus.PENDING_REVIEW,
        )
    )
    target_session.flush()
    return requisition


def _apply_visibility(stmt, actor):
    if has_global_purchase_requisition_read(actor):
        return stmt

    role = normalize_role(getattr(actor, "rol", None))
    creator_condition = (
        PurchaseRequisitionORM.created_by_user_id == int(actor.id)
    )

    if role in MAINTENANCE_ROLES:
        return stmt.where(
            or_(
                creator_condition,
                PurchaseRequisitionORM.status
                == PurchaseRequisitionStatus.IN_QUOTATION,
            )
        )

    branch_ids = assigned_branch_ids(actor)
    if not branch_ids:
        return stmt.where(creator_condition)

    return stmt.where(
        or_(
            creator_condition,
            PurchaseRequisitionORM.sucursal_id.in_(branch_ids),
        )
    )


def _parse_date(value: object, field: str) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise PurchaseRequisitionValidationError(
            f"{field} debe tener formato YYYY-MM-DD."
        ) from exc


def list_purchase_requisitions(
    actor,
    *,
    status: object = None,
    branch_id: object = None,
    priority: object = None,
    date_from: object = None,
    date_to: object = None,
    session: Session | None = None,
) -> list[PurchaseRequisitionORM]:
    target_session = _session(session)
    stmt = select(PurchaseRequisitionORM)
    stmt = _apply_visibility(stmt, actor)

    if status not in (None, ""):
        normalized_status = _validate_choice(
            status,
            "status",
            PurchaseRequisitionStatus.ALL,
        )
        stmt = stmt.where(
            PurchaseRequisitionORM.status == normalized_status
        )

    if priority not in (None, ""):
        normalized_priority = _validate_choice(
            priority,
            "priority",
            PurchaseRequisitionPriority.ALL,
        )
        stmt = stmt.where(
            PurchaseRequisitionORM.priority == normalized_priority
        )

    if branch_id not in (None, ""):
        parsed_branch_id = _positive_int(
            branch_id,
            "sucursal_id",
        )
        stmt = stmt.where(
            PurchaseRequisitionORM.sucursal_id == parsed_branch_id
        )

    parsed_from = _parse_date(date_from, "date_from")
    parsed_to = _parse_date(date_to, "date_to")
    if parsed_from and parsed_to and parsed_from > parsed_to:
        raise PurchaseRequisitionValidationError(
            "date_from no puede ser posterior a date_to."
        )

    if parsed_from:
        start = datetime.combine(
            parsed_from,
            time.min,
            tzinfo=BUSINESS_TZ,
        ).astimezone(timezone.utc)
        stmt = stmt.where(
            PurchaseRequisitionORM.created_at >= start
        )

    if parsed_to:
        end = datetime.combine(
            parsed_to,
            time.max,
            tzinfo=BUSINESS_TZ,
        ).astimezone(timezone.utc)
        stmt = stmt.where(
            PurchaseRequisitionORM.created_at <= end
        )

    stmt = stmt.order_by(
        PurchaseRequisitionORM.created_at.desc(),
        PurchaseRequisitionORM.id.desc(),
    )
    return list(target_session.scalars(stmt).all())


def get_purchase_requisition(
    requisition_id: int,
    actor,
    *,
    session: Session | None = None,
) -> PurchaseRequisitionORM:
    target_session = _session(session)
    row = target_session.get(
        PurchaseRequisitionORM,
        int(requisition_id),
    )
    if row is None:
        raise PurchaseRequisitionNotFoundError(
            "Requisición no encontrada."
        )
    if not can_purchase_requisition_view(actor, row):
        raise PurchaseRequisitionAuthorizationError(
            "No tienes acceso a esta requisición."
        )
    return row
