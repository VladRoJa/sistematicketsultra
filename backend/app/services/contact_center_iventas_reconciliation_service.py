"""Reconciliación iVentas -> Contact Center por teléfono MX10.

Regla:
- sólo trabaja sobre un sync_run COMPLETED + canónico;
- sólo considera filas que cumplen la semántica canónica del Funnel;
- autovincula únicamente cuando existe exactamente un contacto CC activo
  con el mismo phone_mx10;
- nunca fusiona contactos ni decide entre coincidencias ambiguas.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.extensions import db
from app.models import (
    MarketingIventasContactORM,
    MarketingIventasSyncRunORM,
)
from app.models.contact_center import (
    ContactCenterContactLinkORM,
    ContactCenterContactORM,
)
from app.services.marketing_leads_detail_service import (
    build_marketing_lead_contacts_statement,
)


@dataclass(frozen=True)
class ContactCenterIventasReconciliationResult:
    sync_run_id: int
    leads_scanned: int
    links_created: int
    already_linked: int
    no_contact_match: int
    ambiguous_contact_match: int


def _session_or_default(session: Any | None):
    return session if session is not None else db.session


def reconcile_contact_center_iventas_run(
    *,
    sync_run_id: int,
    session: Any | None = None,
) -> ContactCenterIventasReconciliationResult:
    session_value = _session_or_default(session)

    run = session_value.get(
        MarketingIventasSyncRunORM,
        int(sync_run_id),
    )
    if run is None:
        raise ValueError("No existe el sync_run iVentas indicado.")
    if run.status != "COMPLETED" or not bool(run.is_canonical):
        raise ValueError(
            "La reconciliación requiere un sync_run COMPLETED y canónico."
        )

    branch_ids = tuple(
        int(row[0])
        for row in (
            session_value.query(
                MarketingIventasContactORM.sucursal_id
            )
            .filter(
                MarketingIventasContactORM.sync_run_id == int(sync_run_id)
            )
            .distinct()
            .all()
        )
    )
    if not branch_ids:
        return ContactCenterIventasReconciliationResult(
            sync_run_id=int(sync_run_id),
            leads_scanned=0,
            links_created=0,
            already_linked=0,
            no_contact_match=0,
            ambiguous_contact_match=0,
        )

    statement = (
        build_marketing_lead_contacts_statement(
            iventas_sync_run_id=int(sync_run_id),
            branch_ids=branch_ids,
        )
        .where(
            MarketingIventasContactORM.phone_mx10.isnot(None)
        )
    )
    lead_rows = session_value.execute(statement).mappings().all()

    contacts_by_phone: dict[str, list[ContactCenterContactORM]] = {}
    contacts = (
        session_value.query(ContactCenterContactORM)
        .filter(
            ContactCenterContactORM.is_active.is_(True),
            ContactCenterContactORM.merged_into_contact_id.is_(None),
            ContactCenterContactORM.phone_mx10.isnot(None),
        )
        .all()
    )
    for contact in contacts:
        phone = str(contact.phone_mx10 or "").strip()
        if phone:
            contacts_by_phone.setdefault(phone, []).append(contact)

    existing_links = {
        str(row.source_key): int(row.contact_id)
        for row in (
            session_value.query(ContactCenterContactLinkORM)
            .filter(
                ContactCenterContactLinkORM.source_type
                == "IVENTAS_CONTACT"
            )
            .all()
        )
    }

    links_created = 0
    already_linked = 0
    no_contact_match = 0
    ambiguous_contact_match = 0

    for row in lead_rows:
        branch_id = int(row["sucursal_id"])
        source_key = f"{branch_id}:{str(row['contact_id'])}"

        if source_key in existing_links:
            already_linked += 1
            continue

        phone = str(row.get("phone_mx10") or "").strip()
        matches = contacts_by_phone.get(phone, [])

        if not matches:
            no_contact_match += 1
            continue

        if len(matches) != 1:
            ambiguous_contact_match += 1
            continue

        contact = matches[0]
        session_value.add(
            ContactCenterContactLinkORM(
                contact_id=int(contact.id),
                source_type="IVENTAS_CONTACT",
                source_key=source_key,
                source_row_id=int(row["contact_row_id"]),
                source_metadata_json={
                    "sync_run_id": int(sync_run_id),
                    "contact_id": str(row["contact_id"]),
                    "branch_code": str(row.get("branch_code") or ""),
                    "matched_by": "PHONE_MX10",
                },
            )
        )
        existing_links[source_key] = int(contact.id)
        links_created += 1

    session_value.commit()

    return ContactCenterIventasReconciliationResult(
        sync_run_id=int(sync_run_id),
        leads_scanned=len(lead_rows),
        links_created=links_created,
        already_linked=already_linked,
        no_contact_match=no_contact_match,
        ambiguous_contact_match=ambiguous_contact_match,
    )