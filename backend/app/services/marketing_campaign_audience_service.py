"""Campaign V1 selection and the temporary Suite export frequency policy."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, text

from app.models import MarketingIventasSyncRunORM
from app.services.marketing_iventas_service import normalize_iventas_phone
from app.models.marketing import MarketingReactivationCampaignORM as Campaign
from app.models.marketing import MarketingReactivationCampaignRecipientORM as Recipient
from app.models.sucursal_model import Sucursal
from app.models.suite_governance import SuiteRegionORM, SuiteSucursalRegionAssignmentORM
from app.models.warehouse import VentasNuevosSociosDetalleSnapshotORM as NewSnapshot
from app.warehouse.services.socios_vencidos_current_status_resolver import normalize_socios_vencidos_branch_key as branch_key

TZ = ZoneInfo("America/Tijuana")
TYPES = {"BASCULA_RETENCION", "PROXIMOS_VENCER", "VENCIDOS_RECIENTES", "WINBACK", "INVITA_GANA", "COBRANZA_LIGERA", "PERSONALIZADA"}
WINBACK = {"WINBACK_30": (8, 30), "WINBACK_60": (31, 60), "WINBACK_90": (61, 90)}


def week_window(now):
    today = now.astimezone(TZ).date()
    monday = today - timedelta(days=today.weekday())
    return (datetime.combine(monday, time.min, TZ).astimezone(timezone.utc),
            datetime.combine(monday + timedelta(days=7), time.min, TZ).astimezone(timezone.utc))


def exported_counts(phones, *, session, now):
    if not phones:
        return {}
    start, end = week_window(now)
    return dict(session.query(Recipient.phone_mx10, func.count(Campaign.id)).join(
        Campaign, Campaign.id == Recipient.campaign_id,
    ).filter(Campaign.status == "EXPORTED", Campaign.exported_at >= start,
             Campaign.exported_at < end, Recipient.phone_mx10.in_(sorted(phones)))
        .group_by(Recipient.phone_mx10).all())


def lock_export_phones(phones, *, session):
    # One policy lock serializes first exports until commit, independent of audience size.
    if phones and session.get_bind().dialect.name == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 0x43414D504149474E})


def region_branches(*, region_id, today, session):
    return session.query(Sucursal).join(
        SuiteSucursalRegionAssignmentORM,
        SuiteSucursalRegionAssignmentORM.sucursal_id == Sucursal.sucursal_id,
    ).join(SuiteRegionORM, SuiteRegionORM.id == SuiteSucursalRegionAssignmentORM.region_id).filter(
        SuiteRegionORM.id == region_id, SuiteRegionORM.is_active.is_(True),
        SuiteSucursalRegionAssignmentORM.is_current.is_(True),
        or_(SuiteSucursalRegionAssignmentORM.valid_from.is_(None), SuiteSucursalRegionAssignmentORM.valid_from <= today),
        or_(SuiteSucursalRegionAssignmentORM.valid_to.is_(None), SuiteSucursalRegionAssignmentORM.valid_to >= today),
    ).all()


def campaign_options(*, allowed_sucursal_keys, session, now):
    today = now.astimezone(TZ).date()
    branches = [row for row in session.query(Sucursal).order_by(Sucursal.sucursal).all()
                if allowed_sucursal_keys is None or branch_key(row.sucursal) in allowed_sucursal_keys]
    keys = {branch_key(row.sucursal) for row in branches}
    regions = []
    for region in session.query(SuiteRegionORM).filter(SuiteRegionORM.is_active.is_(True)).order_by(SuiteRegionORM.region_label).all():
        members = sorted({branch_key(row.sucursal) for row in region_branches(region_id=region.id, today=today, session=session)} & keys)
        if members:
            regions.append({"id": region.id, "label": region.region_label, "branch_keys": members})
    return {"branches": [{"key": branch_key(row.sucursal), "label": row.sucursal} for row in branches], "regions": regions}


def new_member_rows(*, today, session):
    from app.services.marketing_reactivation_service import MarketingReactivationValidationError
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    cursor = monday
    snapshots = []
    while cursor <= today:
        next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        cutoff = min(today, next_month - timedelta(days=1))
        snapshot = session.query(NewSnapshot).filter(
            NewSnapshot.report_type_key == "ventas_nuevos_socios_detalle",
            NewSnapshot.snapshot_kind == "month_to_date", NewSnapshot.is_canonical.is_(True),
            NewSnapshot.date_from == cursor.replace(day=1), NewSnapshot.date_to == cutoff,
        ).order_by(NewSnapshot.captured_at.desc(), NewSnapshot.id.desc()).first()
        if snapshot is None:
            raise MarketingReactivationValidationError(f"Falta la fuente canónica de nuevos socios con corte {cutoff.isoformat()}.")
        snapshots.append(snapshot)
        cursor = next_month
    rows = []
    for snapshot in snapshots:
        for row in sorted(snapshot.rows, key=lambda item: item.id):
            if not monday <= row.fecha_pago_at.astimezone(TZ).date() <= sunday:
                continue
            rows.append({"vencido_row_id": None, "telefono": row.telefono,
                         "nombre": " ".join(filter(None, (row.nombre, row.apellido_paterno, row.apellido_materno))),
                         "sucursal": row.sucursal_raw, "fecha_vencimiento": None,
                         "tarifa": row.tarifa, "operational_status": "AVAILABLE", "reason": "NEW_MEMBER_PAYMENT"})
    return rows, {"date_from": monday.isoformat(), "date_to": sunday.isoformat(),
                  "nuevos_snapshot_ids": [snapshot.id for snapshot in snapshots]}


def clean_contact_rows(rows, *, scope):
    """Shared phone validation and deduplication for active/new member sources."""
    eligible = []
    seen = set()
    total = invalid = duplicates = 0
    for row in rows:
        if scope is not None and branch_key(row["sucursal"]) not in scope:
            continue
        total += 1
        phone = normalize_iventas_phone(row["telefono"]).phone_mx10
        if phone is None:
            invalid += 1
        elif phone in seen:
            duplicates += 1
        else:
            seen.add(phone)
            eligible.append({**row, "phone_mx10": phone})
    return eligible, {
        "total_candidates": total, "eligible": len(eligible), "excluded_invalid_phone": invalid,
        "duplicate_phone": duplicates, "excluded_active": 0, "excluded_tariff": 0,
        "review_identity": 0, "domiciliated_flow": 0, "review_tariff": 0,
        "excluded_recent_campaign": 0, "review": 0,
    }


def prepare_v1_plan(*, filters, allowed_sucursal_keys, session, now, active_builder, expired_builder):
    from app.services import marketing_reactivation_service as service
    kind = filters.get("campaign_type")
    if not isinstance(kind, str) or kind not in TYPES:
        raise service.MarketingReactivationValidationError("Tipo de campaña no válido.")
    custom_universe = None
    allowed = {"campaign_type", "sucursal", "region_id"}
    if kind == "WINBACK":
        allowed.add("segment")
    if kind == "COBRANZA_LIGERA":
        allowed.update({"dias_desde", "dias_hasta"})
    if kind == "PERSONALIZADA":
        allowed.update({"universo", "dias_desde", "dias_hasta"})
        custom_universe = filters.get("universo")
        if custom_universe not in {"ACTIVOS", "VENCIDOS"}:
            raise service.MarketingReactivationValidationError("Selecciona un universo válido.")
        if custom_universe == "ACTIVOS" and (
            filters.get("dias_desde") is not None or filters.get("dias_hasta") is not None
        ):
            raise service.MarketingReactivationValidationError(
                "Los días vencidos solo aplican al universo de vencidos."
            )
    if set(filters) - allowed:
        raise service.MarketingReactivationValidationError("Filtros no permitidos para esta campaña.")
    today = now.astimezone(TZ).date()
    branch = service._validate_optional_text(filters.get("sucursal"), "filters.sucursal", max_length=255)
    service._validate_requested_sucursal_scope(sucursal=branch, allowed_sucursal_keys=allowed_sucursal_keys)
    scope = allowed_sucursal_keys
    region = filters.get("region_id")
    if region is not None:
        if not isinstance(region, int) or isinstance(region, bool) or region <= 0:
            raise service.MarketingReactivationValidationError("Región no válida.")
        members = {branch_key(row.sucursal) for row in region_branches(region_id=region, today=today, session=session)}
        if not members or (branch is not None and branch_key(branch) not in members):
            raise service.MarketingReactivationValidationError("La sucursal no pertenece a la región o la región no tiene sucursales vigentes.")
        scope = tuple(sorted(members if scope is None else members & set(scope)))
    service._validate_requested_sucursal_scope(sucursal=branch, allowed_sucursal_keys=scope)
    scope = service._effective_campaign_scope(sucursal=branch, allowed_sucursal_keys=scope)
    if kind in {"BASCULA_RETENCION", "PROXIMOS_VENCER"} or (
        kind == "PERSONALIZADA" and custom_universe == "ACTIVOS"
    ):
        active_kind = "BASCULA_RETENCION" if kind == "PERSONALIZADA" else kind
        plan = active_builder(filters={"campaign_type": active_kind, "sucursal": branch},
                              allowed_sucursal_keys=scope, session=session, now=now)
    elif kind == "INVITA_GANA":
        rows, sources = new_member_rows(today=today, session=session)
        eligible, summary = clean_contact_rows(rows, scope=scope)
        plan = {"sources": sources, "eligible_rows": eligible, "summary": summary}
    else:
        if kind == "VENCIDOS_RECIENTES":
            lower, upper = 1, 7
        elif kind == "WINBACK":
            if not isinstance(filters.get("segment"), str) or filters["segment"] not in WINBACK:
                raise service.MarketingReactivationValidationError("Selecciona un segmento Winback válido.")
            lower, upper = WINBACK[filters["segment"]]
        elif kind == "PERSONALIZADA":
            lower = filters.get("dias_desde")
            raw_upper = filters.get("dias_hasta")
            max_days = today.toordinal() - 1
            if (
                not isinstance(lower, int) or isinstance(lower, bool)
                or lower < 1 or lower > max_days
            ):
                raise service.MarketingReactivationValidationError(
                    "Indica desde cuántos días vencidos quieres contactar."
                )
            if raw_upper is None:
                upper = max_days
            elif (
                not isinstance(raw_upper, int) or isinstance(raw_upper, bool)
                or raw_upper < lower or raw_upper > max_days
            ):
                raise service.MarketingReactivationValidationError(
                    "El límite final debe ser igual o mayor que el inicial."
                )
            else:
                upper = raw_upper
        else:
            lower, upper = filters.get("dias_desde"), filters.get("dias_hasta")
            if any(not isinstance(value, int) or isinstance(value, bool) for value in (lower, upper)) or not 1 <= lower <= upper <= today.toordinal() - 1:
                raise service.MarketingReactivationValidationError("Indica un rango de días vencidos válido, desde 1.")
        run = session.query(MarketingIventasSyncRunORM).filter(
            MarketingIventasSyncRunORM.status == "COMPLETED", MarketingIventasSyncRunORM.is_canonical.is_(True),
        ).order_by(MarketingIventasSyncRunORM.date_to.desc(), MarketingIventasSyncRunORM.id.desc()).first()
        if run is None:
            raise service.MarketingReactivationValidationError("No hay una sincronización iVentas canónica disponible.")
        plan = expired_builder(date_from=today - timedelta(days=upper), date_to=today - timedelta(days=lower),
                               filters={"iventas_period_key": run.period_key, "sucursal": branch, "operational_status": "ALL"},
                               campaign_cooldown_days=None, allowed_sucursal_keys=scope, session=session, now=now)
    counts = exported_counts({row["phone_mx10"] for row in plan["eligible_rows"]}, session=session, now=now)
    before = len(plan["eligible_rows"])
    plan["eligible_rows"] = [row for row in plan["eligible_rows"] if counts.get(row["phone_mx10"], 0) < 2]
    plan["summary"]["excluded_weekly_limit"] = before - len(plan["eligible_rows"])
    plan["summary"]["eligible"] = len(plan["eligible_rows"])
    plan["filters"] = dict(filters)
    plan["scope"] = service._serialize_campaign_scope(scope)
    return plan
