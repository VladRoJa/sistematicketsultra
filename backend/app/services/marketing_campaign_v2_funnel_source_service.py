from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.extensions import db
from app.models.warehouse import SociosActivosSnapshotRowORM
from app.services.marketing_branch_scope import (
    marketing_branch_keys_by_sucursal_ids,
)
from app.services.marketing_phone import normalize_phone
from app.services.marketing_sales_funnel_cutoff_detail_service import (
    build_marketing_funnel_portfolio_at_cutoff,
)
from app.warehouse.services import socios_activos_snapshot_resolver as activos_resolver


SOURCE_FUNNEL_PORTFOLIO = "FUNNEL_PORTFOLIO"


class MarketingCampaignV2FunnelSourceValidationError(ValueError):
    """La fuente Funnel no cumple el contrato Campaign V2."""


@dataclass(frozen=True, slots=True)
class MarketingCampaignV2FunnelCandidate:
    phone_raw: str | None
    phone_mx10: str | None
    contact_id: str | None
    sucursal_id: int | None
    sucursal_key: str | None
    channel: str | None
    source_date: str | None
    origin: str | None
    source_reference: str | None


@dataclass(frozen=True, slots=True)
class MarketingCampaignV2FunnelSourceResult:
    funnel_month: str
    funnel_cutoff_date: str
    universe_count: int
    scoped_count: int
    funnel_candidates: tuple[MarketingCampaignV2FunnelCandidate, ...]
    buyer_excluded: tuple[MarketingCampaignV2FunnelCandidate, ...]
    invalid_phone: tuple[MarketingCampaignV2FunnelCandidate, ...]
    active_member_suppressed: tuple[MarketingCampaignV2FunnelCandidate, ...]
    candidates: tuple[MarketingCampaignV2FunnelCandidate, ...]
    metadata: dict[str, Any]


def load_campaign_v2_funnel_source(
    *,
    funnel_month: Any,
    funnel_cutoff_date: Any,
    marketing_access: Any,
    session: Any | None = None,
) -> MarketingCampaignV2FunnelSourceResult:
    """Adapta la cartera canónica M18 a candidatos de Campaign V2.

    M18 ya aplica el scope backend al consultar Funnel. Aquí se conserva un
    segundo guard fail-closed después de ACTIVE_MEMBER_SUPPRESSION para que un
    futuro candidato sin sucursal nunca amplíe el alcance de un usuario
    limitado.
    """

    if marketing_access is None:
        raise MarketingCampaignV2FunnelSourceValidationError(
            "marketing_access backend es obligatorio para FUNNEL_PORTFOLIO."
        )

    active_session = session if session is not None else db.session
    portfolio = build_marketing_funnel_portfolio_at_cutoff(
        month=funnel_month,
        cutoff_date=funnel_cutoff_date,
        access=marketing_access,
    )

    raw_rows = tuple(portfolio.get("rows", ()))
    buyer_rows = tuple(portfolio.get("buyer_excluded", ()))
    branch_ids = {
        int(row["sucursal_id"])
        for row in (*raw_rows, *buyer_rows)
        if row.get("sucursal_id") is not None
    }
    branch_keys = marketing_branch_keys_by_sucursal_ids(
        sucursal_ids=branch_ids,
        session=active_session,
    )

    funnel_candidates = tuple(
        _candidate_from_portfolio_row(row, branch_keys=branch_keys)
        for row in raw_rows
    )
    buyer_excluded = tuple(
        _candidate_from_portfolio_row(row, branch_keys=branch_keys)
        for row in buyer_rows
    )

    invalid_phone = tuple(
        row for row in funnel_candidates if row.phone_mx10 is None
    )
    valid_phone = tuple(
        row for row in funnel_candidates if row.phone_mx10 is not None
    )

    snapshot = activos_resolver.resolve_latest_canonical_socios_activos_snapshot(
        minimum_cutoff_date=date.min,
        session=active_session,
    )
    if snapshot is None:
        raise MarketingCampaignV2FunnelSourceValidationError(
            "No existe un snapshot canónico de Socios Activos disponible."
        )

    active_phone_rows = (
        active_session.query(SociosActivosSnapshotRowORM.telefono_raw)
        .filter(SociosActivosSnapshotRowORM.snapshot_id == int(snapshot.id))
        .all()
    )
    active_phones = {
        normalized
        for row in active_phone_rows
        for normalized in (_normalize_active_phone_row(row),)
        if normalized is not None
    }

    active_member_suppressed = tuple(
        row for row in valid_phone if row.phone_mx10 in active_phones
    )
    after_active_suppression = tuple(
        row for row in valid_phone if row.phone_mx10 not in active_phones
    )
    scoped = tuple(
        row
        for row in after_active_suppression
        if _candidate_in_access_scope(row, marketing_access)
    )

    metadata = {
        "funnel_month": str(portfolio["funnel_month"]),
        "funnel_cutoff_date": str(portfolio["funnel_cutoff_date"]),
        "iventas_sync_run_id": int(portfolio["iventas_sync_run_id"]),
        "active_members_snapshot_id": int(snapshot.id),
        "active_members_cutoff_date": _iso_date(snapshot.cutoff_date),
        "active_members_snapshot_kind": str(
            getattr(snapshot, "snapshot_kind", "daily")
        ),
        "active_members_captured_at": _iso_datetime(
            getattr(snapshot, "captured_at", None)
        ),
        "funnel_scope": portfolio.get("scope"),
    }

    return MarketingCampaignV2FunnelSourceResult(
        funnel_month=str(portfolio["funnel_month"]),
        funnel_cutoff_date=str(portfolio["funnel_cutoff_date"]),
        universe_count=len(funnel_candidates) + len(buyer_excluded),
        scoped_count=len(scoped),
        funnel_candidates=funnel_candidates,
        buyer_excluded=buyer_excluded,
        invalid_phone=invalid_phone,
        active_member_suppressed=active_member_suppressed,
        candidates=scoped,
        metadata=metadata,
    )


def _candidate_from_portfolio_row(
    row: dict[str, Any],
    *,
    branch_keys: dict[int, str],
) -> MarketingCampaignV2FunnelCandidate:
    raw_phone = _optional_text(row.get("phone_mx10"))
    normalized_phone = normalize_phone(raw_phone)
    sucursal_id = _optional_int(row.get("sucursal_id"))
    contact_id = _optional_text(row.get("contact_id"))
    source_reference = (
        f"{sucursal_id}:{contact_id}"
        if sucursal_id is not None and contact_id is not None
        else contact_id
    )
    return MarketingCampaignV2FunnelCandidate(
        phone_raw=raw_phone,
        phone_mx10=normalized_phone,
        contact_id=contact_id,
        sucursal_id=sucursal_id,
        sucursal_key=(
            branch_keys.get(sucursal_id)
            if sucursal_id is not None
            else None
        ),
        channel=_optional_text(row.get("channel")),
        source_date=_optional_text(row.get("source_date")),
        origin=_optional_text(row.get("origin")),
        source_reference=source_reference,
    )


def _candidate_in_access_scope(
    candidate: MarketingCampaignV2FunnelCandidate,
    marketing_access: Any,
) -> bool:
    if bool(getattr(marketing_access, "is_global", False)):
        return True
    if candidate.sucursal_id is None:
        return False
    allowed = {
        int(value)
        for value in (getattr(marketing_access, "branch_ids", ()) or ())
    }
    return candidate.sucursal_id in allowed


def _normalize_active_phone_row(row: Any) -> str | None:
    raw = getattr(row, "telefono_raw", None)
    if raw is None:
        try:
            raw = row[0]
        except (TypeError, IndexError, KeyError):
            raw = None
    return normalize_phone(raw)


def _optional_text(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _iso_date(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _iso_datetime(value: Any) -> str | None:
    return value.isoformat() if value is not None else None
