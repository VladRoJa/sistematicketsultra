"""Controlled, idempotent Campaign V2 immediate/scheduled submit."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from time import perf_counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2ProviderCampaignORM,
)
from app.services.marketing_campaign_v2_preflight_service import (
    DISPATCH_FINGERPRINT_VERSION,
    CampaignV2DispatchBatchPlan,
    CampaignV2PreflightPlan,
    build_campaign_v2_preflight,
    build_provider_campaign_idempotency_key,
)
from app.services.marketing_campaign_v2_provider import (
    CampaignProvider,
    CampaignProviderAmbiguousError,
    CampaignProviderConfigurationError,
    CampaignProviderDeterministicError,
    CampaignProviderDispatchBatch,
    CampaignProviderLead,
)
from app.services.marketing_phone import format_mexico_international_phone


logger = logging.getLogger(__name__)


class MarketingCampaignV2SubmitError(RuntimeError):
    pass


class MarketingCampaignV2SubmitDisabledError(MarketingCampaignV2SubmitError):
    pass


class MarketingCampaignV2SubmitValidationError(
    MarketingCampaignV2SubmitError,
    ValueError,
):
    pass


class MarketingCampaignV2SubmitPreconditionError(
    MarketingCampaignV2SubmitError
):
    pass


class MarketingCampaignV2SubmitConflictError(
    MarketingCampaignV2SubmitError
):
    pass


class MarketingCampaignV2SubmitPersistenceError(
    MarketingCampaignV2SubmitError
):
    pass


@dataclass(frozen=True)
class CampaignV2SubmittedBatchResult:
    child_id: int
    sucursal_id: int
    sucursal_canon: str
    provider_channel_id: str
    template_name: str
    recipient_count: int
    status: str
    provider_campaign_id: str | None
    provider_deduplicated: bool | None
    scheduled_timezone: str | None
    scheduled_local_at: str | None
    scheduled_for: str | None
    provider_send_at: str | None
    error_code: str | None
    support_ref: str | None


@dataclass(frozen=True)
class CampaignV2SubmitResult:
    campaign_id: int
    dispatch_fingerprint: str
    status: str
    batches: tuple[CampaignV2SubmittedBatchResult, ...]
    stopped_after_child_id: int | None

    @property
    def all_accepted(self) -> bool:
        return bool(self.batches) and all(
            batch.status in {"SUBMITTED", "SCHEDULED"}
            for batch in self.batches
        )

    @property
    def all_submitted(self) -> bool:
        return bool(self.batches) and all(
            batch.status == "SUBMITTED"
            for batch in self.batches
        )


def submit_campaign_v2(
    *,
    campaign_id: int,
    template_id: Any,
    expected_dispatch_fingerprint: Any,
    actor_user_id: int,
    allowed_sucursal_keys,
    provider: CampaignProvider,
    schedule: Any = None,
    send_enabled: bool = False,
    session: Any | None = None,
    now: datetime | None = None,
) -> CampaignV2SubmitResult:
    """Submit the current M1 plan exactly once per provider batch.

    The provider is invoked only after:
    - kill switch has been explicitly enabled by the caller;
    - a fresh preflight is ready;
    - the expected fingerprint matches;
    - child rows are durably persisted;
    - the current batch transitioned atomically READY -> SUBMITTING.
    """

    if send_enabled is not True:
        raise MarketingCampaignV2SubmitDisabledError(
            "El envío Campaign V2 está deshabilitado por kill switch."
        )

    normalized_campaign_id = _positive_int(campaign_id, "campaign_id")
    normalized_actor = _positive_int(actor_user_id, "actor_user_id")
    expected_fingerprint = _fingerprint(expected_dispatch_fingerprint)
    timestamp = _normalize_now(now)

    plan = build_campaign_v2_preflight(
        campaign_id=normalized_campaign_id,
        template_id=template_id,
        allowed_sucursal_keys=allowed_sucursal_keys,
        schedule=schedule,
        session=session if session is not None else db.session,
        now=timestamp,
    )
    if not plan.ready:
        raise MarketingCampaignV2SubmitPreconditionError(
            "El preflight vigente tiene bloqueos y no puede enviarse."
        )
    if plan.dispatch_fingerprint != expected_fingerprint:
        raise MarketingCampaignV2SubmitPreconditionError(
            "El dispatch fingerprint cambió. Ejecuta un nuevo preflight."
        )

    active_session = session if session is not None else db.session
    rows = _prepare_provider_campaign_rows(
        plan=plan,
        actor_user_id=normalized_actor,
        session=active_session,
        now=timestamp,
    )

    results: list[CampaignV2SubmittedBatchResult] = []
    stopped_after: int | None = None

    for batch, row in zip(plan.batches, rows, strict=True):
        _transition_ready_to_submitting(
            row_id=int(row.id),
            actor_user_id=normalized_actor,
            session=active_session,
            now=timestamp,
        )
        _log_transition(
            campaign_id=normalized_campaign_id,
            child_id=int(row.id),
            batch=batch,
            mode=plan.mode,
            state="SUBMITTING",
            error_code=None,
        )

        dispatch_batch = _provider_dispatch_batch(
            plan=plan,
            batch=batch,
        )

        attempt_started = perf_counter()
        try:
            provider_result = provider.create_campaign(dispatch_batch)
        except CampaignProviderDeterministicError as exc:
            row = _persist_provider_failure(
                row_id=int(row.id),
                status="PROVIDER_ERROR",
                error_code=exc.code,
                support_ref=exc.support_ref,
                http_status=exc.http_status,
                actor_user_id=normalized_actor,
                session=active_session,
                now=_normalize_now(None),
            )
            results.append(_serialize_row_result(row))
            stopped_after = int(row.id)
            _log_transition(
                campaign_id=normalized_campaign_id,
                child_id=int(row.id),
                batch=batch,
                mode=plan.mode,
                state="PROVIDER_ERROR",
                error_code=exc.code,
                duration_ms=_duration_ms(attempt_started),
                http_status=exc.http_status,
                support_ref=exc.support_ref,
            )
            break
        except CampaignProviderAmbiguousError as exc:
            row = _persist_provider_failure(
                row_id=int(row.id),
                status="RECONCILIATION_REQUIRED",
                error_code=exc.code,
                support_ref=exc.support_ref,
                http_status=exc.http_status,
                actor_user_id=normalized_actor,
                session=active_session,
                now=_normalize_now(None),
            )
            results.append(_serialize_row_result(row))
            stopped_after = int(row.id)
            _log_transition(
                campaign_id=normalized_campaign_id,
                child_id=int(row.id),
                batch=batch,
                mode=plan.mode,
                state="RECONCILIATION_REQUIRED",
                error_code=exc.code,
                duration_ms=_duration_ms(attempt_started),
                http_status=exc.http_status,
                support_ref=exc.support_ref,
            )
            break
        except CampaignProviderConfigurationError:
            # This should normally be caught before entering submit. If it
            # occurs after SUBMITTING but before a network call, it is still
            # deterministic and requires operator review rather than retry.
            row = _persist_provider_failure(
                row_id=int(row.id),
                status="PROVIDER_ERROR",
                error_code="PROVIDER_CONFIGURATION",
                support_ref=None,
                http_status=None,
                actor_user_id=normalized_actor,
                session=active_session,
                now=_normalize_now(None),
            )
            results.append(_serialize_row_result(row))
            stopped_after = int(row.id)
            _log_transition(
                campaign_id=normalized_campaign_id,
                child_id=int(row.id),
                batch=batch,
                mode=plan.mode,
                state="PROVIDER_ERROR",
                error_code="PROVIDER_CONFIGURATION",
                duration_ms=_duration_ms(attempt_started),
                http_status=None,
                support_ref=None,
            )
            break
        except Exception:
            # An unexpected exception after SUBMITTING cannot prove that the
            # provider did not accept the request. Preserve ambiguity.
            row = _persist_provider_failure(
                row_id=int(row.id),
                status="RECONCILIATION_REQUIRED",
                error_code="UNEXPECTED_PROVIDER_RESULT",
                support_ref=None,
                http_status=None,
                actor_user_id=normalized_actor,
                session=active_session,
                now=_normalize_now(None),
            )
            results.append(_serialize_row_result(row))
            stopped_after = int(row.id)
            _log_transition(
                campaign_id=normalized_campaign_id,
                child_id=int(row.id),
                batch=batch,
                mode=plan.mode,
                state="RECONCILIATION_REQUIRED",
                error_code="UNEXPECTED_PROVIDER_RESULT",
                duration_ms=_duration_ms(attempt_started),
                http_status=None,
                support_ref=None,
            )
            break

        accepted_status = (
            "SCHEDULED"
            if plan.mode == "SCHEDULED"
            else "SUBMITTED"
        )
        row = _persist_provider_success(
            row_id=int(row.id),
            provider_campaign_id=provider_result.provider_campaign_id,
            deduplicated=provider_result.deduplicated,
            response_metadata=provider_result.response_metadata,
            accepted_status=accepted_status,
            actor_user_id=normalized_actor,
            session=active_session,
            now=_normalize_now(None),
        )
        results.append(_serialize_row_result(row))
        _log_transition(
            campaign_id=normalized_campaign_id,
            child_id=int(row.id),
            batch=batch,
            mode=plan.mode,
            state=accepted_status,
            error_code=None,
            duration_ms=_duration_ms(attempt_started),
            http_status=provider_result.http_status,
            support_ref=None,
        )

    # Rows after a stop remain READY. This is intentional: M2 never continues
    # a partially attempted operation automatically. A later request sees the
    # non-READY sibling and is rejected as conflict.
    current_rows = _load_campaign_rows(
        campaign_id=normalized_campaign_id,
        session=active_session,
    )
    overall = _aggregate_status(current_rows)
    return CampaignV2SubmitResult(
        campaign_id=normalized_campaign_id,
        dispatch_fingerprint=plan.dispatch_fingerprint,
        status=overall,
        batches=tuple(
            _serialize_row_result(row)
            for row in current_rows
        ),
        stopped_after_child_id=stopped_after,
    )


def get_campaign_v2_submit_state(
    *,
    campaign_id: int,
    session: Any | None = None,
) -> dict[str, Any]:
    active_session = session if session is not None else db.session
    normalized_campaign_id = _positive_int(campaign_id, "campaign_id")
    rows = _load_campaign_rows(
        campaign_id=normalized_campaign_id,
        session=active_session,
    )
    return {
        "status": _aggregate_status(rows),
        "has_provider_campaigns": bool(rows),
        "batches": [
            _serialize_row_result_dict(row)
            for row in rows
        ],
    }


def serialize_campaign_v2_submit_result(
    result: CampaignV2SubmitResult,
) -> dict[str, Any]:
    return {
        "campaign_id": result.campaign_id,
        "dispatch_fingerprint": result.dispatch_fingerprint,
        "status": result.status,
        "all_accepted": result.all_accepted,
        "all_submitted": result.all_submitted,
        "stopped_after_child_id": result.stopped_after_child_id,
        "batches": [
            {
                "child_id": batch.child_id,
                "sucursal_id": batch.sucursal_id,
                "sucursal_canon": batch.sucursal_canon,
                "provider_channel_id": batch.provider_channel_id,
                "template_name": batch.template_name,
                "recipient_count": batch.recipient_count,
                "status": batch.status,
                "provider_campaign_id": batch.provider_campaign_id,
                "provider_deduplicated": batch.provider_deduplicated,
                "scheduled_timezone": batch.scheduled_timezone,
                "scheduled_local_at": batch.scheduled_local_at,
                "scheduled_for": batch.scheduled_for,
                "provider_send_at": batch.provider_send_at,
                "error_code": batch.error_code,
                "support_ref": batch.support_ref,
            }
            for batch in result.batches
        ],
    }


def _prepare_provider_campaign_rows(
    *,
    plan: CampaignV2PreflightPlan,
    actor_user_id: int,
    session: Any,
    now: datetime,
) -> list[MarketingCampaignV2ProviderCampaignORM]:
    expected: list[tuple[CampaignV2DispatchBatchPlan, str]] = [
        (
            batch,
            build_provider_campaign_idempotency_key(
                campaign_v2_id=plan.campaign_id,
                batch=batch,
                dispatch_fingerprint=plan.dispatch_fingerprint,
            ),
        )
        for batch in plan.batches
    ]

    existing = _load_campaign_rows(
        campaign_id=plan.campaign_id,
        session=session,
    )
    if existing:
        by_key = {row.idempotency_key: row for row in existing}
        expected_keys = {key for _, key in expected}
        if (
            set(by_key) != expected_keys
            or len(by_key) != len(existing)
            or any(row.status != "READY" for row in existing)
        ):
            raise MarketingCampaignV2SubmitConflictError(
                "La campaña ya tiene una operación de provider iniciada o incompatible."
            )
        return [by_key[key] for _, key in expected]

    campaign = (
        session.query(MarketingCampaignV2ORM)
        .filter(MarketingCampaignV2ORM.id == plan.campaign_id)
        .with_for_update()
        .one_or_none()
    )
    if campaign is None:
        raise MarketingCampaignV2SubmitValidationError(
            "Campaign V2 no encontrada."
        )

    rows: list[MarketingCampaignV2ProviderCampaignORM] = []
    for batch, idempotency_key in expected:
        if batch.channel_binding_id is None or batch.provider_channel_id is None:
            raise MarketingCampaignV2SubmitPreconditionError(
                "El batch no tiene channel resuelto."
            )

        dispatch_batch = _provider_dispatch_batch(
            plan=plan,
            batch=batch,
        )
        row = MarketingCampaignV2ProviderCampaignORM(
            campaign_v2_id=plan.campaign_id,
            provider=plan.provider,
            sucursal_id=batch.sucursal_id,
            sucursal_canon=batch.sucursal_canon,
            channel_binding_id=batch.channel_binding_id,
            provider_channel_id=batch.provider_channel_id,
            template_id=batch.template_id,
            template_name=batch.template_name,
            template_snapshot_json={
                "template_id": batch.template_id,
                "template_name": batch.template_name,
                "file_url": batch.file_url,
                "dispatch_fingerprint_version": DISPATCH_FINGERPRINT_VERSION,
            },
            recipient_count=len(batch.recipients),
            dispatch_fingerprint=plan.dispatch_fingerprint,
            idempotency_key=idempotency_key,
            status="READY",
            created_by_user_id=actor_user_id,
            scheduled_by_user_id=(
                actor_user_id
                if plan.mode == "SCHEDULED"
                else None
            ),
            scheduled_timezone=plan.schedule.timezone_name,
            scheduled_local_at=(
                datetime.fromisoformat(plan.schedule.local_datetime)
                if plan.schedule.local_datetime is not None
                else None
            ),
            scheduled_for=plan.schedule.scheduled_for_utc,
            provider_send_at=plan.schedule.provider_send_at,
            request_snapshot_json=_request_snapshot(dispatch_batch),
            provider_response_json={},
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        rows.append(row)

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise MarketingCampaignV2SubmitConflictError(
            "Otra operación de submit creó estos provider campaigns."
        ) from exc
    except SQLAlchemyError as exc:
        session.rollback()
        raise MarketingCampaignV2SubmitPersistenceError(
            "No fue posible preparar los provider campaigns."
        ) from exc

    return _load_rows_by_idempotency(
        keys=[key for _, key in expected],
        session=session,
    )


def _transition_ready_to_submitting(
    *,
    row_id: int,
    actor_user_id: int,
    session: Any,
    now: datetime,
) -> None:
    try:
        updated = (
            session.query(MarketingCampaignV2ProviderCampaignORM)
            .filter(
                MarketingCampaignV2ProviderCampaignORM.id == row_id,
                MarketingCampaignV2ProviderCampaignORM.status == "READY",
            )
            .update(
                {
                    MarketingCampaignV2ProviderCampaignORM.status: "SUBMITTING",
                    MarketingCampaignV2ProviderCampaignORM.submit_started_at: now,
                    MarketingCampaignV2ProviderCampaignORM.submitted_by_user_id: actor_user_id,
                    MarketingCampaignV2ProviderCampaignORM.updated_at: now,
                    MarketingCampaignV2ProviderCampaignORM.error_code: None,
                    MarketingCampaignV2ProviderCampaignORM.support_ref: None,
                },
                synchronize_session=False,
            )
        )
        if updated != 1:
            session.rollback()
            raise MarketingCampaignV2SubmitConflictError(
                "El provider campaign ya fue tomado por otra operación."
            )
        session.commit()
    except MarketingCampaignV2SubmitConflictError:
        raise
    except SQLAlchemyError as exc:
        session.rollback()
        raise MarketingCampaignV2SubmitPersistenceError(
            "No fue posible iniciar el provider campaign."
        ) from exc


def _persist_provider_success(
    *,
    row_id: int,
    provider_campaign_id: str,
    deduplicated: bool,
    response_metadata: dict[str, Any],
    accepted_status: str,
    actor_user_id: int,
    session: Any,
    now: datetime,
) -> MarketingCampaignV2ProviderCampaignORM:
    provider_id = str(provider_campaign_id or "").strip()
    if not provider_id:
        raise MarketingCampaignV2SubmitPersistenceError(
            "El provider no devolvió campaign id persistible."
        )

    if accepted_status not in {"SUBMITTED", "SCHEDULED"}:
        raise MarketingCampaignV2SubmitPersistenceError(
            "Estado de aceptación provider inválido."
        )

    row = session.get(MarketingCampaignV2ProviderCampaignORM, row_id)
    if row is None or row.status != "SUBMITTING":
        raise MarketingCampaignV2SubmitConflictError(
            "El provider campaign cambió de estado antes de persistir éxito."
        )

    row.status = accepted_status
    row.provider_campaign_id = provider_id
    row.provider_deduplicated = bool(deduplicated)
    row.provider_response_json = _safe_provider_response(response_metadata)
    row.submitted_by_user_id = actor_user_id
    row.submitted_at = now
    row.updated_at = now
    row.error_code = None
    row.support_ref = None
    _commit_outcome(session)
    return session.get(MarketingCampaignV2ProviderCampaignORM, row_id)


def _persist_provider_failure(
    *,
    row_id: int,
    status: str,
    error_code: str,
    support_ref: str | None,
    http_status: int | None,
    actor_user_id: int,
    session: Any,
    now: datetime,
) -> MarketingCampaignV2ProviderCampaignORM:
    if status not in {"PROVIDER_ERROR", "RECONCILIATION_REQUIRED"}:
        raise ValueError("Estado de fallo provider inválido.")

    row = session.get(MarketingCampaignV2ProviderCampaignORM, row_id)
    if row is None or row.status != "SUBMITTING":
        raise MarketingCampaignV2SubmitConflictError(
            "El provider campaign cambió de estado antes de persistir fallo."
        )

    row.status = status
    row.error_code = str(error_code or "PROVIDER_ERROR")[:100]
    row.support_ref = _safe_text(support_ref, 200)
    row.provider_response_json = {
        "http_status": http_status,
        "error_code": row.error_code,
        "support_ref": row.support_ref,
    }
    row.submitted_by_user_id = actor_user_id
    row.updated_at = now
    _commit_outcome(session)
    return session.get(MarketingCampaignV2ProviderCampaignORM, row_id)


def _commit_outcome(session: Any) -> None:
    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise MarketingCampaignV2SubmitPersistenceError(
            "No fue posible persistir el resultado del provider."
        ) from exc


def _provider_dispatch_batch(
    *,
    plan: CampaignV2PreflightPlan,
    batch: CampaignV2DispatchBatchPlan,
) -> CampaignProviderDispatchBatch:
    leads: list[CampaignProviderLead] = []
    for recipient in batch.recipients:
        transport_phone = format_mexico_international_phone(
            recipient.phone_mx10
        )
        if transport_phone is None:
            raise MarketingCampaignV2SubmitPreconditionError(
                "El preflight contiene un teléfono no proyectable al provider."
            )

        ordered_positions = [
            int(position)
            for position, _ in recipient.variables
        ]
        if ordered_positions and ordered_positions != list(
            range(1, len(ordered_positions) + 1)
        ):
            raise MarketingCampaignV2SubmitPreconditionError(
                "Las variables del template no son contiguas desde posición 1."
            )

        leads.append(
            CampaignProviderLead(
                phone=transport_phone,
                variables=tuple(
                    value
                    for _, value in recipient.variables
                ),
            )
        )

    if not leads:
        raise MarketingCampaignV2SubmitPreconditionError(
            "El batch no tiene recipients enviables."
        )

    return CampaignProviderDispatchBatch(
        provider=plan.provider,
        campaign_name=_provider_campaign_name(plan, batch),
        provider_channel_id=str(batch.provider_channel_id or ""),
        template_name=batch.template_name,
        leads=tuple(leads),
        file_url=batch.file_url,
        send_at=plan.schedule.provider_send_at,
    )


def _provider_campaign_name(
    plan: CampaignV2PreflightPlan,
    batch: CampaignV2DispatchBatchPlan,
) -> str:
    suffix = f" · {batch.sucursal_canon}"
    base = " ".join(str(plan.campaign_name or "").split()) or (
        f"Campaign V2 #{plan.campaign_id}"
    )
    max_length = 255
    available = max(1, max_length - len(suffix))
    return f"{base[:available]}{suffix}"


def _request_snapshot(
    batch: CampaignProviderDispatchBatch,
) -> dict[str, Any]:
    return {
        "provider": batch.provider,
        "campaign_name": batch.campaign_name,
        "provider_channel_id": batch.provider_channel_id,
        "template_name": batch.template_name,
        "file_url": batch.file_url,
        "send_at": batch.send_at,
        "leads": [
            {
                "phone": lead.phone,
                "variables": list(lead.variables),
                "url_variables": list(lead.url_variables),
            }
            for lead in batch.leads
        ],
    }


def _safe_provider_response(value: dict[str, Any]) -> dict[str, Any]:
    allowed = {"campaign", "deduplicated"}
    return {
        key: value[key]
        for key in sorted(value)
        if key in allowed
    }


def _load_campaign_rows(
    *,
    campaign_id: int,
    session: Any,
) -> list[MarketingCampaignV2ProviderCampaignORM]:
    return (
        session.query(MarketingCampaignV2ProviderCampaignORM)
        .filter(
            MarketingCampaignV2ProviderCampaignORM.campaign_v2_id
            == campaign_id
        )
        .order_by(
            MarketingCampaignV2ProviderCampaignORM.sucursal_canon.asc(),
            MarketingCampaignV2ProviderCampaignORM.id.asc(),
        )
        .all()
    )


def _load_rows_by_idempotency(
    *,
    keys: list[str],
    session: Any,
) -> list[MarketingCampaignV2ProviderCampaignORM]:
    rows = (
        session.query(MarketingCampaignV2ProviderCampaignORM)
        .filter(
            MarketingCampaignV2ProviderCampaignORM.idempotency_key.in_(keys)
        )
        .all()
    )
    by_key = {row.idempotency_key: row for row in rows}
    if set(by_key) != set(keys):
        raise MarketingCampaignV2SubmitPersistenceError(
            "No fue posible recuperar todos los provider campaigns preparados."
        )
    return [by_key[key] for key in keys]


def _aggregate_status(
    rows: list[MarketingCampaignV2ProviderCampaignORM],
) -> str:
    if not rows:
        return "NOT_STARTED"

    statuses = {str(row.status) for row in rows}
    if statuses == {"SUBMITTED"}:
        return "SUBMITTED"
    if statuses == {"SCHEDULED"}:
        return "SCHEDULED"
    if "RECONCILIATION_REQUIRED" in statuses:
        return "RECONCILIATION_REQUIRED"
    if "PROVIDER_ERROR" in statuses:
        return "PROVIDER_ERROR"
    if "SUBMITTING" in statuses:
        return "SUBMITTING"
    if statuses == {"READY"}:
        return "READY"
    return "PARTIAL"


def _serialize_row_result(
    row: MarketingCampaignV2ProviderCampaignORM,
) -> CampaignV2SubmittedBatchResult:
    return CampaignV2SubmittedBatchResult(
        child_id=int(row.id),
        sucursal_id=int(row.sucursal_id),
        sucursal_canon=str(row.sucursal_canon),
        provider_channel_id=str(row.provider_channel_id),
        template_name=str(row.template_name),
        recipient_count=int(row.recipient_count),
        status=str(row.status),
        provider_campaign_id=(
            str(row.provider_campaign_id)
            if row.provider_campaign_id is not None
            else None
        ),
        provider_deduplicated=(
            bool(row.provider_deduplicated)
            if row.provider_deduplicated is not None
            else None
        ),
        scheduled_timezone=row.scheduled_timezone,
        scheduled_local_at=_iso_datetime(row.scheduled_local_at),
        scheduled_for=_iso_datetime(row.scheduled_for),
        provider_send_at=row.provider_send_at,
        error_code=row.error_code,
        support_ref=row.support_ref,
    )


def _serialize_row_result_dict(
    row: MarketingCampaignV2ProviderCampaignORM,
) -> dict[str, Any]:
    result = _serialize_row_result(row)
    return {
        "child_id": result.child_id,
        "sucursal_id": result.sucursal_id,
        "sucursal_canon": result.sucursal_canon,
        "provider_channel_id": result.provider_channel_id,
        "template_name": result.template_name,
        "recipient_count": result.recipient_count,
        "status": result.status,
        "provider_campaign_id": result.provider_campaign_id,
        "provider_deduplicated": result.provider_deduplicated,
        "scheduled_timezone": result.scheduled_timezone,
        "scheduled_local_at": result.scheduled_local_at,
        "scheduled_for": result.scheduled_for,
        "provider_send_at": result.provider_send_at,
        "error_code": result.error_code,
        "support_ref": result.support_ref,
    }


def _log_transition(
    *,
    campaign_id: int,
    child_id: int,
    batch: CampaignV2DispatchBatchPlan,
    mode: str,
    state: str,
    error_code: str | None,
    duration_ms: float | None = None,
    http_status: int | None = None,
    support_ref: str | None = None,
) -> None:
    logger.info(
        "campaign_v2_provider_transition %s",
        {
            "campaign_v2_id": campaign_id,
            "provider_campaign_child_id": child_id,
            "provider": "IVENTAS",
            "sucursal_id": batch.sucursal_id,
            "channel_binding_id": batch.channel_binding_id,
            "recipient_count": len(batch.recipients),
            "operation": (
                "SCHEDULED_SUBMIT"
                if mode == "SCHEDULED"
                else "IMMEDIATE_SUBMIT"
            ),
            "state": state,
            "duration_ms": duration_ms,
            "http_class": (
                f"{http_status // 100}xx"
                if http_status is not None
                else None
            ),
            "error_code": error_code,
            "support_ref": _safe_text(support_ref, 200),
        },
    )


def _duration_ms(started_at: float) -> float:
    return round(max(0.0, perf_counter() - started_at) * 1000.0, 1)


def _fingerprint(value: Any) -> str:
    if not isinstance(value, str):
        raise MarketingCampaignV2SubmitValidationError(
            "expected_dispatch_fingerprint debe ser texto."
        )
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(
        char not in "0123456789abcdef"
        for char in normalized
    ):
        raise MarketingCampaignV2SubmitValidationError(
            "expected_dispatch_fingerprint debe ser SHA-256 hexadecimal."
        )
    return normalized


def _positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise MarketingCampaignV2SubmitValidationError(
            f"{field_name} debe ser entero positivo."
        )
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise MarketingCampaignV2SubmitValidationError(
            f"{field_name} debe ser entero positivo."
        ) from exc
    if normalized <= 0:
        raise MarketingCampaignV2SubmitValidationError(
            f"{field_name} debe ser entero positivo."
        )
    return normalized


def _normalize_now(value: datetime | None) -> datetime:
    current = value if value is not None else datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _iso_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    formatter = getattr(value, "isoformat", None)
    return formatter() if callable(formatter) else str(value)


def _safe_text(value: Any, max_length: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:max_length] or None
