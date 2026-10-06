from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.purchase_requisition import (
    PurchaseRequisitionAttachmentORM,
    PurchaseRequisitionAttachmentType,
    PurchaseRequisitionEventORM,
    PurchaseRequisitionEventType,
    PurchaseRequisitionORM,
    PurchaseRequisitionQuoteFinanceStatus,
    PurchaseRequisitionQuoteORM,
    PurchaseRequisitionStatus,
)
from app.services.purchase_requisition_service import (
    PurchaseRequisitionNotFoundError,
    PurchaseRequisitionValidationError,
)
from app.services.purchase_requisition_workflow_service import (
    PurchaseRequisitionConflictError,
)
from app.utils.purchase_requisition_permissions import (
    PurchaseRequisitionAuthorizationError,
    can_purchase_requisition_manage_quotation,
)


def _session(session: Session | None):
    return session if session is not None else db.session


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _required_text(
    value: object,
    field: str,
    *,
    max_length: int | None = None,
) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise PurchaseRequisitionValidationError(
            f"{field} es obligatorio."
        )
    if max_length is not None and len(normalized) > max_length:
        raise PurchaseRequisitionValidationError(
            f"{field} excede {max_length} caracteres."
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


def _positive_amount(value: object) -> Decimal:
    if isinstance(value, bool):
        raise PurchaseRequisitionValidationError(
            "amount debe ser numérico."
        )
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PurchaseRequisitionValidationError(
            "amount debe ser numérico."
        ) from exc
    if not parsed.is_finite() or parsed <= 0:
        raise PurchaseRequisitionValidationError(
            "amount debe ser mayor que cero."
        )
    if parsed >= Decimal("1000000000000"):
        raise PurchaseRequisitionValidationError(
            "amount excede el límite permitido."
        )
    if abs(parsed.as_tuple().exponent) > 2:
        raise PurchaseRequisitionValidationError(
            "amount admite máximo dos decimales."
        )
    return parsed


def _quote_date(value: object) -> date:
    raw = str(value or "").strip()
    if not raw:
        raise PurchaseRequisitionValidationError(
            "quote_date es obligatorio."
        )
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise PurchaseRequisitionValidationError(
            "quote_date debe tener formato YYYY-MM-DD."
        ) from exc


def _locked_requisition(
    session: Session,
    requisition_id: int,
) -> PurchaseRequisitionORM:
    row = session.execute(
        select(PurchaseRequisitionORM)
        .where(PurchaseRequisitionORM.id == int(requisition_id))
        .with_for_update()
    ).scalar_one_or_none()
    if row is None:
        raise PurchaseRequisitionNotFoundError(
            "Requisición no encontrada."
        )
    return row


def _require_quotation_owner(actor) -> None:
    if not can_purchase_requisition_manage_quotation(actor):
        raise PurchaseRequisitionAuthorizationError(
            "No autorizado para gestionar cotizaciones."
        )


def _require_in_quotation(requisition: PurchaseRequisitionORM) -> None:
    if requisition.status != PurchaseRequisitionStatus.IN_QUOTATION:
        raise PurchaseRequisitionConflictError(
            "La requisición no está en cotización."
        )


def create_purchase_requisition_quote(
    requisition_id: int,
    payload: dict,
    actor,
    *,
    session: Session | None = None,
) -> PurchaseRequisitionQuoteORM:
    _require_quotation_owner(actor)
    if not isinstance(payload, dict):
        raise PurchaseRequisitionValidationError("Payload inválido.")

    target_session = _session(session)
    requisition = _locked_requisition(
        target_session,
        requisition_id,
    )
    _require_in_quotation(requisition)

    supplier_name = _required_text(
        payload.get("supplier_name"),
        "supplier_name",
        max_length=255,
    )
    amount = _positive_amount(payload.get("amount"))
    currency = _required_text(
        payload.get("currency"),
        "currency",
        max_length=8,
    ).upper()
    parsed_quote_date = _quote_date(payload.get("quote_date"))
    attachment_id = _positive_int(
        payload.get("attachment_id"),
        "attachment_id",
    )

    attachment = target_session.get(
        PurchaseRequisitionAttachmentORM,
        attachment_id,
    )
    if (
        attachment is None
        or int(attachment.requisition_id) != int(requisition.id)
        or attachment.deleted_at is not None
    ):
        raise PurchaseRequisitionValidationError(
            "attachment_id no pertenece a la requisición."
        )
    if (
        attachment.attachment_type
        != PurchaseRequisitionAttachmentType.QUOTE
    ):
        raise PurchaseRequisitionValidationError(
            "La cotización debe referenciar un adjunto QUOTE."
        )

    existing_quote_id = target_session.execute(
        select(PurchaseRequisitionQuoteORM.id).where(
            PurchaseRequisitionQuoteORM.attachment_id
            == int(attachment.id)
        )
    ).scalar_one_or_none()
    if existing_quote_id is not None:
        raise PurchaseRequisitionValidationError(
            "Ese adjunto ya está asociado a una cotización."
        )

    quote = PurchaseRequisitionQuoteORM(
        requisition_id=requisition.id,
        supplier_name=supplier_name,
        amount=amount,
        currency=currency,
        quote_date=parsed_quote_date,
        attachment_id=attachment.id,
        notes=_optional_text(payload.get("notes")),
        created_by_user_id=int(actor.id),
        finance_status=PurchaseRequisitionQuoteFinanceStatus.DRAFT,
    )
    target_session.add(quote)
    target_session.flush()

    target_session.add(
        PurchaseRequisitionEventORM(
            requisition_id=requisition.id,
            event_type=PurchaseRequisitionEventType.QUOTE_ADDED,
            actor_user_id=int(actor.id),
            from_status=requisition.status,
            to_status=requisition.status,
            metadata_json={
                "quote_id": int(quote.id),
                "attachment_id": int(attachment.id),
                "supplier_name": supplier_name,
                "amount": format(amount, "f"),
                "currency": currency,
                "quote_date": parsed_quote_date.isoformat(),
            },
        )
    )
    target_session.flush()
    return quote


def select_purchase_requisition_quote(
    requisition_id: int,
    quote_id: int,
    actor,
    *,
    session: Session | None = None,
) -> PurchaseRequisitionQuoteORM:
    _require_quotation_owner(actor)
    target_session = _session(session)
    requisition = _locked_requisition(
        target_session,
        requisition_id,
    )
    _require_in_quotation(requisition)

    quote = target_session.get(
        PurchaseRequisitionQuoteORM,
        int(quote_id),
    )
    if (
        quote is None
        or int(quote.requisition_id) != int(requisition.id)
    ):
        raise PurchaseRequisitionNotFoundError(
            "Cotización no encontrada."
        )
    if (
        quote.finance_status
        != PurchaseRequisitionQuoteFinanceStatus.DRAFT
    ):
        raise PurchaseRequisitionConflictError(
            "Solo una cotización en borrador puede seleccionarse."
        )

    selected_quotes = list(
        target_session.scalars(
            select(PurchaseRequisitionQuoteORM).where(
                PurchaseRequisitionQuoteORM.requisition_id
                == requisition.id,
                PurchaseRequisitionQuoteORM.is_selected.is_(True),
            )
        ).all()
    )

    if (
        len(selected_quotes) == 1
        and int(selected_quotes[0].id) == int(quote.id)
    ):
        return quote

    now = _utc_now()
    previous_quote_ids = []
    for selected in selected_quotes:
        previous_quote_ids.append(int(selected.id))
        selected.is_selected = False
        selected.selected_by_user_id = None
        selected.selected_at = None

    target_session.flush()

    quote.is_selected = True
    quote.selected_by_user_id = int(actor.id)
    quote.selected_at = now
    target_session.flush()

    target_session.add(
        PurchaseRequisitionEventORM(
            requisition_id=requisition.id,
            event_type=PurchaseRequisitionEventType.QUOTE_SELECTED,
            actor_user_id=int(actor.id),
            from_status=requisition.status,
            to_status=requisition.status,
            metadata_json={
                "quote_id": int(quote.id),
                "previous_quote_ids": previous_quote_ids,
            },
        )
    )
    target_session.flush()
    return quote
