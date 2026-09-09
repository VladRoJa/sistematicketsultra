"""Builds campaign delivery files from frozen recipients.

The campaign audience remains frozen by the existing campaign service. This
module only changes the delivery package: one XLSX for one branch, or a ZIP
with one XLSX per branch plus a summary when several branches are present.
"""

from __future__ import annotations

from collections import defaultdict
from io import BytesIO
import re
import unicodedata
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import Workbook

from app.services.marketing_reactivation_service import (
    export_marketing_reactivation_campaign as _validate_and_mark_exported,
    get_marketing_reactivation_campaign,
)


XLSX_MIMETYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
ZIP_MIMETYPE = "application/zip"


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
    still called before returning so scope, weekly-frequency policy and the
    DRAFT -> EXPORTED transition remain the source of truth.
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

    campaign_part = _filename_part(
        campaign.get("name"),
        fallback=f"CAMPANA_{int(campaign_id)}",
    )
    export_bytes, filename = _build_delivery_package(
        campaign_part=campaign_part,
        groups=groups,
    )

    # Run the existing guarded export after the package is safely built. Its
    # workbook is intentionally discarded; its validation/state transition is
    # preserved without rebuilding the campaign audience.
    _validate_and_mark_exported(
        campaign_id=campaign_id,
        allowed_sucursal_keys=allowed_sucursal_keys,
        session=session,
        now=now,
    )
    return export_bytes, filename


def _build_delivery_package(
    *,
    campaign_part: str,
    groups: dict[str, list[dict[str, Any]]],
) -> tuple[bytes, str]:
    ordered_groups = sorted(groups.items(), key=lambda item: item[0].casefold())
    if len(ordered_groups) == 1:
        branch, recipients = ordered_groups[0]
        branch_part = _filename_part(branch, fallback="SIN_SUCURSAL")
        return (
            _phones_workbook(recipients),
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
            archive.writestr(entry_name, _phones_workbook(recipients))
        archive.writestr("RESUMEN.xlsx", _summary_workbook(ordered_groups))
    return archive_output.getvalue(), f"{campaign_part}.zip"


def _phones_workbook(recipients: list[dict[str, Any]]) -> bytes:
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Destinatarios")
    sheet.append(["telefono"])
    for recipient in sorted(
        recipients,
        key=lambda row: str(row.get("phone_mx10") or ""),
    ):
        sheet.append([str(recipient.get("phone_mx10") or "")])
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
