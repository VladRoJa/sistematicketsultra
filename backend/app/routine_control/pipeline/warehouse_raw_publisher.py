from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import current_app

from app.routine_control.providers.runtime import ProviderArtifact


WAREHOUSE_REPORT_TYPE_KEY = "ventas_nuevos_socios_detalle"
XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


class RoutineControlWarehousePublishError(RuntimeError):
    """Error al publicar un artifact de Control de Rutinas en Warehouse."""


@dataclass(frozen=True, slots=True)
class RoutineControlWarehousePublishResult:
    warehouse_upload_id: int
    upload_status: str
    duplicate_detected: bool
    duplicate_upload_id: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "warehouse_upload_id": self.warehouse_upload_id,
            "upload_status": self.upload_status,
            "duplicate_detected": self.duplicate_detected,
            "duplicate_upload_id": self.duplicate_upload_id,
        }


def _resolve_upload_creator() -> Callable[..., Any]:
    upload_creator = current_app.config.get(
        "WAREHOUSE_INTERNAL_UPLOAD_CREATOR"
    )

    if not callable(upload_creator):
        raise RoutineControlWarehousePublishError(
            "WAREHOUSE_INTERNAL_UPLOAD_CREATOR no está registrado."
        )

    return upload_creator


def _validate_artifact(artifact: ProviderArtifact) -> None:
    if artifact.provider_key != "gasca":
        raise RoutineControlWarehousePublishError(
            "Sólo se pueden publicar artifacts producidos por Gasca."
        )

    if artifact.dataset_key != "new_members":
        raise RoutineControlWarehousePublishError(
            "El artifact no corresponde al dataset 'new_members'."
        )

    if artifact.business_date_from > artifact.business_date_to:
        raise RoutineControlWarehousePublishError(
            "El rango de fechas del artifact es inválido."
        )

    if not artifact.local_path.exists():
        raise RoutineControlWarehousePublishError(
            "El archivo local del artifact no existe."
        )

    if artifact.local_path.suffix.lower() != ".xlsx":
        raise RoutineControlWarehousePublishError(
            "El artifact de nuevos socios debe ser un archivo XLSX."
        )


def _normalize_upload_result(
    raw_result: Any,
) -> RoutineControlWarehousePublishResult:
    if not isinstance(raw_result, dict):
        raise RoutineControlWarehousePublishError(
            "El creador de Warehouse devolvió un resultado inválido."
        )

    warehouse_upload_id = raw_result.get("warehouse_upload_id")
    if not isinstance(warehouse_upload_id, int) or warehouse_upload_id <= 0:
        raise RoutineControlWarehousePublishError(
            "Warehouse no devolvió un warehouse_upload_id válido."
        )

    upload_status = raw_result.get("upload_status", "created")
    if not isinstance(upload_status, str) or not upload_status.strip():
        raise RoutineControlWarehousePublishError(
            "Warehouse devolvió un upload_status inválido."
        )

    metadata = raw_result.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise RoutineControlWarehousePublishError(
            "Warehouse devolvió metadata inválida."
        )

    duplicate_upload_id = metadata.get("duplicate_upload_id")
    if duplicate_upload_id is not None and not isinstance(
        duplicate_upload_id,
        int,
    ):
        raise RoutineControlWarehousePublishError(
            "Warehouse devolvió duplicate_upload_id inválido."
        )

    return RoutineControlWarehousePublishResult(
        warehouse_upload_id=warehouse_upload_id,
        upload_status=upload_status,
        duplicate_detected=bool(
            metadata.get("duplicate_detected", False)
        ),
        duplicate_upload_id=duplicate_upload_id,
    )


def publish_gasca_new_members_artifact_to_warehouse(
    *,
    artifact: ProviderArtifact,
    generation_mode: str,
    trigger_source: str,
) -> RoutineControlWarehousePublishResult:
    """
    Publica en Warehouse el mismo XLSX detallado descargado por Gasca.

    No vuelve a consultar Gasca ni modifica el archivo original del provider.
    """
    _validate_artifact(artifact)
    upload_creator = _resolve_upload_creator()

    try:
        raw_result = upload_creator(
            report_type_key=WAREHOUSE_REPORT_TYPE_KEY,
            original_filename=artifact.source_filename,
            content_type=XLSX_CONTENT_TYPE,
            file_path=str(artifact.local_path),
            captured_at=artifact.extracted_at_utc,
            source_key=artifact.provider_key,
            metadata={
                "date_from": artifact.business_date_from.isoformat(),
                "date_to": artifact.business_date_to.isoformat(),
                "producer_module": "routine_control",
                "provider_key": artifact.provider_key,
                "dataset_key": artifact.dataset_key,
                "artifact_sha256": artifact.sha256,
                "artifact_size_bytes": artifact.size_bytes,
                "generation_mode": generation_mode,
                "trigger_source": trigger_source,
            },
        )
    except RoutineControlWarehousePublishError:
        raise
    except Exception as exc:
        raise RoutineControlWarehousePublishError(
            "Falló la publicación del detalle de nuevos socios en Warehouse."
        ) from exc

    return _normalize_upload_result(raw_result)
