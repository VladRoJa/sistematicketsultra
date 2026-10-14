"""Issue #856 C: tightly scoped HTTP gateway to existing QA_MANUAL service.

Not a general phone-upload endpoint: authenticated global operator only;
exactly one recipient, one active default IVENTAS channel, no sending.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.extensions import db
from app.services.marketing_campaign_v2_dispatch_config_service import list_channel_bindings
from app.services.marketing_campaign_v2_qa_manual_service import (
    MarketingCampaignV2QAManualValidationError as QAValidation,
    MarketingCampaignV2QAManualConflictError as QAConflict,
    build_campaign_v2_qa_manual_preview,
    freeze_campaign_v2_qa_manual,
)


def _validate_qa_inputs(
    *, name: Any, purpose: Any, sucursal_id: Any,
    provider_channel_id: Any, recipients: Any, session: Any,
) -> tuple[dict, dict]:
    if not isinstance(name, str) or not name.strip().upper().startswith("QA "):
        raise QAValidation("La campaña debe comenzar con 'QA ' para identificar el uso interno.")
    if not isinstance(recipients, list) or len(recipients) != 1:
        raise QAValidation("QA desde Suite Ultra admite exactamente un destinatario.")
    recipient = recipients[0]
    if not isinstance(recipient, dict) or set(recipient) != {"name", "phone"}:
        raise QAValidation("Destinatario QA requiere solamente name y phone.")
    if type(sucursal_id) is not int or sucursal_id <= 0:
        raise QAValidation("sucursal_id debe ser un entero positivo.")
    if not isinstance(provider_channel_id, str) or not provider_channel_id.strip():
        raise QAValidation("Selecciona un canal iVentas activo.")
    if type(purpose) is not str or purpose not in {"NEW_SALE", "REACTIVATION", "ACTIVE_MEMBERS", "UNCLASSIFIED"}:
        raise QAValidation("Propósito de QA inválido.")
    active = list_channel_bindings(provider="IVENTAS", active_only=True, session=session)
    candidates = [
        row for row in active
        if row["sucursal_id"] == sucursal_id and row["is_default"] is True
    ]
    if len(candidates) != 1:
        raise QAValidation("La sucursal QA requiere exactamente un canal iVentas predeterminado activo.")
    binding = candidates[0]
    if binding["provider_channel_id"] != provider_channel_id.strip():
        raise QAValidation("El canal seleccionado no coincide con el predeterminado; actualiza el catálogo.")
    common = dict(
        name=name, purpose=purpose, sucursal_id=sucursal_id,
        recipients=recipients, session=session,
    )
    return binding, common


def _safe_preview(preview: dict, binding: dict) -> dict:
    # Do not duplicate personally identifying phone numbers in the API response.
    recipient = preview["recipients"][0]
    return {
        "name": preview["name"],
        "purpose": preview["purpose"],
        "source": "QA_MANUAL",
        "sucursal_id": preview["sucursal_id"],
        "sucursal_canon": preview["sucursal_canon"],
        "track_label": preview["track_label"],
        "provider_channel_id": binding["provider_channel_id"],
        "channel_binding_id": binding["id"],
        "recipient_count": 1,
        "recipient_name": recipient["name"],
        "recipient_phone_masked": "******" + recipient["phone_mx10"][-4:],
        "preview_fingerprint_version": preview["preview_fingerprint_version"],
        "preview_fingerprint": preview["preview_fingerprint"],
        "provider_send_enabled": False,
        "is_dispatch_authorized": False,
    }


def preview_qa_manual_http(
    *, name: Any, purpose: Any, sucursal_id: Any,
    provider_channel_id: Any, recipients: Any, session=None,
) -> dict:
    active = session if session is not None else db.session
    binding, common = _validate_qa_inputs(
        name=name, purpose=purpose, sucursal_id=sucursal_id,
        provider_channel_id=provider_channel_id, recipients=recipients, session=active,
    )
    preview = build_campaign_v2_qa_manual_preview(**common)
    return _safe_preview(preview, binding)


def freeze_qa_manual_http(
    *, name: Any, purpose: Any, sucursal_id: Any, provider_channel_id: Any,
    recipients: Any, expected_preview_fingerprint: Any,
    expected_channel_binding_id: Any, confirm_freeze: Any,
    actor_user_id: int, session=None,
) -> dict:
    if confirm_freeze is not True:
        raise QAValidation("Confirma explícitamente la congelación QA (no es un envío).")
    if type(expected_channel_binding_id) is not int or expected_channel_binding_id <= 0:
        raise QAValidation("Identificador de binding del Preview obligatorio.")
    active = session if session is not None else db.session
    binding, common = _validate_qa_inputs(
        name=name, purpose=purpose, sucursal_id=sucursal_id,
        provider_channel_id=provider_channel_id, recipients=recipients, session=active,
    )
    if binding["id"] != expected_channel_binding_id:
        raise QAValidation("El binding iVentas cambió. Repite el Preview.")
    # Serialize same-name freezes across tabs/workers without changing the CLI flow.
    # A nonblocking PostgreSQL transaction lock returns 409 rather than hanging.
    if hasattr(active, "get_bind") and active.get_bind().dialect.name == "postgresql":
        acquired = active.execute(
            text("SELECT pg_try_advisory_xact_lock(hashtext(:name))"),
            {"name": "campaign-v2-qa-manual:" + name.strip()},
        ).scalar()
        if not acquired:
            raise QAConflict("Otra congelación QA con este nombre está en curso.")
    result = freeze_campaign_v2_qa_manual(
        **common,
        expected_preview_fingerprint=expected_preview_fingerprint,
        created_by_user_id=actor_user_id,
    )
    return {
        **result,
        "provider_channel_id": binding["provider_channel_id"],
        "channel_binding_id": binding["id"],
        "provider_send_enabled": False,
        "is_dispatch_authorized": False,
    }
