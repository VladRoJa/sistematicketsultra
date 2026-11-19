"""M2 read-only, worker-side evidence adapter: iVentas SUCCESSFUL -> Gasca.

A sale-month report makes cross-month campaigns compete for every purchase:
all eligible proven submissions in [sale_start - lookback, sale_end] are
considered before allocating each sale. There is no provider network call,
database mutation, frontend endpoint, or per-phone output.
Not for web requests: the canonical Gasca scan belongs in a worker.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2ProviderCampaignORM,
    MarketingCampaignV2ProviderRecipientObservationORM,
    MarketingCampaignV2ProviderStatsSnapshotORM,
    MarketingCampaignV2RecipientORM,
)
from app.models.warehouse import (
    TrackBranchAliasORM,
    TrackBranchCatalogORM,
    VentaTotalSnapshotORM,
    VentaTotalSnapshotRowORM,
)
from app.services.marketing_campaign_v2_commercial_attribution_service import (
    CommercialChildResolutionError,
    required_commercial_sale_kind,
    resolve_submitted_child_recipients,
)
from app.services.marketing_campaign_v2_unique_sales_service import (
    CanonicalMembershipTransaction,
    ProvenContact,
    UniqueSalesEvidenceError,
    allocate_unique_membership_sales,
)
from app.services.marketing_phone import normalize_phone
from app.services.marketing_sales_funnel_service import _normalize_text
from app.services.marketing_campaign_v2_reporting_service import (
    _is_valid_status,
    _is_membership_purchase_row,
    _parse_venta_total_row_local_datetime,
    _NON_MEMBERSHIP_PREFIXES,
)

_TZ = ZoneInfo("America/Tijuana")
_MAX_CONTACT_PROOFS = 300_000
_MAX_GASCA_ROWS_SCANNED = 1_000_000


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise UniqueSalesEvidenceError("La evidencia no contiene fecha de envío válida.")
    if value.tzinfo is None:
        # Existing SQLAlchemy PostgreSQL sessions return UTC datetimes, while
        # SQLite tests may return naive timestamps; align to existing services.
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _month_window(from_date: str, to_date: str, *, window_days: int):
    if window_days not in (7, 14, 30) or type(window_days) is not int:
        raise UniqueSalesEvidenceError("Ventana de 7, 14 o 30 días requerida.")
    try:
        first = date.fromisoformat(from_date)
        last = date.fromisoformat(to_date)
    except (ValueError, TypeError) as exc:
        raise UniqueSalesEvidenceError("Fechas de venta inválidas YYYY-MM-DD.") from exc
    if (first.isoformat() != from_date or last.isoformat() != to_date
            or last < first or (first.year, first.month) != (last.year, last.month)):
        raise UniqueSalesEvidenceError("Selecciona un rango dentro del mismo mes.")
    sent_start = datetime.combine(first - timedelta(days=window_days), time.min, _TZ).astimezone(timezone.utc)
    sale_start = datetime.combine(first, time.min, _TZ).astimezone(timezone.utc)
    sale_end = datetime.combine(last + timedelta(days=1), time.min, _TZ).astimezone(timezone.utc)
    return first, last, sent_start, sale_start, sale_end


def _base(*, first: date, last: date, window_days: int, status: str, reason: str | None = None) -> dict:
    return {
        "status": status, "source": "VENTA_TOTAL_CANONICAL_SALE_MONTH",
        "from": first.isoformat(), "to": last.isoformat(), "window_days": window_days,
        "timezone": "America/Tijuana",
        "revenue_observed_mxn": None,
        "transactions_observed": None,
        "buyers_observed": None,
        "campaigns": None,
        "reason": reason,
        "disclaimer": "Venta posterior al envío probado; no demuestra causalidad.",
    }


def _proven_contacts(*, children, recipients, snapshots, observations):
    """Resolve frozen->actually sent->latest successful provider observation."""
    children_by_campaign = defaultdict(list)
    for child in children:
        children_by_campaign[int(child.campaign_v2_id)].append(child)
    recipients_by_campaign = defaultdict(list)
    for recipient in recipients:
        recipients_by_campaign[int(recipient.campaign_id)].append(recipient)

    scopes = {}
    for campaign_id, group in children_by_campaign.items():
        scopes[campaign_id] = resolve_submitted_child_recipients(
            campaign_id=campaign_id, children=group,
            frozen_recipients=recipients_by_campaign[campaign_id],
        )
        if scopes[campaign_id].unresolved_child_ids:
            raise UniqueSalesEvidenceError("Hay lotes de envío con estado no verificable.")
    latest = {}
    for snapshot in sorted(
        snapshots, key=lambda row: (_utc(row.fetched_at), int(row.id)), reverse=True
    ):
        identity = (int(snapshot.campaign_v2_id), str(snapshot.provider_campaign_id))
        latest.setdefault(identity, snapshot)

    snapshot_to_scope = {}
    for campaign_id, resolved in scopes.items():
        for submitted in resolved.submitted:
            snap = latest.get((campaign_id, submitted.provider_campaign_id))
            if snap is None:
                raise UniqueSalesEvidenceError("Falta snapshot iVentas de un lote enviado.")
            if snap.analytics_status != "ok" and int(snap.raw_successful) == 0:
                raise UniqueSalesEvidenceError("Snapshot iVentas todavía sin captura exitosa.")
            if int(snap.id) in snapshot_to_scope:
                raise UniqueSalesEvidenceError("Snapshot duplicado entre dos children.")
            snapshot_to_scope[int(snap.id)] = (submitted, dict(submitted.recipients), snap)

    successful = defaultdict(set)
    for observation in observations:
        source = snapshot_to_scope.get(int(observation.snapshot_id))
        if source is None or observation.outcome != "SUCCESSFUL":
            continue
        child, recipient_by_phone, _ = source
        raw = observation.normalized_phone
        phone = normalize_phone(
            raw[5:] if isinstance(raw, str) and raw.startswith("mx10:") else raw
        )
        if (phone is None or observation.campaign_recipient_id is None
                or recipient_by_phone.get(phone) != int(observation.campaign_recipient_id)):
            raise UniqueSalesEvidenceError("Observación SUCCESSFUL fuera del lote enviado.")
        successful[int(child.child_id)].add(phone)

    proofs = []
    for child, recipient_by_phone, snap in snapshot_to_scope.values():
        phones = successful.get(int(child.child_id), set())
        if len(phones) != int(snap.raw_successful):
            raise UniqueSalesEvidenceError("Cobertura de exitosos iVentas no coincide con snapshot.")
        proofs.extend((child, phone) for phone in sorted(phones))
    if len(proofs) > _MAX_CONTACT_PROOFS:
        raise UniqueSalesEvidenceError("El volumen excede el límite del proceso de conciliación.")
    return proofs


def _group_gasca_orders(
    *, rows, contact_identities: set[tuple[str, int, str]],
    branch_aliases: dict[str, int], first: date, last: date, snapshot_id: int,
):
    """Filter real membership rows before order-level sum, no per-line conversions."""
    grouped = {}
    scanned = 0
    phones_and_kinds = {(phone, kind) for phone, _, kind in contact_identities}
    first_utc = datetime.combine(first, time.min, _TZ).astimezone(timezone.utc)
    last_utc = datetime.combine(last + timedelta(days=1), time.min, _TZ).astimezone(timezone.utc)
    for row in rows:
        scanned += 1
        if scanned > _MAX_GASCA_ROWS_SCANNED:
            raise UniqueSalesEvidenceError("Corte Gasca demasiado grande para conciliación acotada.")
        phone = normalize_phone(row.telefono)
        if phone is None:
            continue
        kind = _normalize_text(getattr(row, "nuevo", None))
        if kind not in {"NUEVO", "REACTIVACION"}:
            continue
        branch = branch_aliases.get(_normalize_text(row.sucursal))
        if branch is None:
            if (phone, kind) in phones_and_kinds:
                raise UniqueSalesEvidenceError("Sucursal Gasca sin alias verificable para un contacto.")
            continue
        if (phone, branch, kind) not in contact_identities:
            continue
        if (not _is_valid_status(row.estatus)
                or _normalize_text(row.descripcion).startswith(_NON_MEMBERSHIP_PREFIXES)
                or not _is_membership_purchase_row(row)):
            continue
        occurred_at = _parse_venta_total_row_local_datetime(row)
        if occurred_at is None:
            raise UniqueSalesEvidenceError("Compra de membresía sin fecha/hora verificable.")
        occurred_utc = _utc(occurred_at)
        if not first_utc <= occurred_utc < last_utc:
            continue
        try:
            amount = Decimal(str(row.total))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise UniqueSalesEvidenceError("Importe Gasca inválido.") from exc
        if not amount.is_finite():
            raise UniqueSalesEvidenceError("Importe Gasca no finito.")
        order = str(row.id_orden or "").strip()
        folio = str(row.folio or "").strip()
        key = ("order:" + order if order else "folio:" + folio if folio
               else "row:" + str(row.id))
        identity = (phone, branch, kind, key)
        old = grouped.get(identity)
        if old is None:
            grouped[identity] = [occurred_utc, amount]
        else:
            if abs((occurred_utc - old[0]).total_seconds()) > 600:
                raise UniqueSalesEvidenceError("Orden Gasca con horas incompatibles.")
            old[0] = min(old[0], occurred_utc)
            old[1] += amount

    out = []
    for (phone, branch, kind, key), (occurred, amount) in grouped.items():
        if amount <= 0:
            continue
        out.append(CanonicalMembershipTransaction(
            transaction_key=key, branch_id=branch,
            phone_mx10=phone, sale_kind=kind,
            occurred_at=occurred, amount_mxn=amount,
            venta_total_snapshot_id=snapshot_id,
        ))
    return out, scanned


def reconcile_sale_month(
    *, from_date: str, to_date: str, window_days: int, session=None,
) -> dict:
    """Worker-only, read-only end-to-end correlation by SALE date (not send month).

    No results are considered complete until the canonical Venta Total has
    business_date >= to_date and capture timestamp after the day ends.
    A consumer must materialize this result in a governed job, not run via GET.
    """
    first, last, sent_start, sale_start, sale_end = _month_window(
        from_date, to_date, window_days=window_days
    )
    base = _base(first=first, last=last, window_days=window_days, status="PENDING")
    active = session if session is not None else db.session
    Child = MarketingCampaignV2ProviderCampaignORM
    Campaign = MarketingCampaignV2ORM
    Snapshot = MarketingCampaignV2ProviderStatsSnapshotORM
    Obs = MarketingCampaignV2ProviderRecipientObservationORM

    with active.no_autoflush:
        children_and_campaigns = (
            active.query(Child, Campaign).join(Campaign, Campaign.id == Child.campaign_v2_id)
            .filter(Child.provider == "IVENTAS", Child.status == "SUBMITTED",
                    Child.submitted_at >= sent_start, Child.submitted_at < sale_end)
            .all()
        )
        eligible = [
            (child, campaign, required_commercial_sale_kind(
                purpose=campaign.purpose, source=campaign.source))
            for child, campaign in children_and_campaigns
        ]
        eligible = [(child, campaign, kind) for child, campaign, kind in eligible
                    if kind in {"NUEVO", "REACTIVACION"}]
        if not eligible:
            return {**base, "status": "NO_ELIGIBLE_CONTACTS"}
        campaign_ids = {int(c.id) for _, c, _ in eligible}
        campaign_kind = {int(c.id): kind for _, c, kind in eligible}
        children = [child for child, _, _ in eligible]
        snapshots = (
            active.query(Snapshot).filter(
                Snapshot.campaign_v2_id.in_(sorted(campaign_ids)),
                Snapshot.provider == "IVENTAS",
            ).all()
        )
        latest_snapshot_ids = {}
        valid_identities = {
            (int(child.campaign_v2_id), str(child.provider_campaign_id)) for child in children
        }
        for snapshot in sorted(
            snapshots, key=lambda row: (_utc(row.fetched_at), int(row.id)), reverse=True
        ):
            identity = (int(snapshot.campaign_v2_id), str(snapshot.provider_campaign_id))
            if identity in valid_identities:
                latest_snapshot_ids.setdefault(identity, int(snapshot.id))
        recipients = (
            active.query(MarketingCampaignV2RecipientORM).filter(
                MarketingCampaignV2RecipientORM.campaign_id.in_(sorted(campaign_ids)),
            ).all()
        )
        observations = (
            active.query(Obs).filter(
                Obs.snapshot_id.in_(sorted(latest_snapshot_ids.values())),
                Obs.outcome == "SUCCESSFUL",
            ).all()
        ) if latest_snapshot_ids else []
        try:
            proof_rows = _proven_contacts(
                children=children, recipients=recipients,
                snapshots=snapshots, observations=observations,
            )
        except (CommercialChildResolutionError, UniqueSalesEvidenceError) as exc:
            return {**base, "status": "PENDING_PROVIDER_EVIDENCE", "reason": str(exc)}

        contacts = []
        for child, phone in proof_rows:
            contacts.append(ProvenContact(
                campaign_id=int(child.campaign_v2_id), child_id=int(child.child_id),
                provider_campaign_id=child.provider_campaign_id,
                branch_id=int(child.sucursal_id), phone_mx10=phone,
                sale_kind=campaign_kind[int(child.campaign_v2_id)],
                submitted_at=_utc(child.submitted_at),
            ))
        # A valid empty success cohort still requires an actual canonical cut.
        month_end = (
            date(last.year + 1, 1, 1) if last.month == 12
            else date(last.year, last.month + 1, 1)
        )
        venta = (
            active.query(VentaTotalSnapshotORM)
            .filter(
                VentaTotalSnapshotORM.report_type_key == "venta_total",
                VentaTotalSnapshotORM.snapshot_kind == "daily",
                VentaTotalSnapshotORM.is_canonical.is_(True),
                VentaTotalSnapshotORM.business_date >= last,
                VentaTotalSnapshotORM.business_date < month_end,
                VentaTotalSnapshotORM.captured_at >= sale_end,
            ).order_by(
                VentaTotalSnapshotORM.business_date.desc(),
                VentaTotalSnapshotORM.captured_at.desc(),
                VentaTotalSnapshotORM.id.desc(),
            ).first()
        )
        if venta is None:
            return {**base, "status": "PENDING_CANONICAL_SALES"}
        aliases = (
            active.query(TrackBranchAliasORM, TrackBranchCatalogORM)
            .join(TrackBranchCatalogORM,
                  TrackBranchCatalogORM.sucursal_canon == TrackBranchAliasORM.sucursal_canon)
            .filter(
                TrackBranchAliasORM.source_family == "gasca_family",
                TrackBranchAliasORM.is_active.is_(True),
                TrackBranchCatalogORM.is_track_active.is_(True),
                TrackBranchCatalogORM.sucursal_id.isnot(None),
            ).all()
        )
        alias_map = {}
        for alias, branch in aliases:
            alias_name = _normalize_text(alias.raw_branch_name)
            resolved = int(branch.sucursal_id)
            if alias_name in alias_map and alias_map[alias_name] != resolved:
                return {**base, "status": "PENDING_ALIAS_CONFLICT"}
            alias_map[alias_name] = resolved
        identities = {(c.phone_mx10, c.branch_id, c.sale_kind) for c in contacts}
        try:
            rows = (
                active.query(VentaTotalSnapshotRowORM)
                .filter(VentaTotalSnapshotRowORM.snapshot_id == venta.id)
                .yield_per(1000)
            )
            sales, scanned = _group_gasca_orders(
                rows=rows, contact_identities=identities, branch_aliases=alias_map,
                first=first, last=last, snapshot_id=int(venta.id),
            )
            result = allocate_unique_membership_sales(
                contacts=contacts, transactions=sales, window_days=window_days,
            )
        except UniqueSalesEvidenceError as exc:
            return {**base, "status": "PENDING_SALES_EVIDENCE", "reason": str(exc)}
        # Do not expose individual transaction references or phones.
        result.pop("allocations_private", None)
        return {
            **base,
            **result,
            "status": "READY",
            "source": "VENTA_TOTAL_CANONICAL_SALE_MONTH",
            "from": first.isoformat(), "to": last.isoformat(),
            "timezone": "America/Tijuana",
            "sale_snapshot_id": int(venta.id),
            "sale_business_date": venta.business_date.isoformat(),
            "contacts_proven": len(contacts),
            "gasca_rows_scanned": scanned,
            "buyer_count_note": "buyers_observed por campaña; un teléfono puede comprar en más de una campaña/operación.",
        }
