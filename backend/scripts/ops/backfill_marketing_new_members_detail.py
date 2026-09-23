from __future__ import annotations

import argparse
import hashlib
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from app import create_app
from app.extensions import db
from app.models.warehouse import VentasNuevosSociosDetalleSnapshotORM
from app.routine_control.pipeline.warehouse_raw_publisher import (
    publish_gasca_new_members_artifact_to_warehouse,
)
from app.routine_control.providers.runtime import ProviderArtifact
from app.warehouse.services.ventas_nuevos_socios_detalle_ingestion_service import (
    ingest_ventas_nuevos_socios_detalle_upload,
)


REPORT_TYPE_KEY = "ventas_nuevos_socios_detalle"
SNAPSHOT_KIND = "month_to_date"
TRIGGER_SOURCE = "MARKETING_FUNNEL_HISTORICAL_BACKFILL"


@dataclass(frozen=True, slots=True)
class ArtifactSpec:
    month: str
    run_id: str
    date_from: date
    date_to: date
    size_bytes: int
    sha256: str


ARTIFACTS = (
    ArtifactSpec(
        month="2026-02",
        run_id="ad191015244048e383ed81531485a312",
        date_from=date(2026, 2, 1),
        date_to=date(2026, 2, 28),
        size_bytes=538459,
        sha256="d80ccdf25e45ffebe0a80a76d64dd1218cbf069017655f5f0342c52313d87757",
    ),
    ArtifactSpec(
        month="2026-03",
        run_id="099a3c4bb27c41e4a97d9e44f43433e6",
        date_from=date(2026, 3, 1),
        date_to=date(2026, 3, 31),
        size_bytes=464582,
        sha256="6e099712e2c3bf78be1a002c9e326e2eeb0dbcf1aaf661dc0ca3324c17d2a818",
    ),
    ArtifactSpec(
        month="2026-04",
        run_id="0d7a918e22e2461f8a49b56f89e1d931",
        date_from=date(2026, 4, 1),
        date_to=date(2026, 4, 30),
        size_bytes=371345,
        sha256="8be6d41e063c4c20cd76cb8622cfbe068d9b3df3eee3921acf37965edbf13243",
    ),
    ArtifactSpec(
        month="2026-05",
        run_id="f33f37649b5646a7ac5186f8bdddafc4",
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
        size_bytes=343616,
        sha256="60b335024f9d0e68d00d7708fb9d81040b98340d5cb6b7ad8f4c90dfd76ba76d",
    ),
    ArtifactSpec(
        month="2026-06",
        run_id="1da99208ec8b462196a7a78cff111404",
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
        size_bytes=426826,
        sha256="ae1082122ff21d990c0179fabd50ca7292baf22ad145bec5926b342b7d943dc1",
    ),
)


def _artifact_path(root: Path, spec: ArtifactSpec) -> Path:
    return (
        root
        / "gasca"
        / "new_members"
        / spec.run_id
        / "gasca-new-members.xlsx"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_artifact(root: Path, spec: ArtifactSpec) -> Path:
    path = _artifact_path(root, spec)

    if not path.is_file():
        raise RuntimeError(
            f"{spec.month}: artifact no encontrado: {path}"
        )

    actual_size = path.stat().st_size
    if actual_size != spec.size_bytes:
        raise RuntimeError(
            f"{spec.month}: size_bytes cambió. "
            f"Esperado={spec.size_bytes}, actual={actual_size}."
        )

    actual_sha256 = _sha256(path)
    if actual_sha256 != spec.sha256:
        raise RuntimeError(
            f"{spec.month}: SHA-256 cambió. "
            f"Esperado={spec.sha256}, actual={actual_sha256}."
        )

    return path


def _existing_canonical(
    spec: ArtifactSpec,
) -> VentasNuevosSociosDetalleSnapshotORM | None:
    return (
        VentasNuevosSociosDetalleSnapshotORM.query.filter_by(
            report_type_key=REPORT_TYPE_KEY,
            business_date=spec.date_to,
            date_from=spec.date_from,
            date_to=spec.date_to,
            snapshot_kind=SNAPSHOT_KIND,
            is_canonical=True,
        )
        .order_by(
            VentasNuevosSociosDetalleSnapshotORM.id.desc()
        )
        .first()
    )


def _build_provider_artifact(
    *,
    path: Path,
    spec: ArtifactSpec,
    observed_at_utc: datetime,
) -> ProviderArtifact:
    return ProviderArtifact(
        provider_key="gasca",
        dataset_key="new_members",
        local_path=path,
        sha256=spec.sha256,
        size_bytes=spec.size_bytes,
        extracted_at_utc=observed_at_utc,
        business_date_from=spec.date_from,
        business_date_to=spec.date_to,
        source_filename=path.name,
        diagnostic_metadata={
            "report_contract": "verified_kpi_new_members_detailed",
            "historical_backfill": True,
            "source_run_id": spec.run_id,
        },
    )


def _run_month(
    *,
    artifact_root: Path,
    spec: ArtifactSpec,
    commit: bool,
) -> None:
    path = _verify_artifact(artifact_root, spec)

    existing = _existing_canonical(spec)
    if existing is not None:
        print(
            f"{spec.month} SKIP "
            f"snapshot_id={existing.id} "
            f"rows={existing.row_count_valid}"
        )
        return

    if not commit:
        print(
            f"{spec.month} READY "
            f"size={spec.size_bytes} sha256={spec.sha256[:12]} "
            f"path={path}"
        )
        return

    observed_at_utc = datetime.now(timezone.utc)
    artifact = _build_provider_artifact(
        path=path,
        spec=spec,
        observed_at_utc=observed_at_utc,
    )

    upload = publish_gasca_new_members_artifact_to_warehouse(
        artifact=artifact,
        generation_mode="BACKFILL",
        trigger_source=TRIGGER_SOURCE,
    )

    ingestion = ingest_ventas_nuevos_socios_detalle_upload(
        warehouse_upload_id=upload.warehouse_upload_id,
        snapshot_kind=SNAPSHOT_KIND,
        requested_by="backfill_marketing_new_members_detail",
        ingestion_source=TRIGGER_SOURCE,
    )

    canonical = _existing_canonical(spec)
    if canonical is None:
        raise RuntimeError(
            f"{spec.month}: la ingesta terminó sin snapshot canónico."
        )

    print(
        f"{spec.month} OK "
        f"upload_id={upload.warehouse_upload_id} "
        f"upload_status={upload.upload_status} "
        f"snapshot_id={canonical.id} "
        f"rows={canonical.row_count_valid} "
        f"ingestion_status={ingestion.get('status')}"
    )


def run_backfill(
    *,
    artifact_root: Path,
    commit: bool,
) -> None:
    for spec in ARTIFACTS:
        _run_month(
            artifact_root=artifact_root,
            spec=spec,
            commit=commit,
        )
        db.session.remove()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Publica e ingiere en Warehouse los artifacts Gasca auditados "
            "de ventas de nuevos socios para febrero-junio 2026."
        )
    )
    parser.add_argument(
        "--artifact-root",
        default=os.getenv(
            "ROUTINE_CONTROL_ARTIFACT_DIR",
            "/app/runtime/routine-control/artifacts",
        ),
        help=(
            "Raíz de artifacts de Routine Control. "
            "Default: ROUTINE_CONTROL_ARTIFACT_DIR."
        ),
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help=(
            "Publica e ingiere los meses faltantes. "
            "Sin este flag solo valida artifacts y muestra el plan."
        ),
    )
    args = parser.parse_args()

    app = create_app()

    with app.app_context():
        try:
            run_backfill(
                artifact_root=Path(args.artifact_root).resolve(),
                commit=args.commit,
            )
        except Exception as exc:
            db.session.rollback()
            print(f"FAILED {type(exc).__name__}: {exc}")
            return 1
        finally:
            db.session.remove()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
