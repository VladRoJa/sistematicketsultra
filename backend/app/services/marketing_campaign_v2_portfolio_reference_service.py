"""Issue 856 B1: append-only, unverified Meta business identity references.

This catalog does not assert WABA/channel membership, nominal limits, actual
Meta capacity, or sending authorization. There are no provider API calls.
"""
from __future__ import annotations

import re
from datetime import timezone

from app.extensions import db
from app.models.marketing import MarketingCampaignV2PortfolioReferenceORM as Reference

_ID = re.compile(r"^[1-9][0-9]{5,31}$")


class CampaignV2PortfolioReferenceValidationError(ValueError):
    pass


class CampaignV2PortfolioReferenceConflictError(RuntimeError):
    pass


def validate_reference(*, business_id, display_name, app_id, source_reference):
    if not isinstance(business_id, str) or not _ID.fullmatch(business_id.strip()):
        raise CampaignV2PortfolioReferenceValidationError("Business ID inválido.")
    if display_name is not None and not isinstance(display_name, str):
        raise CampaignV2PortfolioReferenceValidationError("Nombre del negocio inválido.")
    if app_id is not None and not isinstance(app_id, str):
        raise CampaignV2PortfolioReferenceValidationError("App ID inválido.")
    if not isinstance(source_reference, str) or not (1 <= len(source_reference.strip()) <= 255):
        raise CampaignV2PortfolioReferenceValidationError("Fuente documental obligatoria (máximo 255).")
    normalized_app = (app_id or "").strip() or None
    if normalized_app and not _ID.fullmatch(normalized_app):
        raise CampaignV2PortfolioReferenceValidationError("App ID inválido.")
    normalized_name = (display_name or "").strip() or None
    if normalized_name and len(normalized_name) > 160:
        raise CampaignV2PortfolioReferenceValidationError("Nombre demasiado largo.")
    return {
        "business_id": business_id.strip(),
        "display_name": normalized_name,
        "app_id": normalized_app,
        "source_reference": source_reference.strip(),
    }


def _serialize(row):
    timestamp = row.created_at
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return {
        "revision_id": int(row.id),
        "business_id": row.business_id,
        "display_name": row.display_name,
        "app_id": row.app_id,
        "source_reference": row.source_reference,
        "created_by_user_id": int(row.created_by_user_id),
        "created_at": timestamp.astimezone(timezone.utc).isoformat(),
        "verification_status": "UNVERIFIED",
        "verified_channel_count": 0,
    }


def list_portfolio_references(*, session=None):
    active = session if session is not None else db.session
    # The catalogue is append-only; each business is represented by its newest revision.
    rows = active.query(Reference).order_by(Reference.id.desc()).limit(2000).all()
    seen = set()
    latest = []
    for row in rows:
        if row.business_id not in seen:
            latest.append(_serialize(row))
            seen.add(row.business_id)
    return {"rows": latest}


def register_portfolio_reference(
    *, business_id, display_name, app_id, source_reference,
    actor_user_id, session=None,
):
    if type(actor_user_id) is not int or actor_user_id <= 0:
        raise CampaignV2PortfolioReferenceValidationError("Actor inválido.")
    values = validate_reference(
        business_id=business_id, display_name=display_name,
        app_id=app_id, source_reference=source_reference,
    )
    active = session if session is not None else db.session
    previous = active.query(Reference).filter(
        Reference.business_id == values["business_id"]
    ).order_by(Reference.id.desc()).first()
    if previous and all(getattr(previous, key) == value for key, value in values.items()):
        raise CampaignV2PortfolioReferenceConflictError(
            "Referencia idéntica ya registrada; no se creó una revisión."
        )
    row = Reference(**values, created_by_user_id=actor_user_id)
    active.add(row)
    try:
        active.commit()
    except Exception:
        active.rollback()
        raise
    return _serialize(row)
