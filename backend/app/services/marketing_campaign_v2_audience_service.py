from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, datetime
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
from app.services.marketing_tariff_normalization import normalize_marketing_tariff_key
from app.warehouse.services import socios_activos_snapshot_resolver as activos_resolver
from app.warehouse.services import socios_vencidos_current_status_resolver as current_status


SOURCE_EXPIRED_MEMBERS = "EXPIRED_MEMBERS"
SOURCE_ACTIVE_MEMBERS = "ACTIVE_MEMBERS"
SUPPORTED_SOURCES = frozenset({SOURCE_EXPIRED_MEMBERS, SOURCE_ACTIVE_MEMBERS})

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

BUCKET_RECIPIENTS = "RECIPIENTS"
BUCKET_INVALID_PHONE = "INVALID_PHONE"
BUCKET_DUPLICATES = "DUPLICATES"
BUCKET_OUT_OF_SEGMENT = "OUT_OF_SEGMENT"
BUCKET_UNCLASSIFIED = "UNCLASSIFIED"
BUCKET_FAMILY = "FAMILY"
BUCKET_CURRENT_STATUS_BLOCKED = "CURRENT_STATUS_BLOCKED"
SUPPORTED_BUCKETS = frozenset(
    {
        BUCKET_RECIPIENTS,
        BUCKET_INVALID_PHONE,
        BUCKET_DUPLICATES,
        BUCKET_OUT_OF_SEGMENT,
        BUCKET_UNCLASSIFIED,
        BUCKET_FAMILY,
        BUCKET_CURRENT_STATUS_BLOCKED,
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


def build_campaign_v2_audience_preview(
    *,
    source: Any,
    audience_families: Any,
    allowed_sucursal_keys: Iterable[Any] | None,
    expiration_date_from: Any = None,
    expiration_date_to: Any = None,
    session: Any | None = None,
) -> dict[str, Any]:
    """Build a deterministic, read-only Campaign V2 audience preview."""

    plan = _build_campaign_v2_audience_plan(
        source=source,
        audience_families=audience_families,
        allowed_sucursal_keys=allowed_sucursal_keys,
        expiration_date_from=expiration_date_from,
        expiration_date_to=expiration_date_to,
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
        session=session,
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
            _serialize_recipient(row)
            if isinstance(row, MarketingCampaignV2RecipientCandidate)
            else _serialize_candidate(row)
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
    session: Any | None,
) -> _AudiencePlan:
    normalized_source = _normalize_source(source)
    selected_families = _normalize_family_selection(audience_families)
    normalized_scope = _normalize_scope(allowed_sucursal_keys)
    active_session = session if session is not None else db.session

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

    tariff_catalog = _read_v2_tariff_catalog(session=active_session)
    classified = tuple(
        _classify_candidate(candidate, tariff_catalog=tariff_catalog)
        for candidate in source_result.candidates
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
    recipients, duplicate_rows = _deduplicate_candidates(valid_rows)

    return _AudiencePlan(
        source=normalized_source,
        filters=normalized_filters,
        source_metadata=dict(source_result.metadata),
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
    )


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
                inclusion_reason="AUDIENCE_FAMILY_MATCH",
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
    return {
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
    raise AssertionError(f"Bucket no soportado: {bucket}")


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
            "source debe ser EXPIRED_MEMBERS o ACTIVE_MEMBERS."
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
