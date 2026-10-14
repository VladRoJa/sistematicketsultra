"""Issue 856 B2: audited operator-declared IVENTAS channel → Meta business mapping.

These claims NEVER prove Meta ownership, create quota policies, or permit sending.
A revision can be withdrawn; older evidence remains available for audit.
"""
from __future__ import annotations

import re
from datetime import timezone

from sqlalchemy import func

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ChannelBindingORM as Binding,
    MarketingCampaignV2PortfolioReferenceORM as Portfolio,
    MarketingCampaignV2ChannelPortfolioEvidenceORM as Evidence,
)

_ID = re.compile(r"^[1-9][0-9]{5,31}$")
_KINDS = frozenset(("OPERATOR_STATEMENT", "META_DOCUMENT", "IVENTAS_CONFIRMATION"))
_STATES = frozenset(("DECLARED", "WITHDRAWN"))


class CampaignV2ChannelPortfolioValidationError(ValueError):
    pass


class CampaignV2ChannelPortfolioConflictError(RuntimeError):
    pass


def normalize_claim(
    *, provider_channel_id, business_id, waba_id, state, evidence_kind, source_reference,
    expected_revision_id,
):
    if not isinstance(provider_channel_id, str) or not (
        1 <= len(provider_channel_id.strip()) <= 255
    ):
        raise CampaignV2ChannelPortfolioValidationError("Canal iVentas obligatorio.")
    if not isinstance(state, str) or state not in _STATES:
        raise CampaignV2ChannelPortfolioValidationError("Estado de asociación inválido.")
    if not isinstance(evidence_kind, str) or evidence_kind not in _KINDS:
        raise CampaignV2ChannelPortfolioValidationError("Tipo de evidencia inválido.")
    if not isinstance(source_reference, str) or not (
        1 <= len(source_reference.strip()) <= 255
    ):
        raise CampaignV2ChannelPortfolioValidationError("Referencia documental obligatoria.")
    if expected_revision_id is not None and (
        type(expected_revision_id) is not int or expected_revision_id <= 0
    ):
        raise CampaignV2ChannelPortfolioValidationError("Revisión esperada inválida.")
    if state == "DECLARED":
        if not isinstance(business_id, str) or not _ID.fullmatch(business_id.strip()):
            raise CampaignV2ChannelPortfolioValidationError("Business ID inválido.")
        normalized_business = business_id.strip()
        if waba_id is not None and not isinstance(waba_id, str):
            raise CampaignV2ChannelPortfolioValidationError("WABA ID inválido.")
        normalized_waba = (waba_id or "").strip() or None
        if normalized_waba and not _ID.fullmatch(normalized_waba):
            raise CampaignV2ChannelPortfolioValidationError("WABA ID inválido.")
    else:
        if business_id is not None or waba_id is not None:
            raise CampaignV2ChannelPortfolioValidationError(
                "Retirar una asociación no permite Business ID ni WABA ID."
            )
        normalized_business = normalized_waba = None
    return {
        "provider_channel_id": provider_channel_id.strip(),
        "business_id": normalized_business,
        "waba_id": normalized_waba,
        "state": state,
        "evidence_kind": evidence_kind,
        "source_reference": source_reference.strip(),
        "expected_revision_id": expected_revision_id,
    }


def _serialize(row):
    created = row.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return {
        "revision_id": int(row.id),
        "provider_channel_id": row.provider_channel_id,
        "business_id": row.business_id,
        "waba_id": row.waba_id,
        "state": row.state,
        "evidence_kind": row.evidence_kind,
        "source_reference": row.source_reference,
        "created_by_user_id": int(row.created_by_user_id),
        "created_at": created.astimezone(timezone.utc).isoformat(),
        "api_verified": False,
    }


def list_channel_portfolio_evidence(*, session=None):
    active = session if session is not None else db.session
    latest_ids = active.query(
        func.max(Evidence.id).label("id")
    ).group_by(Evidence.provider_channel_id).subquery()
    current = active.query(Evidence).join(
        latest_ids, latest_ids.c.id == Evidence.id,
    ).order_by(Evidence.provider_channel_id.asc()).all()
    history = active.query(Evidence).order_by(Evidence.id.desc()).limit(250).all()
    return {
        "rows": [_serialize(row) for row in current],
        "history": [_serialize(row) for row in history],
        "history_is_limited": len(history) >= 250,
    }


def register_channel_portfolio_evidence(
    *, provider_channel_id, business_id, waba_id, state, evidence_kind,
    source_reference, expected_revision_id, actor_user_id, session=None,
):
    values = normalize_claim(
        provider_channel_id=provider_channel_id, business_id=business_id,
        waba_id=waba_id, state=state, evidence_kind=evidence_kind,
        source_reference=source_reference,
        expected_revision_id=expected_revision_id,
    )
    if type(actor_user_id) is not int or actor_user_id <= 0:
        raise CampaignV2ChannelPortfolioValidationError("Actor inválido.")
    active = session if session is not None else db.session
    try:
        # Lock the stable binding row, including when this channel has no history.
        binding = active.query(Binding).filter(
            Binding.provider == "IVENTAS",
            Binding.provider_channel_id == values["provider_channel_id"],
            Binding.is_active.is_(True),
            Binding.is_default.is_(True),
        ).with_for_update().one_or_none()
        if binding is None:
            raise CampaignV2ChannelPortfolioValidationError(
                "El canal debe existir y ser predeterminado activo en iVentas."
            )
        previous = active.query(Evidence).filter(
            Evidence.provider_channel_id == values["provider_channel_id"],
        ).order_by(Evidence.id.desc()).first()
        previous_id = int(previous.id) if previous is not None else None
        if previous_id != values["expected_revision_id"]:
            raise CampaignV2ChannelPortfolioConflictError(
                "La asociación cambió. Actualiza y vuelve a revisar antes de guardar."
            )
        if values["state"] == "DECLARED":
            exists = active.query(Portfolio.id).filter(
                Portfolio.business_id == values["business_id"],
            ).first()
            if exists is None:
                raise CampaignV2ChannelPortfolioValidationError(
                    "Registra primero este Business ID en el catálogo de portafolios."
                )
        elif previous is None or previous.state == "WITHDRAWN":
            raise CampaignV2ChannelPortfolioConflictError(
                "No existe una asociación vigente para retirar."
            )
        if previous and all(
            getattr(previous, key) == values[key]
            for key in ("business_id", "waba_id", "state", "evidence_kind", "source_reference")
        ):
            raise CampaignV2ChannelPortfolioConflictError(
                "La revisión idéntica ya existe."
            )
        row = Evidence(
            **{k: v for k, v in values.items() if k != "expected_revision_id"},
            created_by_user_id=actor_user_id,
        )
        active.add(row)
        active.commit()
        return _serialize(row)
    except Exception:
        active.rollback()
        raise
