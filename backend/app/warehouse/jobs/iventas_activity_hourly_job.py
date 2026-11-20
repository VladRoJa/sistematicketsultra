from __future__ import annotations

import argparse
from datetime import datetime
from fcntl import LOCK_EX, LOCK_NB, flock
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from app.extensions import db
from app.models.warehouse import VentaTotalSnapshotORM
from app.warehouse.services.gasca_single_report_runner_impl import capture_socios_activos_xlsx
from app.warehouse.services.iventas_activity_export_service import (
    IventasActivityExportError,
    write_iventas_activity_xlsx,
)
from app.warehouse.services.socios_activos_parser import parse_socios_activos_xlsx
from app.warehouse.services.venta_total_parser import parse_venta_total_xlsx
from app.warehouse.services.warehouse_upload_loader import load_warehouse_upload


def run_job(
    *,
    venta_total_upload_id: int,
    output_path: Path,
    exclude_passes_for_current_members: bool = False,
    known_movements: set[str] | None = None,
    baseline_only: bool = False,
    full_output_path: Path | None = None,
) -> dict[str, int | str | list[str]]:
    if output_path.suffix.lower() != ".xlsx":
        raise IventasActivityExportError("La ruta de salida debe terminar en .xlsx.")

    snapshot = VentaTotalSnapshotORM.query.filter_by(
        warehouse_upload_id=venta_total_upload_id,
        report_type_key="venta_total",
    ).one_or_none()
    upload = load_warehouse_upload(warehouse_upload_id=venta_total_upload_id)
    if (
        snapshot is None or upload is None
        or upload.get("report_type_key") != "venta_total"
        or not upload.get("storage_path")
    ):
        raise IventasActivityExportError(
            "El upload indicado debe ser un Venta Total con ingesta y archivo RAW disponibles."
        )

    sales_cutoff = snapshot.business_date
    snapshot_id = snapshot.id
    db.session.remove()
    if (
        upload.get("date_from") != sales_cutoff.replace(day=1)
        or upload.get("date_to") != sales_cutoff
    ):
        raise IventasActivityExportError(
            "Venta Total debe cubrir del primer día del mes hasta el corte indicado."
        )

    active_cutoff = datetime.now(ZoneInfo("America/Tijuana")).date()
    if sales_cutoff > active_cutoff:
        raise IventasActivityExportError("El corte de Venta Total es posterior a hoy.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = output_path.with_suffix(".lock")
    with lock_path.open("a") as lock:
        try:
            flock(lock.fileno(), LOCK_EX | LOCK_NB)
        except BlockingIOError:
            raise IventasActivityExportError("Ya se está generando este Excel de iVentas.") from None

        sales = parse_venta_total_xlsx(file_path=upload["storage_path"])
        with TemporaryDirectory(prefix=".iventas-", dir=output_path.parent) as workspace:
            active_path = Path(workspace) / "socios_activos.xlsx"
            capture_socios_activos_xlsx(output_path=active_path, business_date=active_cutoff)
            active_members = parse_socios_activos_xlsx(file_path=str(active_path))
            temporary_output = Path(workspace) / "actividad.xlsx"
            counts = write_iventas_activity_xlsx(
                sales=sales,
                active_members=active_members,
                sales_cutoff=sales_cutoff,
                active_cutoff=active_cutoff,
                output_path=temporary_output,
                exclude_passes_for_current_members=exclude_passes_for_current_members,
                known_movements=known_movements,
                baseline_only=baseline_only,
                workbook_identifier=output_path.name,
            )
            if full_output_path is not None:
                temporary_full = Path(workspace) / "acumulado.xlsx"
                full_counts = write_iventas_activity_xlsx(
                    sales=sales,
                    active_members=active_members,
                    sales_cutoff=sales_cutoff,
                    active_cutoff=active_cutoff,
                    output_path=temporary_full,
                    exclude_passes_for_current_members=exclude_passes_for_current_members,
                    workbook_identifier=full_output_path.name,
                )
                temporary_full.chmod(0o600)
                temporary_full.replace(full_output_path)
                counts["full_rows"] = full_counts["rows"]
            if temporary_output.exists():
                temporary_output.chmod(0o600)
                temporary_output.replace(output_path)

    return {
        **counts,
        "venta_total_upload_id": venta_total_upload_id,
        "venta_total_snapshot_id": snapshot_id,
        "venta_total_cutoff": sales_cutoff.isoformat(),
        "socios_activos_cutoff": active_cutoff.isoformat(),
        "socios_activos_rows": active_members.row_count_valid,
        "socios_activos_rejected_rows": active_members.row_count_rejected,
        "output_path": str(output_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera el Excel de actividad para iVentas.")
    parser.add_argument("--venta-total-upload-id", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--exclude-passes-for-current-members",
        action="store_true",
        help="Omite pases y recorridos de personas con una membresía vigente.",
    )
    args = parser.parse_args()

    from app import create_app

    with create_app().app_context():
        result = run_job(
            venta_total_upload_id=args.venta_total_upload_id,
            output_path=args.output,
            exclude_passes_for_current_members=args.exclude_passes_for_current_members,
        )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
