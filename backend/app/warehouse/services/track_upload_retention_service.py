# backend/app/warehouse/services/track_upload_retention_service.py

from __future__ import annotations

from typing import Any

from app.extensions import db
from app.models.warehouse import WarehouseUploadORM


def extract_warehouse_upload_ids_from_track_raw_ingestion(
    raw_ingestion: dict[str, Any] | None,
) -> list[int]:
    if not raw_ingestion:
        return []

    upload_ids: list[int] = []
    seen: set[int] = set()

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            warehouse_upload_id = value.get("warehouse_upload_id")

            if warehouse_upload_id is not None:
                try:
                    normalized_upload_id = int(warehouse_upload_id)
                except (TypeError, ValueError):
                    normalized_upload_id = None

                if (
                    normalized_upload_id is not None
                    and normalized_upload_id not in seen
                ):
                    seen.add(normalized_upload_id)
                    upload_ids.append(normalized_upload_id)

            for nested_value in value.values():
                collect(nested_value)

        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(raw_ingestion)

    return upload_ids


def link_warehouse_uploads_to_track_daily_version(
    *,
    track_daily_version_id: int,
    warehouse_upload_ids: list[int],
    auto_commit: bool = False,
) -> dict[str, Any]:
    normalized_upload_ids = sorted(
        {
            int(upload_id)
            for upload_id in warehouse_upload_ids
            if upload_id is not None
        }
    )

    if not normalized_upload_ids:
        return {
            "track_daily_version_id": track_daily_version_id,
            "warehouse_upload_ids": [],
            "uploads_linked": 0,
        }

    uploads_linked = (
        WarehouseUploadORM.query
        .filter(WarehouseUploadORM.id.in_(normalized_upload_ids))
        .update(
            {
                WarehouseUploadORM.track_daily_version_id: track_daily_version_id,
            },
            synchronize_session=False,
        )
    )

    db.session.flush()

    if auto_commit:
        db.session.commit()

    return {
        "track_daily_version_id": track_daily_version_id,
        "warehouse_upload_ids": normalized_upload_ids,
        "uploads_linked": uploads_linked,
    }


def archive_warehouse_uploads_for_track_daily_version(
    *,
    track_daily_version_id: int,
    auto_commit: bool = False,
) -> dict[str, Any]:
    uploads_archived = (
        WarehouseUploadORM.query
        .filter(
            WarehouseUploadORM.track_daily_version_id == track_daily_version_id,
            WarehouseUploadORM.status != "ARCHIVED",
        )
        .update(
            {
                WarehouseUploadORM.status: "ARCHIVED",
            },
            synchronize_session=False,
        )
    )

    db.session.flush()

    if auto_commit:
        db.session.commit()

    return {
        "track_daily_version_id": track_daily_version_id,
        "uploads_archived": uploads_archived,
    }

