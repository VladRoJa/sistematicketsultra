"""Prepare a Campaign V2 audience from the existing per-branch cobranza XLSX files.

This service never contacts iVentas. The daily report remains successful even
when campaign preparation is impossible (for example, no template is assigned).
"""
from __future__ import annotations

import io
import os
import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook

from app.extensions import db
from app.models.marketing import MarketingCampaignV2ORM
from app.services.marketing_phone import normalize_phone
from app.services.marketing_campaign_v2_excel_import_service import (
    freeze_excel_campaign,
    preview_excel_campaign,
)
from app.services.marketing_campaign_v2_dispatch_branch_service import resolve_dispatch_branch_key
from app.services.marketing_campaign_v2_dispatch_config_service import (
    resolve_dispatch_channel_binding,
    resolve_dispatch_template,
    template_allows_channel,
)

CAMPAIGN_PREFIX = "COBRANZA RECURRENTE RECHAZADOS"
JOB_KEY = "cobranza_recurrente_rechazados"
PHONE_HEADERS = {
    "telefono", "telefono 1", "telefono celular", "celular",
    "numero telefonico", "numero de telefono", "numero de celular",
    "telefono socio", "tel",
}


class CobranzaCampaignPreparationError(ValueError):
    pass


def _header(value: object) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^a-zA-Z0-9]+", " ", value).strip().lower()
    return re.sub(r"\\s+", " ", value)


def _phone(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if not value.is_integer():
            return ""
        return str(int(value))
    if isinstance(value, int):
        return str(value)
    return str(value).strip()


def build_import_bytes(artifacts: list[dict[str, Any]]) -> tuple[bytes, int]:
    """Translate generated XLSX to the exact Excel importer contract."""
    book = Workbook(write_only=True)
    sheet = book.create_sheet("Destinatarios")
    sheet.append(["sucursal", "telefono"])
    recipients: dict[str, str] = {}
    ambiguous: set[str] = set()
    for artifact in artifacts:
        branch = str(artifact.get("sucursal_raw") or "").strip()
        path = Path(str(artifact.get("path") or ""))
        if not branch or not path.is_file():
            raise CobranzaCampaignPreparationError("Falta un archivo o sucursal de cobranza.")
        source = load_workbook(path, read_only=True, data_only=True)
        try:
            values = source.active.iter_rows(values_only=True)
            headings = [_header(cell) for cell in (next(values, ()) or ())]
            matches = [index for index, heading in enumerate(headings) if heading in PHONE_HEADERS]
            if len(matches) != 1:
                raise CobranzaCampaignPreparationError(
                    f"La sucursal {branch} no tiene una columna de telefono unica."
                )
            column = matches[0]
            for cells in values:
                phone = normalize_phone(_phone(cells[column] if len(cells) > column else None))
                if not phone or phone in ambiguous:
                    continue
                previous = recipients.get(phone)
                if previous is not None and previous != branch:
                    ambiguous.add(phone)
                    recipients.pop(phone, None)
                else:
                    recipients[phone] = branch
        finally:
            source.close()
    for phone, branch in sorted(recipients.items()):
        sheet.append([branch, phone])
    count = len(recipients)
    if not count:
        raise CobranzaCampaignPreparationError("Los archivos de cobranza no contienen telefonos validos.")
    output = io.BytesIO()
    book.save(output)
    return output.getvalue(), count


def prepare_cobranza_iventas_campaign(
    *, business_date: date | str, artifacts: list[dict[str, Any]],
    pilot_branch_key: str | None = None,
    auto_pilot_date: date | None = None,
) -> dict[str, Any]:
    """Freeze one idempotent daily campaign, without sending a message."""
    day = date.fromisoformat(str(business_date))
    name = f"{CAMPAIGN_PREFIX} - {day.isoformat()}"
    if pilot_branch_key is not None and (
        not isinstance(pilot_branch_key, str) or
        not pilot_branch_key.strip() or pilot_branch_key != pilot_branch_key.strip()
    ):
        raise CobranzaCampaignPreparationError("Sucursal de piloto invalida.")
    existing = db.session.query(MarketingCampaignV2ORM).filter(
        MarketingCampaignV2ORM.name == name,
        MarketingCampaignV2ORM.source == "EXCEL_IMPORT",
    ).one_or_none()
    if existing:
        metadata = (existing.audience_definition_json or {}).get("source_metadata") or {}
        if metadata.get("automation_job") != JOB_KEY:
            raise CobranzaCampaignPreparationError("Nombre de campana reservado ocupado.")
        if metadata.get("pilot_branch_key") != pilot_branch_key:
            raise CobranzaCampaignPreparationError(
                "Ya existe una campana del mismo corte con otro alcance. "
                "No se mezclaran un piloto y una campana general."
            )
        return {
            "status": "ALREADY_PREPARED", "campaign_id": int(existing.id),
            **({"pilot_branch_key": pilot_branch_key} if pilot_branch_key else {}),
        }

    # A fixed template binding is configuration, not a send switch. Missing
    # config never blocks the Gasca/Warehouse publishing job.
    template_raw = os.getenv("COBRANZA_IVENTAS_TEMPLATE_ID", "").strip()
    if not template_raw:
        return {"status": "TEMPLATE_NOT_CONFIGURED"}
    try:
        template_id = int(template_raw)
        actor_id = int(os.environ["WAREHOUSE_AUTOMATION_USER_ID"])
    except (KeyError, ValueError) as exc:
        raise CobranzaCampaignPreparationError(
            "Plantilla o usuario tecnico de cobranza invalido."
        ) from exc
    if template_id <= 0 or actor_id <= 0:
        raise CobranzaCampaignPreparationError("Plantilla o usuario tecnico invalido.")

    template = resolve_dispatch_template(
        template_id=template_id, purpose="ACTIVE_MEMBERS", session=db.session,
    )
    eligible: list[dict[str, Any]] = []
    skipped_branches: list[dict[str, str]] = []
    pilot_found = False
    for artifact in artifacts:
        branch_raw = str(artifact.get("sucursal_raw") or "").strip()
        branch = resolve_dispatch_branch_key(branch_raw, session=db.session)
        if branch is None:
            skipped_branches.append({"sucursal": branch_raw, "reason": "SIN_SUCURSAL_CANONICA"})
            continue
        if pilot_branch_key is not None and branch.sucursal_canon != pilot_branch_key:
            continue  # Intentionally out of scope, not a delivery error.
        pilot_found = True
        binding = resolve_dispatch_channel_binding(
            sucursal_id=branch.sucursal_id, session=db.session,
        )
        if binding is None or not template_allows_channel(
            template, str(binding.provider_channel_id),
        ):
            skipped_branches.append({"sucursal": branch_raw, "reason": "CANAL_O_PLANTILLA"})
            continue
        try:
            build_import_bytes([artifact])
        except CobranzaCampaignPreparationError:
            skipped_branches.append({"sucursal": branch_raw, "reason": "ARCHIVO_O_TELEFONOS"})
            continue
        eligible.append(artifact)
    if pilot_branch_key is not None and not pilot_found:
        raise CobranzaCampaignPreparationError("La sucursal piloto no aparece en el corte diario.")
    if not eligible:
        raise CobranzaCampaignPreparationError("Ninguna sucursal tiene cobranza enviable.")
    payload, rows = build_import_bytes(eligible)
    filename = f"cobranza_recurrente_{day.isoformat()}.xlsx"
    args = dict(
        file_bytes=payload, filename=filename, name=name,
        purpose="ACTIVE_MEMBERS", template_id=template_id,
        allowed_sucursal_keys=None, session=db.session,
    )
    preview = preview_excel_campaign(**args)
    result = freeze_excel_campaign(
        **args, expected_preview_fingerprint=preview["preview_fingerprint"],
        created_by_user_id=actor_id,
        source_metadata_extra={
            "automation_job": JOB_KEY,
            "business_date": day.isoformat(),
            "generated_rows_with_phone": rows,
            "skipped_branches": skipped_branches,
            **({"pilot_branch_key": pilot_branch_key} if pilot_branch_key else {}),
            **({"auto_pilot_date": day.isoformat()} if auto_pilot_date == day else {}),
        },
    )
    return {
        "status": "PREPARED",
        "campaign_id": int(result["campaign_id"]),
        "recipient_count": int(result["recipient_count"]),
        "blacklist_excluded_count": int(result["blacklist_excluded_count"]),
        "skipped_branches": skipped_branches,
        "pilot_branch_key": pilot_branch_key,
    }
