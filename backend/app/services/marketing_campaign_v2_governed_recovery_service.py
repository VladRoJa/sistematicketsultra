"""Audited, fail-closed continuation for the known Campaign #41 provider rejection.

Does not weaken the standard governed or legacy dispatch gates. The original
REVIEW_REQUIRED execution and its failed child remain unchanged.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from sqlalchemy import text

from app.models.marketing import (
    MarketingCampaignV2ORM as Campaign,
    MarketingCampaignV2DispatchApprovalORM as Approval,
    MarketingCampaignV2GovernedExecutionORM as Execution,
    MarketingCampaignV2ProviderCampaignORM as Child,
)
from app.models.marketing_campaign_v2_background_job import (
    MarketingCampaignV2BackgroundJobORM as BackgroundJob,
)
from app.models.user_model import UserORM
from app.services.marketing_access import resolve_marketing_access
from app.services.marketing_campaign_v2_contact_gate_service import (
    acquire_campaign_v2_contact_gate, verify_outbound_contact_admission,
)
from app.services.marketing_campaign_v2_dispatch_approval_service import _assess_scopes
from app.services.marketing_campaign_v2_governed_dispatch_service import manifest_digest
from app.services.marketing_campaign_v2_manifest_service import (
    _assert_manifest, budget_for_existing_approval,
)
from app.services.marketing_campaign_v2_preflight_service import (
    build_campaign_v2_preflight, build_provider_campaign_idempotency_key,
)
from app.services.marketing_campaign_v2_submit_service import (
    _persist_provider_failure, _persist_provider_success,
    build_campaign_v2_provider_dispatch_batch,
    serialize_campaign_v2_provider_request_snapshot,
)
from app.services.marketing_campaign_v2_provider import (
    CampaignProviderDeterministicError, CampaignProviderAmbiguousError,
    CampaignProviderConfigurationError,
)

logger = logging.getLogger(__name__)
CAMPAIGN_ID = 41
FAILED_ID = 255
FAILED_ERROR = "TEMPLATE_NOT_FOUND"
FAILED_REF = "bc-mw1c1why-phq041"


class GovernedRecoveryBlocked(RuntimeError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise GovernedRecoveryBlocked(message)


def verify_suffix(
    *, rows: list, accepted_original: tuple[tuple[int, str], ...],
    ready_ids: tuple[int, ...], completed: tuple[tuple[int, str], ...],
    next_id: int, actor_user_id: int,
) -> None:
    """Prove immutable original prefix, rejected #255 and ordered READY suffix."""
    by_id = {int(row.id): row for row in rows}
    require(len(by_id) == len(rows), "Children duplicados.")
    require(next_id in ready_ids and len(set(ready_ids)) == len(ready_ids),
            "Sufijo READY inválido.")
    require(len(completed) == ready_ids.index(next_id)
            and tuple(i for i, _ in completed) == ready_ids[:len(completed)],
            "La continuación tiene envíos fuera de orden.")
    for child_id, provider_id in accepted_original:
        row = by_id.get(child_id)
        require(row is not None and row.status == "SUBMITTED"
                and row.provider_campaign_id == provider_id
                and row.submitted_at is not None,
                "Un lote aceptado previamente cambió.")
    failed = by_id.get(FAILED_ID)
    require(failed is not None and failed.status == "PROVIDER_ERROR"
            and failed.error_code == FAILED_ERROR
            and failed.support_ref == FAILED_REF
            and failed.provider_campaign_id is None
            and failed.submitted_at is None,
            "El lote omitido #255 cambió.")
    for position, child_id in enumerate(ready_ids):
        row = by_id.get(child_id)
        require(row is not None, "Falta un lote del manifiesto.")
        if position < len(completed):
            provider_id = completed[position][1]
            require(row.status == "SUBMITTED"
                    and row.provider_campaign_id == provider_id
                    and row.submitted_at is not None
                    and row.submitted_by_user_id == actor_user_id,
                    "El prefijo continuado cambió.")
        else:
            require(row.status == "READY"
                    and row.provider_campaign_id is None
                    and row.submit_started_at is None
                    and row.submitted_at is None,
                    "Un lote pendiente fue intentado o modificado.")
