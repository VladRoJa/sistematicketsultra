"""Builds campaign delivery files from frozen recipients.

The campaign audience remains frozen by the existing campaign service. This
module only changes the delivery package: one XLSX for one branch, or a ZIP
with one XLSX per branch plus a summary when several branches are present.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from io import BytesIO
import re
import unicodedata
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import Workbook

from app.extensions import db
from app.models.marketing import MarketingReactivationCampaignORM
from app.models.sucursal_model import Sucursal
from app.models.warehouse import TrackBranchCatalogORM
from app.services.marketing_reactivation_service import (
    CAMPAIGN_STATUS_DRAFT,
    CAMPAIGN_STATUS_EXPORTED,
    MarketingReactivationConflictError,
    MarketingReactivationValidationError,
    export_marketing_reactivation_campaign as _validate_and_mark_exported,
    get_marketing_reactivation_campaign,
)
from app.warehouse.services.socios_vencidos_current_status_resolver import (
    normalize_socios_vencidos_branch_key,
)


XLSX_MIMETYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
ZIP_MIMETYPE = "application/zip"
WEEKLY_FREQUENCY_KEEP = "KEEP"
_LOWERCASE_MESSAGE_WORDS = frozenset({"de", "del", "el", "la", "las", "los", "y"})
_SHORT_NAME_ABBREVIATIONS = frozenset({"MA", "MA."})
_SHORT_NAME_CONNECTORS = frozenset({"DE", "DEL", "EL", "LA", "LAS", "LOS", "Y"})


def campaign_export_mimetype(filename: str) -> str:
    return ZIP_MIMETYPE if str(filename).lower().endswith(".zip") else XLSX_MIMETYPE


def export_marketing_reactivation_campaign(
    *,
    campaign_id: int,
    allowed_sucursal_keys: tuple[str, ...] | None = None,
    session: Any | None = None,
    now=None,
) -> tuple[bytes, str]:
    """Returns files ready to upload from each club's iVentas profile.

    The package is built only from frozen recipients. The existing exporter is
    still called first so scope, status and the weekly-frequency guard remain
    the source of truth. A frozen KEEP decision only overrides that final
    frequency conflict; it does not bypass any other export validation.
    """

    campaign = get_marketing_reactivation_campaign(
        campaign_id=campaign_id,
        session=session,
    )
    recipients = list(campaign.get("recipients") or [])
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for recipient in recipients:
        branch = str(recipient.get("sucursal") or "SIN SUCURSAL").strip()
        groups[branch].append(recipient)

    branch_message_labels = _branch_message_labels(session=session)
    campaign_part = _filename_part(
        campaign.get("name"),
        fallback=f"CAMPANA_{int(campaign_id)}",
    )
    export_bytes, filename = _build_delivery_package(
        campaign_part=campaign_part,
        groups=groups,
        branch_message_labels=branch_message_labels,
    )

    try:
        # Run the existing guarded export after the package is safely built. Its
        # workbook is intentionally discarded; validation/state transition is
        # preserved without rebuilding the frozen audience.
        _validate_and_mark_exported(
            campaign_id=campaign_id,
            allowed_sucursal_keys=allowed_sucursal_keys,
            session=session,
            now=now,
        )
    except MarketingReactivationConflictError:
        if _frozen_weekly_frequency_action(campaign) != WEEKLY_FREQUENCY_KEEP:
            raise
        # The guarded exporter reaches its frequency conflict only after it has
        # validated state and frozen scope and acquired the export lock. KEEP is
        # therefore allowed to override exactly that conflict, nothing else.
        _mark_keep_override_exported(
            campaign_id=campaign_id,
            session=session,
            now=now,
        )
    return export_bytes, filename


def _frozen_weekly_frequency_action(campaign: dict[str, Any]) -> str | None:
    filters = campaign.get("filters")
    if not isinstance(filters, dict):
        return None
    action = filters.get("weekly_frequency_action")
    return str(action) if action is not None else None


def _mark_keep_override_exported(
    *,
    campaign_id: int,
    session: Any | None,
    now,
) -> None:
    active_session = session if session is not None else db.session
    campaign = (
        active_session.query(MarketingReactivationCampaignORM)
        .filter(MarketingReactivationCampaignORM.id == campaign_id)
        .one()
    )
    if campaign.status == CAMPAIGN_STATUS_EXPORTED:
        return
    if campaign.status != CAMPAIGN_STATUS_DRAFT:
        raise MarketingReactivationConflictError(
            "La campaña cambió de estado antes de completar la exportación."
        )
    now_value = now if now is not None else datetime.now(timezone.utc)
    campaign.status = CAMPAIGN_STATUS_EXPORTED
    campaign.exported_at = now_value
    campaign.updated_at = now_value
    try:
        active_session.commit()
    except Exception:
        active_session.rollback()
        raise


def _message_branch_label(value: Any) -> str:
    words = " ".join(str(value or "").split()).split(" ")
    rendered: list[str] = []
    for index, word in enumerate(words):
        lowered = word.lower()
        if index > 0 and lowered in _LOWERCASE_MESSAGE_WORDS:
            rendered.append(lowered)
        else:
            rendered.append(lowered.capitalize())
    return " ".join(rendered)


def _catalog_branch_lookup_key(value: Any) -> str | None:
    canonical = str(value or "").replace("_", " ")
    return normalize_socios_vencidos_branch_key(canonical)


def _branch_message_labels(*, session: Any | None = None) -> dict[str, str]:
    active_session = session if session is not None else db.session
    rows = (
        active_session.query(
            TrackBranchCatalogORM.sucursal_canon,
            Sucursal.sucursal,
        )
        .join(
            Sucursal,
            Sucursal.sucursal_id == TrackBranchCatalogORM.sucursal_id,
        )
        .filter(TrackBranchCatalogORM.sucursal_id.isnot(None))
        .order_by(TrackBranchCatalogORM.sucursal_canon.asc())
        .all()
    )

    labels: dict[str, str] = {}
    for sucursal_canon, sucursal_name in rows:
        label = _message_branch_label(sucursal_name)
        if not label:
            continue

        canonical_key = _catalog_branch_lookup_key(sucursal_canon)
        human_key = normalize_socios_vencidos_branch_key(sucursal_name)
        if canonical_key:
            labels[canonical_key] = label
        if human_key:
            labels[human_key] = label
    return labels


def _resolve_branch_message_label(
    branch: str,
    branch_message_labels: dict[str, str],
) -> str:
    key = normalize_socios_vencidos_branch_key(branch)
    label = branch_message_labels.get(key) if key is not None else None
    if label:
        return label
    raise MarketingReactivationValidationError(
        "No existe un nombre de comunicación configurado para la sucursal "
        f"{branch!r}. Revisa la relación Track/sucursales antes de exportar."
    )


def _build_delivery_package(
    *,
    campaign_part: str,
    groups: dict[str, list[dict[str, Any]]],
    branch_message_labels: dict[str, str],
) -> tuple[bytes, str]:
    ordered_groups = sorted(groups.items(), key=lambda item: item[0].casefold())
    if len(ordered_groups) == 1:
        branch, recipients = ordered_groups[0]
        branch_part = _filename_part(branch, fallback="SIN_SUCURSAL")
        return (
            _phones_workbook(
                recipients,
                branch_message_labels=branch_message_labels,
            ),
            f"{campaign_part}__{branch_part}.xlsx",
        )

    archive_output = BytesIO()
    used_names: set[str] = set()
    with ZipFile(archive_output, "w", compression=ZIP_DEFLATED) as archive:
        for branch, recipients in ordered_groups:
            branch_part = _filename_part(branch, fallback="SIN_SUCURSAL")
            entry_name = _unique_archive_name(
                f"{campaign_part}__{branch_part}.xlsx",
                used_names,
            )
            archive.writestr(
                entry_name,
                _phones_workbook(
                    recipients,
                    branch_message_labels=branch_message_labels,
                ),
            )
        archive.writestr("RESUMEN.xlsx", _summary_workbook(ordered_groups))
    return archive_output.getvalue(), f"{campaign_part}.zip"


def _short_name(value: Any) -> str:
    full_name = " ".join(str(value or "").split())
    if not full_name:
        return ""

    words = full_name.split(" ")
    first_token = words[0]
    if first_token.upper() not in _SHORT_NAME_ABBREVIATIONS:
        return first_token.title()

    for word in words[1:]:
        if word.upper() not in _SHORT_NAME_CONNECTORS:
            return word.title()

    return first_token.title()


def _phones_workbook(
    recipients: list[dict[str, Any]],
    *,
    branch_message_labels: dict[str, str],
) -> bytes:
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Destinatarios")
    sheet.append(
        [
            "telefono",
            "nombre",
            "nombre_completo",
            "sucursal",
            "sucursal_mensaje",
        ]
    )
    for recipient in sorted(
        recipients,
        key=lambda row: str(row.get("phone_mx10") or ""),
    ):
        full_name = " ".join(str(recipient.get("member_name") or "").split())
        branch = str(recipient.get("sucursal") or "").strip()
        sheet.append(
            [
                str(recipient.get("phone_mx10") or ""),
                _short_name(full_name),
                full_name,
                branch,
                _resolve_branch_message_label(branch, branch_message_labels),
            ]
        )
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _summary_workbook(
    groups: list[tuple[str, list[dict[str, Any]]]],
) -> bytes:
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Resumen")
    sheet.append(["sucursal", "contactos"])
    total = 0
    for branch, recipients in groups:
        count = len(recipients)
        total += count
        sheet.append([branch, count])
    sheet.append(["TOTAL", total])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _filename_part(value: Any, *, fallback: str, max_length: int = 80) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").upper()
    safe = re.sub(r"[^A-Z0-9]+", "_", ascii_value).strip("_")
    return (safe or fallback)[:max_length].rstrip("_") or fallback


def _unique_archive_name(filename: str, used_names: set[str]) -> str:
    candidate = filename
    stem, extension = filename.rsplit(".", 1)
    suffix = 2
    while candidate.casefold() in used_names:
        candidate = f"{stem}_{suffix}.{extension}"
        suffix += 1
    used_names.add(candidate.casefold())
    return candidate
