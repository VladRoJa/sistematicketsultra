"""Fail-closed, one-off continuation of already-persisted Campaign V2 children.

Only READY children can be submitted; previously SUBMITTED/PROVIDER_ERROR
children are immutable. The caller must supply an exact expected manifest.
No API route and no automatic retry are introduced.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Mapping

from app.models.marketing import MarketingCampaignV2ProviderCampaignORM
from app.services.marketing_campaign_v2_preflight_service import (
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
)
from app.services.marketing_campaign_v2_submit_service import (
    MarketingCampaignV2SubmitPreconditionError,
    _load_campaign_rows,
    _log_transition,
    _persist_provider_failure,
    _persist_provider_success,
    _transition_ready_to_submitting,
    build_campaign_v2_provider_dispatch_batch,
    serialize_campaign_v2_provider_request_snapshot,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReadyChild:
    batch: CampaignV2DispatchBatchPlan
    child_id: int


@dataclass(frozen=True)
class PartialResumeReview:
    plan: CampaignV2PreflightPlan
    ready_children: tuple[ReadyChild, ...]


def review_partial_resume(
    *,
    campaign_id: int,
    template_id: int,
    expected_fingerprint: str,
    expected_submitted: Mapping[str, tuple[int, str]],
    expected_failed: Mapping[str, tuple[int, str, str]],
    expected_ready: Mapping[str, int],
    session: Any,
) -> PartialResumeReview:
    """Read-only check of EVERY persisted child against the approved manifest."""
    plan = build_campaign_v2_preflight(
        campaign_id=campaign_id,
        template_id=template_id,
        allowed_sucursal_keys=None,
        session=session,
    )
    if (
        not plan.ready
        or plan.mode != "IMMEDIATE"
        or plan.dispatch_fingerprint != expected_fingerprint
    ):
        raise MarketingCampaignV2SubmitPreconditionError(
            "Preflight changed or blocked; continuation denied."
        )
    expected_names = (
        set(expected_submitted) | set(expected_failed) | set(expected_ready)
    )
    if (
        len(expected_names)
        != len(expected_submitted) + len(expected_failed) + len(expected_ready)
        or len(plan.batches) != len(expected_names)
    ):
        raise MarketingCampaignV2SubmitPreconditionError(
            "Manifest missing branches or contains duplicate branch names."
        )

    rows = _load_campaign_rows(campaign_id=campaign_id, session=session)
    by_name = {str(row.sucursal_canon): row for row in rows}
    batches = {str(batch.sucursal_canon): batch for batch in plan.batches}
    if len(rows) != len(by_name) or set(by_name) != expected_names or set(batches) != expected_names:
        raise MarketingCampaignV2SubmitPreconditionError(
            "Existing provider children do not match the exact branch manifest."
        )

    pending: list[ReadyChild] = []
    for name in sorted(expected_names):
        row = by_name[name]
        batch = batches[name]
        if (
            int(row.campaign_v2_id) != campaign_id
            or str(row.provider) != str(plan.provider)
            or str(row.dispatch_fingerprint) != expected_fingerprint
            or int(row.sucursal_id) != int(batch.sucursal_id)
            or int(row.channel_binding_id) != int(batch.channel_binding_id or 0)
            or str(row.provider_channel_id) != str(batch.provider_channel_id)
            or int(row.template_id) != template_id
            or str(row.template_name) != str(batch.template_name)
            or not batch.ready
            or int(row.recipient_count) != len(batch.recipients)
            or str(row.idempotency_key) != build_provider_campaign_idempotency_key(
                campaign_v2_id=campaign_id,
                batch=batch,
                dispatch_fingerprint=expected_fingerprint,
            )
        ):
            raise MarketingCampaignV2SubmitPreconditionError(
                f"Persisted identity/count mismatch in {name}."
            )

        dispatch = build_campaign_v2_provider_dispatch_batch(plan=plan, batch=batch)
        snapshot = serialize_campaign_v2_provider_request_snapshot(dispatch)
        if dict(row.request_snapshot_json or {}) != snapshot:
            raise MarketingCampaignV2SubmitPreconditionError(
                f"Provider request snapshot changed for {name}."
            )

        if name in expected_submitted:
            count, provider_id = expected_submitted[name]
            if (
                str(row.status) != "SUBMITTED"
                or int(row.recipient_count) != count
                or str(row.provider_campaign_id) != provider_id
                or row.submitted_at is None
            ):
                raise MarketingCampaignV2SubmitPreconditionError(
                    f"Previously accepted child changed: {name}."
                )
        elif name in expected_failed:
            count, error_code, support_ref = expected_failed[name]
            if (
                str(row.status) != "PROVIDER_ERROR"
                or int(row.recipient_count) != count
                or str(row.error_code) != error_code
                or str(row.support_ref) != support_ref
                or row.provider_campaign_id is not None
            ):
                raise MarketingCampaignV2SubmitPreconditionError(
                    f"Authorized skip no longer matches original error: {name}."
                )
        else:
            count = expected_ready[name]
            if (
                str(row.status) != "READY"
                or int(row.recipient_count) != count
                or row.provider_campaign_id is not None
                or row.submit_started_at is not None
            ):
                raise MarketingCampaignV2SubmitPreconditionError(
                    f"Pending child is not untouched READY: {name}."
                )
            pending.append(ReadyChild(batch=batch, child_id=int(row.id)))

    return PartialResumeReview(plan=plan, ready_children=tuple(pending))


def continue_ready_children(
    *,
    review: PartialResumeReview,
    actor_user_id: int,
    provider: CampaignProvider,
    send_enabled: bool,
    session: Any,
) -> list[tuple[str, str, str | None]]:
    """POST only approved READY children, in order, stopping on first failure.

    This function must be called only after a fresh review in the SAME process.
    Each READY -> SUBMITTING transition is durable and conditional in the DB.
    """
    if send_enabled is not True or not review.ready_children or actor_user_id <= 0:
        raise MarketingCampaignV2SubmitPreconditionError("Continuation not authorized.")
    results: list[tuple[str, str, str | None]] = []
    for child in review.ready_children:
        batch = child.batch
        dispatch = build_campaign_v2_provider_dispatch_batch(plan=review.plan, batch=batch)
        _transition_ready_to_submitting(
            row_id=child.child_id,
            actor_user_id=actor_user_id,
            session=session,
            now=datetime.now(timezone.utc),
        )
        _log_transition(
            campaign_id=review.plan.campaign_id,
            child_id=child.child_id,
            batch=batch,
            mode=review.plan.mode,
            state="SUBMITTING",
            error_code=None,
        )
        started = perf_counter()
        try:
            response = provider.create_campaign(dispatch)
        except CampaignProviderDeterministicError as exc:
            status, code, http, ref = "PROVIDER_ERROR", exc.code, exc.http_status, exc.support_ref
        except CampaignProviderAmbiguousError as exc:
            status, code, http, ref = "RECONCILIATION_REQUIRED", exc.code, exc.http_status, exc.support_ref
        except CampaignProviderConfigurationError:
            status, code, http, ref = "PROVIDER_ERROR", "PROVIDER_CONFIGURATION", None, None
        except Exception:
            status, code, http, ref = "RECONCILIATION_REQUIRED", "UNEXPECTED_PROVIDER_RESULT", None, None
        else:
            _persist_provider_success(
                row_id=child.child_id,
                provider_campaign_id=response.provider_campaign_id,
                deduplicated=response.deduplicated,
                response_metadata=response.response_metadata,
                accepted_status="SUBMITTED",
                actor_user_id=actor_user_id,
                session=session,
                now=datetime.now(timezone.utc),
            )
            _log_transition(
                campaign_id=review.plan.campaign_id,
                child_id=child.child_id,
                batch=batch,
                mode=review.plan.mode,
                state="SUBMITTED",
                error_code=None,
                duration_ms=(perf_counter() - started) * 1000,
                http_status=response.http_status,
            )
            results.append((batch.sucursal_canon, "SUBMITTED", response.provider_campaign_id))
            logger.info("campaign_v2_partial_resume_success campaign=%s child=%s branch=%s", review.plan.campaign_id, child.child_id, batch.sucursal_canon)
            continue

        _persist_provider_failure(
            row_id=child.child_id,
            status=status,
            error_code=code,
            support_ref=ref,
            http_status=http,
            actor_user_id=actor_user_id,
            session=session,
            now=datetime.now(timezone.utc),
        )
        _log_transition(
            campaign_id=review.plan.campaign_id,
            child_id=child.child_id,
            batch=batch,
            mode=review.plan.mode,
            state=status,
            error_code=code,
            duration_ms=(perf_counter() - started) * 1000,
            http_status=http,
            support_ref=ref,
        )
        results.append((batch.sucursal_canon, status, code))
        logger.warning("campaign_v2_partial_resume_stopped campaign=%s child=%s branch=%s status=%s code=%s", review.plan.campaign_id, child.child_id, batch.sucursal_canon, status, code)
        break

    return results
