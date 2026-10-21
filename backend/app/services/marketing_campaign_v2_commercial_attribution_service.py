"""Read-only, per-child recipient proof for Campaign V2 commercial attribution.

This module does not calculate sales or fetch provider data. It resolves which
frozen recipients belonged to each provably submitted child. Unsent and
uncertain children are returned separately so callers never treat incomplete
coverage as a real zero or a completed campaign total.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from app.services.marketing_campaign_v2_contact_gate_service import (
    CampaignV2ContactGateConflict,
    _claim_phones,
)


class CommercialChildResolutionError(ValueError):
    """Persisted child/recipient evidence is inconsistent; fail closed."""


_DIRECT_ATTRIBUTION_PAIRS = frozenset({
    ("NEW_SALE", "FUNNEL_PORTFOLIO"),
    ("REACTIVATION", "EXPIRED_MEMBERS"),
})


def direct_attribution_ineligibility_reason(
    *, purpose: str | None, source: str | None,
) -> str | None:
    """Fail closed when the contacted person is not the direct sales target.

    Referrals to third parties need a separate inviter/invitee link, which a
    matching recipient phone and subsequent membership payment cannot prove.
    """
    normalized = (str(purpose or "").strip().upper(),
                  str(source or "").strip().upper())
    if normalized in _DIRECT_ATTRIBUTION_PAIRS:
        return None
    if normalized[1] == "ACTIVE_MEMBERS":
        return "INDIRECT_OR_ACTIVE_MEMBERS_AUDIENCE"
    return "PURPOSE_SOURCE_NOT_DIRECT"


@dataclass(frozen=True)
class SubmittedChildRecipientScope:
    child_id: int
    sucursal_id: int
    provider_campaign_id: str
    submitted_at: datetime
    # Each MX10 phone maps to its original frozen recipient ID.
    recipients: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class SubmittedChildResolution:
    submitted: tuple[SubmittedChildRecipientScope, ...]
    not_sent_child_ids: tuple[int, ...]
    unresolved_child_ids: tuple[int, ...]


def resolve_submitted_child_recipients(
    *,
    campaign_id: int,
    children: Iterable[Any],
    frozen_recipients: Iterable[Any],
) -> SubmittedChildResolution:
    """Resolve only proven SUBMITTED child payloads to frozen campaign IDs.

    The child owns the branch and actual provider campaign identity. The exact
    transport phones come from its immutable provider request snapshot, not
    from the entire frozen audience. A scheduled/ambiguous child is unresolved,
    never presumed successful. No database or upstream calls are made here.
    """
    if type(campaign_id) is not int or campaign_id <= 0:
        raise CommercialChildResolutionError("ID de campaña inválido.")

    frozen_by_phone: dict[str, int] = {}
    for recipient in frozen_recipients:
        if int(recipient.campaign_id) != campaign_id:
            raise CommercialChildResolutionError(
                "Destinatario congelado pertenece a otra campaña."
            )
        phone = recipient.phone_mx10
        if (
            not isinstance(phone, str)
            or len(phone) != 10
            or not phone.isdigit()
            or phone in frozen_by_phone
        ):
            raise CommercialChildResolutionError(
                "Destinatarios congelados con teléfono inválido o duplicado."
            )
        frozen_by_phone[phone] = int(recipient.id)

    submitted: list[SubmittedChildRecipientScope] = []
    not_sent: list[int] = []
    unresolved: list[int] = []
    seen_child_ids: set[int] = set()
    seen_submitted_phones: set[str] = set()
    seen_provider_ids: set[str] = set()

    for child in sorted(children, key=lambda row: int(row.id)):
        child_id = int(child.id)
        if child_id in seen_child_ids or int(child.campaign_v2_id) != campaign_id:
            raise CommercialChildResolutionError(
                "Child duplicado o perteneciente a otra campaña."
            )
        seen_child_ids.add(child_id)

        status = str(child.status)
        if status != "SUBMITTED":
            if status in {"PREPARED", "READY", "BLOCKED", "HELD"} and all(
                getattr(child, field, None) is None
                for field in ("submit_started_at", "submitted_at", "provider_campaign_id")
            ):
                not_sent.append(child_id)
            else:
                # Includes SCHEDULED, in-flight, errors and inconsistent READY.
                unresolved.append(child_id)
            continue

        provider_campaign_id = str(child.provider_campaign_id or "").strip()
        if (
            child.provider != "IVENTAS"
            or not provider_campaign_id
            or child.submitted_at is None
            or int(child.sucursal_id) <= 0
            or provider_campaign_id in seen_provider_ids
        ):
            raise CommercialChildResolutionError(
                "Child SUBMITTED carece de identidad verificable."
            )
        seen_provider_ids.add(provider_campaign_id)
        try:
            phones = _claim_phones(child)
        except CampaignV2ContactGateConflict as exc:
            raise CommercialChildResolutionError(
                "Payload enviado del child inconsistente."
            ) from exc

        if any(phone not in frozen_by_phone for phone in phones):
            raise CommercialChildResolutionError(
                "Child contiene destinatarios ajenos a la cohorte congelada."
            )
        if any(phone in seen_submitted_phones for phone in phones):
            raise CommercialChildResolutionError(
                "Teléfono duplicado entre children enviados."
            )
        seen_submitted_phones.update(phones)
        submitted.append(
            SubmittedChildRecipientScope(
                child_id=child_id,
                sucursal_id=int(child.sucursal_id),
                provider_campaign_id=provider_campaign_id,
                submitted_at=child.submitted_at,
                recipients=tuple((phone, frozen_by_phone[phone]) for phone in phones),
            )
        )

    return SubmittedChildResolution(
        submitted=tuple(submitted),
        not_sent_child_ids=tuple(not_sent),
        unresolved_child_ids=tuple(unresolved),
    )
