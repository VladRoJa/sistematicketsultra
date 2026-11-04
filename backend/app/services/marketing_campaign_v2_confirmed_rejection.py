"""Strict evidence gate for iVentas requests confirmed *not* accepted.

Only an explicitly whitelisted deterministic error can be skipped. Unknown
4xx, transport failures, 409/429, 5xx and missing provider refs are ambiguous.
"""
from __future__ import annotations

from typing import Any

SAFE_REJECTIONS = frozenset({(400, "TEMPLATE_NOT_FOUND")})


def confirmed_not_accepted(*, status: Any, error_code: Any,
                           http_status: Any, support_ref: Any) -> bool:
    return (
        status == "PROVIDER_ERROR"
        and (http_status, error_code) in SAFE_REJECTIONS
        and isinstance(support_ref, str)
        and bool(support_ref.strip())
    )


def confirmed_rejected_child(child: Any) -> bool:
    response = getattr(child, "provider_response_json", None) or {}
    return (
        confirmed_not_accepted(
            status=getattr(child, "status", None),
            error_code=getattr(child, "error_code", None),
            http_status=response.get("http_status") if isinstance(response, dict) else None,
            support_ref=getattr(child, "support_ref", None),
        )
        and getattr(child, "provider_campaign_id", None) is None
        and getattr(child, "submitted_at", None) is None
        and getattr(child, "submit_started_at", None) is not None
        and getattr(child, "submitted_by_user_id", None) is not None
        and getattr(child, "reconciliation_resolution", None) is None
        and int(getattr(child, "retry_attempt_count", 0) or 0) == 0
        and not getattr(child, "retry_history_json", None)
    )
