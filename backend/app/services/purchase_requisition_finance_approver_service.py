from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.purchase_requisition import (
    PurchaseRequisitionFinanceApproverORM,
)
from app.models.user_model import UserORM
from app.services.purchase_requisition_service import (
    PurchaseRequisitionNotFoundError,
    PurchaseRequisitionValidationError,
)
from app.utils.purchase_requisition_permissions import (
    PurchaseRequisitionAuthorizationError,
    can_purchase_requisition_configure_finance_approvers,
)


def _session(session: Session | None):
    return session if session is not None else db.session


def _require_admin(actor) -> None:
    if not can_purchase_requisition_configure_finance_approvers(actor):
        raise PurchaseRequisitionAuthorizationError(
            "No autorizado para configurar aprobadores financieros."
        )


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


def _optional_text(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _user_summary(
    session: Session,
    user_id: int,
) -> dict | None:
    row = session.execute(
        select(
            UserORM.id,
            UserORM.username,
            UserORM.email,
            UserORM.rol,
        ).where(UserORM.id == int(user_id))
    ).one_or_none()
    if row is None:
        return None
    return {
        "id": int(row.id),
        "username": row.username,
        "email": row.email,
        "role": row.rol,
    }


def _serialize(
    session: Session,
    row: PurchaseRequisitionFinanceApproverORM,
) -> dict:
    payload = row.to_dict()
    payload["user"] = _user_summary(session, row.user_id)
    payload["added_by_user"] = (
        _user_summary(session, row.added_by_user_id)
        if row.added_by_user_id
        else None
    )
    return payload


def list_purchase_requisition_finance_approvers(
    actor,
    *,
    session: Session | None = None,
) -> dict:
    _require_admin(actor)
    target_session = _session(session)
    rows = list(
        target_session.scalars(
            select(PurchaseRequisitionFinanceApproverORM).order_by(
                PurchaseRequisitionFinanceApproverORM.is_active.desc(),
                PurchaseRequisitionFinanceApproverORM.created_at.asc(),
                PurchaseRequisitionFinanceApproverORM.id.asc(),
            )
        ).all()
    )
    items = [_serialize(target_session, row) for row in rows]
    return {
        "rows": items,
        "count": len(items),
        "active_count": sum(
            1 for row in rows if bool(row.is_active)
        ),
    }


def create_purchase_requisition_finance_approver(
    payload: dict,
    actor,
    *,
    session: Session | None = None,
) -> PurchaseRequisitionFinanceApproverORM:
    _require_admin(actor)
    if not isinstance(payload, dict):
        raise PurchaseRequisitionValidationError("Payload inválido.")

    target_session = _session(session)
    user_id = _positive_int(payload.get("user_id"), "user_id")

    if _user_summary(target_session, user_id) is None:
        raise PurchaseRequisitionValidationError(
            "El usuario seleccionado no existe."
        )

    existing = target_session.execute(
        select(PurchaseRequisitionFinanceApproverORM).where(
            PurchaseRequisitionFinanceApproverORM.user_id == user_id
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise PurchaseRequisitionValidationError(
            "El usuario ya existe en la configuración de aprobadores financieros."
        )

    row = PurchaseRequisitionFinanceApproverORM(
        user_id=user_id,
        is_active=True,
        added_by_user_id=int(actor.id),
        notes=_optional_text(payload.get("notes")),
    )
    target_session.add(row)
    target_session.flush()
    return row


def update_purchase_requisition_finance_approver(
    user_id: int,
    payload: dict,
    actor,
    *,
    session: Session | None = None,
) -> PurchaseRequisitionFinanceApproverORM:
    _require_admin(actor)
    if not isinstance(payload, dict):
        raise PurchaseRequisitionValidationError("Payload inválido.")

    target_session = _session(session)
    normalized_user_id = _positive_int(user_id, "user_id")

    row = target_session.execute(
        select(PurchaseRequisitionFinanceApproverORM).where(
            PurchaseRequisitionFinanceApproverORM.user_id
            == normalized_user_id
        )
    ).scalar_one_or_none()
    if row is None:
        raise PurchaseRequisitionNotFoundError(
            "Aprobador financiero no encontrado."
        )

    has_change = False

    if "is_active" in payload:
        if not isinstance(payload["is_active"], bool):
            raise PurchaseRequisitionValidationError(
                "is_active debe ser booleano."
            )
        row.is_active = payload["is_active"]
        has_change = True

    if "notes" in payload:
        row.notes = _optional_text(payload.get("notes"))
        has_change = True

    if not has_change:
        raise PurchaseRequisitionValidationError(
            "Debes enviar is_active o notes."
        )

    target_session.flush()
    return row


def serialize_purchase_requisition_finance_approver(
    row: PurchaseRequisitionFinanceApproverORM,
    *,
    session: Session | None = None,
) -> dict:
    return _serialize(_session(session), row)
