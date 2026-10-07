"""Deterministic, side-effect-free Campaign V2 dispatch preflight."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from app.extensions import db
from app.services.marketing_campaign_v2_delivery_export_service import (
    build_campaign_v2_sendable_projection,
    campaign_v2_first_name,
)
from app.services.marketing_campaign_v2_dispatch_branch_service import (
    MarketingCampaignV2DispatchBranch,
    resolve_frozen_recipient_branch,
)
from app.services.marketing_campaign_v2_dispatch_config_service import (
    DEFAULT_PROVIDER,
    MarketingCampaignV2DispatchConfigNotFoundError,
    MarketingCampaignV2DispatchConfigValidationError,
    resolve_dispatch_channel_binding,
    resolve_dispatch_template,
    template_allows_channel,
)
from app.services.marketing_phone import normalize_phone


DISPATCH_FINGERPRINT_VERSION = "campaign-v2-dispatch-v1"
DISPATCH_MODE = "IMMEDIATE"


@dataclass(frozen=True)
class CampaignV2DispatchRecipientPlan:
    recipient_id: int
    phone_mx10: str
    variables: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class CampaignV2DispatchBatchPlan:
    sucursal_id: int
    sucursal_canon: str
    track_label: str
    channel_binding_id: int | None
    provider_channel_id: str | None
    template_id: int
    template_name: str
    recipients: tuple[CampaignV2DispatchRecipientPlan, ...]
    blocked_reasons: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.blocked_reasons


@dataclass(frozen=True)
class CampaignV2PreflightPlan:
    campaign_id: int
    campaign_name: str
    campaign_purpose: str
    provider: str
    mode: str
    frozen_count: int
    blacklisted_phones: tuple[str, ...]
    sendable_phones: tuple[str, ...]
    batches: tuple[CampaignV2DispatchBatchPlan, ...]
    blocked_missing_branch: tuple[int, ...]
    blocked_missing_channel: tuple[int, ...]
    blocked_missing_required_variable: tuple[int, ...]
    blocked_invalid_phone: tuple[int, ...]
    blocked_template_channel_mismatch: tuple[int, ...]
    dispatch_fingerprint: str

    @property
    def ready(self) -> bool:
        return (
            bool(self.sendable_phones)
            and not self.blocked_missing_branch
            and not self.blocked_missing_channel
            and not self.blocked_missing_required_variable
            and not self.blocked_invalid_phone
            and not self.blocked_template_channel_mismatch
            and all(batch.ready for batch in self.batches)
        )


def build_campaign_v2_preflight(
    *,
    campaign_id: int,
    template_id: Any,
    allowed_sucursal_keys,
    provider: Any = DEFAULT_PROVIDER,
    session: Any | None = None,
) -> CampaignV2PreflightPlan:
    active_session = session if session is not None else db.session
    projection = build_campaign_v2_sendable_projection(
        campaign_id=campaign_id,
        allowed_sucursal_keys=allowed_sucursal_keys,
        session=active_session,
    )
    campaign = projection["campaign"]
    purpose = str(campaign.get("purpose") or "").strip().upper()
    provider_name = str(provider or DEFAULT_PROVIDER).strip().upper()

    template = resolve_dispatch_template(
        template_id=template_id,
        purpose=purpose,
        provider=provider_name,
        session=active_session,
    )

    frozen_recipients = list(projection["frozen_recipients"])
    sendable_recipients = list(projection["sendable_recipients"])
    blacklisted_phones = tuple(
        sorted(str(value) for value in projection["blacklisted_phones"])
    )

    missing_branch: set[int] = set()
    missing_channel: set[int] = set()
    missing_variable: set[int] = set()
    invalid_phone: set[int] = set()
    template_channel_mismatch: set[int] = set()

    grouped: dict[
        tuple[int, str],
        dict[str, Any],
    ] = {}

    for recipient in sorted(
        sendable_recipients,
        key=lambda row: (str(getattr(row, "phone_mx10", "")), int(row.id)),
    ):
        recipient_id = int(recipient.id)
        raw_phone = str(getattr(recipient, "phone_mx10", "") or "")
        phone = normalize_phone(raw_phone)
        if phone is None or phone != raw_phone:
            invalid_phone.add(recipient_id)
            continue

        branch = resolve_frozen_recipient_branch(
            recipient,
            session=active_session,
        )
        if branch is None:
            missing_branch.add(recipient_id)
            continue

        key = (branch.sucursal_id, branch.sucursal_canon)
        group = grouped.setdefault(
            key,
            {
                "branch": branch,
                "binding": None,
                "recipients": [],
                "missing_channel": False,
                "template_channel_mismatch": False,
            },
        )
        if group["binding"] is None and not group["missing_channel"]:
            binding = resolve_dispatch_channel_binding(
                sucursal_id=branch.sucursal_id,
                provider=provider_name,
                session=active_session,
            )
            if binding is None:
                group["missing_channel"] = True
            else:
                group["binding"] = binding
                if not template_allows_channel(
                    template,
                    str(binding.provider_channel_id),
                ):
                    group["template_channel_mismatch"] = True

        variables, missing_sources = _recipient_variables(
            recipient=recipient,
            branch=branch,
            mapping=dict(template.variables_json or {}),
        )
        if missing_sources:
            missing_variable.add(recipient_id)

        group["recipients"].append(
            CampaignV2DispatchRecipientPlan(
                recipient_id=recipient_id,
                phone_mx10=phone,
                variables=tuple(
                    (position, variables[position])
                    for position in sorted(
                        variables,
                        key=lambda item: int(item),
                    )
                ),
            )
        )

    batches: list[CampaignV2DispatchBatchPlan] = []
    for (_sucursal_id, _sucursal_canon), group in sorted(
        grouped.items(),
        key=lambda item: (item[0][1], item[0][0]),
    ):
        branch: MarketingCampaignV2DispatchBranch = group["branch"]
        binding = group["binding"]
        batch_recipient_ids = {
            row.recipient_id for row in group["recipients"]
        }
        reasons: list[str] = []

        if group["missing_channel"]:
            reasons.append("MISSING_CHANNEL")
            missing_channel.update(batch_recipient_ids)

        if group["template_channel_mismatch"]:
            reasons.append("TEMPLATE_CHANNEL_MISMATCH")
            template_channel_mismatch.update(batch_recipient_ids)

        if batch_recipient_ids & missing_variable:
            reasons.append("MISSING_REQUIRED_VARIABLE")

        batches.append(
            CampaignV2DispatchBatchPlan(
                sucursal_id=branch.sucursal_id,
                sucursal_canon=branch.sucursal_canon,
                track_label=branch.track_label,
                channel_binding_id=(
                    int(binding.id) if binding is not None else None
                ),
                provider_channel_id=(
                    str(binding.provider_channel_id)
                    if binding is not None
                    else None
                ),
                template_id=int(template.id),
                template_name=str(template.template_name),
                recipients=tuple(
                    sorted(
                        group["recipients"],
                        key=lambda row: (row.phone_mx10, row.recipient_id),
                    )
                ),
                blocked_reasons=tuple(sorted(set(reasons))),
            )
        )

    sendable_phones = tuple(
        sorted(
            str(getattr(recipient, "phone_mx10", "") or "")
            for recipient in sendable_recipients
        )
    )

    fingerprint = _dispatch_fingerprint(
        campaign_id=int(campaign_id),
        provider=provider_name,
        mode=DISPATCH_MODE,
        template=template,
        sendable_phones=sendable_phones,
        batches=tuple(batches),
        missing_branch=tuple(sorted(missing_branch)),
        invalid_phone=tuple(sorted(invalid_phone)),
    )

    return CampaignV2PreflightPlan(
        campaign_id=int(campaign_id),
        campaign_name=str(campaign.get("name") or ""),
        campaign_purpose=purpose,
        provider=provider_name,
        mode=DISPATCH_MODE,
        frozen_count=len(frozen_recipients),
        blacklisted_phones=blacklisted_phones,
        sendable_phones=sendable_phones,
        batches=tuple(batches),
        blocked_missing_branch=tuple(sorted(missing_branch)),
        blocked_missing_channel=tuple(sorted(missing_channel)),
        blocked_missing_required_variable=tuple(sorted(missing_variable)),
        blocked_invalid_phone=tuple(sorted(invalid_phone)),
        blocked_template_channel_mismatch=tuple(
            sorted(template_channel_mismatch)
        ),
        dispatch_fingerprint=fingerprint,
    )


def serialize_campaign_v2_preflight(
    plan: CampaignV2PreflightPlan,
) -> dict[str, Any]:
    return {
        "campaign_id": plan.campaign_id,
        "campaign_name": plan.campaign_name,
        "campaign_purpose": plan.campaign_purpose,
        "provider": plan.provider,
        "mode": plan.mode,
        "frozen_count": plan.frozen_count,
        "suppressed": {
            "blacklist": len(plan.blacklisted_phones),
        },
        "sendable_count": len(plan.sendable_phones),
        "template": (
            {
                "id": plan.batches[0].template_id,
                "template_name": plan.batches[0].template_name,
            }
            if plan.batches
            else None
        ),
        "batches": [
            {
                "sucursal_id": batch.sucursal_id,
                "sucursal_canon": batch.sucursal_canon,
                "track_label": batch.track_label,
                "channel_binding_id": batch.channel_binding_id,
                "provider_channel_id": batch.provider_channel_id,
                "template_id": batch.template_id,
                "template_name": batch.template_name,
                "recipient_count": len(batch.recipients),
                "blocked_reasons": list(batch.blocked_reasons),
                "ready": batch.ready,
            }
            for batch in plan.batches
        ],
        "blocked": {
            "missing_branch": len(plan.blocked_missing_branch),
            "missing_channel": len(plan.blocked_missing_channel),
            "missing_required_variable": len(
                plan.blocked_missing_required_variable
            ),
            "invalid_phone": len(plan.blocked_invalid_phone),
            "template_channel_mismatch": len(
                plan.blocked_template_channel_mismatch
            ),
        },
        "provider_campaign_count": len(plan.batches),
        "dispatch_fingerprint_version": DISPATCH_FINGERPRINT_VERSION,
        "dispatch_fingerprint": plan.dispatch_fingerprint,
        "ready": plan.ready,
    }


def _recipient_variables(
    *,
    recipient: Any,
    branch: MarketingCampaignV2DispatchBranch,
    mapping: dict[str, Any],
) -> tuple[dict[str, str], tuple[str, ...]]:
    values: dict[str, str] = {}
    missing: list[str] = []

    for raw_position, raw_source in sorted(
        mapping.items(),
        key=lambda item: int(str(item[0])),
    ):
        position = str(int(str(raw_position)))
        source = str(raw_source or "").strip().lower()
        value = _variable_value(
            source=source,
            recipient=recipient,
            branch=branch,
        )
        if value is None or value == "":
            missing.append(source)
            continue
        values[position] = value

    return values, tuple(sorted(set(missing)))


def _variable_value(
    *,
    source: str,
    recipient: Any,
    branch: MarketingCampaignV2DispatchBranch,
) -> str | None:
    if source == "first_name":
        return campaign_v2_first_name(getattr(recipient, "member_name", None)) or None
    if source == "expiration_date":
        return _iso_date(getattr(recipient, "fecha_vencimiento_date", None))
    if source == "tariff":
        return _clean_optional(getattr(recipient, "tarifa_raw", None))
    if source == "branch":
        return _clean_optional(branch.track_label)
    if source == "member_id":
        return _clean_optional(getattr(recipient, "member_id", None))
    if source == "member_pin":
        return _clean_optional(getattr(recipient, "member_pin", None))
    if source == "amount":
        return None
    raise MarketingCampaignV2DispatchConfigValidationError(
        f"Fuente de variable no soportada en preflight: {source}."
    )


def _dispatch_fingerprint(
    *,
    campaign_id: int,
    provider: str,
    mode: str,
    template: Any,
    sendable_phones: tuple[str, ...],
    batches: tuple[CampaignV2DispatchBatchPlan, ...],
    missing_branch: tuple[int, ...],
    invalid_phone: tuple[int, ...],
) -> str:
    payload = {
        "version": DISPATCH_FINGERPRINT_VERSION,
        "campaign_id": campaign_id,
        "provider": provider,
        "mode": mode,
        "template": {
            "id": int(template.id),
            "template_name": str(template.template_name),
            "variables": _canonical_value(dict(template.variables_json or {})),
            "compatible_channel_ids": sorted(
                str(value)
                for value in (template.compatible_channel_ids_json or [])
            ),
        },
        "sendable_phones": list(sendable_phones),
        "batches": [
            {
                "sucursal_id": batch.sucursal_id,
                "sucursal_canon": batch.sucursal_canon,
                "channel_binding_id": batch.channel_binding_id,
                "provider_channel_id": batch.provider_channel_id,
                "template_id": batch.template_id,
                "template_name": batch.template_name,
                "blocked_reasons": list(batch.blocked_reasons),
                "recipients": [
                    {
                        "recipient_id": recipient.recipient_id,
                        "phone_mx10": recipient.phone_mx10,
                        "variables": list(recipient.variables),
                    }
                    for recipient in batch.recipients
                ],
            }
            for batch in sorted(
                batches,
                key=lambda row: (row.sucursal_canon, row.sucursal_id),
            )
        ],
        "unbatched": {
            "missing_branch": list(missing_branch),
            "invalid_phone": list(invalid_phone),
        },
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_provider_campaign_idempotency_key(
    *,
    campaign_v2_id: int,
    batch: CampaignV2DispatchBatchPlan,
    dispatch_fingerprint: str,
) -> str:
    payload = {
        "campaign_v2_id": int(campaign_v2_id),
        "sucursal_id": int(batch.sucursal_id),
        "provider_channel_id": batch.provider_channel_id,
        "template_id": int(batch.template_id),
        "dispatch_fingerprint": str(dispatch_fingerprint),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _canonical_value(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _iso_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None
