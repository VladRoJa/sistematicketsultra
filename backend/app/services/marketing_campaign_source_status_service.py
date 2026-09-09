"""Compact freshness metadata for Marketing campaign audience sources."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.models import MarketingIventasSyncRunORM
from app.models.warehouse import SociosActivosSnapshotORM, SociosVencidosSnapshotORM


TIJUANA_TZ = ZoneInfo("America/Tijuana")


def read_campaign_source_status(*, session: Any, now: datetime | None = None) -> dict[str, object]:
    now_value = now or datetime.now(timezone.utc)
    business_date = now_value.astimezone(TIJUANA_TZ).date()

    activos = (
        session.query(SociosActivosSnapshotORM)
        .filter(SociosActivosSnapshotORM.is_canonical.is_(True))
        .order_by(
            SociosActivosSnapshotORM.cutoff_date.desc(),
            SociosActivosSnapshotORM.id.desc(),
        )
        .first()
    )
    vencidos = (
        session.query(SociosVencidosSnapshotORM)
        .filter(SociosVencidosSnapshotORM.is_canonical.is_(True))
        .order_by(
            SociosVencidosSnapshotORM.business_date.desc(),
            SociosVencidosSnapshotORM.id.desc(),
        )
        .first()
    )
    iventas = (
        session.query(MarketingIventasSyncRunORM)
        .filter(
            MarketingIventasSyncRunORM.status == "COMPLETED",
            MarketingIventasSyncRunORM.is_canonical.is_(True),
        )
        .order_by(
            MarketingIventasSyncRunORM.date_to.desc(),
            MarketingIventasSyncRunORM.id.desc(),
        )
        .first()
    )

    return {
        "business_date": business_date.isoformat(),
        "sources": {
            "activos": _serialize_source(
                cutoff_date=getattr(activos, "cutoff_date", None),
                business_date=business_date,
            ),
            "vencidos": _serialize_source(
                cutoff_date=getattr(vencidos, "business_date", None),
                business_date=business_date,
            ),
            "iventas": _serialize_source(
                cutoff_date=getattr(iventas, "date_to", None),
                business_date=business_date,
            ),
        },
    }


def _serialize_source(*, cutoff_date, business_date) -> dict[str, object]:
    if cutoff_date is None:
        return {"cutoff_date": None, "age_days": None, "status": "UNAVAILABLE"}
    age_days = max((business_date - cutoff_date).days, 0)
    if age_days == 0:
        status = "CURRENT"
    elif age_days == 1:
        status = "RECENT"
    else:
        status = "STALE"
    return {
        "cutoff_date": cutoff_date.isoformat(),
        "age_days": age_days,
        "status": status,
    }
