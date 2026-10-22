"""Reporting individual offline/read-only para Campaign V2."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo
from numbers import Real
from typing import Any, Iterable, Mapping

from sqlalchemy import func

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2CommercialResultORM,
    MarketingCampaignV2ProviderCampaignORM,
    MarketingCampaignV2ProviderRecipientObservationORM,
    MarketingCampaignV2ProviderStatsSnapshotORM,
    MarketingCampaignV2RecipientEvidenceORM,
    MarketingCampaignV2RecipientORM,
)
from app.services.marketing_campaign_v2_query_service import (
    MarketingCampaignV2NotFoundError,
    _campaign_visible_to_scope,
    _extract_frozen_scope,
    _load_visible_campaign_orm,
    _normalize_current_scope,
    _normalize_optional_purpose,
    _normalize_optional_source,
    _positive_int,
)
from app.services.marketing_campaign_v2_provider_binding_service import (
    _normalize_provider,
)
from app.services.marketing_campaign_v2_reporting_cost_service import (
    extract_campaign_cost_projection,
)
from app.models.warehouse import (
    TrackBranchAliasORM, TrackBranchCatalogORM,
    VentaTotalSnapshotORM, VentaTotalSnapshotRowORM,
)
from app.services.marketing_phone import normalize_phone
from app.services.marketing_campaign_v2_commercial_attribution_service import (
    direct_attribution_ineligibility_reason,
    required_commercial_sale_kind,
    COMMERCIAL_SALE_KIND_RULE_VERSION,
)
from app.services.marketing_sales_funnel_service import _is_valid_status, _normalize_text
from app.services.contact_center_service import (
    _is_membership_purchase_row,
    _parse_venta_total_row_local_datetime,
)


_UNKNOWN_DIMENSION = "UNKNOWN"
_SUCCESSFUL = "SUCCESSFUL"
_FAILED = "FAILED"
_SENT = "SENT"
_DELIVERED = "DELIVERED"
_VIEWED = "VIEWED"

_SNAPSHOT_WITH = "WITH_SNAPSHOT"
_SNAPSHOT_WITHOUT = "WITHOUT_SNAPSHOT"
_SNAPSHOT_STATUSES = frozenset({_SNAPSHOT_WITH, _SNAPSHOT_WITHOUT})


class MarketingCampaignV2ReportingValidationError(ValueError):
    """Filtros inválidos del reporting Campaign V2."""




def build_campaign_v2_consolidated_report(
    *,
    allowed_sucursal_keys: Iterable[str] | None,
    filters: Mapping[str, Any] | None = None,
    session=None,
) -> dict[str, Any]:
    """Consolida campañas visibles desde evidencia persistida, sin N+1."""
    active_session = session if session is not None else db.session
    normalized_scope = _normalize_current_scope(allowed_sucursal_keys)
    normalized_filters = _normalize_consolidated_filters(filters)

    with active_session.no_autoflush:
        campaign_query = active_session.query(MarketingCampaignV2ORM)
        if normalized_filters["purpose"] is not None:
            campaign_query = campaign_query.filter(
                MarketingCampaignV2ORM.purpose
                == normalized_filters["purpose"]
            )
        if normalized_filters["source"] is not None:
            campaign_query = campaign_query.filter(
                MarketingCampaignV2ORM.source
                == normalized_filters["source"]
            )
        if normalized_filters["provider"] is not None:
            campaign_query = campaign_query.filter(
                MarketingCampaignV2ORM.provider
                == normalized_filters["provider"]
            )

        campaigns = [
            campaign
            for campaign in campaign_query.order_by(
                MarketingCampaignV2ORM.id.asc()
            ).all()
            if _campaign_visible_to_scope(campaign, normalized_scope)
        ]
        campaign_ids = [int(campaign.id) for campaign in campaigns]

        latest_snapshots = _load_latest_snapshots_bulk(
            campaign_ids=campaign_ids,
            session=active_session,
        )
        latest_by_campaign = {
            int(snapshot.campaign_v2_id): snapshot
            for snapshot in latest_snapshots
        }

        selected_campaigns = [
            campaign
            for campaign in campaigns
            if _campaign_matches_snapshot_filters(
                campaign=campaign,
                latest_snapshot=latest_by_campaign.get(int(campaign.id)),
                filters=normalized_filters,
            )
        ]
        selected_ids = [int(campaign.id) for campaign in selected_campaigns]
        selected_id_set = set(selected_ids)
        latest_by_campaign = {
            campaign_id: snapshot
            for campaign_id, snapshot in latest_by_campaign.items()
            if campaign_id in selected_id_set
        }

        recipients = []
        if selected_ids:
            recipients = (
                active_session.query(MarketingCampaignV2RecipientORM)
                .filter(
                    MarketingCampaignV2RecipientORM.campaign_id.in_(
                        selected_ids
                    )
                )
                .order_by(
                    MarketingCampaignV2RecipientORM.campaign_id.asc(),
                    MarketingCampaignV2RecipientORM.id.asc(),
                )
                .all()
            )
        recipient_ids = [int(row.id) for row in recipients]

        evidence_rows = []
        if recipient_ids:
            evidence_rows = (
                active_session.query(MarketingCampaignV2RecipientEvidenceORM)
                .filter(
                    MarketingCampaignV2RecipientEvidenceORM.recipient_id.in_(
                        recipient_ids
                    )
                )
                .order_by(
                    MarketingCampaignV2RecipientEvidenceORM.recipient_id.asc(),
                    MarketingCampaignV2RecipientEvidenceORM.evidence_order.asc(),
                    MarketingCampaignV2RecipientEvidenceORM.id.asc(),
                )
                .all()
            )

        latest_snapshot_ids = [
            int(snapshot.id)
            for snapshot in latest_by_campaign.values()
        ]
        observations = []
        if latest_snapshot_ids:
            observations = (
                active_session.query(
                    MarketingCampaignV2ProviderRecipientObservationORM
                )
                .filter(
                    MarketingCampaignV2ProviderRecipientObservationORM.snapshot_id.in_(
                        latest_snapshot_ids
                    )
                )
                .order_by(
                    MarketingCampaignV2ProviderRecipientObservationORM.snapshot_id.asc(),
                    MarketingCampaignV2ProviderRecipientObservationORM.id.asc(),
                )
                .all()
            )

    recipients_by_campaign: dict[int, list[Any]] = defaultdict(list)
    for recipient in recipients:
        recipients_by_campaign[int(recipient.campaign_id)].append(recipient)

    evidence_by_recipient: dict[int, list[Any]] = defaultdict(list)
    for evidence in evidence_rows:
        evidence_by_recipient[int(evidence.recipient_id)].append(evidence)

    observations_by_snapshot: dict[int, list[Any]] = defaultdict(list)
    for observation in observations:
        observations_by_snapshot[int(observation.snapshot_id)].append(
            observation
        )

    campaign_rows = []
    campaign_contexts = []
    for campaign in selected_campaigns:
        campaign_id = int(campaign.id)
        snapshot = latest_by_campaign.get(campaign_id)
        campaign_recipients = recipients_by_campaign.get(campaign_id, [])
        latest_observations = (
            observations_by_snapshot.get(int(snapshot.id), [])
            if snapshot is not None
            else []
        )
        row = _build_compact_campaign_report_row(
            campaign=campaign,
            recipients=campaign_recipients,
            snapshot=snapshot,
            observations=latest_observations,
        )
        campaign_rows.append(row)
        campaign_contexts.append(
            (
                campaign,
                campaign_recipients,
                snapshot,
                latest_observations,
            )
        )

    campaign_rows.sort(key=_campaign_row_sort_key)
    summary = _consolidated_summary(campaign_rows)
    breakdowns = _consolidated_breakdowns(
        campaign_contexts=campaign_contexts,
        evidence_by_recipient=evidence_by_recipient,
    )

    return {
        "filters": _serialize_consolidated_filters(normalized_filters),
        "summary": summary,
        "campaigns": campaign_rows,
        "breakdowns": breakdowns,
    }


def build_campaign_v2_reporting_export_dataset(
    *,
    allowed_sucursal_keys: Iterable[str] | None,
    filters: Mapping[str, Any] | None = None,
    session=None,
) -> dict[str, Any]:
    """Extiende el consolidado M28 con evolución histórica bulk para XLSX."""
    active_session = session if session is not None else db.session
    normalized_scope = _normalize_current_scope(allowed_sucursal_keys)
    report = build_campaign_v2_consolidated_report(
        allowed_sucursal_keys=normalized_scope,
        filters=filters,
        session=active_session,
    )
    selected_campaigns = {
        int(row["campaign"]["id"]): row["campaign"]["name"]
        for row in report["campaigns"]
    }
    selected_ids = sorted(selected_campaigns)

    snapshots = []
    observations = []
    if selected_ids:
        with active_session.no_autoflush:
            snapshots = (
                active_session.query(
                    MarketingCampaignV2ProviderStatsSnapshotORM
                )
                .filter(
                    MarketingCampaignV2ProviderStatsSnapshotORM.campaign_v2_id.in_(
                        selected_ids
                    )
                )
                .order_by(
                    MarketingCampaignV2ProviderStatsSnapshotORM.campaign_v2_id.asc(),
                    MarketingCampaignV2ProviderStatsSnapshotORM.fetched_at.asc(),
                    MarketingCampaignV2ProviderStatsSnapshotORM.id.asc(),
                )
                .all()
            )
            snapshot_ids = [int(row.id) for row in snapshots]
            if snapshot_ids:
                observations = (
                    active_session.query(
                        MarketingCampaignV2ProviderRecipientObservationORM
                    )
                    .filter(
                        MarketingCampaignV2ProviderRecipientObservationORM.snapshot_id.in_(
                            snapshot_ids
                        )
                    )
                    .order_by(
                        MarketingCampaignV2ProviderRecipientObservationORM.snapshot_id.asc(),
                        MarketingCampaignV2ProviderRecipientObservationORM.id.asc(),
                    )
                    .all()
                )

    observations_by_snapshot: dict[int, list[Any]] = defaultdict(list)
    for observation in observations:
        observations_by_snapshot[int(observation.snapshot_id)].append(
            observation
        )

    evolution = [
        {
            "campaign_id": int(snapshot.campaign_v2_id),
            "campaign_name": selected_campaigns[int(snapshot.campaign_v2_id)],
            **_evolution_point(
                snapshot=snapshot,
                observations=observations_by_snapshot.get(
                    int(snapshot.id),
                    [],
                ),
            ),
        }
        for snapshot in snapshots
    ]
    return {
        "report_type": "CONSOLIDATED",
        "report": report,
        "evolution": evolution,
        "scope": {
            "is_global": normalized_scope is None,
            "allowed_sucursal_keys": (
                None
                if normalized_scope is None
                else list(normalized_scope)
            ),
        },
    }


def _load_latest_snapshots_bulk(
    *,
    campaign_ids: list[int],
    session,
) -> list[Any]:
    if not campaign_ids:
        return []
    ranked = (
        session.query(
            MarketingCampaignV2ProviderStatsSnapshotORM.id.label(
                "snapshot_id"
            ),
            func.row_number()
            .over(
                partition_by=(
                    MarketingCampaignV2ProviderStatsSnapshotORM.campaign_v2_id
                ),
                order_by=(
                    MarketingCampaignV2ProviderStatsSnapshotORM.fetched_at.desc(),
                    MarketingCampaignV2ProviderStatsSnapshotORM.id.desc(),
                ),
            )
            .label("snapshot_rank"),
        )
        .filter(
            MarketingCampaignV2ProviderStatsSnapshotORM.campaign_v2_id.in_(
                campaign_ids
            )
        )
        .subquery()
    )
    return (
        session.query(MarketingCampaignV2ProviderStatsSnapshotORM)
        .join(
            ranked,
            MarketingCampaignV2ProviderStatsSnapshotORM.id
            == ranked.c.snapshot_id,
        )
        .filter(ranked.c.snapshot_rank == 1)
        .all()
    )


def _build_compact_campaign_report_row(
    *,
    campaign: Any,
    recipients: list[Any],
    snapshot: Any | None,
    observations: list[Any],
) -> dict[str, Any]:
    total_recipients = len(recipients)
    normalized = _normalized_metrics(observations)
    coverage = _coverage(
        snapshot=snapshot,
        total_recipients=total_recipients,
    )
    interaction_detail = _interactions(
        snapshot=snapshot,
        observations=observations,
    )
    analytics = snapshot.analytics_json if snapshot is not None else None
    return {
        "campaign": {
            "id": int(campaign.id),
            "name": campaign.name,
            "purpose": campaign.purpose,
            "source": campaign.source,
            "provider": campaign.provider,
            "provider_campaign_id": campaign.provider_campaign_id,
            "frozen_at": _iso_datetime(campaign.frozen_at),
        },
        "observation": {
            "snapshot_id": int(snapshot.id) if snapshot is not None else None,
            "latest_observed_at": (
                _iso_datetime(snapshot.fetched_at)
                if snapshot is not None
                else None
            ),
            "analytics_status": (
                snapshot.analytics_status
                if snapshot is not None
                else None
            ),
        },
        "audience": {
            "total_recipients": total_recipients,
        },
        "normalized": normalized,
        "rates": _rates(
            total_recipients=total_recipients,
            normalized=normalized,
        ),
        "coverage": coverage,
        "provider_raw": _provider_raw(snapshot),
        "interactions": {
            "unique_button_recipients": interaction_detail[
                "unique_button_recipients"
            ],
            "responders_aggregate": _analytics_number(
                analytics,
                "responders",
            ),
            "free_text_aggregate": _analytics_number(
                analytics,
                "interactions",
                "freeText",
            ),
        },
        "cost": extract_campaign_cost_projection(analytics),
    }


def _consolidated_summary(
    campaign_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    total_recipients = sum(
        int(row["audience"]["total_recipients"])
        for row in campaign_rows
    )
    normalized = _sum_normalized(
        row["normalized"] for row in campaign_rows
    )
    campaigns_with_snapshot = sum(
        1
        for row in campaign_rows
        if row["observation"]["snapshot_id"] is not None
    )
    coverage = {
        "matched_recipient_count": sum(
            int(row["coverage"]["matched_recipient_count"])
            for row in campaign_rows
        ),
        "unmatched_provider_count": sum(
            int(row["coverage"]["unmatched_provider_count"])
            for row in campaign_rows
        ),
        "frozen_recipient_without_provider_status_count": sum(
            int(
                row["coverage"][
                    "frozen_recipient_without_provider_status_count"
                ]
            )
            for row in campaign_rows
        ),
    }
    coverage["status_coverage_rate"] = _safe_rate(
        int(coverage["matched_recipient_count"]),
        total_recipients,
    )

    provider_raw = {
        key: sum(
            int(row["provider_raw"][key])
            for row in campaign_rows
            if row["provider_raw"] is not None
        )
        for key in (
            "successful",
            "failed",
            "sent",
            "delivered",
            "viewed",
            "answered",
            "interaction_groups",
            "interaction_items",
        )
    }
    responders_values = [
        row["interactions"]["responders_aggregate"]
        for row in campaign_rows
        if row["interactions"]["responders_aggregate"] is not None
    ]
    free_text_values = [
        row["interactions"]["free_text_aggregate"]
        for row in campaign_rows
        if row["interactions"]["free_text_aggregate"] is not None
    ]

    return {
        "campaign_count": len(campaign_rows),
        "campaigns_with_snapshot": campaigns_with_snapshot,
        "campaigns_without_snapshot": (
            len(campaign_rows) - campaigns_with_snapshot
        ),
        "total_recipients": total_recipients,
        "normalized": normalized,
        "rates": _rates(
            total_recipients=total_recipients,
            normalized=normalized,
        ),
        "coverage": coverage,
        "provider_raw": provider_raw,
        "interactions": {
            "button_interaction_recipient_exposures": sum(
                int(row["interactions"]["unique_button_recipients"])
                for row in campaign_rows
            ),
            "responders_aggregate": (
                sum(responders_values)
                if responders_values
                else None
            ),
            "responders_campaigns_with_value": len(responders_values),
            "free_text_aggregate": (
                sum(free_text_values)
                if free_text_values
                else None
            ),
            "free_text_campaigns_with_value": len(free_text_values),
        },
        "cost": {
            "status": "unavailable",
            "currency": None,
            "total": None,
        },
    }


def _consolidated_breakdowns(
    *,
    campaign_contexts: list[tuple[Any, list[Any], Any | None, list[Any]]],
    evidence_by_recipient: Mapping[int, list[Any]],
) -> dict[str, Any]:
    branch_buckets: dict[str, dict[str, Any]] = {}
    family_buckets: dict[str, dict[str, Any]] = {}

    for _campaign, recipients, snapshot, observations in campaign_contexts:
        observations_by_recipient = {
            int(row.campaign_recipient_id): row
            for row in observations
            if row.campaign_recipient_id is not None
        }
        matched_recipient_ids = set(observations_by_recipient)

        for recipient in recipients:
            recipient_id = int(recipient.id)
            evidence = evidence_by_recipient.get(recipient_id, [])
            branch = _recipient_dimension(
                getattr(recipient, "sucursal", None),
                [
                    getattr(row, "sucursal_key", None)
                    or getattr(row, "sucursal", None)
                    for row in evidence
                ],
            )
            family = _recipient_dimension(
                getattr(recipient, "audience_family", None),
                [
                    getattr(row, "audience_family", None)
                    for row in evidence
                ],
            )
            observation = observations_by_recipient.get(recipient_id)
            for bucket_map, value in (
                (branch_buckets, branch),
                (family_buckets, family),
            ):
                bucket = bucket_map.setdefault(
                    value,
                    _empty_dimension_bucket(value),
                )
                _accumulate_dimension_recipient(
                    bucket=bucket,
                    recipient_id=recipient_id,
                    observation=observation,
                    matched=recipient_id in matched_recipient_ids,
                )

    return {
        "branches": _finalize_dimension_buckets(branch_buckets),
        "audience_families": _finalize_dimension_buckets(family_buckets),
    }


def _empty_dimension_bucket(value: str) -> dict[str, Any]:
    return {
        "value": value,
        "recipient_exposures": 0,
        "successful": 0,
        "failed": 0,
        "sent": 0,
        "delivered": 0,
        "viewed": 0,
        "reach_count": 0,
        "button_interaction_recipient_exposures": 0,
        "_matched": 0,
    }


def _accumulate_dimension_recipient(
    *,
    bucket: dict[str, Any],
    recipient_id: int,
    observation: Any | None,
    matched: bool,
) -> None:
    del recipient_id
    bucket["recipient_exposures"] += 1
    if matched:
        bucket["_matched"] += 1
    if observation is None:
        return

    outcome = str(getattr(observation, "outcome", "") or "").upper()
    delivery = str(
        getattr(observation, "delivery_bucket", "") or ""
    ).upper()
    if outcome == _FAILED:
        bucket["failed"] += 1
    elif outcome == _SUCCESSFUL:
        bucket["successful"] += 1
        if delivery == _SENT:
            bucket["sent"] += 1
        elif delivery == _DELIVERED:
            bucket["delivered"] += 1
            bucket["reach_count"] += 1
        elif delivery == _VIEWED:
            bucket["viewed"] += 1
            bucket["reach_count"] += 1

    if _string_labels(
        getattr(observation, "button_labels_json", None)
    ):
        bucket["button_interaction_recipient_exposures"] += 1


def _finalize_dimension_buckets(
    buckets: Mapping[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for value in sorted(buckets):
        source = buckets[value]
        total = int(source["recipient_exposures"])
        normalized = {
            key: int(source[key])
            for key in (
                "successful",
                "failed",
                "sent",
                "delivered",
                "viewed",
                "reach_count",
            )
        }
        matched = int(source["_matched"])
        rows.append(
            {
                "value": value,
                "recipient_exposures": total,
                **normalized,
                "button_interaction_recipient_exposures": int(
                    source["button_interaction_recipient_exposures"]
                ),
                "rates": _rates(
                    total_recipients=total,
                    normalized=normalized,
                ),
                "coverage": {
                    "matched_recipient_count": matched,
                    "frozen_recipient_without_provider_status_count": (
                        total - matched
                    ),
                    "status_coverage_rate": _safe_rate(
                        matched,
                        total,
                    ),
                },
            }
        )
    return rows


def _sum_normalized(
    rows: Iterable[Mapping[str, int]],
) -> dict[str, int]:
    materialized = list(rows)
    keys = (
        "successful",
        "failed",
        "sent",
        "delivered",
        "viewed",
        "reach_count",
    )
    return {
        key: sum(int(row[key]) for row in materialized)
        for key in keys
    }


def _campaign_row_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    campaign_id = int(row["campaign"]["id"])
    observed = row["observation"]["latest_observed_at"]
    if observed is not None:
        return (
            0,
            -_timestamp_sort_value(observed),
            -campaign_id,
        )
    frozen_at = row["campaign"]["frozen_at"]
    return (
        1,
        -_timestamp_sort_value(frozen_at),
        -campaign_id,
    )


def _timestamp_sort_value(value: Any) -> float:
    if not isinstance(value, str) or not value:
        return float("-inf")
    return datetime.fromisoformat(value).timestamp()


def _normalize_consolidated_filters(
    filters: Mapping[str, Any] | None,
) -> dict[str, Any]:
    raw = dict(filters or {})
    allowed = {
        "observed_from",
        "observed_to",
        "purpose",
        "source",
        "provider",
        "snapshot_status",
    }
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise MarketingCampaignV2ReportingValidationError(
            "Filtros no permitidos: " + ", ".join(unknown) + "."
        )

    observed_from = _normalize_optional_observed_at(
        raw.get("observed_from"),
        field_name="observed_from",
    )
    observed_to = _normalize_optional_observed_at(
        raw.get("observed_to"),
        field_name="observed_to",
    )
    if (
        observed_from is not None
        and observed_to is not None
        and observed_from > observed_to
    ):
        raise MarketingCampaignV2ReportingValidationError(
            "observed_from no puede ser posterior a observed_to."
        )

    try:
        purpose = _normalize_optional_purpose(raw.get("purpose"))
        source = _normalize_optional_source(raw.get("source"))
    except ValueError as exc:
        raise MarketingCampaignV2ReportingValidationError(str(exc)) from exc

    provider = _normalize_optional_provider(raw.get("provider"))
    snapshot_status = _normalize_snapshot_status(
        raw.get("snapshot_status")
    )
    return {
        "observed_from": observed_from,
        "observed_to": observed_to,
        "purpose": purpose,
        "source": source,
        "provider": provider,
        "snapshot_status": snapshot_status,
    }


def _normalize_optional_provider(value: Any) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return _normalize_provider(value)
    except ValueError as exc:
        raise MarketingCampaignV2ReportingValidationError(str(exc)) from exc


def _normalize_snapshot_status(value: Any) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    normalized = str(value).strip().upper()
    if normalized not in _SNAPSHOT_STATUSES:
        raise MarketingCampaignV2ReportingValidationError(
            "snapshot_status debe ser WITH_SNAPSHOT o WITHOUT_SNAPSHOT."
        )
    return normalized


def _normalize_optional_observed_at(
    value: Any,
    *,
    field_name: str,
) -> datetime | None:
    if value is None:
        return None
    parsed: datetime
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise MarketingCampaignV2ReportingValidationError(
                f"{field_name} debe ser fecha ISO con zona horaria."
            ) from exc
    else:
        raise MarketingCampaignV2ReportingValidationError(
            f"{field_name} debe ser fecha ISO con zona horaria."
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MarketingCampaignV2ReportingValidationError(
            f"{field_name} debe incluir zona horaria."
        )
    return parsed.astimezone(timezone.utc)


def _campaign_matches_snapshot_filters(
    *,
    campaign: Any,
    latest_snapshot: Any | None,
    filters: Mapping[str, Any],
) -> bool:
    status = filters["snapshot_status"]
    if status == _SNAPSHOT_WITH and latest_snapshot is None:
        return False
    if status == _SNAPSHOT_WITHOUT and latest_snapshot is not None:
        return False

    observed_from = filters["observed_from"]
    observed_to = filters["observed_to"]
    if observed_from is None and observed_to is None:
        return True
    if latest_snapshot is None:
        return False

    observed_at = _as_utc_datetime(latest_snapshot.fetched_at)
    if observed_from is not None and observed_at < observed_from:
        return False
    if observed_to is not None and observed_at > observed_to:
        return False
    return True


def _as_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _serialize_consolidated_filters(
    filters: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "observed_from": _iso_datetime(filters["observed_from"]),
        "observed_to": _iso_datetime(filters["observed_to"]),
        "purpose": filters["purpose"],
        "source": filters["source"],
        "provider": filters["provider"],
        "snapshot_status": filters["snapshot_status"],
    }


def build_campaign_v2_individual_report(
    *,
    campaign_id: Any,
    allowed_sucursal_keys: Iterable[str] | None,
    session=None,
) -> dict[str, Any]:
    """Construye un reporte reproducible sólo desde persistencia Suite."""
    active_session = session if session is not None else db.session
    normalized_id = _positive_int(
        campaign_id,
        field_name="campaign_id",
        maximum=None,
    )
    current_scope = _normalize_current_scope(allowed_sucursal_keys)

    with active_session.no_autoflush:
        campaign = _load_visible_campaign_orm(
            campaign_id=normalized_id,
            scope=current_scope,
            session=active_session,
        )

        recipients = (
            active_session.query(MarketingCampaignV2RecipientORM)
            .filter(
                MarketingCampaignV2RecipientORM.campaign_id
                == normalized_id
            )
            .order_by(MarketingCampaignV2RecipientORM.id.asc())
            .all()
        )
        recipient_ids = [int(row.id) for row in recipients]

        evidence_rows = []
        if recipient_ids:
            evidence_rows = (
                active_session.query(MarketingCampaignV2RecipientEvidenceORM)
                .filter(
                    MarketingCampaignV2RecipientEvidenceORM.recipient_id.in_(
                        recipient_ids
                    )
                )
                .order_by(
                    MarketingCampaignV2RecipientEvidenceORM.recipient_id.asc(),
                    MarketingCampaignV2RecipientEvidenceORM.evidence_order.asc(),
                    MarketingCampaignV2RecipientEvidenceORM.id.asc(),
                )
                .all()
            )

        snapshots = (
            active_session.query(MarketingCampaignV2ProviderStatsSnapshotORM)
            .filter(
                MarketingCampaignV2ProviderStatsSnapshotORM.campaign_v2_id
                == normalized_id
            )
            .order_by(
                MarketingCampaignV2ProviderStatsSnapshotORM.fetched_at.asc(),
                MarketingCampaignV2ProviderStatsSnapshotORM.id.asc(),
            )
            .all()
        )
        snapshot_ids = [int(row.id) for row in snapshots]

        observation_rows = []
        if snapshot_ids:
            observation_rows = (
                active_session.query(
                    MarketingCampaignV2ProviderRecipientObservationORM
                )
                .filter(
                    MarketingCampaignV2ProviderRecipientObservationORM.snapshot_id.in_(
                        snapshot_ids
                    )
                )
                .order_by(
                    MarketingCampaignV2ProviderRecipientObservationORM.snapshot_id.asc(),
                    MarketingCampaignV2ProviderRecipientObservationORM.id.asc(),
                )
                .all()
            )

    observations_by_snapshot: dict[int, list[Any]] = defaultdict(list)
    for row in observation_rows:
        observations_by_snapshot[int(row.snapshot_id)].append(row)

    latest_snapshot = snapshots[-1] if snapshots else None
    latest_observations = (
        observations_by_snapshot[int(latest_snapshot.id)]
        if latest_snapshot is not None
        else []
    )
    total_recipients = len(recipients)
    normalized = _normalized_metrics(latest_observations)
    rates = _rates(
        total_recipients=total_recipients,
        normalized=normalized,
    )
    coverage = _coverage(
        snapshot=latest_snapshot,
        total_recipients=total_recipients,
    )
    interactions = _interactions(
        snapshot=latest_snapshot,
        observations=latest_observations,
    )
    analytics = (
        latest_snapshot.analytics_json
        if latest_snapshot is not None
        else None
    )

    return {
        "campaign": {
            "id": int(campaign.id),
            "name": campaign.name,
            "purpose": campaign.purpose,
            "source": campaign.source,
            "provider": campaign.provider,
            "provider_campaign_id": campaign.provider_campaign_id,
            "frozen_at": _iso_datetime(campaign.frozen_at),
        },
        "observation": {
            "snapshot_id": (
                int(latest_snapshot.id)
                if latest_snapshot is not None
                else None
            ),
            "latest_observed_at": (
                _iso_datetime(latest_snapshot.fetched_at)
                if latest_snapshot is not None
                else None
            ),
            "analytics_status": (
                latest_snapshot.analytics_status
                if latest_snapshot is not None
                else None
            ),
            "fingerprint": (
                latest_snapshot.fingerprint
                if latest_snapshot is not None
                else None
            ),
        },
        "audience": {
            "total_recipients": total_recipients,
        },
        "normalized": normalized,
        "rates": rates,
        "coverage": coverage,
        "provider_raw": _provider_raw(latest_snapshot),
        "interactions": {
            **interactions,
            "responders_aggregate": _analytics_number(
                analytics,
                "responders",
            ),
            "free_text_aggregate": _analytics_number(
                analytics,
                "interactions",
                "freeText",
            ),
        },
        "cost": extract_campaign_cost_projection(analytics),
        "dimensions": _dimensions(
            campaign=campaign,
            recipients=recipients,
            evidence_rows=evidence_rows,
        ),
        "evolution": [
            _evolution_point(
                snapshot=snapshot,
                observations=observations_by_snapshot[int(snapshot.id)],
            )
            for snapshot in snapshots
        ],
    }


def _normalized_metrics(observations: Iterable[Any]) -> dict[str, int]:
    successful: set[int] = set()
    failed: set[int] = set()
    sent: set[int] = set()
    delivered: set[int] = set()
    viewed: set[int] = set()

    for row in observations:
        recipient_id = getattr(row, "campaign_recipient_id", None)
        if recipient_id is None:
            continue
        recipient_id = int(recipient_id)
        outcome = str(getattr(row, "outcome", "") or "").upper()
        delivery = str(
            getattr(row, "delivery_bucket", "") or ""
        ).upper()

        if outcome == _FAILED:
            failed.add(recipient_id)
            continue
        if outcome != _SUCCESSFUL:
            continue

        successful.add(recipient_id)
        if delivery == _SENT:
            sent.add(recipient_id)
        elif delivery == _DELIVERED:
            delivered.add(recipient_id)
        elif delivery == _VIEWED:
            viewed.add(recipient_id)

    reach = delivered | viewed
    return {
        "successful": len(successful),
        "failed": len(failed),
        "sent": len(sent),
        "delivered": len(delivered),
        "viewed": len(viewed),
        "reach_count": len(reach),
    }


def _rates(
    *,
    total_recipients: int,
    normalized: Mapping[str, int],
) -> dict[str, float | None]:
    reach_count = int(normalized["reach_count"])
    return {
        "successful_rate": _safe_rate(
            int(normalized["successful"]),
            total_recipients,
        ),
        "reach_rate": _safe_rate(
            reach_count,
            total_recipients,
        ),
        "read_rate": _safe_rate(
            int(normalized["viewed"]),
            reach_count,
        ),
        "failure_rate": _safe_rate(
            int(normalized["failed"]),
            total_recipients,
        ),
    }


def _coverage(
    *,
    snapshot: Any | None,
    total_recipients: int,
) -> dict[str, int | float | None]:
    if snapshot is None:
        matched = 0
        unmatched = 0
        without_status = total_recipients
    else:
        matched = int(snapshot.matched_recipient_count)
        unmatched = int(snapshot.unmatched_provider_count)
        without_status = int(
            snapshot.frozen_recipient_without_provider_status_count
        )
    return {
        "matched_recipient_count": matched,
        "unmatched_provider_count": unmatched,
        "frozen_recipient_without_provider_status_count": without_status,
        "status_coverage_rate": _safe_rate(
            matched,
            total_recipients,
        ),
    }


def _provider_raw(snapshot: Any | None) -> dict[str, int] | None:
    if snapshot is None:
        return None
    return {
        "successful": int(snapshot.raw_successful),
        "failed": int(snapshot.raw_failed),
        "sent": int(snapshot.raw_sent),
        "delivered": int(snapshot.raw_delivered),
        "viewed": int(snapshot.raw_viewed),
        "answered": int(snapshot.raw_answered),
        "interaction_groups": int(snapshot.raw_interaction_groups),
        "interaction_items": int(snapshot.raw_interaction_items),
    }


def _interactions(
    *,
    snapshot: Any | None,
    observations: Iterable[Any],
) -> dict[str, Any]:
    recipients_by_label: dict[str, set[int]] = defaultdict(set)
    unique_button_recipients: set[int] = set()

    for row in observations:
        recipient_id = getattr(row, "campaign_recipient_id", None)
        if recipient_id is None:
            continue
        labels = _string_labels(
            getattr(row, "button_labels_json", None)
        )
        if not labels:
            continue
        recipient_id = int(recipient_id)
        unique_button_recipients.add(recipient_id)
        for label in labels:
            recipients_by_label[label].add(recipient_id)

    raw_items_by_label: dict[str, int] = {}
    if snapshot is not None:
        payload = snapshot.button_interactions_json
        if isinstance(payload, list):
            for item in payload:
                if not isinstance(item, Mapping):
                    continue
                label = _clean_string(item.get("label"))
                raw_item_count = item.get("raw_item_count")
                if (
                    label is not None
                    and _is_nonnegative_int(raw_item_count)
                ):
                    raw_items_by_label[label] = (
                        raw_items_by_label.get(label, 0)
                        + int(raw_item_count)
                    )

    labels = sorted(
        set(recipients_by_label) | set(raw_items_by_label)
    )
    return {
        "unique_button_recipients": len(unique_button_recipients),
        "button_groups": [
            {
                "label": label,
                "unique_recipient_count": len(
                    recipients_by_label.get(label, set())
                ),
                "raw_item_count": raw_items_by_label.get(label),
            }
            for label in labels
        ],
    }


def _dimensions(
    *,
    campaign: Any,
    recipients: list[Any],
    evidence_rows: list[Any],
) -> dict[str, Any]:
    evidence_by_recipient: dict[int, list[Any]] = defaultdict(list)
    for row in evidence_rows:
        evidence_by_recipient[int(row.recipient_id)].append(row)

    branch_counts: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()

    for recipient in recipients:
        evidence = evidence_by_recipient.get(int(recipient.id), [])
        branch_counts[
            _recipient_dimension(
                getattr(recipient, "sucursal", None),
                [
                    getattr(row, "sucursal_key", None)
                    or getattr(row, "sucursal", None)
                    for row in evidence
                ],
            )
        ] += 1
        family_counts[
            _recipient_dimension(
                getattr(recipient, "audience_family", None),
                [
                    getattr(row, "audience_family", None)
                    for row in evidence
                ],
            )
        ] += 1

    frozen_scope = _extract_frozen_scope(campaign)
    return {
        "scope": {
            "is_global": frozen_scope is None,
            "allowed_sucursal_keys": (
                None
                if frozen_scope is None
                else list(frozen_scope)
            ),
        },
        "branches": _dimension_rows(branch_counts),
        "audience_families": _dimension_rows(family_counts),
    }


def _recipient_dimension(
    primary: Any,
    evidence_values: Iterable[Any],
) -> str:
    primary_value = _clean_string(primary)
    if primary_value is not None:
        return primary_value

    values = {
        value
        for value in (
            _clean_string(raw)
            for raw in evidence_values
        )
        if value is not None
    }
    if len(values) == 1:
        return next(iter(values))
    return _UNKNOWN_DIMENSION


def _dimension_rows(counts: Counter[str]) -> list[dict[str, Any]]:
    return [
        {
            "value": value,
            "recipient_count": int(count),
        }
        for value, count in sorted(counts.items())
    ]


def _evolution_point(
    *,
    snapshot: Any,
    observations: Iterable[Any],
) -> dict[str, Any]:
    return {
        "snapshot_id": int(snapshot.id),
        "observed_at": _iso_datetime(snapshot.fetched_at),
        "normalized": _normalized_metrics(observations),
        "provider_raw": {
            "successful": int(snapshot.raw_successful),
            "failed": int(snapshot.raw_failed),
            "sent": int(snapshot.raw_sent),
            "delivered": int(snapshot.raw_delivered),
            "viewed": int(snapshot.raw_viewed),
        },
        "coverage": {
            "matched_recipient_count": int(
                snapshot.matched_recipient_count
            ),
            "unmatched_provider_count": int(
                snapshot.unmatched_provider_count
            ),
        },
    }


def _analytics_number(
    analytics: Any,
    *path: str,
) -> int | float | None:
    current = analytics
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    if isinstance(current, bool) or not isinstance(current, Real):
        return None
    return current


def _safe_rate(
    numerator: int,
    denominator: int,
) -> float | None:
    if denominator == 0:
        return None
    return float(numerator) / float(denominator)


def _string_labels(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(
        sorted(
            {
                label
                for label in (
                    _clean_string(item)
                    for item in value
                )
                if label is not None
            }
        )
    )


def _clean_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    return normalized or None


def _is_nonnegative_int(value: Any) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
    )


def _iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = value
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=timezone.utc)
    return normalized.astimezone(timezone.utc).isoformat()

# Commercial correlation, deliberately separate from provider delivery reporting.
# A successful submitted message + a later valid membership sale counts as
# commercially attributable. This does NOT establish causal attribution.
_COMMERCIAL_TZ = ZoneInfo("America/Tijuana")
_NON_MEMBERSHIP_PREFIXES = (
    "PASE ", "PENALIZACION", "RECARGO", "INSCRIPCION",
)


def _commercial_month_end_exclusive(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def _summarize_campaign_v2_membership_movements(
    *,
    rows: Iterable[Any],
    sent_local: datetime,
    successful_phones: set[str],
    branch_id: int,
    alias_map: Mapping[str, int],
    required_sale_kind: str,
) -> dict[str, Any]:
    """Count only purchases whose Gasca kind matches the campaign objective."""
    if required_sale_kind not in {"NUEVO", "REACTIVACION"}:
        raise MarketingCampaignV2ReportingValidationError(
            "Tipo de venta atribuible inválido."
        )
    grouped: dict[tuple[str, str], Decimal] = {}
    for row in rows:
        phone = normalize_phone(row.telefono)
        if phone not in successful_phones:
            continue
        if alias_map.get(_normalize_text(row.sucursal)) != branch_id:
            continue
        if not _is_valid_status(row.estatus):
            continue
        if _normalize_text(getattr(row, "nuevo", None)) != required_sale_kind:
            continue
        description = _normalize_text(row.descripcion)
        if description.startswith(_NON_MEMBERSHIP_PREFIXES):
            continue
        if not _is_membership_purchase_row(row):
            continue
        occurred_at = _parse_venta_total_row_local_datetime(row)
        if occurred_at is None or occurred_at <= sent_local:
            continue
        try:
            amount = Decimal(str(row.total))
        except (InvalidOperation, TypeError, ValueError):
            continue
        order_id = str(row.id_orden or "").strip()
        folio = str(row.folio or "").strip()
        transaction_key = (
            f"order:{order_id}" if order_id else
            f"folio:{folio}" if folio else
            f"row:{row.id}"
        )
        key = (phone, transaction_key)
        grouped[key] = grouped.get(key, Decimal("0")) + amount

    paid = {key: amount for key, amount in grouped.items() if amount > 0}
    return {
        "buyers_attributed": len({phone for phone, _ in paid}),
        "transactions_attributed": len(paid),
        "revenue_attributed_mxn": str(
            sum(paid.values(), Decimal("0")).quantize(Decimal("0.01"))
        ),
    }


def _summarize_campaign_v2_multichild_membership_movements(
    *,
    child_inputs: Iterable[Mapping[str, Any]],
    expected_submitted_child_ids: Iterable[int],
    alias_map: Mapping[str, int],
    required_sale_kind: str,
) -> dict[str, Any]:
    """Combine proven per-child results without adding snapshots as revenue.

    Callers must supply one canonical, cumulative Venta Total cut and one
    provider-success evidence set for every eligible child. This pure function
    deliberately does not fetch either source and MUST NOT mark missing
    evidence as a zero. Children with no successful sends may have zero sales.
    """
    expected_ids = tuple(expected_submitted_child_ids)
    if (
        not expected_ids
        or any(type(identifier) is not int or identifier <= 0 for identifier in expected_ids)
        or len(set(expected_ids)) != len(expected_ids)
    ):
        raise MarketingCampaignV2ReportingValidationError(
            "El alcance de children enviados es inválido."
        )
    seen_child_ids: set[int] = set()
    seen_phones: set[str] = set()
    total_buyers = 0
    total_transactions = 0
    total_revenue = Decimal("0")
    children: list[dict[str, Any]] = []

    for entry in child_inputs:
        child_id = int(entry["child_id"])
        if child_id <= 0 or child_id in seen_child_ids:
            raise MarketingCampaignV2ReportingValidationError(
                "Children comerciales duplicados o inválidos."
            )
        seen_child_ids.add(child_id)
        successful_phones = set(entry["successful_phones"])
        if successful_phones & seen_phones:
            raise MarketingCampaignV2ReportingValidationError(
                "Un teléfono exitoso no puede atribuirse a dos children."
            )
        if any(normalize_phone(p) != p for p in successful_phones):
            raise MarketingCampaignV2ReportingValidationError(
                "El teléfono exitoso no tiene identidad MX10 verificable."
            )
        seen_phones.update(successful_phones)

        metrics = _summarize_campaign_v2_membership_movements(
            rows=entry["rows"],
            sent_local=entry["sent_local"],
            successful_phones=successful_phones,
            branch_id=int(entry["branch_id"]),
            alias_map=alias_map,
            required_sale_kind=required_sale_kind,
        )
        total_buyers += metrics["buyers_attributed"]
        total_transactions += metrics["transactions_attributed"]
        total_revenue += Decimal(metrics["revenue_attributed_mxn"])
        children.append({
            "child_id": child_id,
            "successful_recipient_count": len(successful_phones),
            **metrics,
        })

    if seen_child_ids != set(expected_ids):
        raise MarketingCampaignV2ReportingValidationError(
            "Falta evidencia comercial de uno o más children enviados."
        )
    return {
        "successful_recipient_count": len(seen_phones),
        "buyers_attributed": total_buyers,
        "transactions_attributed": total_transactions,
        "revenue_attributed_mxn": str(
            total_revenue.quantize(Decimal("0.01"))
        ),
        "children": sorted(children, key=lambda row: row["child_id"]),
    }


def _materialized_multichild_commercial_payload(
    *,
    record: Any | None,
    children: Iterable[Any],
    campaign: Any,
) -> dict[str, Any] | None:
    """Reject stale/ineligible cached READY without running Gasca queries."""
    if record is None:
        return None
    reason = direct_attribution_ineligibility_reason(
        purpose=getattr(campaign, "purpose", None),
        source=getattr(campaign, "source", None),
    )
    if reason is not None:
        return {
            "campaign_id": int(record.campaign_v2_id),
            "status": "NOT_ATTRIBUTABLE",
            "reason": reason,
            "buyers_attributed": None,
            "transactions_attributed": None,
            "revenue_attributed_mxn": None,
        }
    payload = dict(record.result_json or {})
    status = str(payload.get("status", record.status))
    if status == "READY":
        if payload.get("attribution_rule_version") != COMMERCIAL_SALE_KIND_RULE_VERSION:
            return {
                "campaign_id": int(record.campaign_v2_id),
                "status": "PENDING_RECONCILIATION",
                "buyers_attributed": None,
                "transactions_attributed": None,
                "revenue_attributed_mxn": None,
            }
        submitted_ids = sorted(
            int(child.id) for child in children
            if getattr(child, "status", None) == "SUBMITTED"
        )
        actual = sorted(payload.get("submitted_child_ids") or [])
        if not submitted_ids or actual != submitted_ids or any(
            child.status not in {"SUBMITTED", "PREPARED", "READY", "BLOCKED", "HELD"}
            for child in children
        ):
            return {
                "campaign_id": int(record.campaign_v2_id),
                "status": "PENDING_RECONCILIATION",
                "buyers_attributed": None,
                "transactions_attributed": None,
                "revenue_attributed_mxn": None,
            }
    payload["checked_at_utc"] = _iso_datetime(record.checked_at)
    return payload


def build_campaign_v2_commercial_attribution(
    *,
    campaign_id: Any,
    allowed_sucursal_keys: Iterable[str] | None,
    session=None,
) -> dict[str, Any]:
    """Read-only initial scope: one submitted child, one send-month canonical cut.

    Never interprets a frozen campaign as sent. Provider FAILED recipients
    cannot contribute. Multi-branch campaigns remain explicitly unsupported
    until their per-child recipient-level evidence can be reconciled.
    """
    active_session = session if session is not None else db.session
    normalized_id = _positive_int(campaign_id, field_name="campaign_id", maximum=None)
    scope = _normalize_current_scope(allowed_sucursal_keys)
    with active_session.no_autoflush:
        campaign = _load_visible_campaign_orm(
            campaign_id=normalized_id, scope=scope, session=active_session
        )
        children = (
            active_session.query(MarketingCampaignV2ProviderCampaignORM)
            .filter(MarketingCampaignV2ProviderCampaignORM.campaign_v2_id == normalized_id)
            .all()
        )
        base = {
            "campaign_id": normalized_id,
            "rule": "SUCCESSFUL_PROVIDER_SEND_AND_LATER_MEMBERSHIP_PAYMENT",
            "source": "VENTA_TOTAL_CANONICAL",
            "buyers_attributed": None,
            "transactions_attributed": None,
            "revenue_attributed_mxn": None,
        }
        if len(children) != 1:
            if len(children) >= 2:
                record = active_session.get(
                    MarketingCampaignV2CommercialResultORM, normalized_id
                )
                materialized = _materialized_multichild_commercial_payload(
                    record=record, children=children, campaign=campaign,
                )
                if materialized is not None:
                    return {**base, **materialized}
            return {**base, "status": "UNSUPPORTED_MULTICHILD_OR_UNSENT"}
        child = children[0]
        if child.submitted_at is None or not child.provider_campaign_id:
            return {**base, "status": "NOT_SUBMITTED"}
        reason = direct_attribution_ineligibility_reason(
            purpose=campaign.purpose, source=campaign.source,
        )
        if reason is not None:
            return {**base, "status": "NOT_ATTRIBUTABLE", "reason": reason}
        required_sale_kind = required_commercial_sale_kind(
            purpose=campaign.purpose, source=campaign.source,
        )
        sent = child.submitted_at
        if sent.tzinfo is None:
            sent = sent.replace(tzinfo=timezone.utc)
        sent_local = sent.astimezone(_COMMERCIAL_TZ)

        provider_snapshot = (
            active_session.query(MarketingCampaignV2ProviderStatsSnapshotORM)
            .filter(
                MarketingCampaignV2ProviderStatsSnapshotORM.campaign_v2_id == normalized_id,
                MarketingCampaignV2ProviderStatsSnapshotORM.provider_campaign_id
                == child.provider_campaign_id,
            )
            .order_by(
                MarketingCampaignV2ProviderStatsSnapshotORM.fetched_at.desc(),
                MarketingCampaignV2ProviderStatsSnapshotORM.id.desc(),
            )
            .first()
        )
        if provider_snapshot is None:
            return {**base, "status": "NO_PROVIDER_SNAPSHOT"}

        recipients = (
            active_session.query(MarketingCampaignV2RecipientORM)
            .filter(MarketingCampaignV2RecipientORM.campaign_id == normalized_id)
            .all()
        )
        recipient_by_id = {int(r.id): r.phone_mx10 for r in recipients}
        successful_ids = (
            active_session.query(
                MarketingCampaignV2ProviderRecipientObservationORM.campaign_recipient_id
            )
            .filter(
                MarketingCampaignV2ProviderRecipientObservationORM.snapshot_id
                == provider_snapshot.id,
                MarketingCampaignV2ProviderRecipientObservationORM.outcome == "SUCCESSFUL",
                MarketingCampaignV2ProviderRecipientObservationORM.campaign_recipient_id.isnot(None),
            )
            .all()
        )
        successful_phones = {
            recipient_by_id[int(recipient_id)]
            for (recipient_id,) in successful_ids
            if int(recipient_id) in recipient_by_id
        }

        venta_snapshot = (
            active_session.query(VentaTotalSnapshotORM)
            .filter(
                VentaTotalSnapshotORM.report_type_key == "venta_total",
                VentaTotalSnapshotORM.snapshot_kind == "daily",
                VentaTotalSnapshotORM.is_canonical.is_(True),
                VentaTotalSnapshotORM.business_date >= sent_local.date(),
                VentaTotalSnapshotORM.business_date
                < _commercial_month_end_exclusive(sent_local.date()),
                VentaTotalSnapshotORM.captured_at >= sent,
            )
            .order_by(
                VentaTotalSnapshotORM.business_date.desc(),
                VentaTotalSnapshotORM.captured_at.desc(),
                VentaTotalSnapshotORM.id.desc(),
            )
            .first()
        )
        if venta_snapshot is None:
            return {**base, "status": "NO_CANONICAL_VENTA_TOTAL"}

        alias_rows = (
            active_session.query(TrackBranchAliasORM, TrackBranchCatalogORM)
            .join(
                TrackBranchCatalogORM,
                TrackBranchCatalogORM.sucursal_canon
                == TrackBranchAliasORM.sucursal_canon,
            )
            .filter(
                TrackBranchAliasORM.source_family == "gasca_family",
                TrackBranchAliasORM.is_active.is_(True),
                TrackBranchCatalogORM.is_track_active.is_(True),
                TrackBranchCatalogORM.sucursal_id.isnot(None),
            )
            .all()
        )
        alias_map = {
            _normalize_text(alias.raw_branch_name): int(catalog.sucursal_id)
            for alias, catalog in alias_rows
        }

        rows = []
        if successful_phones:
            phone_digits = func.regexp_replace(
                VentaTotalSnapshotRowORM.telefono, "[^0-9]", "", "g"
            )
            rows = (
                active_session.query(VentaTotalSnapshotRowORM)
                .filter(
                    VentaTotalSnapshotRowORM.snapshot_id == venta_snapshot.id,
                    func.right(phone_digits, 10).in_(sorted(successful_phones)),
                )
                .all()
            )
        metrics = _summarize_campaign_v2_membership_movements(
            rows=rows,
            sent_local=sent_local,
            successful_phones=successful_phones,
            branch_id=int(child.sucursal_id),
            alias_map=alias_map,
            required_sale_kind=required_sale_kind,
        )
        return {
            **base,
            "status": "READY",
            "submitted_at_local": sent_local.isoformat(),
            "provider_snapshot_id": int(provider_snapshot.id),
            "venta_total_snapshot_id": int(venta_snapshot.id),
            "venta_total_cutoff": venta_snapshot.business_date.isoformat(),
            "coverage": "LATEST_CANONICAL_WITHIN_SEND_MONTH",
            "successful_recipient_count": len(successful_phones),
            **metrics,
        }


def _validate_commercial_batch_ids(campaign_ids: Any) -> tuple[int, ...]:
    """Bound an on-demand dashboard read to one visible page of campaigns."""
    if not isinstance(campaign_ids, list) or not (1 <= len(campaign_ids) <= 100):
        raise MarketingCampaignV2ReportingValidationError(
            "campaign_ids debe contener entre 1 y 100 IDs."
        )
    if any(type(value) is not int or value <= 0 for value in campaign_ids):
        raise MarketingCampaignV2ReportingValidationError(
            "campaign_ids debe contener enteros positivos."
        )
    if len(set(campaign_ids)) != len(campaign_ids):
        raise MarketingCampaignV2ReportingValidationError(
            "campaign_ids no permite duplicados."
        )
    return tuple(campaign_ids)


def _commercial_batch_base(campaign_id: int, status: str) -> dict[str, Any]:
    return {
        "campaign_id": campaign_id,
        "status": status,
        "buyers_attributed": None,
        "transactions_attributed": None,
        "revenue_attributed_mxn": None,
    }


def build_campaign_v2_commercial_attribution_batch(
    *,
    campaign_ids: Any,
    allowed_sucursal_keys: Iterable[str] | None,
    session=None,
) -> dict[str, Any]:
    """Page-scoped read-only dashboard reconciliation; never N queries per campaign.

    The initial calculator intentionally covers single-child, single-month
    campaigns, just like the individually QA-validated endpoint. Multi-child,
    unsent and missing-evidence campaigns return a status, never a false zero.
    """
    from collections import defaultdict

    ids = _validate_commercial_batch_ids(campaign_ids)
    active_session = session if session is not None else db.session
    scope = _normalize_current_scope(allowed_sucursal_keys)

    with active_session.no_autoflush:
        campaigns = active_session.query(MarketingCampaignV2ORM).filter(
            MarketingCampaignV2ORM.id.in_(ids)
        ).all()
        by_id = {int(campaign.id): campaign for campaign in campaigns}
        # Fail closed for the whole batch: no partial data leaks across branches.
        if len(by_id) != len(ids) or any(
            not _campaign_visible_to_scope(by_id[identifier], scope)
            for identifier in ids
        ):
            raise MarketingCampaignV2NotFoundError(
                "Una o más campañas no están disponibles."
            )

        children = active_session.query(
            MarketingCampaignV2ProviderCampaignORM
        ).filter(
            MarketingCampaignV2ProviderCampaignORM.campaign_v2_id.in_(ids)
        ).all()
        children_by_campaign: dict[int, list[Any]] = defaultdict(list)
        for child in children:
            children_by_campaign[int(child.campaign_v2_id)].append(child)

        statuses: dict[int, dict[str, Any]] = {}
        candidates: dict[int, tuple[Any, datetime]] = {}
        multichild_ids: list[int] = []
        for identifier in ids:
            child_rows = children_by_campaign.get(identifier, [])
            if len(child_rows) != 1:
                statuses[identifier] = _commercial_batch_base(
                    identifier, "UNSUPPORTED_MULTICHILD_OR_UNSENT"
                )
                if len(child_rows) >= 2:
                    multichild_ids.append(identifier)
                continue
            child = child_rows[0]
            if child.submitted_at is None or not child.provider_campaign_id:
                statuses[identifier] = _commercial_batch_base(
                    identifier, "NOT_SUBMITTED"
                )
                continue
            reason = direct_attribution_ineligibility_reason(
                purpose=by_id[identifier].purpose,
                source=by_id[identifier].source,
            )
            if reason is not None:
                statuses[identifier] = {
                    **_commercial_batch_base(identifier, "NOT_ATTRIBUTABLE"),
                    "reason": reason,
                }
                continue
            submitted = child.submitted_at
            if submitted.tzinfo is None:
                submitted = submitted.replace(tzinfo=timezone.utc)
            candidates[identifier] = (
                child, submitted.astimezone(_COMMERCIAL_TZ)
            )

        # Materialized multi-child rows are one indexed lookup for the page;
        # never query or scan Gasca from a web request for multi-child campaigns.
        if multichild_ids:
            cached = active_session.query(
                MarketingCampaignV2CommercialResultORM
            ).filter(
                MarketingCampaignV2CommercialResultORM.campaign_v2_id.in_(
                    multichild_ids
                )
            ).all()
            for record in cached:
                identifier = int(record.campaign_v2_id)
                payload = _materialized_multichild_commercial_payload(
                    record=record,
                    children=children_by_campaign[identifier],
                    campaign=by_id[identifier],
                )
                if payload is not None:
                    statuses[identifier] = {
                        **_commercial_batch_base(identifier, payload["status"]),
                        **payload,
                    }

        if not candidates:
            return {"rows": [statuses[i] for i in ids]}

        # Read provider snapshots in bulk and choose the latest for the actual
        # provider campaign attached to each submitted child.
        snapshots = active_session.query(
            MarketingCampaignV2ProviderStatsSnapshotORM
        ).filter(
            MarketingCampaignV2ProviderStatsSnapshotORM.campaign_v2_id.in_(
                tuple(candidates)
            )
        ).order_by(
            MarketingCampaignV2ProviderStatsSnapshotORM.fetched_at.desc(),
            MarketingCampaignV2ProviderStatsSnapshotORM.id.desc(),
        ).all()
        provider_by_campaign = {}
        for snapshot in snapshots:
            identifier = int(snapshot.campaign_v2_id)
            child = candidates[identifier][0]
            if (
                identifier not in provider_by_campaign
                and snapshot.provider_campaign_id == child.provider_campaign_id
            ):
                provider_by_campaign[identifier] = snapshot
        for identifier in candidates:
            if identifier not in provider_by_campaign:
                statuses[identifier] = _commercial_batch_base(
                    identifier, "NO_PROVIDER_SNAPSHOT"
                )

        eligible = {
            identifier: value for identifier, value in candidates.items()
            if identifier in provider_by_campaign
        }
        if not eligible:
            return {"rows": [statuses[i] for i in ids]}

        # One canonical Venta Total cut per campaign's send month; never union
        # cumulative snapshots or silently roll into a later month.
        first_date = min(value[1].date() for value in eligible.values())
        last_end = max(
            _commercial_month_end_exclusive(value[1].date())
            for value in eligible.values()
        )
        venta_snapshots = active_session.query(VentaTotalSnapshotORM).filter(
            VentaTotalSnapshotORM.report_type_key == "venta_total",
            VentaTotalSnapshotORM.snapshot_kind == "daily",
            VentaTotalSnapshotORM.is_canonical.is_(True),
            VentaTotalSnapshotORM.business_date >= first_date,
            VentaTotalSnapshotORM.business_date < last_end,
        ).order_by(
            VentaTotalSnapshotORM.business_date.desc(),
            VentaTotalSnapshotORM.captured_at.desc(),
            VentaTotalSnapshotORM.id.desc(),
        ).all()
        venta_by_campaign = {}
        for identifier, (_, sent_local) in eligible.items():
            sent_utc = sent_local.astimezone(timezone.utc)
            end_date = _commercial_month_end_exclusive(sent_local.date())
            for snapshot in venta_snapshots:
                captured_at = snapshot.captured_at
                if captured_at.tzinfo is None:
                    captured_at = captured_at.replace(tzinfo=timezone.utc)
                if (
                    sent_local.date() <= snapshot.business_date < end_date
                    and captured_at >= sent_utc
                ):
                    venta_by_campaign[identifier] = snapshot
                    break
            if identifier not in venta_by_campaign:
                statuses[identifier] = _commercial_batch_base(
                    identifier, "NO_CANONICAL_VENTA_TOTAL"
                )

        eligible = {
            identifier: value for identifier, value in eligible.items()
            if identifier in venta_by_campaign
        }
        if not eligible:
            return {"rows": [statuses[i] for i in ids]}

        # Query only successful provider observations and their frozen phones,
        # not the entire frozen audience of large historical campaigns.
        provider_ids = {
            int(provider_by_campaign[i].id): i for i in eligible
        }
        successful_rows = active_session.query(
            MarketingCampaignV2ProviderRecipientObservationORM.snapshot_id,
            MarketingCampaignV2RecipientORM.campaign_id,
            MarketingCampaignV2RecipientORM.phone_mx10,
        ).join(
            MarketingCampaignV2RecipientORM,
            MarketingCampaignV2ProviderRecipientObservationORM.campaign_recipient_id
            == MarketingCampaignV2RecipientORM.id,
        ).filter(
            MarketingCampaignV2ProviderRecipientObservationORM.snapshot_id.in_(
                tuple(provider_ids)
            ),
            MarketingCampaignV2ProviderRecipientObservationORM.outcome
            == "SUCCESSFUL",
            MarketingCampaignV2RecipientORM.campaign_id.in_(tuple(eligible)),
        ).all()
        phones_by_campaign: dict[int, set[str]] = {
            identifier: set() for identifier in eligible
        }
        for snapshot_id, campaign_id, phone in successful_rows:
            identifier = int(campaign_id)
            if provider_ids.get(int(snapshot_id)) == identifier:
                phones_by_campaign[identifier].add(phone)

        # Hard safeguard against an unbounded live query. A dedicated
        # materialized reconciliation is needed for substantially larger pages.
        unique_phones: set[str] = set()
        covered: dict[int, tuple[Any, datetime]] = {}
        for identifier in ids:
            if identifier not in eligible:
                continue
            candidate_phones = unique_phones | phones_by_campaign[identifier]
            if len(candidate_phones) > 10000:
                statuses[identifier] = _commercial_batch_base(
                    identifier, "BATCH_SCOPE_TOO_LARGE"
                )
                continue
            unique_phones = candidate_phones
            covered[identifier] = eligible[identifier]
        eligible = covered
        phones_by_campaign = {
            identifier: phones_by_campaign[identifier]
            for identifier in eligible
        }
        if not eligible:
            return {"rows": [statuses[i] for i in ids]}

        from app.services.marketing_sales_funnel_service import (
            _load_branch_alias_map,
        )
        alias_map = _load_branch_alias_map()
        snapshot_phone_campaigns: dict[tuple[int, str], set[int]] = defaultdict(set)
        for identifier, phones in phones_by_campaign.items():
            snapshot_id = int(venta_by_campaign[identifier].id)
            for phone in phones:
                snapshot_phone_campaigns[(snapshot_id, phone)].add(identifier)

        rows_by_campaign: dict[int, list[Any]] = defaultdict(list)
        if unique_phones:
            phone_digits = func.regexp_replace(
                VentaTotalSnapshotRowORM.telefono, "[^0-9]", "", "g"
            )
            venta_rows = active_session.query(
                VentaTotalSnapshotRowORM
            ).filter(
                VentaTotalSnapshotRowORM.snapshot_id.in_(
                    tuple({int(s.id) for s in venta_by_campaign.values()})
                ),
                func.right(phone_digits, 10).in_(sorted(unique_phones)),
            ).yield_per(1000)
            for row in venta_rows:
                phone = normalize_phone(row.telefono)
                for identifier in snapshot_phone_campaigns.get(
                    (int(row.snapshot_id), phone), ()
                ):
                    rows_by_campaign[identifier].append(row)

        for identifier, (child, sent_local) in eligible.items():
            metrics = _summarize_campaign_v2_membership_movements(
                rows=rows_by_campaign[identifier],
                sent_local=sent_local,
                successful_phones=phones_by_campaign[identifier],
                branch_id=int(child.sucursal_id),
                alias_map=alias_map,
                required_sale_kind=required_commercial_sale_kind(
                    purpose=by_id[identifier].purpose,
                    source=by_id[identifier].source,
                ),
            )
            statuses[identifier] = {
                **_commercial_batch_base(identifier, "READY"),
                "successful_recipient_count": len(phones_by_campaign[identifier]),
                "provider_snapshot_id": int(provider_by_campaign[identifier].id),
                "venta_total_snapshot_id": int(venta_by_campaign[identifier].id),
                "venta_total_cutoff": venta_by_campaign[identifier].business_date.isoformat(),
                **metrics,
            }

    return {"rows": [statuses[i] for i in ids]}
