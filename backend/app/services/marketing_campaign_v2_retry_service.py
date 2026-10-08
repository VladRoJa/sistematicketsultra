"""Safe, explicit retry for reconciled Campaign V2 provider children."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.marketing import MarketingCampaignV2ProviderCampaignORM
from app.services.marketing_campaign_v2_preflight_service import (
    build_campaign_v2_preflight,
)
from app.services.marketing_campaign_v2_provider import (
    CampaignProvider,
    CampaignProviderAmbiguousError,
    CampaignProviderConfigurationError,
    CampaignProviderDeterministicError,
)
from app.services.marketing_campaign_v2_retry_policy import (
    MAX_SAFE_RETRY_ATTEMPTS,
    retry_is_exhausted,
)
from app.services.marketing_campaign_v2_submit_service import (
    MarketingCampaignV2SubmitPreconditionError,
    build_campaign_v2_provider_dispatch_batch,
    serialize_campaign_v2_provider_request_snapshot,
)


NEVER_RETRY_CAMPAIGN_IDS = frozenset({9, 10, 11})


class MarketingCampaignV2SafeRetryError(RuntimeError):
    pass


class MarketingCampaignV2SafeRetryDisabledError(
    MarketingCampaignV2SafeRetryError
):
    pass


class MarketingCampaignV2SafeRetryValidationError(
    MarketingCampaignV2SafeRetryError,
    ValueError,
):
    pass


class MarketingCampaignV2SafeRetryNotFoundError(
    MarketingCampaignV2SafeRetryError
):
    pass


class MarketingCampaignV2SafeRetryPreconditionError(
    MarketingCampaignV2SafeRetryError
):
    pass


class MarketingCampaignV2SafeRetryConflictError(
    MarketingCampaignV2SafeRetryError
):
    pass


class MarketingCampaignV2SafeRetryPersistenceError(
    MarketingCampaignV2SafeRetryError
):
    pass


def retry_campaign_v2_provider_child(
    *,
    child_id: Any,
    actor_user_id: Any,
    provider: CampaignProvider,
    send_enabled: bool,
    session: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not send_enabled:
        raise MarketingCampaignV2SafeRetryDisabledError(
            "El retry Campaign V2 está deshabilitado por kill switch."
        )

    active_session = session if session is not None else db.session
    normalized_child_id = _positive_int(child_id, "child_id")
    normalized_actor = _positive_int(actor_user_id, "actor_user_id")
    timestamp = _normalize_now(now)

    row = _load_retry_candidate(
        child_id=normalized_child_id,
        session=active_session,
    )
    _validate_retry_candidate(row=row, now=timestamp)

    schedule = _schedule_payload(row)
    try:
        plan = build_campaign_v2_preflight(
            campaign_id=int(row.campaign_v2_id),
            template_id=int(row.template_id),
            allowed_sucursal_keys=None,
            provider=str(row.provider),
            schedule=schedule,
            session=active_session,
            now=timestamp,
        )
    except Exception as exc:
        raise MarketingCampaignV2SafeRetryPreconditionError(
            "No fue posible reconstruir el preflight vigente del retry."
        ) from exc

    if plan.dispatch_fingerprint != str(row.dispatch_fingerprint):
        raise MarketingCampaignV2SafeRetryPreconditionError(
            "El plan vigente cambió desde la confirmación original; retry bloqueado."
        )

    matching_batches = [
        batch
        for batch in plan.batches
        if int(batch.sucursal_id) == int(row.sucursal_id)
        and str(batch.sucursal_canon) == str(row.sucursal_canon)
    ]
    if len(matching_batches) != 1:
        raise MarketingCampaignV2SafeRetryPreconditionError(
            "No existe un único batch vigente para el child a reintentar."
        )

    try:
        dispatch_batch = build_campaign_v2_provider_dispatch_batch(
            plan=plan,
            batch=matching_batches[0],
        )
    except MarketingCampaignV2SubmitPreconditionError as exc:
        raise MarketingCampaignV2SafeRetryPreconditionError(
            str(exc)
        ) from exc

    request_snapshot = serialize_campaign_v2_provider_request_snapshot(
        dispatch_batch
    )
    if request_snapshot != dict(row.request_snapshot_json or {}):
        raise MarketingCampaignV2SafeRetryPreconditionError(
            "El request provider vigente difiere del request original; retry bloqueado."
        )

    attempt_number = int(row.retry_attempt_count or 0) + 1
    row = _mark_retry_submitting(
        row_id=normalized_child_id,
        expected_attempt_count=attempt_number - 1,
        actor_user_id=normalized_actor,
        now=timestamp,
        session=active_session,
    )

    try:
        provider_result = provider.create_campaign(dispatch_batch)
    except CampaignProviderDeterministicError as exc:
        row = _finish_retry_failure(
            row_id=normalized_child_id,
            attempt_number=attempt_number,
            status="PROVIDER_ERROR",
            outcome="DETERMINISTIC_ERROR",
            error_code=exc.code,
            http_status=exc.http_status,
            support_ref=exc.support_ref,
            actor_user_id=normalized_actor,
            now=_normalize_now(None),
            session=active_session,
        )
        return serialize_campaign_v2_safe_retry(row)
    except CampaignProviderAmbiguousError as exc:
        row = _finish_retry_failure(
            row_id=normalized_child_id,
            attempt_number=attempt_number,
            status="RECONCILIATION_REQUIRED",
            outcome="AMBIGUOUS",
            error_code=exc.code,
            http_status=exc.http_status,
            support_ref=exc.support_ref,
            actor_user_id=normalized_actor,
            now=_normalize_now(None),
            session=active_session,
        )
        return serialize_campaign_v2_safe_retry(row)
    except CampaignProviderConfigurationError:
        row = _finish_retry_failure(
            row_id=normalized_child_id,
            attempt_number=attempt_number,
            status="PROVIDER_ERROR",
            outcome="PROVIDER_CONFIGURATION",
            error_code="PROVIDER_CONFIGURATION",
            http_status=None,
            support_ref=None,
            actor_user_id=normalized_actor,
            now=_normalize_now(None),
            session=active_session,
        )
        return serialize_campaign_v2_safe_retry(row)
    except Exception:
        row = _finish_retry_failure(
            row_id=normalized_child_id,
            attempt_number=attempt_number,
            status="RECONCILIATION_REQUIRED",
            outcome="UNEXPECTED_AMBIGUOUS",
            error_code="UNEXPECTED_PROVIDER_RESULT",
            http_status=None,
            support_ref=None,
            actor_user_id=normalized_actor,
            now=_normalize_now(None),
            session=active_session,
        )
        return serialize_campaign_v2_safe_retry(row)

    accepted_status = (
        "SCHEDULED"
        if row.provider_send_at is not None
        else "SUBMITTED"
    )
    row = _finish_retry_success(
        row_id=normalized_child_id,
        attempt_number=attempt_number,
        accepted_status=accepted_status,
        provider_campaign_id=provider_result.provider_campaign_id,
        deduplicated=provider_result.deduplicated,
        http_status=provider_result.http_status,
        response_metadata=provider_result.response_metadata,
        actor_user_id=normalized_actor,
        now=_normalize_now(None),
        session=active_session,
    )
    return serialize_campaign_v2_safe_retry(row)


def serialize_campaign_v2_safe_retry(
    row: MarketingCampaignV2ProviderCampaignORM,
) -> dict[str, Any]:
    return {
        "child_id": int(row.id),
        "campaign_id": int(row.campaign_v2_id),
        "sucursal_id": int(row.sucursal_id),
        "sucursal_canon": str(row.sucursal_canon),
        "provider": str(row.provider),
        "status": str(row.status),
        "provider_campaign_id": (
            str(row.provider_campaign_id)
            if row.provider_campaign_id is not None
            else None
        ),
        "retry": {
            "attempt_count": int(row.retry_attempt_count or 0),
            "max_attempts": MAX_SAFE_RETRY_ATTEMPTS,
            "last_attempt_at": _iso_datetime(row.retry_last_attempt_at),
            "next_allowed_at": _iso_datetime(row.retry_next_allowed_at),
            "last_by_user_id": row.retry_last_by_user_id,
            "exhausted": str(row.status) == "RETRY_EXHAUSTED",
            "history": deepcopy(list(row.retry_history_json or [])),
        },
        "reconciliation": {
            "resolution": row.reconciliation_resolution,
            "note": row.reconciliation_note,
            "reconciled_by_user_id": row.reconciled_by_user_id,
            "reconciled_at": _iso_datetime(row.reconciled_at),
        },
        "error_code": row.error_code,
        "support_ref": row.support_ref,
    }


def _load_retry_candidate(
    *,
    child_id: int,
    session: Any,
) -> MarketingCampaignV2ProviderCampaignORM:
    row = (
        session.query(MarketingCampaignV2ProviderCampaignORM)
        .filter(MarketingCampaignV2ProviderCampaignORM.id == child_id)
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        raise MarketingCampaignV2SafeRetryNotFoundError(
            "Provider campaign child no encontrado."
        )
    return row


def _validate_retry_candidate(
    *,
    row: MarketingCampaignV2ProviderCampaignORM,
    now: datetime,
) -> None:
    if int(row.campaign_v2_id) in NEVER_RETRY_CAMPAIGN_IDS:
        raise MarketingCampaignV2SafeRetryPreconditionError(
            "Esta Campaign V2 está bloqueada permanentemente para retry."
        )
    if row.status != "RETRY_ELIGIBLE":
        raise MarketingCampaignV2SafeRetryConflictError(
            "El child no está en RETRY_ELIGIBLE."
        )
    if row.reconciliation_resolution != "NOT_CREATED_CONFIRMED":
        raise MarketingCampaignV2SafeRetryPreconditionError(
            "Falta evidencia NOT_CREATED_CONFIRMED para retry."
        )
    if row.provider_campaign_id is not None:
        raise MarketingCampaignV2SafeRetryConflictError(
            "El child ya tiene provider_campaign_id."
        )

    attempts = int(row.retry_attempt_count or 0)
    if retry_is_exhausted(attempts):
        raise MarketingCampaignV2SafeRetryConflictError(
            "El child agotó el máximo de retries."
        )

    next_allowed = _as_utc(row.retry_next_allowed_at)
    if next_allowed is not None and now < next_allowed:
        raise MarketingCampaignV2SafeRetryPreconditionError(
            "El retry está dentro de la ventana de backoff."
        )

    if row.provider_send_at is not None:
        scheduled_for = _as_utc(row.scheduled_for)
        if scheduled_for is None:
            raise MarketingCampaignV2SafeRetryPreconditionError(
                "El child scheduled no tiene scheduled_for auditable."
            )
        if scheduled_for <= now:
            raise MarketingCampaignV2SafeRetryPreconditionError(
                "El sendAt original ya venció; requiere nueva programación confirmada."
            )


def _schedule_payload(
    row: MarketingCampaignV2ProviderCampaignORM,
) -> dict[str, str] | None:
    if row.provider_send_at is None:
        return None
    if row.scheduled_timezone is None or row.scheduled_local_at is None:
        raise MarketingCampaignV2SafeRetryPreconditionError(
            "El child scheduled no conserva timezone/datetime local completos."
        )

    local_value = row.scheduled_local_at
    if isinstance(local_value, datetime):
        local_text = local_value.isoformat(timespec="seconds")
    else:
        local_text = str(local_value).strip()

    return {
        "timezone": str(row.scheduled_timezone),
        "local_datetime": local_text,
    }


def _mark_retry_submitting(
    *,
    row_id: int,
    expected_attempt_count: int,
    actor_user_id: int,
    now: datetime,
    session: Any,
) -> MarketingCampaignV2ProviderCampaignORM:
    row = (
        session.query(MarketingCampaignV2ProviderCampaignORM)
        .filter(MarketingCampaignV2ProviderCampaignORM.id == row_id)
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        raise MarketingCampaignV2SafeRetryNotFoundError(
            "Provider campaign child no encontrado."
        )
    if (
        row.status != "RETRY_ELIGIBLE"
        or int(row.retry_attempt_count or 0) != expected_attempt_count
        or row.reconciliation_resolution != "NOT_CREATED_CONFIRMED"
        or row.provider_campaign_id is not None
    ):
        raise MarketingCampaignV2SafeRetryConflictError(
            "El child cambió antes de iniciar el retry."
        )

    attempt_number = expected_attempt_count + 1
    history = list(row.retry_history_json or [])
    history.append(
        {
            "schema_version": 1,
            "attempt": attempt_number,
            "started_at": _iso_datetime(now),
            "actor_user_id": actor_user_id,
            "dispatch_fingerprint": str(row.dispatch_fingerprint),
            "source_reconciliation": {
                "resolution": row.reconciliation_resolution,
                "note": row.reconciliation_note,
                "reconciled_by_user_id": row.reconciled_by_user_id,
                "reconciled_at": _iso_datetime(row.reconciled_at),
                "snapshot": deepcopy(
                    dict(row.reconciliation_snapshot_json or {})
                ),
            },
            "outcome": "SUBMITTING",
        }
    )

    row.status = "SUBMITTING"
    row.retry_attempt_count = attempt_number
    row.retry_last_attempt_at = now
    row.retry_next_allowed_at = None
    row.retry_last_by_user_id = actor_user_id
    row.retry_history_json = history
    row.submit_started_at = now
    row.submitted_by_user_id = actor_user_id
    row.error_code = None
    row.support_ref = None

    row.reconciliation_resolution = None
    row.reconciliation_note = None
    row.reconciliation_snapshot_json = {}
    row.reconciled_by_user_id = None
    row.reconciled_at = None
    row.updated_at = now

    _commit_retry(session)
    return session.get(MarketingCampaignV2ProviderCampaignORM, row_id)


def _finish_retry_success(
    *,
    row_id: int,
    attempt_number: int,
    accepted_status: str,
    provider_campaign_id: Any,
    deduplicated: bool,
    http_status: int,
    response_metadata: dict[str, Any],
    actor_user_id: int,
    now: datetime,
    session: Any,
) -> MarketingCampaignV2ProviderCampaignORM:
    provider_id = str(provider_campaign_id or "").strip()
    if not provider_id:
        return _finish_retry_failure(
            row_id=row_id,
            attempt_number=attempt_number,
            status="RECONCILIATION_REQUIRED",
            outcome="MISSING_PROVIDER_CAMPAIGN_ID",
            error_code="MISSING_CAMPAIGN_ID",
            http_status=http_status,
            support_ref=None,
            actor_user_id=actor_user_id,
            now=now,
            session=session,
        )

    row = _load_submitting_attempt(
        row_id=row_id,
        attempt_number=attempt_number,
        session=session,
    )
    row.status = accepted_status
    row.provider_campaign_id = provider_id
    row.provider_deduplicated = bool(deduplicated)
    row.provider_response_json = _safe_provider_response(
        response_metadata
    )
    row.submitted_by_user_id = actor_user_id
    row.submitted_at = now
    row.updated_at = now
    row.error_code = None
    row.support_ref = None
    row.retry_history_json = _finish_history(
        row.retry_history_json,
        attempt_number=attempt_number,
        finished_at=now,
        outcome="ACCEPTED",
        http_status=http_status,
        error_code=None,
        support_ref=None,
        provider_campaign_id=provider_id,
    )

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return _mark_success_persistence_ambiguous(
            row_id=row_id,
            attempt_number=attempt_number,
            provider_campaign_id=provider_id,
            actor_user_id=actor_user_id,
            now=now,
            session=session,
        )
    except SQLAlchemyError as exc:
        session.rollback()
        raise MarketingCampaignV2SafeRetryPersistenceError(
            "No fue posible persistir el resultado exitoso del retry."
        ) from exc

    return session.get(MarketingCampaignV2ProviderCampaignORM, row_id)


def _mark_success_persistence_ambiguous(
    *,
    row_id: int,
    attempt_number: int,
    provider_campaign_id: str,
    actor_user_id: int,
    now: datetime,
    session: Any,
) -> MarketingCampaignV2ProviderCampaignORM:
    row = _load_submitting_attempt(
        row_id=row_id,
        attempt_number=attempt_number,
        session=session,
    )
    row.status = "RECONCILIATION_REQUIRED"
    row.error_code = "PROVIDER_IDENTITY_CONFLICT"
    row.support_ref = None
    row.submitted_by_user_id = actor_user_id
    row.updated_at = now
    row.retry_history_json = _finish_history(
        row.retry_history_json,
        attempt_number=attempt_number,
        finished_at=now,
        outcome="PERSISTENCE_IDENTITY_CONFLICT",
        http_status=200,
        error_code="PROVIDER_IDENTITY_CONFLICT",
        support_ref=None,
        provider_campaign_id=provider_campaign_id,
    )
    _commit_retry(session)
    return session.get(MarketingCampaignV2ProviderCampaignORM, row_id)


def _finish_retry_failure(
    *,
    row_id: int,
    attempt_number: int,
    status: str,
    outcome: str,
    error_code: str,
    http_status: int | None,
    support_ref: str | None,
    actor_user_id: int,
    now: datetime,
    session: Any,
) -> MarketingCampaignV2ProviderCampaignORM:
    if status not in {"PROVIDER_ERROR", "RECONCILIATION_REQUIRED"}:
        raise ValueError("Estado final de retry inválido.")

    row = _load_submitting_attempt(
        row_id=row_id,
        attempt_number=attempt_number,
        session=session,
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
    row.retry_history_json = _finish_history(
        row.retry_history_json,
        attempt_number=attempt_number,
        finished_at=now,
        outcome=outcome,
        http_status=http_status,
        error_code=row.error_code,
        support_ref=row.support_ref,
        provider_campaign_id=None,
    )
    _commit_retry(session)
    return session.get(MarketingCampaignV2ProviderCampaignORM, row_id)


def _load_submitting_attempt(
    *,
    row_id: int,
    attempt_number: int,
    session: Any,
) -> MarketingCampaignV2ProviderCampaignORM:
    row = (
        session.query(MarketingCampaignV2ProviderCampaignORM)
        .filter(MarketingCampaignV2ProviderCampaignORM.id == row_id)
        .with_for_update()
        .one_or_none()
    )
    if (
        row is None
        or row.status != "SUBMITTING"
        or int(row.retry_attempt_count or 0) != attempt_number
    ):
        raise MarketingCampaignV2SafeRetryConflictError(
            "El child cambió durante el retry."
        )
    return row


def _finish_history(
    raw_history: Any,
    *,
    attempt_number: int,
    finished_at: datetime,
    outcome: str,
    http_status: int | None,
    error_code: str | None,
    support_ref: str | None,
    provider_campaign_id: str | None,
) -> list[dict[str, Any]]:
    history = [deepcopy(dict(item)) for item in (raw_history or [])]
    if not history or int(history[-1].get("attempt") or 0) != attempt_number:
        raise MarketingCampaignV2SafeRetryPersistenceError(
            "Historial de retry inconsistente."
        )

    history[-1].update(
        {
            "finished_at": _iso_datetime(finished_at),
            "outcome": outcome,
            "http_status": http_status,
            "error_code": error_code,
            "support_ref": support_ref,
            "provider_campaign_id": provider_campaign_id,
        }
    )
    return history


def _commit_retry(session: Any) -> None:
    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise MarketingCampaignV2SafeRetryPersistenceError(
            "No fue posible persistir el retry Campaign V2."
        ) from exc


def _safe_provider_response(value: dict[str, Any]) -> dict[str, Any]:
    allowed = {"campaign", "deduplicated"}
    return {
        key: value[key]
        for key in sorted(value)
        if key in allowed
    }


def _positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise MarketingCampaignV2SafeRetryValidationError(
            f"{field_name} debe ser entero positivo."
        )
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise MarketingCampaignV2SafeRetryValidationError(
            f"{field_name} debe ser entero positivo."
        ) from exc
    if normalized <= 0:
        raise MarketingCampaignV2SafeRetryValidationError(
            f"{field_name} debe ser entero positivo."
        )
    return normalized


def _normalize_now(value: datetime | None) -> datetime:
    current = value if value is not None else datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _as_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise MarketingCampaignV2SafeRetryPreconditionError(
            "Timestamp de retry inválido."
        )
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


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
    normalized = str(value).strip()
    return normalized[:max_length] or None
