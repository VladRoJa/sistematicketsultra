"""Persist validated Google Ads daily campaign data from a Warehouse raw upload.

Raw document is already committed by Warehouse. Structured data only commits
if the whole import has been reconciled and is conflict-free.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
import os
import re
from zoneinfo import ZoneInfo

from flask import current_app

from app.extensions import db
from app.models.google_ads_daily import GoogleAdsDailyMetricORM
from app.models.warehouse import WarehouseUploadORM
from app.warehouse.services.google_ads_daily_xlsx_parser import (
    GoogleAdsXlsxValidationError,
    parse_google_ads_daily_xlsx,
)


REPORT_TYPE_KEY = "google_ads_campaign_daily"
MAX_EXISTING_ROWS = 5000


class GoogleAdsDailyIngestionError(RuntimeError):
    pass


def _upload_content(warehouse_upload_id: int) -> tuple[WarehouseUploadORM, bytes]:
    upload = db.session.get(WarehouseUploadORM, warehouse_upload_id)
    if (
        upload is None or upload.status != "ACTIVE"
        or upload.report_type is None or upload.report_type.key != REPORT_TYPE_KEY
    ):
        raise GoogleAdsDailyIngestionError("Upload Google Ads inexistente o inactivo.")
    if upload.extension.lower() != "xlsx":
        raise GoogleAdsDailyIngestionError("Google Ads solo acepta XLSX.")

    root = Path(current_app.root_path).parent.parent.resolve()
    relative_dir = Path(upload.stored_path)
    if relative_dir.is_absolute():
        raise GoogleAdsDailyIngestionError("Ruta documental inválida.")
    target = (root / relative_dir / upload.stored_filename).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise GoogleAdsDailyIngestionError("Archivo documental no disponible.")
    if target.stat().st_size > 8 * 1024 * 1024:
        raise GoogleAdsDailyIngestionError("Excel demasiado grande.")
    return upload, target.read_bytes()


def _customer_id() -> str:
    customer_id = os.getenv("GOOGLE_ADS_OAUTH_CUSTOMER_ID", "").replace("-", "").strip()
    if not re.fullmatch(r"[0-9]{10}", customer_id):
        raise GoogleAdsDailyIngestionError("Customer Google Ads no configurado.")
    return customer_id


def import_google_ads_warehouse_upload(*, warehouse_upload_id: int) -> dict:
    upload, content = _upload_content(warehouse_upload_id)
    try:
        parsed = parse_google_ads_daily_xlsx(content)
    except GoogleAdsXlsxValidationError as exc:
        raise GoogleAdsDailyIngestionError(str(exc)) from exc

    if parsed.date_from != upload.date_from or parsed.date_to != upload.date_to:
        raise GoogleAdsDailyIngestionError(
            "El periodo declarado en Warehouse no coincide con el Excel."
        )
    if parsed.date_to >= datetime.now(ZoneInfo("America/Tijuana")).date():
        raise GoogleAdsDailyIngestionError("Solo se admiten días cerrados.")

    customer_id = _customer_id()
    existing = (
        db.session.query(GoogleAdsDailyMetricORM)
        .filter(
            GoogleAdsDailyMetricORM.customer_id == customer_id,
            GoogleAdsDailyMetricORM.report_date.between(
                parsed.date_from, parsed.date_to,
            ),
        )
        .all()
    )
    if len(existing) > MAX_EXISTING_ROWS:
        raise GoogleAdsDailyIngestionError("Histórico demasiado grande.")

    by_key = {
        (item.report_date, item.campaign_key): item
        for item in existing
    }
    new_rows = []
    unchanged = 0
    for row in parsed.rows:
        previous = by_key.get((row.report_date, row.campaign_key))
        if previous is None:
            new_rows.append(
                GoogleAdsDailyMetricORM(
                    customer_id=customer_id,
                    campaign_id=None,
                    campaign_key=row.campaign_key,
                    campaign_name=row.campaign_name,
                    report_date=row.report_date,
                    currency_code=row.currency_code,
                    cost=row.cost,
                    clicks=row.clicks,
                    impressions=row.impressions,
                    conversions=row.conversions,
                    conversion_value=row.conversion_value,
                    source_kind="WAREHOUSE_XLSX",
                    source_upload_id=upload.id,
                )
            )
            continue
        if (
            previous.currency_code != row.currency_code
            or Decimal(previous.cost) != row.cost
            or previous.clicks != row.clicks
            or previous.impressions != row.impressions
            or Decimal(previous.conversions) != row.conversions
            or Decimal(previous.conversion_value) != row.conversion_value
        ):
            raise GoogleAdsDailyIngestionError(
                "Conflicto para campaña y día "
                f"{row.campaign_name!r} ({row.report_date.isoformat()}). "
                "No se cambió ningún registro; requiere revisión explícita."
            )
        unchanged += 1

    try:
        db.session.add_all(new_rows)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Error persistiendo importación Google Ads %s", warehouse_upload_id,
        )
        raise GoogleAdsDailyIngestionError(
            "No se pudo guardar la carga estructurada de Google Ads."
        ) from None

    return {
        "status": "ingested",
        "customer_id": customer_id,
        "warehouse_upload_id": upload.id,
        "date_from": parsed.date_from.isoformat(),
        "date_to": parsed.date_to.isoformat(),
        "currency_code": parsed.currency_code,
        "source": "WAREHOUSE_XLSX",
        "campaign_day_rows": len(parsed.rows),
        "created_rows": len(new_rows),
        "unchanged_rows": unchanged,
        "total_cost_in_file": str(parsed.total_cost),
        "campaign_id_binding": "PENDING_EXPLICIT_MAPPING",
    }
