from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.extensions import db
from app.models.marketing import (
    MarketingIventasContactORM,
    MarketingIventasContactTagORM,
    MarketingIventasSyncRunORM,
    MarketingReactivationCampaignRecipientORM,
)


TZ = ZoneInfo("America/Tijuana")
UTC = timezone.utc


def _session_or_default(session: Any | None):
    return session if session is not None else db.session


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _as_aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _to_tijuana_local_iso(value: datetime | None) -> str | None:
    aware = _as_aware_utc(value)
    if aware is None:
        return None
    return aware.astimezone(TZ).replace(tzinfo=None).isoformat()


def _parse_iso_utc(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _latest_canonical_run(*, session: Any):
    return (
        session.query(MarketingIventasSyncRunORM)
        .filter(MarketingIventasSyncRunORM.is_canonical.is_(True))
        .order_by(
            MarketingIventasSyncRunORM.date_to.desc(),
            MarketingIventasSyncRunORM.finished_at.desc(),
            MarketingIventasSyncRunORM.id.desc(),
        )
        .first()
    )


def _recipient_phones(
    *,
    recipient_ids: list[int],
    session: Any,
) -> dict[int, str]:
    if not recipient_ids:
        return {}
    rows = (
        session.query(
            MarketingReactivationCampaignRecipientORM.id,
            MarketingReactivationCampaignRecipientORM.phone_mx10,
        )
        .filter(
            MarketingReactivationCampaignRecipientORM.id.in_(
                tuple(sorted(set(recipient_ids)))
            )
        )
        .all()
    )
    return {
        int(recipient_id): str(phone_mx10)
        for recipient_id, phone_mx10 in rows
        if phone_mx10 is not None
    }


def _contact_sort_key(contact: MarketingIventasContactORM):
    return (
        _as_aware_utc(contact.last_outbound_message_at_utc)
        or _as_aware_utc(contact.first_message_at_utc)
        or _as_aware_utc(contact.created_at_utc)
        or datetime.min.replace(tzinfo=UTC),
        int(contact.id),
    )


def _contacts_by_phone(
    *,
    sync_run_id: int,
    phones: set[str],
    session: Any,
) -> dict[str, list[MarketingIventasContactORM]]:
    if not phones:
        return {}
    contacts = (
        session.query(MarketingIventasContactORM)
        .filter(
            MarketingIventasContactORM.sync_run_id == int(sync_run_id),
            MarketingIventasContactORM.phone_mx10.in_(tuple(sorted(phones))),
        )
        .all()
    )
    grouped: dict[str, list[MarketingIventasContactORM]] = defaultdict(list)
    for contact in contacts:
        if contact.phone_mx10 is None:
            continue
        grouped[str(contact.phone_mx10)].append(contact)
    for values in grouped.values():
        values.sort(key=_contact_sort_key, reverse=True)
    return dict(grouped)


def _tags_by_contact_row(
    *,
    contact_row_ids: set[int],
    session: Any,
) -> dict[int, list[str]]:
    if not contact_row_ids:
        return {}
    rows = (
        session.query(
            MarketingIventasContactTagORM.iventas_contact_row_id,
            MarketingIventasContactTagORM.tag_raw,
        )
        .filter(
            MarketingIventasContactTagORM.iventas_contact_row_id.in_(
                tuple(sorted(contact_row_ids))
            )
        )
        .order_by(
            MarketingIventasContactTagORM.iventas_contact_row_id.asc(),
            MarketingIventasContactTagORM.tag_raw.asc(),
        )
        .all()
    )
    result: dict[int, list[str]] = defaultdict(list)
    for contact_row_id, tag_raw in rows:
        result[int(contact_row_id)].append(str(tag_raw))
    return dict(result)


def _agent_name(agent_json: Any) -> str | None:
    if not isinstance(agent_json, dict):
        return None
    value = str(agent_json.get("name") or "").strip()
    return value or None


def _activity_after_send(
    *,
    last_outbound: datetime | None,
    sent_at: Any,
) -> bool | None:
    outbound_utc = _as_aware_utc(last_outbound)
    sent_utc = _parse_iso_utc(sent_at)
    if outbound_utc is None or sent_utc is None:
        return None
    return outbound_utc >= sent_utc


def _empty_iventas_context(*, phone: str | None) -> dict[str, Any]:
    return {
        "phone_mx10": phone,
        "iventas_contact_found": False,
        "iventas_match_status": "NOT_FOUND",
        "iventas_match_count": 0,
        "iventas_contact_id": None,
        "iventas_name": None,
        "iventas_branch_code": None,
        "iventas_created_at_local": None,
        "iventas_first_message_at_local": None,
        "iventas_last_outbound_at_local": None,
        "iventas_last_message_status": None,
        "iventas_channel_name": None,
        "iventas_channel_platform": None,
        "iventas_agent_name": None,
        "iventas_tags": [],
        "iventas_is_from_ads": None,
        "iventas_ads_source_id": None,
        "iventas_activity_after_send": None,
    }


def enrich_campaign_outcome_detail_with_iventas(
    result: dict[str, Any],
    *,
    session: Any | None = None,
) -> dict[str, Any]:
    """Add read-only iVentas context to sent campaign recipients.

    The enrichment is observational only. lastMessageStatus and
    lastOutboundMessageAt describe the latest state exposed by iVentas for the
    selected contact and must not be interpreted as proof that this specific
    Suite campaign was delivered/read.
    """

    active_session = _session_or_default(session)
    rows = result.get("rows")
    if not isinstance(rows, list):
        return result

    recipient_ids = [
        int(row["recipient_id"])
        for row in rows
        if isinstance(row, dict) and row.get("recipient_id") is not None
    ]
    phones_by_recipient = _recipient_phones(
        recipient_ids=recipient_ids,
        session=active_session,
    )

    run = _latest_canonical_run(session=active_session)
    result["iventas_source"] = {
        "available": run is not None,
        "sync_run_id": int(run.id) if run is not None else None,
        "period_key": str(run.period_key) if run is not None else None,
        "date_from": _iso(run.date_from) if run is not None else None,
        "date_to": _iso(run.date_to) if run is not None else None,
        "finished_at": _iso(run.finished_at) if run is not None else None,
    }

    if run is None:
        for row in rows:
            if not isinstance(row, dict):
                continue
            phone = phones_by_recipient.get(int(row.get("recipient_id") or 0))
            row.update(_empty_iventas_context(phone=phone))
        return result

    phones = set(phones_by_recipient.values())
    contacts_by_phone = _contacts_by_phone(
        sync_run_id=int(run.id),
        phones=phones,
        session=active_session,
    )
    chosen_contact_ids = {
        int(contacts[0].id)
        for contacts in contacts_by_phone.values()
        if contacts
    }
    tags_by_contact = _tags_by_contact_row(
        contact_row_ids=chosen_contact_ids,
        session=active_session,
    )

    for row in rows:
        if not isinstance(row, dict):
            continue
        recipient_id = int(row.get("recipient_id") or 0)
        phone = phones_by_recipient.get(recipient_id)
        context = _empty_iventas_context(phone=phone)
        matches = contacts_by_phone.get(phone or "", [])
        if not matches:
            row.update(context)
            continue

        contact = matches[0]
        context.update(
            {
                "iventas_contact_found": True,
                "iventas_match_status": "MATCHED" if len(matches) == 1 else "MULTIPLE",
                "iventas_match_count": len(matches),
                "iventas_contact_id": str(contact.contact_id),
                "iventas_name": contact.name,
                "iventas_branch_code": contact.branch_code,
                "iventas_created_at_local": _iso(contact.created_at_local),
                "iventas_first_message_at_local": _iso(contact.first_message_at_local),
                "iventas_last_outbound_at_local": _to_tijuana_local_iso(
                    contact.last_outbound_message_at_utc
                ),
                "iventas_last_message_status": contact.last_message_status,
                "iventas_channel_name": contact.channel_name,
                "iventas_channel_platform": contact.channel_platform,
                "iventas_agent_name": _agent_name(contact.agent_json),
                "iventas_tags": tags_by_contact.get(int(contact.id), []),
                "iventas_is_from_ads": contact.is_from_ads,
                "iventas_ads_source_id": contact.ads_source_id,
                "iventas_activity_after_send": _activity_after_send(
                    last_outbound=contact.last_outbound_message_at_utc,
                    sent_at=row.get("sent_at"),
                ),
            }
        )
        row.update(context)

    return result
