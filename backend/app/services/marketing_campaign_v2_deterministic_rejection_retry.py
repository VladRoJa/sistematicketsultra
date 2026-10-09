"""Strict one-time deterministic retry of campaign #8 / PASEO_LA_PAZ.

The previous 4xx TEMPLATE_NOT_FOUND was confirmed not accepted. A new
attempt is allowed only after ALL OTHER 25 children were accepted.
The original error is written durably to retry_history_json BEFORE HTTP.
No generic retry route or provider child is created.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy.exc import SQLAlchemyError

from app.models.marketing import MarketingCampaignV2ProviderCampaignORM
from app.services.marketing_campaign_v2_preflight_service import (
    build_campaign_v2_preflight,
    build_provider_campaign_idempotency_key,
)
from app.services.marketing_campaign_v2_provider import (
    CampaignProvider,
    CampaignProviderAmbiguousError,
    CampaignProviderConfigurationError,
    CampaignProviderDeterministicError,
)
from app.services.marketing_campaign_v2_submit_service import (
    MarketingCampaignV2SubmitPreconditionError,
    _load_campaign_rows,
    build_campaign_v2_provider_dispatch_batch,
    serialize_campaign_v2_provider_request_snapshot,
)
from app.services.marketing_campaign_v2_retry_service import (
    _finish_retry_failure,
    _finish_retry_success,
)


class Campaign8DeterministicRetryError(MarketingCampaignV2SubmitPreconditionError):
    pass


@dataclass(frozen=True)
class LaPazRetryReview:
    plan: Any
    batch: Any
    child_id: int


def review_campaign8_la_paz_retry(
    *,
    fingerprint: str,
    accepted_counts: Mapping[str, int],
    original_provider_ids: Mapping[str, str],
    session: Any,
) -> LaPazRetryReview:
    """No mutations. Reject drift in ANY child or provider payload."""
    plan = build_campaign_v2_preflight(
        campaign_id=8, template_id=1, allowed_sucursal_keys=None, session=session
    )
    if (
        not plan.ready or plan.mode != "IMMEDIATE" or plan.provider != "IVENTAS"
        or plan.campaign_name != "Socios activos/venta nueva invita y gana"
        or plan.campaign_purpose != "NEW_SALE"
        or plan.frozen_count != 14002 or len(plan.sendable_phones) != 13999
        or len(set(plan.sendable_phones)) != 13999
        or plan.dispatch_fingerprint != fingerprint
        or len(plan.blacklisted_phones) != 0
        or set(plan.campaign_excluded_recipient_ids) != {59510, 59859, 60120}
        or len(plan.batches) != 26
        or len(accepted_counts) != 25
        or sum(accepted_counts.values()) != 13829
        or len(original_provider_ids) != 11
        or not set(original_provider_ids) <= set(accepted_counts)
    ):
        raise Campaign8DeterministicRetryError("Campaign #8 preflight or manifest drift.")

    rows = _load_campaign_rows(campaign_id=8, session=session)
    by_name = {str(row.sucursal_canon): row for row in rows}
    batches = {str(batch.sucursal_canon): batch for batch in plan.batches}
    expected_names = set(accepted_counts) | {"PASEO_LA_PAZ"}
    if (
        len(rows) != 26 or len(by_name) != 26 or len(batches) != 26
        or set(by_name) != expected_names or set(batches) != expected_names
    ):
        raise Campaign8DeterministicRetryError("Provider children differ from approved manifest.")

    existing_provider_ids: set[str] = set()
    for name in sorted(expected_names):
        row = by_name[name]
        batch = batches[name]
        expected_count = 170 if name == "PASEO_LA_PAZ" else accepted_counts[name]
        if (
            int(row.campaign_v2_id) != 8
            or row.provider != "IVENTAS"
            or row.dispatch_fingerprint != fingerprint
            or int(row.sucursal_id) != int(batch.sucursal_id)
            or int(row.channel_binding_id) != int(batch.channel_binding_id or 0)
            or str(row.provider_channel_id) != str(batch.provider_channel_id)
            or int(row.template_id) != 1
            or row.template_name != batch.template_name
            or batch.template_name != "invita_y_gana_4800"
            or not batch.ready
            or int(row.recipient_count) != expected_count
            or len(batch.recipients) != expected_count
            or row.idempotency_key != build_provider_campaign_idempotency_key(
                campaign_v2_id=8, batch=batch, dispatch_fingerprint=fingerprint
            )
        ):
            raise Campaign8DeterministicRetryError(f"Child identity changed: {name}")
        dispatch = build_campaign_v2_provider_dispatch_batch(plan=plan, batch=batch)
        if dict(row.request_snapshot_json or {}) != serialize_campaign_v2_provider_request_snapshot(dispatch):
            raise Campaign8DeterministicRetryError(f"Provider payload changed: {name}")

        if name == "PASEO_LA_PAZ":
            if (
                int(row.id) != 15
                or row.status != "PROVIDER_ERROR"
                or row.provider_campaign_id is not None
                or row.error_code != "TEMPLATE_NOT_FOUND"
                or row.support_ref != "bc-mv09582n-ly0gq0"
                or int(row.retry_attempt_count or 0) != 0
                or bool(row.retry_history_json)
                or row.reconciliation_resolution is not None
            ):
                raise Campaign8DeterministicRetryError("La Paz original rejection was modified.")
        else:
            if (
                row.status != "SUBMITTED"
                or not row.provider_campaign_id
                or row.submitted_at is None
            ):
                raise Campaign8DeterministicRetryError(f"Other branch not accepted: {name}")
            provider_id = str(row.provider_campaign_id)
            if provider_id in existing_provider_ids:
                raise Campaign8DeterministicRetryError("Duplicate accepted provider ID.")
            existing_provider_ids.add(provider_id)
            if name in original_provider_ids and provider_id != original_provider_ids[name]:
                raise Campaign8DeterministicRetryError(f"Original provider ID changed: {name}")
    return LaPazRetryReview(plan=plan, batch=batches["PASEO_LA_PAZ"], child_id=15)


def _mark_la_paz_retry_started(*, review: LaPazRetryReview, actor_user_id: int, session: Any) -> None:
    """Durably preserve prior 4xx before sending; one guarded transition only."""
    now = datetime.now(timezone.utc)
    row = (
        session.query(MarketingCampaignV2ProviderCampaignORM)
        .filter(MarketingCampaignV2ProviderCampaignORM.id == review.child_id)
        .with_for_update()
        .one_or_none()
    )
    if (
        row is None or row.campaign_v2_id != 8
        or row.sucursal_canon != "PASEO_LA_PAZ"
        or row.status != "PROVIDER_ERROR"
        or row.dispatch_fingerprint != review.plan.dispatch_fingerprint
        or row.provider_campaign_id is not None
        or row.error_code != "TEMPLATE_NOT_FOUND"
        or row.support_ref != "bc-mv09582n-ly0gq0"
        or int(row.retry_attempt_count or 0) != 0
        or bool(row.retry_history_json)
    ):
        session.rollback()
        raise Campaign8DeterministicRetryError("Concurrent change: La Paz retry denied.")

    history = [{
        "schema_version": 1, "attempt": 1,
        "started_at": now.isoformat(),
        "actor_user_id": actor_user_id,
        "dispatch_fingerprint": review.plan.dispatch_fingerprint,
        "source_deterministic_rejection": {
            "status": row.status,
            "error_code": row.error_code,
            "support_ref": row.support_ref,
            "provider_response": dict(row.provider_response_json or {}),
        },
        "reason": "CAMPAIGN_8_TEMPLATE_NOW_APPROVED_LA_PAZ",
        "outcome": "SUBMITTING",
    }]
    row.retry_history_json = history
    row.retry_attempt_count = 1
    row.retry_last_attempt_at = now
    row.retry_last_by_user_id = actor_user_id
    row.retry_next_allowed_at = None
    row.submit_started_at = now
    row.submitted_by_user_id = actor_user_id
    row.updated_at = now
    row.error_code = None
    row.support_ref = None
    row.status = "SUBMITTING"
    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise Campaign8DeterministicRetryError("Unable to audit La Paz retry BEFORE HTTP.") from exc


def send_campaign8_la_paz_once(
    *,
    review: LaPazRetryReview,
    actor_user_id: int,
    provider: CampaignProvider,
    send_enabled: bool,
    session: Any,
) -> tuple[str, str | None]:
    if send_enabled is not True or actor_user_id <= 0:
        raise Campaign8DeterministicRetryError("Process kill switch or authorization missing.")
    dispatch = build_campaign_v2_provider_dispatch_batch(plan=review.plan, batch=review.batch)
    _mark_la_paz_retry_started(review=review, actor_user_id=actor_user_id, session=session)
    now = lambda: datetime.now(timezone.utc)
    try:
        response = provider.create_campaign(dispatch)
    except CampaignProviderDeterministicError as exc:
        _finish_retry_failure(
            row_id=review.child_id, attempt_number=1,
            status="PROVIDER_ERROR", outcome="DETERMINISTIC_ERROR",
            error_code=exc.code, http_status=exc.http_status, support_ref=exc.support_ref,
            actor_user_id=actor_user_id, now=now(), session=session,
        )
        return "PROVIDER_ERROR", exc.code
    except CampaignProviderAmbiguousError as exc:
        _finish_retry_failure(
            row_id=review.child_id, attempt_number=1,
            status="RECONCILIATION_REQUIRED", outcome="AMBIGUOUS",
            error_code=exc.code, http_status=exc.http_status, support_ref=exc.support_ref,
            actor_user_id=actor_user_id, now=now(), session=session,
        )
        return "RECONCILIATION_REQUIRED", exc.code
    except CampaignProviderConfigurationError:
        _finish_retry_failure(
            row_id=review.child_id, attempt_number=1,
            status="PROVIDER_ERROR", outcome="PROVIDER_CONFIGURATION",
            error_code="PROVIDER_CONFIGURATION", http_status=None, support_ref=None,
            actor_user_id=actor_user_id, now=now(), session=session,
        )
        return "PROVIDER_ERROR", "PROVIDER_CONFIGURATION"
    except Exception:
        _finish_retry_failure(
            row_id=review.child_id, attempt_number=1,
            status="RECONCILIATION_REQUIRED", outcome="UNEXPECTED_PROVIDER_RESULT",
            error_code="UNEXPECTED_PROVIDER_RESULT", http_status=None, support_ref=None,
            actor_user_id=actor_user_id, now=now(), session=session,
        )
        return "RECONCILIATION_REQUIRED", "UNEXPECTED_PROVIDER_RESULT"

    _finish_retry_success(
        row_id=review.child_id, attempt_number=1, accepted_status="SUBMITTED",
        provider_campaign_id=response.provider_campaign_id,
        deduplicated=response.deduplicated, http_status=response.http_status,
        response_metadata=response.response_metadata,
        actor_user_id=actor_user_id, now=now(), session=session,
    )
    return "SUBMITTED", response.provider_campaign_id
