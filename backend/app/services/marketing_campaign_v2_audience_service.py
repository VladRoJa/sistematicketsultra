from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2TariffORM,
    MarketingCampaignV2TariffOverrideORM,
)
from app.models.warehouse import (
    SociosActivosSnapshotRowORM,
    SociosVencidosCarteraORM,
)
from app.services.marketing_phone import normalize_phone
from app.services.marketing_campaign_iventas_followup_service import (
    get_latest_iventas_status_by_phone,
)
from app.services import marketing_campaign_v2_funnel_source_service as funnel_source
from app.services.marketing_campaign_v2_provider_history_service import (
    MarketingCampaignV2ProviderHistoryValidationError,
    get_provider_history_for_phones,
)
from app.services.marketing_tariff_normalization import normalize_marketing_tariff_key
from app.warehouse.services import socios_activos_snapshot_resolver as activos_resolver
from app.warehouse.services import socios_vencidos_current_status_resolver as current_status


SOURCE_EXPIRED_MEMBERS = "EXPIRED_MEMBERS"
SOURCE_ACTIVE_MEMBERS = "ACTIVE_MEMBERS"
SOURCE_FUNNEL_PORTFOLIO = funnel_source.SOURCE_FUNNEL_PORTFOLIO
SUPPORTED_SOURCES = frozenset(
    {
        SOURCE_EXPIRED_MEMBERS,
        SOURCE_ACTIVE_MEMBERS,
        SOURCE_FUNNEL_PORTFOLIO,
    }
)

SELECTABLE_AUDIENCE_FAMILIES = (
    "DOMICILIADO",
    "TRIMESTRAL",
    "CONVENIO",
    "SEMESTRE",
    "ESTUDIANTE",
)
ALL_AUDIENCE_FAMILIES = (
    *SELECTABLE_AUDIENCE_FAMILIES,
    "MES",
    "OUT_OF_SEGMENT",
)

HISTORICAL_TARGETING_MODES = ("INCLUDE", "EXCLUDE")
HISTORICAL_TARGETING_MATCHES = ("ALL", "ANY")
HISTORICAL_TARGETING_DELIVERY_BUCKETS = ("SENT", "DELIVERED", "VIEWED")
HISTORICAL_TARGETING_OUTCOMES = ("SUCCESSFUL", "FAILED")
HISTORICAL_TARGETING_WINDOW_MODES = ("ALL_HISTORY", "LOOKBACK_DAYS")
IVENTAS_CURRENT_STATUSES = ("SENT", "DELIVERED", "VIEWED", "FAILED", "NO_DATA")

BUCKET_RECIPIENTS = "RECIPIENTS"
BUCKET_INVALID_PHONE = "INVALID_PHONE"
BUCKET_DUPLICATES = "DUPLICATES"
BUCKET_OUT_OF_SEGMENT = "OUT_OF_SEGMENT"
BUCKET_UNCLASSIFIED = "UNCLASSIFIED"
BUCKET_FAMILY = "FAMILY"
BUCKET_CURRENT_STATUS_BLOCKED = "CURRENT_STATUS_BLOCKED"
BUCKET_HISTORY_EXCLUDED = "HISTORY_EXCLUDED"
BUCKET_HISTORY_INCLUDED = "HISTORY_INCLUDED"
BUCKET_FUNNEL_CANDIDATES = "FUNNEL_CANDIDATES"
BUCKET_FUNNEL_BUYER_EXCLUDED = "FUNNEL_BUYER_EXCLUDED"
BUCKET_ACTIVE_MEMBER_SUPPRESSION = "ACTIVE_MEMBER_SUPPRESSION"
SUPPORTED_BUCKETS = frozenset(
    {
        BUCKET_RECIPIENTS,
        BUCKET_INVALID_PHONE,
        BUCKET_DUPLICATES,
        BUCKET_OUT_OF_SEGMENT,
        BUCKET_UNCLASSIFIED,
        BUCKET_FAMILY,
        BUCKET_CURRENT_STATUS_BLOCKED,
        BUCKET_HISTORY_EXCLUDED,
        BUCKET_HISTORY_INCLUDED,
        BUCKET_FUNNEL_CANDIDATES,
        BUCKET_FUNNEL_BUYER_EXCLUDED,
        BUCKET_ACTIVE_MEMBER_SUPPRESSION,
    }
)


class MarketingCampaignV2AudienceValidationError(ValueError):
    """Los filtros del Audience Builder V2 no cumplen el contrato."""


@dataclass(frozen=True, slots=True)
class MarketingCampaignV2AudienceCandidate:
    source: str
    source_ref_type: str
    source_ref_id: int | None
    source_snapshot_id: int | None = None
    phone_raw: str | None = None
    phone_mx10: str | None = None
    member_id: str | None = None
    member_pin: str | None = None
    member_name: str | None = None
    sucursal: str | None = None
    sucursal_key: str | None = None
    tarifa_raw: str | None = None
    tarifa_key: str | None = None
    categoria_tarifa: str | None = None
    audience_family: str | None = None
    fecha_vencimiento: date | None = None
    adeudo: Decimal | None = None
    current_status: str | None = None
    evidence: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class MarketingCampaignV2RecipientCandidate:
    source: str
    phone_mx10: str
    member_id: str | None
    member_pin: str | None
    member_name: str | None
    sucursal: str | None
    tarifa_raw: str | None
    tarifa_key: str | None
    categoria_tarifa: str | None
    audience_family: str | None
    fecha_vencimiento: date | None
    inclusion_reason: str
    conflict_fields: tuple[str, ...]
    evidence_rows: tuple[MarketingCampaignV2AudienceCandidate, ...]


@dataclass(frozen=True, slots=True)
class MarketingCampaignV2HistoryExcludedCandidate:
    candidate: MarketingCampaignV2AudienceCandidate
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MarketingCampaignV2HistoricalDecisionCandidate:
    candidate: MarketingCampaignV2AudienceCandidate
    matched: bool
    decision: str
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _HistoricalTargetingResolution:
    rule: dict[str, Any] | None
    filter_key: str | None
    filter_value: dict[str, Any] | None
    legacy: bool


@dataclass(frozen=True, slots=True)
class _SourceLoadResult:
    universe_count: int
    scoped_count: int
    candidates: tuple[MarketingCampaignV2AudienceCandidate, ...]
    current_status_blocked: tuple[MarketingCampaignV2AudienceCandidate, ...]
    current_status_counts: dict[str, int]
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _AudiencePlan:
    source: str
    filters: dict[str, Any]
    source_metadata: dict[str, Any]
    universe_count: int
    scoped_count: int
    current_status_counts: dict[str, int]
    current_status_blocked: tuple[MarketingCampaignV2AudienceCandidate, ...]
    classified_candidates: tuple[MarketingCampaignV2AudienceCandidate, ...]
    selected_candidates: tuple[MarketingCampaignV2AudienceCandidate, ...]
    invalid_phone_rows: tuple[MarketingCampaignV2AudienceCandidate, ...]
    duplicate_rows: tuple[MarketingCampaignV2AudienceCandidate, ...]
    recipients: tuple[MarketingCampaignV2RecipientCandidate, ...]
    family_counts: dict[str, int]
    unclassified_family_count: int
    out_of_segment_count: int
    history_excluded_rows: tuple[
        MarketingCampaignV2HistoryExcludedCandidate,
        ...,
    ] = field(default_factory=tuple)
    historical_decision_rows: tuple[
        MarketingCampaignV2HistoricalDecisionCandidate,
        ...,
    ] = field(default_factory=tuple)
    history_diagnostics: dict[str, Any] = field(default_factory=dict)
    funnel_candidate_rows: tuple[
        MarketingCampaignV2AudienceCandidate,
        ...,
    ] = field(default_factory=tuple)
    funnel_buyer_excluded_rows: tuple[
        MarketingCampaignV2AudienceCandidate,
        ...,
    ] = field(default_factory=tuple)
    active_member_suppressed_rows: tuple[
        MarketingCampaignV2AudienceCandidate,
        ...,
    ] = field(default_factory=tuple)


def build_campaign_v2_audience_preview(
    *,
    source: Any,
    audience_families: Any,
    allowed_sucursal_keys: Iterable[Any] | None,
    expiration_date_from: Any = None,
    expiration_date_to: Any = None,
    adeudo_min: Any = None,
    history_exclusion: Any = None,
    historical_targeting: Any = None,
    iventas_current_statuses: Any = None,
    funnel_month: Any = None,
    funnel_cutoff_date: Any = None,
    marketing_access: Any = None,
    session: Any | None = None,
) -> dict[str, Any]:
    """Build a deterministic, read-only Campaign V2 audience preview."""

    plan = _build_campaign_v2_audience_plan(
        source=source,
        audience_families=audience_families,
        allowed_sucursal_keys=allowed_sucursal_keys,
        expiration_date_from=expiration_date_from,
        expiration_date_to=expiration_date_to,
        adeudo_min=adeudo_min,
        history_exclusion=history_exclusion,
        historical_targeting=historical_targeting,
        iventas_current_statuses=iventas_current_statuses,
        funnel_month=funnel_month,
        funnel_cutoff_date=funnel_cutoff_date,
        marketing_access=marketing_access,
        session=session,
    )
    return _serialize_preview(plan)

def build_campaign_v2_audience_preview_detail(
    *,
    source: Any,
    audience_families: Any,
    allowed_sucursal_keys: Iterable[Any] | None,
    bucket: Any,
    audience_family: Any = None,
    page: Any = 1,
    page_size: Any = 50,
    expiration_date_from: Any = None,
    expiration_date_to: Any = None,
    adeudo_min: Any = None,
    history_exclusion: Any = None,
    historical_targeting: Any = None,
    iventas_current_statuses: Any = None,
    funnel_month: Any = None,
    funnel_cutoff_date: Any = None,
    marketing_access: Any = None,
    session: Any | None = None,
) -> dict[str, Any]:
    """Rebuild preview and return a stable paged bucket, failing closed."""

    normalized_bucket = _normalize_bucket(bucket)
    normalized_family = _normalize_detail_family(
        bucket=normalized_bucket,
        audience_family=audience_family,
    )
    normalized_page = _positive_int(page, field_name="page", maximum=1_000_000)
    normalized_page_size = _positive_int(
        page_size,
        field_name="page_size",
        maximum=100,
    )

    plan = _build_campaign_v2_audience_plan(
        source=source,
        audience_families=audience_families,
        allowed_sucursal_keys=allowed_sucursal_keys,
        expiration_date_from=expiration_date_from,
        expiration_date_to=expiration_date_to,
        adeudo_min=adeudo_min,
        history_exclusion=history_exclusion,
        historical_targeting=historical_targeting,
        iventas_current_statuses=iventas_current_statuses,
        funnel_month=funnel_month,
        funnel_cutoff_date=funnel_cutoff_date,
        marketing_access=marketing_access,
        session=session,
    )
    _validate_bucket_for_source(
        source=plan.source,
        bucket=normalized_bucket,
    )
    preview = _serialize_preview(plan)
    bucket_rows = _bucket_rows(
        plan,
        bucket=normalized_bucket,
        audience_family=normalized_family,
    )
    expected_total = _expected_bucket_total(
        preview,
        bucket=normalized_bucket,
        audience_family=normalized_family,
    )
    if len(bucket_rows) != expected_total:
        raise RuntimeError(
            "Campaign V2 preview detail no coincide con el contador del preview: "
            f"{normalized_bucket} detalle={len(bucket_rows)} preview={expected_total}."
        )

    offset = (normalized_page - 1) * normalized_page_size
    if expected_total > 0 and offset >= expected_total:
        raise MarketingCampaignV2AudienceValidationError(
            "page está fuera del rango disponible para el detalle solicitado."
        )
    page_rows = bucket_rows[offset : offset + normalized_page_size]

    return {
        "source": plan.source,
        "source_metadata": dict(plan.source_metadata),
        "filters": dict(plan.filters),
        "bucket": normalized_bucket,
        "audience_family": normalized_family,
        "total": expected_total,
        "page": normalized_page,
        "page_size": normalized_page_size,
        "pages": (
            (expected_total + normalized_page_size - 1) // normalized_page_size
            if expected_total
            else 0
        ),
        "rows": [
            _serialize_preview_detail_row(
                row,
                legacy_history=("history_exclusion" in plan.filters),
            )
            for row in page_rows
        ],
    }

def _build_campaign_v2_audience_plan(
    *,
    source: Any,
    audience_families: Any,
    allowed_sucursal_keys: Iterable[Any] | None,
    expiration_date_from: Any,
    expiration_date_to: Any,
    adeudo_min: Any = None,
    history_exclusion: Any = None,
    historical_targeting: Any = None,
    iventas_current_statuses: Any = None,
    funnel_month: Any = None,
    funnel_cutoff_date: Any = None,
    marketing_access: Any = None,
    session: Any | None = None,
) -> _AudiencePlan:
    normalized_source = _normalize_source(source)
    normalized_scope = _normalize_scope(allowed_sucursal_keys)
    history_resolution = _resolve_historical_targeting_input(
        history_exclusion=history_exclusion,
        historical_targeting=historical_targeting,
    )
    normalized_iventas_statuses = _normalize_iventas_current_statuses(
        iventas_current_statuses
    )
    normalized_adeudo_min = _normalize_adeudo_min(adeudo_min)
    if normalized_source != SOURCE_EXPIRED_MEMBERS and normalized_adeudo_min is not None:
        raise MarketingCampaignV2AudienceValidationError(
            "adeudo_min sólo aplica a EXPIRED_MEMBERS."
        )
    active_session = session if session is not None else db.session

    if normalized_source == SOURCE_FUNNEL_PORTFOLIO:
        return _build_funnel_audience_plan(
            audience_families=audience_families,
            allowed_sucursal_keys=normalized_scope,
            expiration_date_from=expiration_date_from,
            expiration_date_to=expiration_date_to,
            history_resolution=history_resolution,
            iventas_current_statuses=normalized_iventas_statuses,
            funnel_month=funnel_month,
            funnel_cutoff_date=funnel_cutoff_date,
            marketing_access=marketing_access,
            session=active_session,
        )

    selected_families = _normalize_family_selection(audience_families)

    if normalized_source == SOURCE_EXPIRED_MEMBERS:
        date_from = _ensure_date(expiration_date_from, field_name="expiration_date_from")
        date_to = _ensure_date(expiration_date_to, field_name="expiration_date_to")
        if date_from > date_to:
            raise MarketingCampaignV2AudienceValidationError(
                "expiration_date_from no puede ser posterior a expiration_date_to."
            )
        source_result = _load_expired_source(
            date_from=date_from,
            date_to=date_to,
            allowed_sucursal_keys=normalized_scope,
            session=active_session,
        )
        normalized_filters: dict[str, Any] = {
            "source": normalized_source,
            "expiration_date_from": date_from.isoformat(),
            "expiration_date_to": date_to.isoformat(),
            "allowed_sucursal_keys": (
                list(normalized_scope) if normalized_scope is not None else None
            ),
            "audience_families": list(selected_families),
        }
        if normalized_adeudo_min is not None:
            normalized_filters["adeudo_min"] = format(normalized_adeudo_min, "f")
    else:
        if expiration_date_from is not None or expiration_date_to is not None:
            raise MarketingCampaignV2AudienceValidationError(
                "Los filtros de vencimiento sólo aplican a EXPIRED_MEMBERS."
            )
        source_result = _load_active_source(
            allowed_sucursal_keys=normalized_scope,
            session=active_session,
        )
        normalized_filters = {
            "source": normalized_source,
            "allowed_sucursal_keys": (
                list(normalized_scope) if normalized_scope is not None else None
            ),
            "audience_families": list(selected_families),
        }

    if history_resolution.filter_key is not None:
        normalized_filters[history_resolution.filter_key] = (
            history_resolution.filter_value
        )
    if normalized_iventas_statuses:
        normalized_filters["iventas_current_statuses"] = list(
            normalized_iventas_statuses
        )

    source_candidates = source_result.candidates
    if normalized_adeudo_min is not None:
        source_candidates = tuple(
            candidate
            for candidate in source_candidates
            if candidate.adeudo is not None
            and candidate.adeudo >= normalized_adeudo_min
        )

    tariff_catalog = _read_v2_tariff_catalog(session=active_session)
    classified = tuple(
        _classify_candidate(candidate, tariff_catalog=tariff_catalog)
        for candidate in source_candidates
    )
    classified = tuple(sorted(classified, key=_candidate_sort_key))

    counts = Counter(candidate.audience_family for candidate in classified)
    family_counts = {
        family: int(counts.get(family, 0))
        for family in ALL_AUDIENCE_FAMILIES
    }
    unclassified_count = int(counts.get(None, 0))
    out_of_segment_count = family_counts["OUT_OF_SEGMENT"]

    selected = tuple(
        candidate
        for candidate in classified
        if candidate.audience_family in selected_families
    )
    invalid_phone_rows = tuple(
        candidate for candidate in selected if candidate.phone_mx10 is None
    )
    valid_rows = tuple(
        candidate for candidate in selected if candidate.phone_mx10 is not None
    )

    source_metadata = dict(source_result.metadata)
    if normalized_adeudo_min is not None:
        source_metadata["adeudo_min"] = format(normalized_adeudo_min, "f")
    history_excluded_rows: tuple[
        MarketingCampaignV2HistoryExcludedCandidate,
        ...,
    ] = ()
    historical_decision_rows: tuple[
        MarketingCampaignV2HistoricalDecisionCandidate,
        ...,
    ] = ()
    history_diagnostics: dict[str, Any] = {}

    if history_resolution.rule is not None:
        (
            valid_rows,
            historical_decision_rows,
            history_diagnostics,
            history_evaluation,
        ) = _evaluate_historical_targeting(
            candidates=valid_rows,
            rule=history_resolution.rule,
            allowed_sucursal_keys=normalized_scope,
            session=active_session,
            legacy=history_resolution.legacy,
        )
        history_excluded_rows = _legacy_history_excluded_rows(
            historical_decision_rows
        )
        source_metadata["history_evaluation"] = history_evaluation

    if normalized_iventas_statuses:
        valid_rows, iventas_evaluation = _filter_by_iventas_current_status(
            candidates=valid_rows,
            selected_statuses=normalized_iventas_statuses,
            session=active_session,
        )
        source_metadata["iventas_current_status_evaluation"] = iventas_evaluation

    recipients, duplicate_rows = _deduplicate_candidates(valid_rows)

    return _AudiencePlan(
        source=normalized_source,
        filters=normalized_filters,
        source_metadata=source_metadata,
        universe_count=int(source_result.universe_count),
        scoped_count=int(source_result.scoped_count),
        current_status_counts=dict(source_result.current_status_counts),
        current_status_blocked=source_result.current_status_blocked,
        classified_candidates=classified,
        selected_candidates=selected,
        invalid_phone_rows=invalid_phone_rows,
        duplicate_rows=duplicate_rows,
        recipients=recipients,
        family_counts=family_counts,
        unclassified_family_count=unclassified_count,
        out_of_segment_count=out_of_segment_count,
        history_excluded_rows=history_excluded_rows,
        historical_decision_rows=historical_decision_rows,
        history_diagnostics=history_diagnostics,
    )

def _build_funnel_audience_plan(
    *,
    audience_families: Any,
    allowed_sucursal_keys: tuple[str, ...] | None,
    expiration_date_from: Any,
    expiration_date_to: Any,
    history_resolution: _HistoricalTargetingResolution,
    iventas_current_statuses: tuple[str, ...],
    funnel_month: Any,
    funnel_cutoff_date: Any,
    marketing_access: Any,
    session: Any,
) -> _AudiencePlan:
    if audience_families is not None:
        raise MarketingCampaignV2AudienceValidationError(
            "audience_families no aplica a FUNNEL_PORTFOLIO."
        )
    if expiration_date_from is not None or expiration_date_to is not None:
        raise MarketingCampaignV2AudienceValidationError(
            "Los filtros de vencimiento no aplican a FUNNEL_PORTFOLIO."
        )
    if marketing_access is None:
        raise MarketingCampaignV2AudienceValidationError(
            "FUNNEL_PORTFOLIO requiere scope backend de Marketing."
        )

    normalized_month = str(funnel_month or "").strip()
    normalized_cutoff = str(funnel_cutoff_date or "").strip()
    if not normalized_month:
        raise MarketingCampaignV2AudienceValidationError(
            "funnel_month es obligatorio para FUNNEL_PORTFOLIO."
        )
    if not normalized_cutoff:
        raise MarketingCampaignV2AudienceValidationError(
            "funnel_cutoff_date es obligatorio para FUNNEL_PORTFOLIO."
        )

    try:
        loaded = funnel_source.load_campaign_v2_funnel_source(
            funnel_month=normalized_month,
            funnel_cutoff_date=normalized_cutoff,
            marketing_access=marketing_access,
            session=session,
        )
    except (funnel_source.MarketingCampaignV2FunnelSourceValidationError, ValueError) as exc:
        raise MarketingCampaignV2AudienceValidationError(str(exc)) from exc

    funnel_candidates = tuple(_funnel_candidate(row) for row in loaded.funnel_candidates)
    buyer_excluded = tuple(_funnel_candidate(row) for row in loaded.buyer_excluded)
    invalid_phone_rows = tuple(_funnel_candidate(row) for row in loaded.invalid_phone)
    active_member_suppressed = tuple(
        _funnel_candidate(row) for row in loaded.active_member_suppressed
    )
    valid_rows = tuple(_funnel_candidate(row) for row in loaded.candidates)

    normalized_filters: dict[str, Any] = {
        "source": SOURCE_FUNNEL_PORTFOLIO,
        "funnel_month": loaded.funnel_month,
        "funnel_cutoff_date": loaded.funnel_cutoff_date,
        "allowed_sucursal_keys": (
            list(allowed_sucursal_keys)
            if allowed_sucursal_keys is not None
            else None
        ),
    }
    if history_resolution.filter_key is not None:
        normalized_filters[history_resolution.filter_key] = (
            history_resolution.filter_value
        )
    if iventas_current_statuses:
        normalized_filters["iventas_current_statuses"] = list(
            iventas_current_statuses
        )

    source_metadata = dict(loaded.metadata)
    history_excluded_rows: tuple[
        MarketingCampaignV2HistoryExcludedCandidate,
        ...,
    ] = ()
    historical_decision_rows: tuple[
        MarketingCampaignV2HistoricalDecisionCandidate,
        ...,
    ] = ()
    history_diagnostics = _empty_history_diagnostics(
        len({row.phone_mx10 for row in valid_rows if row.phone_mx10})
    )
    if history_resolution.rule is not None:
        (
            valid_rows,
            historical_decision_rows,
            history_diagnostics,
            history_evaluation,
        ) = _evaluate_historical_targeting(
            candidates=valid_rows,
            rule=history_resolution.rule,
            allowed_sucursal_keys=allowed_sucursal_keys,
            session=session,
            legacy=history_resolution.legacy,
        )
        history_excluded_rows = _legacy_history_excluded_rows(
            historical_decision_rows
        )
        source_metadata["history_evaluation"] = history_evaluation

    if iventas_current_statuses:
        valid_rows, iventas_evaluation = _filter_by_iventas_current_status(
            candidates=valid_rows,
            selected_statuses=iventas_current_statuses,
            session=session,
        )
        source_metadata["iventas_current_status_evaluation"] = iventas_evaluation

    recipients, duplicate_rows = _deduplicate_candidates(valid_rows)

    return _AudiencePlan(
        source=SOURCE_FUNNEL_PORTFOLIO,
        filters=normalized_filters,
        source_metadata=source_metadata,
        universe_count=int(loaded.universe_count),
        scoped_count=int(loaded.scoped_count),
        current_status_counts={},
        current_status_blocked=(),
        classified_candidates=funnel_candidates,
        selected_candidates=tuple(
            _funnel_candidate(row) for row in loaded.candidates
        ),
        invalid_phone_rows=invalid_phone_rows,
        duplicate_rows=duplicate_rows,
        recipients=recipients,
        family_counts={family: 0 for family in ALL_AUDIENCE_FAMILIES},
        unclassified_family_count=0,
        out_of_segment_count=0,
        history_excluded_rows=history_excluded_rows,
        historical_decision_rows=historical_decision_rows,
        history_diagnostics=history_diagnostics,
        funnel_candidate_rows=funnel_candidates,
        funnel_buyer_excluded_rows=buyer_excluded,
        active_member_suppressed_rows=active_member_suppressed,
    )


def _normalize_adeudo_min(value: Any) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, bool):
        raise MarketingCampaignV2AudienceValidationError(
            "adeudo_min debe ser un número mayor o igual a cero."
        )
    try:
        normalized = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise MarketingCampaignV2AudienceValidationError(
            "adeudo_min debe ser un número mayor o igual a cero."
        ) from exc
    if not normalized.is_finite() or normalized < 0:
        raise MarketingCampaignV2AudienceValidationError(
            "adeudo_min debe ser un número mayor o igual a cero."
        )
    return normalized


def _optional_decimal_value(value: Any) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        normalized = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None
    return normalized if normalized.is_finite() else None


def _normalize_iventas_current_statuses(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise MarketingCampaignV2AudienceValidationError(
            "iventas_current_statuses debe ser una lista."
        )
    normalized = {
        str(item or "").strip().upper()
        for item in value
        if str(item or "").strip()
    }
    unsupported = sorted(normalized - set(IVENTAS_CURRENT_STATUSES))
    if unsupported:
        raise MarketingCampaignV2AudienceValidationError(
            "Estados iVentas no soportados: " + ", ".join(unsupported) + "."
        )
    return tuple(
        status for status in IVENTAS_CURRENT_STATUSES if status in normalized
    )


def _filter_by_iventas_current_status(
    *,
    candidates: tuple[MarketingCampaignV2AudienceCandidate, ...],
    selected_statuses: tuple[str, ...],
    session: Any,
) -> tuple[
    tuple[MarketingCampaignV2AudienceCandidate, ...],
    dict[str, Any],
]:
    phones = {
        str(candidate.phone_mx10)
        for candidate in candidates
        if candidate.phone_mx10 is not None
    }
    resolved = get_latest_iventas_status_by_phone(
        phones=phones,
        session=session,
    )
    statuses_by_phone = dict(resolved.get("statuses") or {})
    observed = {
        phone: (statuses_by_phone.get(phone) or "NO_DATA")
        for phone in phones
    }
    counts = Counter(observed.values())
    selected = set(selected_statuses)
    kept = tuple(
        candidate
        for candidate in candidates
        if candidate.phone_mx10 is not None
        and observed.get(str(candidate.phone_mx10), "NO_DATA") in selected
    )
    matched_phones = {
        str(candidate.phone_mx10)
        for candidate in kept
        if candidate.phone_mx10 is not None
    }
    evaluation = {
        "sync_run_ids": list(resolved.get("sync_run_ids") or []),
        "period_keys": list(resolved.get("period_keys") or []),
        "selected_statuses": list(selected_statuses),
        "before_phone_count": len(phones),
        "matched_phone_count": len(matched_phones),
        "status_counts": {
            status: int(counts.get(status, 0))
            for status in (*IVENTAS_CURRENT_STATUSES,)
        },
    }
    return kept, evaluation


def _funnel_candidate(
    row: funnel_source.MarketingCampaignV2FunnelCandidate,
) -> MarketingCampaignV2AudienceCandidate:
    evidence = ["FUNNEL_PORTFOLIO"]
    if row.source_reference is not None:
        evidence.append(f"SOURCE_REFERENCE:{row.source_reference}")
    if row.contact_id is not None:
        evidence.append(f"CONTACT_ID:{row.contact_id}")
    if row.sucursal_id is not None:
        evidence.append(f"SUCURSAL_ID:{row.sucursal_id}")
    if row.channel is not None:
        evidence.append(f"CHANNEL:{row.channel}")
    if row.source_date is not None:
        evidence.append(f"SOURCE_DATE:{row.source_date}")
    if row.origin is not None:
        evidence.append(f"ORIGIN:{row.origin}")

    return MarketingCampaignV2AudienceCandidate(
        source=SOURCE_FUNNEL_PORTFOLIO,
        source_ref_type="IVENTAS_CONTACT",
        source_ref_id=None,
        phone_raw=row.phone_raw,
        phone_mx10=row.phone_mx10,
        sucursal=row.sucursal_key,
        sucursal_key=row.sucursal_key,
        evidence=tuple(evidence),
    )


def _resolve_historical_targeting_input(
    *,
    history_exclusion: Any,
    historical_targeting: Any,
) -> _HistoricalTargetingResolution:
    if history_exclusion is not None and historical_targeting is not None:
        raise MarketingCampaignV2AudienceValidationError(
            "history_exclusion y historical_targeting no pueden enviarse juntos."
        )

    if historical_targeting is not None:
        normalized = _normalize_historical_targeting(historical_targeting)
        return _HistoricalTargetingResolution(
            rule=normalized,
            filter_key="historical_targeting",
            filter_value=normalized,
            legacy=False,
        )

    normalized_legacy = _normalize_history_exclusion(history_exclusion)
    if normalized_legacy is None:
        return _HistoricalTargetingResolution(
            rule=None,
            filter_key=None,
            filter_value=None,
            legacy=False,
        )

    internal_rule = {
        "mode": "EXCLUDE",
        "match": "ANY",
        **normalized_legacy,
    }
    return _HistoricalTargetingResolution(
        rule=internal_rule,
        filter_key="history_exclusion",
        filter_value=normalized_legacy,
        legacy=True,
    )


def _normalize_historical_targeting(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MarketingCampaignV2AudienceValidationError(
            "historical_targeting debe ser un objeto."
        )

    allowed = {
        "mode",
        "match",
        "delivery_buckets",
        "outcomes",
        "button_interacted",
        "lookback_days",
    }
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise MarketingCampaignV2AudienceValidationError(
            "Campos historical_targeting no permitidos: "
            + ", ".join(unknown)
            + "."
        )

    mode = str(value.get("mode") or "").strip().upper()
    if mode not in HISTORICAL_TARGETING_MODES:
        raise MarketingCampaignV2AudienceValidationError(
            "historical_targeting.mode debe ser INCLUDE o EXCLUDE."
        )

    match = str(value.get("match") or "").strip().upper()
    if match not in HISTORICAL_TARGETING_MATCHES:
        raise MarketingCampaignV2AudienceValidationError(
            "historical_targeting.match debe ser ALL o ANY."
        )

    delivery = _normalize_history_enum_list(
        value.get("delivery_buckets", []),
        field_name="historical_targeting.delivery_buckets",
        allowed=HISTORICAL_TARGETING_DELIVERY_BUCKETS,
    )
    outcomes = _normalize_history_enum_list(
        value.get("outcomes", []),
        field_name="historical_targeting.outcomes",
        allowed=HISTORICAL_TARGETING_OUTCOMES,
    )
    raw_button = value.get("button_interacted", False)
    if not isinstance(raw_button, bool):
        raise MarketingCampaignV2AudienceValidationError(
            "historical_targeting.button_interacted debe ser booleano."
        )
    lookback_days = _normalize_history_lookback_days(
        value.get("lookback_days"),
        field_name="historical_targeting.lookback_days",
    )

    if not (delivery or outcomes or raw_button):
        raise MarketingCampaignV2AudienceValidationError(
            "historical_targeting requiere al menos una condición efectiva."
        )

    return {
        "mode": mode,
        "match": match,
        "delivery_buckets": list(delivery),
        "outcomes": list(outcomes),
        "button_interacted": raw_button,
        "lookback_days": lookback_days,
    }


def _normalize_history_exclusion(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise MarketingCampaignV2AudienceValidationError(
            "history_exclusion debe ser un objeto o null."
        )

    allowed = {
        "delivery_buckets",
        "outcomes",
        "button_interacted",
        "lookback_days",
    }
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise MarketingCampaignV2AudienceValidationError(
            "Campos history_exclusion no permitidos: "
            + ", ".join(unknown)
            + "."
        )

    delivery = _normalize_history_enum_list(
        value.get("delivery_buckets", []),
        field_name="history_exclusion.delivery_buckets",
        allowed=HISTORICAL_TARGETING_DELIVERY_BUCKETS,
    )
    outcomes = _normalize_history_enum_list(
        value.get("outcomes", []),
        field_name="history_exclusion.outcomes",
        allowed=HISTORICAL_TARGETING_OUTCOMES,
    )
    raw_button = value.get("button_interacted", False)
    if not isinstance(raw_button, bool):
        raise MarketingCampaignV2AudienceValidationError(
            "history_exclusion.button_interacted debe ser booleano."
        )
    lookback_days = _normalize_history_lookback_days(
        value.get("lookback_days"),
        field_name="history_exclusion.lookback_days",
    )

    has_condition = bool(delivery or outcomes or raw_button)
    if not has_condition:
        if lookback_days is not None:
            raise MarketingCampaignV2AudienceValidationError(
                "history_exclusion.lookback_days requiere al menos una condición."
            )
        return None

    return {
        "delivery_buckets": list(delivery),
        "outcomes": list(outcomes),
        "button_interacted": raw_button,
        "lookback_days": lookback_days,
    }


def _normalize_history_lookback_days(
    value: Any,
    *,
    field_name: str,
) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise MarketingCampaignV2AudienceValidationError(
            f"{field_name} debe ser entero positivo o null."
        )
    try:
        lookback_days = int(value)
    except (TypeError, ValueError) as exc:
        raise MarketingCampaignV2AudienceValidationError(
            f"{field_name} debe ser entero positivo o null."
        ) from exc
    if lookback_days <= 0:
        raise MarketingCampaignV2AudienceValidationError(
            f"{field_name} debe ser entero positivo o null."
        )
    return lookback_days


def _normalize_history_enum_list(
    value: Any,
    *,
    field_name: str,
    allowed: tuple[str, ...],
) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise MarketingCampaignV2AudienceValidationError(
            f"{field_name} debe ser una lista."
        )
    allowed_set = set(allowed)
    normalized: set[str] = set()
    for raw in value:
        item = str(raw or "").strip().upper()
        if item not in allowed_set:
            raise MarketingCampaignV2AudienceValidationError(
                f"{field_name} contiene un valor no soportado."
            )
        normalized.add(item)
    return tuple(item for item in allowed if item in normalized)


def _selected_history_conditions(rule: dict[str, Any]) -> frozenset[str]:
    conditions = {
        f"HISTORY_DELIVERY_{bucket}"
        for bucket in rule["delivery_buckets"]
    }
    conditions.update(
        f"HISTORY_OUTCOME_{outcome}"
        for outcome in rule["outcomes"]
    )
    if bool(rule["button_interacted"]):
        conditions.add("HISTORY_BUTTON_INTERACTION")
    return frozenset(conditions)


def _satisfied_history_reasons(
    *,
    rule: dict[str, Any],
    ever: dict[str, Any],
) -> frozenset[str]:
    reasons: set[str] = set()
    observed_delivery = set(ever.get("delivery_buckets") or [])
    observed_outcomes = set(ever.get("outcomes") or [])

    for bucket in rule["delivery_buckets"]:
        if bucket in observed_delivery:
            reasons.add(f"HISTORY_DELIVERY_{bucket}")
    for outcome in rule["outcomes"]:
        if outcome in observed_outcomes:
            reasons.add(f"HISTORY_OUTCOME_{outcome}")
    if bool(rule["button_interacted"]) and bool(ever.get("button_interacted")):
        reasons.add("HISTORY_BUTTON_INTERACTION")
    return frozenset(reasons)


def _evaluate_historical_targeting(
    *,
    candidates: tuple[MarketingCampaignV2AudienceCandidate, ...],
    rule: dict[str, Any],
    allowed_sucursal_keys: tuple[str, ...] | None,
    session: Any,
    legacy: bool,
):
    unique_phones = tuple(
        sorted(
            {
                str(candidate.phone_mx10)
                for candidate in candidates
                if candidate.phone_mx10 is not None
            }
        )
    )
    before_count = len(unique_phones)

    if not unique_phones:
        diagnostics = (
            _empty_history_diagnostics(before_count)
            if legacy
            else _empty_historical_targeting_diagnostics(before_count)
        )
        return candidates, (), diagnostics, {
            "observed_before": None,
            "observed_after": None,
        }

    try:
        anchor = get_provider_history_for_phones(
            phones=unique_phones,
            allowed_sucursal_keys=allowed_sucursal_keys,
            max_phones=None,
            session=session,
        )
    except MarketingCampaignV2ProviderHistoryValidationError as exc:
        raise RuntimeError(
            "No fue posible evaluar histórico provider para Campaign V2."
        ) from exc

    observed_before = _max_history_observed_at(anchor)
    observed_after = None
    evaluated = anchor

    lookback_days = rule.get("lookback_days")
    if observed_before is not None and lookback_days is not None:
        observed_after = observed_before - timedelta(days=int(lookback_days))
        evaluated = get_provider_history_for_phones(
            phones=unique_phones,
            allowed_sucursal_keys=allowed_sucursal_keys,
            observed_before=observed_before,
            observed_after=observed_after,
            max_phones=None,
            session=session,
        )

    selected_conditions = _selected_history_conditions(rule)
    match_mode = str(rule["match"])
    mode = str(rule["mode"])

    representative_by_phone: dict[
        str,
        MarketingCampaignV2AudienceCandidate,
    ] = {}
    for candidate in candidates:
        if candidate.phone_mx10 is not None:
            representative_by_phone.setdefault(
                str(candidate.phone_mx10),
                candidate,
            )

    decisions_by_phone: dict[
        str,
        MarketingCampaignV2HistoricalDecisionCandidate,
    ] = {}
    matched_reason_counts: Counter[str] = Counter()

    for row in evaluated["rows"]:
        normalized_phone = str(row["normalized_phone"])
        mx10 = (
            normalized_phone[5:]
            if normalized_phone.startswith("mx10:")
            else normalized_phone
        )
        if mx10 not in representative_by_phone:
            continue

        satisfied = _satisfied_history_reasons(
            rule=rule,
            ever=row["ever_observed"],
        )
        matched = (
            selected_conditions.issubset(satisfied)
            if match_mode == "ALL"
            else bool(selected_conditions.intersection(satisfied))
        )
        keep = matched if mode == "INCLUDE" else not matched
        decision = "INCLUDED" if keep else "EXCLUDED"
        ordered_reasons = tuple(sorted(satisfied))
        decisions_by_phone[mx10] = MarketingCampaignV2HistoricalDecisionCandidate(
            candidate=representative_by_phone[mx10],
            matched=matched,
            decision=decision,
            reasons=ordered_reasons,
        )
        if matched:
            for reason in ordered_reasons:
                matched_reason_counts[reason] += 1

    # M13 returns one row for every requested phone, including phones with no history.
    # Fail closed if a custom/test implementation ever omits one.
    for phone in unique_phones:
        if phone in decisions_by_phone:
            continue
        keep = mode == "EXCLUDE"
        decisions_by_phone[phone] = MarketingCampaignV2HistoricalDecisionCandidate(
            candidate=representative_by_phone[phone],
            matched=False,
            decision="INCLUDED" if keep else "EXCLUDED",
            reasons=(),
        )

    decisions = tuple(
        decisions_by_phone[phone]
        for phone in sorted(decisions_by_phone)
    )
    matched_phones = {
        phone
        for phone, decision in decisions_by_phone.items()
        if decision.matched
    }
    included_phones = {
        phone
        for phone, decision in decisions_by_phone.items()
        if decision.decision == "INCLUDED"
    }
    excluded_phones = set(unique_phones) - included_phones

    remaining = tuple(
        candidate
        for candidate in candidates
        if candidate.phone_mx10 in included_phones
    )

    if legacy:
        diagnostics = {
            "before_history_filter_count": before_count,
            "history_excluded_count": len(excluded_phones),
            "after_history_filter_count": len(included_phones),
            "excluded_by_delivery_bucket": {
                bucket: int(
                    matched_reason_counts.get(
                        f"HISTORY_DELIVERY_{bucket}",
                        0,
                    )
                )
                for bucket in rule["delivery_buckets"]
            },
            "excluded_by_outcome": {
                outcome: int(
                    matched_reason_counts.get(
                        f"HISTORY_OUTCOME_{outcome}",
                        0,
                    )
                )
                for outcome in rule["outcomes"]
            },
            "excluded_by_button_interaction": int(
                matched_reason_counts.get(
                    "HISTORY_BUTTON_INTERACTION",
                    0,
                )
            ),
        }
    else:
        diagnostics = {
            "before_history_filter_count": before_count,
            "history_matched_count": len(matched_phones),
            "history_not_matched_count": before_count - len(matched_phones),
            "history_included_count": len(included_phones),
            "history_excluded_count": len(excluded_phones),
            "after_history_filter_count": len(included_phones),
            "matched_by_delivery_bucket": {
                bucket: int(
                    matched_reason_counts.get(
                        f"HISTORY_DELIVERY_{bucket}",
                        0,
                    )
                )
                for bucket in rule["delivery_buckets"]
            },
            "matched_by_outcome": {
                outcome: int(
                    matched_reason_counts.get(
                        f"HISTORY_OUTCOME_{outcome}",
                        0,
                    )
                )
                for outcome in rule["outcomes"]
            },
            "matched_by_button_interaction": int(
                matched_reason_counts.get(
                    "HISTORY_BUTTON_INTERACTION",
                    0,
                )
            ),
        }

    return remaining, decisions, diagnostics, {
        "observed_before": (
            observed_before.isoformat()
            if observed_before is not None
            else None
        ),
        "observed_after": (
            observed_after.isoformat()
            if observed_after is not None
            else None
        ),
    }


def _legacy_history_excluded_rows(
    decisions: tuple[MarketingCampaignV2HistoricalDecisionCandidate, ...],
) -> tuple[MarketingCampaignV2HistoryExcludedCandidate, ...]:
    return tuple(
        MarketingCampaignV2HistoryExcludedCandidate(
            candidate=row.candidate,
            reasons=row.reasons,
        )
        for row in decisions
        if row.decision == "EXCLUDED"
    )


def _apply_history_exclusion(
    *,
    candidates: tuple[MarketingCampaignV2AudienceCandidate, ...],
    rule: dict[str, Any],
    allowed_sucursal_keys: tuple[str, ...] | None,
    session: Any,
):
    """Compat M14: conserva la API interna legacy sobre el evaluator común."""
    internal_rule = {
        "mode": "EXCLUDE",
        "match": "ANY",
        **rule,
    }
    remaining, decisions, diagnostics, evaluation = _evaluate_historical_targeting(
        candidates=candidates,
        rule=internal_rule,
        allowed_sucursal_keys=allowed_sucursal_keys,
        session=session,
        legacy=True,
    )
    return (
        remaining,
        _legacy_history_excluded_rows(decisions),
        diagnostics,
        evaluation,
    )


def _empty_historical_targeting_diagnostics(
    before_count: int,
) -> dict[str, Any]:
    return {
        "before_history_filter_count": before_count,
        "history_matched_count": 0,
        "history_not_matched_count": before_count,
        "history_included_count": 0,
        "history_excluded_count": before_count,
        "after_history_filter_count": 0,
        "matched_by_delivery_bucket": {},
        "matched_by_outcome": {},
        "matched_by_button_interaction": 0,
    }


def _empty_history_diagnostics(before_count: int) -> dict[str, Any]:
    return {
        "before_history_filter_count": before_count,
        "history_excluded_count": 0,
        "after_history_filter_count": before_count,
        "excluded_by_delivery_bucket": {},
        "excluded_by_outcome": {},
        "excluded_by_button_interaction": 0,
    }


def _max_history_observed_at(result: dict[str, Any]) -> datetime | None:
    values: list[datetime] = []
    for row in result.get("rows", []):
        raw = row.get("last_observed_at")
        if raw:
            values.append(datetime.fromisoformat(str(raw)))
    return max(values) if values else None


def _load_expired_source(
    *,
    date_from: date,
    date_to: date,
    allowed_sucursal_keys: tuple[str, ...] | None,
    session: Any,
) -> _SourceLoadResult:
    rows = (
        session.query(SociosVencidosCarteraORM)
        .filter(SociosVencidosCarteraORM.fecha_vencimiento_date.between(date_from, date_to))
        .order_by(
            SociosVencidosCarteraORM.fecha_vencimiento_date.asc(),
            SociosVencidosCarteraORM.id.asc(),
        )
        .all()
    )
    # Defensive filter keeps the inclusive contract explicit even in mocked sessions.
    rows = [
        row
        for row in rows
        if date_from <= _row_expiration_date(row) <= date_to
    ]
    rows.sort(key=lambda row: (_row_expiration_date(row), int(getattr(row, "id"))))
    universe_count = len(rows)
    scoped_rows = [row for row in rows if _row_in_scope(row, allowed_sucursal_keys)]

    context = current_status.prepare_socios_vencidos_current_status_context(
        minimum_cutoff_date=date_to,
        session=session,
    )
    resolved = current_status.resolve_socios_vencidos_rows_with_context(
        vencidos_rows=scoped_rows,
        context=context,
        session=session,
    )
    status_by_id = {int(row.vencido_row_id): row for row in resolved}
    expected_ids = {int(getattr(row, "id")) for row in scoped_rows}
    if set(status_by_id) != expected_ids:
        raise RuntimeError(
            "El resolver canónico de estado actual no devolvió exactamente "
            "las filas vencidas solicitadas."
        )

    status_counts = Counter(row.status for row in resolved)
    candidates: list[MarketingCampaignV2AudienceCandidate] = []
    blocked: list[MarketingCampaignV2AudienceCandidate] = []
    for row in scoped_rows:
        status = status_by_id[int(getattr(row, "id"))]
        candidate = _expired_candidate(row, current_status_value=str(status.status))
        if status.status == current_status.STATUS_NOT_FOUND:
            candidates.append(candidate)
        else:
            blocked.append(candidate)

    return _SourceLoadResult(
        universe_count=universe_count,
        scoped_count=len(scoped_rows),
        candidates=tuple(sorted(candidates, key=_candidate_sort_key)),
        current_status_blocked=tuple(sorted(blocked, key=_candidate_sort_key)),
        current_status_counts={key: int(value) for key, value in sorted(status_counts.items())},
        metadata={
            "expired_storage": "socios_vencidos_cartera",
            "expiration_date_from": date_from.isoformat(),
            "expiration_date_to": date_to.isoformat(),
            "current_status_activos_snapshot_id": int(context.activos_snapshot_id),
            "current_status_activos_cutoff_date": str(context.activos_cutoff_date),
        },
    )


def _load_active_source(
    *,
    allowed_sucursal_keys: tuple[str, ...] | None,
    session: Any,
) -> _SourceLoadResult:
    snapshot = activos_resolver.resolve_latest_canonical_socios_activos_snapshot(
        minimum_cutoff_date=date.min,
        session=session,
    )
    if snapshot is None:
        raise MarketingCampaignV2AudienceValidationError(
            "No existe un snapshot canónico de Socios Activos disponible."
        )

    rows = (
        session.query(SociosActivosSnapshotRowORM)
        .filter(SociosActivosSnapshotRowORM.snapshot_id == int(snapshot.id))
        .order_by(
            SociosActivosSnapshotRowORM.row_index.asc(),
            SociosActivosSnapshotRowORM.id.asc(),
        )
        .all()
    )
    rows.sort(
        key=lambda row: (
            int(getattr(row, "row_index", 0)),
            int(getattr(row, "id")),
        )
    )
    universe_count = len(rows)
    scoped_rows = [row for row in rows if _row_in_scope(row, allowed_sucursal_keys)]
    candidates = tuple(
        sorted(
            (_active_candidate(row, snapshot_id=int(snapshot.id)) for row in scoped_rows),
            key=_candidate_sort_key,
        )
    )

    return _SourceLoadResult(
        universe_count=universe_count,
        scoped_count=len(scoped_rows),
        candidates=candidates,
        current_status_blocked=(),
        current_status_counts={},
        metadata={
            "activos_snapshot_id": int(snapshot.id),
            "activos_cutoff_date": _iso_date(snapshot.cutoff_date),
            "activos_captured_at": _iso_datetime(getattr(snapshot, "captured_at", None)),
            "snapshot_kind": str(getattr(snapshot, "snapshot_kind", "daily")),
        },
    )


def _expired_candidate(
    row: Any,
    *,
    current_status_value: str,
) -> MarketingCampaignV2AudienceCandidate:
    phone_raw = _optional_text(getattr(row, "telefono_raw", None))
    phone_digits = _optional_text(getattr(row, "telefono_digits", None))
    phone_mx10 = normalize_phone(phone_digits or phone_raw)
    sucursal = _optional_text(getattr(row, "sucursal_raw", None))
    sucursal_key = current_status.normalize_socios_vencidos_branch_key(
        getattr(row, "sucursal_key", None) or sucursal
    )
    return MarketingCampaignV2AudienceCandidate(
        source=SOURCE_EXPIRED_MEMBERS,
        source_ref_type="SOCIOS_VENCIDOS_CARTERA",
        source_ref_id=int(getattr(row, "id")),
        phone_raw=phone_raw or phone_digits,
        phone_mx10=phone_mx10,
        member_pin=_optional_text(getattr(row, "pin", None)),
        member_name=_optional_text(getattr(row, "nombre", None)),
        sucursal=sucursal,
        sucursal_key=sucursal_key,
        tarifa_raw=_optional_text(getattr(row, "tarifa", None)),
        fecha_vencimiento=_row_expiration_date(row),
        adeudo=_optional_decimal_value(getattr(row, "adeudo", None)),
        current_status=current_status_value,
        evidence=(f"CURRENT_STATUS:{current_status_value}",),
    )


def _active_candidate(
    row: Any,
    *,
    snapshot_id: int,
) -> MarketingCampaignV2AudienceCandidate:
    phone_raw = _optional_text(getattr(row, "telefono_raw", None))
    phone_digits = _optional_text(getattr(row, "telefono_digits", None))
    phone_mx10 = normalize_phone(phone_digits or phone_raw)
    if phone_mx10 is None:
        lada = _optional_text(getattr(row, "lada_raw", None))
        if lada and (phone_digits or phone_raw):
            phone_mx10 = normalize_phone(f"{lada}{phone_digits or phone_raw}")
    sucursal = _optional_text(getattr(row, "sucursal_raw", None))
    return MarketingCampaignV2AudienceCandidate(
        source=SOURCE_ACTIVE_MEMBERS,
        source_ref_type="SOCIOS_ACTIVOS_SNAPSHOT_ROW",
        source_ref_id=int(getattr(row, "id")),
        source_snapshot_id=snapshot_id,
        phone_raw=phone_raw or phone_digits,
        phone_mx10=phone_mx10,
        member_id=_optional_text(getattr(row, "id_socio", None)),
        member_pin=_optional_text(getattr(row, "pin", None)),
        member_name=_optional_text(getattr(row, "nombre", None)),
        sucursal=sucursal,
        sucursal_key=current_status.normalize_socios_vencidos_branch_key(sucursal),
        tarifa_raw=_optional_text(getattr(row, "tarifa", None)),
        fecha_vencimiento=_optional_date(getattr(row, "fecha_vencimiento_date", None)),
        evidence=("CANONICAL_ACTIVE_SNAPSHOT",),
    )


def _read_v2_tariff_catalog(*, session: Any) -> dict[str, tuple[str, str]]:
    snapshot_rows = (
        session.query(MarketingCampaignV2TariffORM)
        .order_by(MarketingCampaignV2TariffORM.tarifa_key.asc())
        .all()
    )
    override_rows = (
        session.query(MarketingCampaignV2TariffOverrideORM)
        .order_by(MarketingCampaignV2TariffOverrideORM.tarifa_key.asc())
        .all()
    )
    effective = {
        str(row.tarifa_key): (str(row.categoria_tarifa), str(row.audience_family))
        for row in snapshot_rows
    }
    effective.update(
        {
            str(row.tarifa_key): (
                str(row.categoria_tarifa),
                str(row.audience_family),
            )
            for row in override_rows
        }
    )
    return effective


def _classify_candidate(
    candidate: MarketingCampaignV2AudienceCandidate,
    *,
    tariff_catalog: dict[str, tuple[str, str]],
) -> MarketingCampaignV2AudienceCandidate:
    tarifa_key = normalize_marketing_tariff_key(candidate.tarifa_raw)
    match = tariff_catalog.get(tarifa_key) if tarifa_key is not None else None
    if match is None:
        return replace(
            candidate,
            tarifa_key=tarifa_key,
            categoria_tarifa=None,
            audience_family=None,
            evidence=(*candidate.evidence, "TARIFF_UNCLASSIFIED"),
        )
    categoria_tarifa, audience_family = match
    return replace(
        candidate,
        tarifa_key=tarifa_key,
        categoria_tarifa=categoria_tarifa,
        audience_family=audience_family,
        evidence=(*candidate.evidence, f"TARIFF_FAMILY:{audience_family}"),
    )


def _deduplicate_candidates(
    candidates: tuple[MarketingCampaignV2AudienceCandidate, ...],
) -> tuple[
    tuple[MarketingCampaignV2RecipientCandidate, ...],
    tuple[MarketingCampaignV2AudienceCandidate, ...],
]:
    grouped: dict[str, list[MarketingCampaignV2AudienceCandidate]] = defaultdict(list)
    for candidate in candidates:
        if candidate.phone_mx10 is None:
            raise AssertionError("Sólo teléfonos válidos pueden llegar a deduplicación.")
        grouped[candidate.phone_mx10].append(candidate)

    recipients: list[MarketingCampaignV2RecipientCandidate] = []
    duplicate_rows: list[MarketingCampaignV2AudienceCandidate] = []
    for phone in sorted(grouped):
        evidence_rows = tuple(sorted(grouped[phone], key=_candidate_sort_key))
        duplicate_rows.extend(evidence_rows[1:])
        merged, conflicts = _merge_candidate_metadata(evidence_rows)
        recipients.append(
            MarketingCampaignV2RecipientCandidate(
                source=merged["source"],
                phone_mx10=phone,
                member_id=merged["member_id"],
                member_pin=merged["member_pin"],
                member_name=merged["member_name"],
                sucursal=merged["sucursal"],
                tarifa_raw=merged["tarifa_raw"],
                tarifa_key=merged["tarifa_key"],
                categoria_tarifa=merged["categoria_tarifa"],
                audience_family=merged["audience_family"],
                fecha_vencimiento=merged["fecha_vencimiento"],
                inclusion_reason=(
                    "FUNNEL_PORTFOLIO_ELIGIBLE"
                    if merged["source"] == SOURCE_FUNNEL_PORTFOLIO
                    else "AUDIENCE_FAMILY_MATCH"
                ),
                conflict_fields=conflicts,
                evidence_rows=evidence_rows,
            )
        )
    return tuple(recipients), tuple(duplicate_rows)


def _merge_candidate_metadata(
    rows: tuple[MarketingCampaignV2AudienceCandidate, ...],
) -> tuple[dict[str, Any], tuple[str, ...]]:
    fields = (
        "source",
        "member_id",
        "member_pin",
        "member_name",
        "sucursal",
        "tarifa_raw",
        "tarifa_key",
        "categoria_tarifa",
        "audience_family",
        "fecha_vencimiento",
    )
    merged: dict[str, Any] = {}
    conflicts: list[str] = []
    for field_name in fields:
        values = []
        for row in rows:
            value = getattr(row, field_name)
            if value is not None and value not in values:
                values.append(value)
        if len(values) <= 1:
            merged[field_name] = values[0] if values else None
        else:
            merged[field_name] = None
            conflicts.append(field_name)
    if merged["source"] is None:
        raise RuntimeError("Un grupo deduplicado no puede mezclar fuentes incompatibles.")
    return merged, tuple(sorted(conflicts))


def _serialize_preview(plan: _AudiencePlan) -> dict[str, Any]:
    payload = {
        "source": plan.source,
        "source_metadata": dict(plan.source_metadata),
        "filters": dict(plan.filters),
        "universe_count": plan.universe_count,
        "scoped_count": plan.scoped_count,
        "current_status_counts": dict(plan.current_status_counts),
        "current_status_blocked_count": len(plan.current_status_blocked),
        "filtered_count": len(plan.selected_candidates),
        "family_counts": dict(plan.family_counts),
        "unclassified_family_count": plan.unclassified_family_count,
        "out_of_segment_count": plan.out_of_segment_count,
        "invalid_phone_count": len(plan.invalid_phone_rows),
        "duplicate_count": len(plan.duplicate_rows),
        "unique_recipient_count": len(plan.recipients),
    }
    if plan.source == SOURCE_FUNNEL_PORTFOLIO:
        payload.update(
            {
                "funnel_candidate_count": len(plan.funnel_candidate_rows),
                "funnel_buyer_excluded_count": len(
                    plan.funnel_buyer_excluded_rows
                ),
                "active_member_suppression_count": len(
                    plan.active_member_suppressed_rows
                ),
            }
        )
        if (
            "history_exclusion" not in plan.filters
            and "historical_targeting" not in plan.filters
        ):
            payload.update(plan.history_diagnostics)
    if (
        "history_exclusion" in plan.filters
        or "historical_targeting" in plan.filters
    ):
        payload.update(plan.history_diagnostics)
    return payload

def _bucket_rows(
    plan: _AudiencePlan,
    *,
    bucket: str,
    audience_family: str | None,
) -> list[Any]:
    if bucket == BUCKET_RECIPIENTS:
        return list(plan.recipients)
    if bucket == BUCKET_INVALID_PHONE:
        return list(plan.invalid_phone_rows)
    if bucket == BUCKET_DUPLICATES:
        return list(plan.duplicate_rows)
    if bucket == BUCKET_OUT_OF_SEGMENT:
        return [
            row for row in plan.classified_candidates
            if row.audience_family == "OUT_OF_SEGMENT"
        ]
    if bucket == BUCKET_UNCLASSIFIED:
        return [row for row in plan.classified_candidates if row.audience_family is None]
    if bucket == BUCKET_FAMILY:
        return [
            row for row in plan.classified_candidates
            if row.audience_family == audience_family
        ]
    if bucket == BUCKET_CURRENT_STATUS_BLOCKED:
        return list(plan.current_status_blocked)
    if bucket == BUCKET_HISTORY_EXCLUDED:
        if "historical_targeting" in plan.filters:
            return [
                row
                for row in plan.historical_decision_rows
                if row.decision == "EXCLUDED"
            ]
        return list(plan.history_excluded_rows)
    if bucket == BUCKET_HISTORY_INCLUDED:
        return [
            row
            for row in plan.historical_decision_rows
            if row.decision == "INCLUDED"
        ]
    if bucket == BUCKET_FUNNEL_CANDIDATES:
        return list(plan.funnel_candidate_rows)
    if bucket == BUCKET_FUNNEL_BUYER_EXCLUDED:
        return list(plan.funnel_buyer_excluded_rows)
    if bucket == BUCKET_ACTIVE_MEMBER_SUPPRESSION:
        return list(plan.active_member_suppressed_rows)
    raise AssertionError(f"Bucket no soportado: {bucket}")

def _expected_bucket_total(
    preview: dict[str, Any],
    *,
    bucket: str,
    audience_family: str | None,
) -> int:
    if bucket == BUCKET_RECIPIENTS:
        return int(preview["unique_recipient_count"])
    if bucket == BUCKET_INVALID_PHONE:
        return int(preview["invalid_phone_count"])
    if bucket == BUCKET_DUPLICATES:
        return int(preview["duplicate_count"])
    if bucket == BUCKET_OUT_OF_SEGMENT:
        return int(preview["out_of_segment_count"])
    if bucket == BUCKET_UNCLASSIFIED:
        return int(preview["unclassified_family_count"])
    if bucket == BUCKET_FAMILY:
        return int((preview["family_counts"] or {}).get(audience_family, 0))
    if bucket == BUCKET_CURRENT_STATUS_BLOCKED:
        return int(preview["current_status_blocked_count"])
    if bucket == BUCKET_HISTORY_EXCLUDED:
        return int(preview.get("history_excluded_count", 0))
    if bucket == BUCKET_HISTORY_INCLUDED:
        filters = preview.get("filters") or {}
        if (
            "historical_targeting" not in filters
            and "history_exclusion" not in filters
        ):
            return 0
        return int(
            preview.get(
                "history_included_count",
                preview.get("after_history_filter_count", 0),
            )
        )
    if bucket == BUCKET_FUNNEL_CANDIDATES:
        return int(preview.get("funnel_candidate_count", 0))
    if bucket == BUCKET_FUNNEL_BUYER_EXCLUDED:
        return int(preview.get("funnel_buyer_excluded_count", 0))
    if bucket == BUCKET_ACTIVE_MEMBER_SUPPRESSION:
        return int(preview.get("active_member_suppression_count", 0))
    raise AssertionError(f"Bucket no soportado: {bucket}")

def _serialize_preview_detail_row(
    row: Any,
    *,
    legacy_history: bool,
) -> dict[str, Any]:
    if isinstance(row, MarketingCampaignV2RecipientCandidate):
        return _serialize_recipient(row)
    if isinstance(row, MarketingCampaignV2HistoricalDecisionCandidate):
        return _serialize_historical_decision(row)
    if isinstance(row, MarketingCampaignV2HistoryExcludedCandidate):
        return _serialize_history_excluded(
            row,
            include_neutral=legacy_history,
        )
    return _serialize_candidate(row)


def _serialize_historical_decision(
    row: MarketingCampaignV2HistoricalDecisionCandidate,
) -> dict[str, Any]:
    return {
        **_serialize_candidate(row.candidate),
        "history_matched": bool(row.matched),
        "history_decision": row.decision,
        "history_reasons": list(row.reasons),
    }


def _serialize_history_excluded(
    row: MarketingCampaignV2HistoryExcludedCandidate,
    *,
    include_neutral: bool = False,
) -> dict[str, Any]:
    payload = {
        **_serialize_candidate(row.candidate),
        "history_exclusion_reasons": list(row.reasons),
    }
    if include_neutral:
        payload.update(
            {
                "history_matched": True,
                "history_decision": "EXCLUDED",
                "history_reasons": list(row.reasons),
            }
        )
    return payload


def _serialize_candidate(row: MarketingCampaignV2AudienceCandidate) -> dict[str, Any]:
    return {
        "source": row.source,
        "source_ref_type": row.source_ref_type,
        "source_ref_id": row.source_ref_id,
        "source_snapshot_id": row.source_snapshot_id,
        "phone_raw": row.phone_raw,
        "phone_mx10": row.phone_mx10,
        "member_id": row.member_id,
        "member_pin": row.member_pin,
        "member_name": row.member_name,
        "sucursal": row.sucursal,
        "sucursal_key": row.sucursal_key,
        "tarifa_raw": row.tarifa_raw,
        "tarifa_key": row.tarifa_key,
        "categoria_tarifa": row.categoria_tarifa,
        "audience_family": row.audience_family,
        "fecha_vencimiento": _iso_date(row.fecha_vencimiento),
        "adeudo": (format(row.adeudo, "f") if row.adeudo is not None else None),
        "current_status": row.current_status,
        "evidence": list(row.evidence),
    }


def _serialize_recipient(row: MarketingCampaignV2RecipientCandidate) -> dict[str, Any]:
    return {
        "source": row.source,
        "phone_mx10": row.phone_mx10,
        "member_id": row.member_id,
        "member_pin": row.member_pin,
        "member_name": row.member_name,
        "sucursal": row.sucursal,
        "tarifa_raw": row.tarifa_raw,
        "tarifa_key": row.tarifa_key,
        "categoria_tarifa": row.categoria_tarifa,
        "audience_family": row.audience_family,
        "fecha_vencimiento": _iso_date(row.fecha_vencimiento),
        "inclusion_reason": row.inclusion_reason,
        "conflict_fields": list(row.conflict_fields),
        "evidence_count": len(row.evidence_rows),
        "source_references": [
            {
                "type": evidence.source_ref_type,
                "id": evidence.source_ref_id,
                "snapshot_id": evidence.source_snapshot_id,
            }
            for evidence in row.evidence_rows
        ],
        "evidence": [_serialize_candidate(evidence) for evidence in row.evidence_rows],
    }


def _normalize_source(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in SUPPORTED_SOURCES:
        raise MarketingCampaignV2AudienceValidationError(
            "source debe ser EXPIRED_MEMBERS, ACTIVE_MEMBERS o FUNNEL_PORTFOLIO."
        )
    return normalized


def _normalize_family_selection(value: Any) -> tuple[str, ...]:
    if isinstance(value, str) or value is None:
        raise MarketingCampaignV2AudienceValidationError(
            "audience_families debe contener una o más familias seleccionables."
        )
    try:
        requested = {str(item).strip().upper() for item in value}
    except TypeError as exc:
        raise MarketingCampaignV2AudienceValidationError(
            "audience_families debe ser una colección."
        ) from exc
    requested.discard("")
    invalid = requested - set(SELECTABLE_AUDIENCE_FAMILIES)
    if invalid:
        raise MarketingCampaignV2AudienceValidationError(
            "audience_families contiene valores no seleccionables: "
            + ", ".join(sorted(invalid))
        )
    if not requested:
        raise MarketingCampaignV2AudienceValidationError(
            "audience_families debe contener al menos una familia."
        )
    return tuple(family for family in SELECTABLE_AUDIENCE_FAMILIES if family in requested)


def _normalize_scope(value: Iterable[Any] | None) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, str):
        raise MarketingCampaignV2AudienceValidationError(
            "allowed_sucursal_keys debe ser una colección o null."
        )
    normalized: set[str] = set()
    for raw in value:
        key = current_status.normalize_socios_vencidos_branch_key(raw)
        if key:
            normalized.add(key)
    return tuple(sorted(normalized))


def _row_in_scope(row: Any, allowed_sucursal_keys: tuple[str, ...] | None) -> bool:
    if allowed_sucursal_keys is None:
        return True
    raw_key = getattr(row, "sucursal_key", None) or getattr(row, "sucursal_raw", None)
    key = current_status.normalize_socios_vencidos_branch_key(raw_key)
    return key in set(allowed_sucursal_keys)


def _validate_bucket_for_source(
    *,
    source: str,
    bucket: str,
) -> None:
    if source != SOURCE_FUNNEL_PORTFOLIO:
        return
    if bucket in {
        BUCKET_OUT_OF_SEGMENT,
        BUCKET_UNCLASSIFIED,
        BUCKET_FAMILY,
        BUCKET_CURRENT_STATUS_BLOCKED,
    }:
        raise MarketingCampaignV2AudienceValidationError(
            f"bucket {bucket} no aplica a FUNNEL_PORTFOLIO."
        )


def _normalize_bucket(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in SUPPORTED_BUCKETS:
        raise MarketingCampaignV2AudienceValidationError("bucket no soportado.")
    return normalized


def _normalize_detail_family(*, bucket: str, audience_family: Any) -> str | None:
    if bucket != BUCKET_FAMILY:
        if audience_family is not None:
            raise MarketingCampaignV2AudienceValidationError(
                "audience_family sólo aplica al bucket FAMILY."
            )
        return None
    normalized = str(audience_family or "").strip().upper()
    if normalized not in set(ALL_AUDIENCE_FAMILIES):
        raise MarketingCampaignV2AudienceValidationError(
            "audience_family no es válida para el detalle FAMILY."
        )
    return normalized


def _ensure_date(value: Any, *, field_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError as exc:
            raise MarketingCampaignV2AudienceValidationError(
                f"{field_name} debe tener formato YYYY-MM-DD."
            ) from exc
    raise MarketingCampaignV2AudienceValidationError(
        f"{field_name} es obligatorio y debe ser una fecha válida."
    )


def _positive_int(value: Any, *, field_name: str, maximum: int) -> int:
    if isinstance(value, bool):
        raise MarketingCampaignV2AudienceValidationError(f"{field_name} debe ser entero positivo.")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise MarketingCampaignV2AudienceValidationError(
            f"{field_name} debe ser entero positivo."
        ) from exc
    if normalized < 1 or normalized > maximum:
        raise MarketingCampaignV2AudienceValidationError(
            f"{field_name} debe estar entre 1 y {maximum}."
        )
    return normalized


def _row_expiration_date(row: Any) -> date:
    value = getattr(row, "fecha_vencimiento_date", None)
    normalized = _optional_date(value)
    if normalized is None:
        raise RuntimeError("Una fila de socios vencidos no tiene fecha_vencimiento_date.")
    return normalized


def _optional_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError as exc:
            raise RuntimeError(f"Fecha no válida en fuente canónica: {value!r}.") from exc
    raise RuntimeError(f"Tipo de fecha no soportado en fuente canónica: {type(value)!r}.")


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _candidate_sort_key(row: MarketingCampaignV2AudienceCandidate) -> tuple[Any, ...]:
    return (
        row.phone_mx10 or "",
        row.source_ref_type,
        row.source_ref_id if row.source_ref_id is not None else 2**63 - 1,
        _iso_date(row.fecha_vencimiento) or "",
        row.sucursal_key or "",
        row.member_pin or "",
        row.member_id or "",
        row.tarifa_key or "",
        row.phone_raw or "",
    )


def _iso_date(value: Any) -> str | None:
    normalized = _optional_date(value)
    return normalized.isoformat() if normalized is not None else None


def _iso_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
