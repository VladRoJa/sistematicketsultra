from __future__ import annotations

import argparse
import hashlib
import sys
import unicodedata
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy.engine import make_url


BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import create_app
from app.extensions import db
from app.models.marketing import MarketingMonthlyInputORM
from app.models.user_model import UserORM
from app.models.warehouse import (
    TrackBranchAliasORM,
    TrackBranchCatalogORM,
    VentaTotalSnapshotORM,
    VentaTotalSnapshotRowORM,
    VentasNuevosSociosDetalleSnapshotORM,
    VentasNuevosSociosDetalleSnapshotRowORM,
    WarehouseOperationalRoleORM,
    WarehouseReportTypeORM,
    WarehouseSourceORM,
    WarehouseUploadORM,
)
from app.services.marketing_access import MarketingAccess
from app.services.marketing_dashboard_service import (
    build_marketing_attribution_detail,
    build_marketing_dashboard,
)
from app.warehouse.services.venta_total_repository import (
    persist_venta_total_snapshot,
)
from app.warehouse.services.ventas_nuevos_socios_detalle_repository import (
    persist_ventas_nuevos_socios_detalle_snapshot,
)


SEED_PREFIX = "LOCAL_MARKETING_SEED"
ALLOWED_LOCAL_HOSTS = {
    None,
    "",
    "localhost",
    "127.0.0.1",
    "::1",
}

MEMBERSHIPS = (
    ("Sin contrato", "CONVENIOS $549", Decimal("549.00")),
    ("No Forzoso", "DOMICILIADO SIN PLAZO $599", Decimal("599.00")),
    ("Sin contrato", "TRIMESTRAL $1,799", Decimal("1799.00")),
    ("No Forzoso", "MENSUALIDAD PROMOCIONAL $699", Decimal("699.00")),
    ("Sin contrato", "CONVENIO EMPRESARIAL $549", Decimal("549.00")),
    ("No Forzoso", "DOMICILIADO SIN PLAZO $599", Decimal("599.00")),
)

NAMES = (
    ("JADE", "PEREZ", "JAUREGUI"),
    ("ROSA MARIA", "CASILLAS", "TOPETE"),
    ("VALERIA", "GARCIA", "ALVAREZ"),
    ("JAVIER", "RUBIO", "XX"),
    ("CARLA GABRIELA", "CORRAL", "AGUILAR"),
    ("KARINA GABRIELA", "CASTRO", "AMAYA"),
    ("MARIO", "LOPEZ", "SOTO"),
)


def parse_month(value: str) -> date:
    try:
        parsed = datetime.strptime(
            value.strip(),
            "%Y-%m",
        ).date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "El mes debe usar formato YYYY-MM."
        ) from exc

    return parsed.replace(day=1)


def month_end(month_start: date) -> date:
    return date(
        month_start.year,
        month_start.month,
        monthrange(
            month_start.year,
            month_start.month,
        )[1],
    )


def normalize_text(value: object) -> str:
    text = str(value or "").strip().upper()
    without_accents = "".join(
        character
        for character in unicodedata.normalize(
            "NFKD",
            text,
        )
        if not unicodedata.combining(character)
    )
    return " ".join(without_accents.split())


def ensure_local_database(app) -> None:
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    url = make_url(uri)

    print("CONEXIÓN LOCAL")
    print(f"driver={url.drivername}")
    print(f"host={url.host}")
    print(f"port={url.port}")
    print(f"database={url.database}")
    print()

    if url.drivername.startswith("sqlite"):
        return

    if url.host not in ALLOWED_LOCAL_HOSTS:
        raise RuntimeError(
            "SEED CANCELADO: la base no apunta a localhost. "
            f"Host recibido: {url.host!r}"
        )


def seed_marker(month_start: date) -> str:
    return (
        f"{SEED_PREFIX}:"
        f"{month_start.strftime('%Y-%m')}"
    )


def delete_seed_data(month_start: date) -> None:
    marker = seed_marker(month_start)

    uploads = (
        WarehouseUploadORM.query
        .filter(WarehouseUploadORM.notes == marker)
        .all()
    )

    for upload in uploads:
        venta_snapshots = (
            VentaTotalSnapshotORM.query
            .filter_by(warehouse_upload_id=upload.id)
            .all()
        )
        for snapshot in venta_snapshots:
            (
                VentaTotalSnapshotRowORM.query
                .filter_by(snapshot_id=snapshot.id)
                .delete(synchronize_session=False)
            )
            db.session.delete(snapshot)

        sales_snapshots = (
            VentasNuevosSociosDetalleSnapshotORM.query
            .filter_by(warehouse_upload_id=upload.id)
            .all()
        )
        for snapshot in sales_snapshots:
            (
                VentasNuevosSociosDetalleSnapshotRowORM.query
                .filter_by(snapshot_id=snapshot.id)
                .delete(synchronize_session=False)
            )
            db.session.delete(snapshot)

        db.session.delete(upload)

    seed_inputs = (
        MarketingMonthlyInputORM.query
        .filter(
            MarketingMonthlyInputORM.month_start
            == month_start,
            MarketingMonthlyInputORM.notes
            == marker,
        )
        .all()
    )
    for row in seed_inputs:
        db.session.delete(row)

    db.session.commit()

    print(
        f"Semilla anterior eliminada: "
        f"uploads={len(uploads)}, "
        f"inputs={len(seed_inputs)}"
    )


def resolve_user() -> UserORM:
    user = (
        UserORM.query
        .order_by(UserORM.id.asc())
        .first()
    )
    if user is None:
        raise RuntimeError(
            "No existe ningún usuario local para asociar "
            "los uploads de desarrollo."
        )
    return user


def resolve_report_type(
    report_type_key: str,
) -> tuple[WarehouseReportTypeORM, int, int]:
    report_type = (
        WarehouseReportTypeORM.query
        .filter_by(key=report_type_key)
        .first()
    )
    if report_type is None:
        raise RuntimeError(
            "No existe el catálogo Warehouse para "
            f"{report_type_key!r}. "
            "Ejecuta primero las migraciones/seeds locales."
        )

    source_id = report_type.default_source_id
    if source_id is None:
        source = (
            WarehouseSourceORM.query
            .filter(WarehouseSourceORM.active.is_(True))
            .order_by(WarehouseSourceORM.id.asc())
            .first()
        )
        if source is None:
            raise RuntimeError(
                "No existe una fuente Warehouse activa."
            )
        source_id = int(source.id)

    role_id = report_type.default_operational_role_id
    if role_id is None:
        role = (
            WarehouseOperationalRoleORM.query
            .filter(
                WarehouseOperationalRoleORM.active.is_(True)
            )
            .order_by(
                WarehouseOperationalRoleORM.id.asc()
            )
            .first()
        )
        if role is None:
            raise RuntimeError(
                "No existe un rol operativo Warehouse activo."
            )
        role_id = int(role.id)

    return (
        report_type,
        int(source_id),
        int(role_id),
    )


def create_upload(
    *,
    report_type_key: str,
    month_start: date,
    user_id: int,
) -> WarehouseUploadORM:
    (
        report_type,
        source_id,
        role_id,
    ) = resolve_report_type(report_type_key)

    end = month_end(month_start)
    marker = seed_marker(month_start)
    filename = (
        f"{SEED_PREFIX.lower()}_"
        f"{report_type_key}_"
        f"{month_start.strftime('%Y_%m')}.xlsx"
    )

    upload = WarehouseUploadORM(
        original_filename=filename,
        stored_filename=filename,
        stored_path=(
            f"local-dev://marketing/"
            f"{month_start.strftime('%Y-%m')}/"
            f"{filename}"
        ),
        file_size_bytes=1,
        file_hash_sha256=hashlib.sha256(
            marker.encode("utf-8")
            + report_type_key.encode("utf-8")
        ).hexdigest(),
        mime_type=(
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        ),
        extension="xlsx",
        source_id=source_id,
        family_id=int(report_type.family_id),
        operational_role_id=role_id,
        report_type_id=int(report_type.id),
        period_type=(
            "diario"
            if report_type_key == "venta_total"
            else "rango"
        ),
        cutoff_date=end,
        date_from=(
            month_start
            if report_type_key
            == "ventas_nuevos_socios_detalle"
            else None
        ),
        date_to=end,
        status="ACTIVE",
        notes=marker,
        uploaded_by_user_id=user_id,
    )

    db.session.add(upload)
    db.session.commit()
    return upload


def resolve_seed_branches(
    limit: int = 3,
) -> list[
    tuple[TrackBranchAliasORM, TrackBranchCatalogORM]
]:
    candidates = (
        db.session.query(
            TrackBranchAliasORM,
            TrackBranchCatalogORM,
        )
        .join(
            TrackBranchCatalogORM,
            TrackBranchCatalogORM.sucursal_canon
            == TrackBranchAliasORM.sucursal_canon,
        )
        .filter(
            TrackBranchAliasORM.source_family
            == "gasca_family",
            TrackBranchAliasORM.is_active.is_(True),
            TrackBranchCatalogORM.is_track_active.is_(
                True
            ),
            TrackBranchCatalogORM.sucursal_id.isnot(
                None
            ),
        )
        .order_by(
            TrackBranchCatalogORM.display_order.asc(),
            TrackBranchCatalogORM.sucursal_id.asc(),
        )
        .all()
    )

    preferred_terms = (
        "VILLA VERDE",
        "VILLAS DEL REY",
        "SENDER0 MEXICALI",
        "SENDERO MEXICALI",
    )

    selected: list[
        tuple[
            TrackBranchAliasORM,
            TrackBranchCatalogORM,
        ]
    ] = []
    selected_ids: set[int] = set()

    for term in preferred_terms:
        for alias, catalog in candidates:
            branch_id = int(catalog.sucursal_id)
            searchable = normalize_text(
                f"{alias.raw_branch_name} "
                f"{catalog.sucursal_canon} "
                f"{catalog.track_label}"
            )
            if (
                term in searchable
                and branch_id not in selected_ids
            ):
                selected.append((alias, catalog))
                selected_ids.add(branch_id)
                break

    for alias, catalog in candidates:
        if len(selected) >= limit:
            break

        branch_id = int(catalog.sucursal_id)
        if branch_id in selected_ids:
            continue

        selected.append((alias, catalog))
        selected_ids.add(branch_id)

    if not selected:
        raise RuntimeError(
            "No existen aliases activos de gasca_family "
            "con sucursal Track activa."
        )

    return selected[:limit]


def branch_label(
    catalog: TrackBranchCatalogORM,
) -> str:
    if catalog.sucursal is not None:
        return str(catalog.sucursal.sucursal).strip()
    return str(
        catalog.track_label
        or catalog.sucursal_canon
    ).strip()


def phone_for(
    branch_position: int,
    person_position: int,
) -> tuple[str, str, str]:
    lada = "686"
    local_number = (
        6_000_000
        + branch_position * 100
        + person_position
    )
    telefono = f"{local_number:07d}"
    return lada, telefono, f"{lada}{telefono}"


def build_visit_rows(
    branches: list[
        tuple[
            TrackBranchAliasORM,
            TrackBranchCatalogORM,
        ]
    ],
    month_start: date,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    row_index = 1

    for branch_position, (alias, _) in enumerate(
        branches,
        start=1,
    ):
        for person_position in range(1, 9):
            visit_day = min(
                2 + person_position * 2,
                month_end(month_start).day,
            )
            _, _, full_phone = phone_for(
                branch_position,
                person_position,
            )

            description = (
                "PASE 2 DIAS GRATIS"
                if person_position % 2
                else "PASE RECORRIDO"
            )

            rows.append(
                {
                    "row_index": row_index,
                    "fecha": date(
                        month_start.year,
                        month_start.month,
                        visit_day,
                    ).isoformat(),
                    "sucursal": str(
                        alias.raw_branch_name
                    ).strip(),
                    "folio": (
                        f"LOCAL-V-{branch_position}-"
                        f"{person_position:03d}"
                    ),
                    "clave": None,
                    "clave_producto": None,
                    "descripcion": description,
                    "cantidad": Decimal("1"),
                    "precio_unitario": Decimal("0"),
                    "subtotal": Decimal("0"),
                    "iva_importe": Decimal("0"),
                    "iva_tasa": Decimal("0"),
                    "total": Decimal("0"),
                    "forma_pago": "CORTESIA",
                    "estatus": "ACTIVO",
                    "motivo": None,
                    "realizo_venta": "LOCAL DEV",
                    "hora": "10:00",
                    "id_orden": (
                        f"LOCAL-ORD-{branch_position}-"
                        f"{person_position:03d}"
                    ),
                    "encuesta": None,
                    "capturista": "LOCAL DEV",
                    "pin": (
                        f"{branch_position:02d}"
                        f"{person_position:04d}"
                    ),
                    "socio": (
                        f"PROSPECTO LOCAL "
                        f"{person_position:02d}"
                    ),
                    "nuevo": "SI",
                    "tipo": "PASE",
                    "telefono": full_phone,
                }
            )
            row_index += 1

    return rows


def build_sales_rows(
    branches: list[
        tuple[
            TrackBranchAliasORM,
            TrackBranchCatalogORM,
        ]
    ],
    month_start: date,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    row_index = 1
    end = month_end(month_start)
    delays = (0, 2, 4, 7, 10, 14)

    for branch_position, (alias, catalog) in enumerate(
        branches,
        start=1,
    ):
        branch_id = int(catalog.sucursal_id)

        for person_position in range(1, 7):
            visit_day = min(
                2 + person_position * 2,
                end.day,
            )
            payment_day = min(
                visit_day + delays[person_position - 1],
                end.day,
            )

            lada, telefono, _ = phone_for(
                branch_position,
                person_position,
            )
            (
                membership_type,
                tariff,
                amount,
            ) = MEMBERSHIPS[person_position - 1]

            if (
                branch_position == 1
                and person_position == 5
            ):
                membership_type = "Sin contrato"
                tariff = (
                    "DOMICILIADO 12 MESES "
                    "PLAN FAMILIAR $999 "
                    "(ADULTO + ADULTO)"
                )
                amount = Decimal("0.00")

            if (
                branch_position == 2
                and person_position == 6
            ):
                amount = Decimal("-50.00")

            name, paternal, maternal = NAMES[
                person_position - 1
            ]

            payment_at = datetime(
                month_start.year,
                month_start.month,
                payment_day,
                18,
                0,
                tzinfo=timezone.utc,
            )
            creation_at = datetime(
                month_start.year,
                month_start.month,
                visit_day,
                17,
                0,
                tzinfo=timezone.utc,
            )

            row_identity = (
                f"{month_start.isoformat()}:"
                f"{branch_id}:"
                f"{person_position}"
            )

            rows.append(
                {
                    "row_index": row_index,
                    "row_hash": hashlib.sha256(
                        row_identity.encode("utf-8")
                    ).hexdigest(),
                    "id_socio": (
                        f"L{branch_id:03d}"
                        f"{person_position:04d}"
                    ),
                    "pin": (
                        f"{branch_position:02d}"
                        f"{person_position:04d}"
                    ),
                    "sucursal_raw": str(
                        alias.raw_branch_name
                    ).strip(),
                    "sucursal_id": branch_id,
                    "nombre": name,
                    "apellido_paterno": paternal,
                    "apellido_materno": maternal,
                    "lada": lada,
                    "telefono": telefono,
                    "domicilio": None,
                    "genero": (
                        "Femenino"
                        if person_position <= 5
                        else "Masculino"
                    ),
                    "fecha_nacimiento": date(
                        1990 + person_position,
                        min(person_position, 12),
                        min(person_position + 3, 28),
                    ),
                    "email": (
                        f"socio.local.{branch_id}."
                        f"{person_position}@example.test"
                    ),
                    "fecha_creacion_at": creation_at,
                    "inscripcion": (
                        "Inscripción $99"
                        if person_position % 2 == 0
                        else "Convenio 300"
                    ),
                    "tipo_membresia": membership_type,
                    "tarifa": tariff,
                    "total": amount,
                    "fecha_pago_at": payment_at,
                    "fecha_renovacion_at": (
                        payment_at + timedelta(days=30)
                    ),
                    "fecha_firma_contrato_at": None,
                    "tipo_pago_code": 2,
                    "tipo_tarjeta_code": None,
                    "lugar_pago": "Sucursal",
                    "id_folio": (
                        f"LOCAL-F-{branch_id}-"
                        f"{person_position:04d}"
                    ),
                    "pase": (
                        "PASE 2 DIAS GRATIS SUCURSAL"
                        if person_position % 2
                        else "PASE RECORRIDO"
                    ),
                    "anfitrion": "EQUIPO LOCAL DEV",
                    "total_pagado": amount,
                    "quality_flags": [],
                }
            )
            row_index += 1

        # Una venta válida de fuente, pero sin visita coincidente.
        unmatched_position = 99
        lada, telefono, _ = phone_for(
            branch_position,
            unmatched_position,
        )
        payment_at = datetime(
            month_start.year,
            month_start.month,
            min(24, end.day),
            18,
            0,
            tzinfo=timezone.utc,
        )

        identity = (
            f"{month_start.isoformat()}:"
            f"{branch_id}:unmatched"
        )

        rows.append(
            {
                "row_index": row_index,
                "row_hash": hashlib.sha256(
                    identity.encode("utf-8")
                ).hexdigest(),
                "id_socio": (
                    f"L{branch_id:03d}9999"
                ),
                "pin": f"{branch_position:02d}9999",
                "sucursal_raw": str(
                    alias.raw_branch_name
                ).strip(),
                "sucursal_id": branch_id,
                "nombre": "VENTA",
                "apellido_paterno": "SIN",
                "apellido_materno": "VISITA",
                "lada": lada,
                "telefono": telefono,
                "domicilio": None,
                "genero": None,
                "fecha_nacimiento": None,
                "email": None,
                "fecha_creacion_at": (
                    payment_at - timedelta(hours=1)
                ),
                "inscripcion": None,
                "tipo_membresia": "No Forzoso",
                "tarifa": "DOMICILIADO SIN PLAZO $599",
                "total": Decimal("599.00"),
                "fecha_pago_at": payment_at,
                "fecha_renovacion_at": (
                    payment_at + timedelta(days=30)
                ),
                "fecha_firma_contrato_at": None,
                "tipo_pago_code": 2,
                "tipo_tarjeta_code": None,
                "lugar_pago": "Sucursal",
                "id_folio": (
                    f"LOCAL-F-{branch_id}-9999"
                ),
                "pase": None,
                "anfitrion": None,
                "total_pagado": Decimal("599.00"),
                "quality_flags": [],
            }
        )
        row_index += 1

    return rows


def force_canonical(**_: object) -> dict[str, object]:
    return {
        "is_canonical": True,
        "replace_existing_canonical": True,
        "reason": "local_marketing_seed",
    }


def seed_inputs(
    *,
    branches: list[
        tuple[
            TrackBranchAliasORM,
            TrackBranchCatalogORM,
        ]
    ],
    month_start: date,
) -> None:
    marker = seed_marker(month_start)

    for position, (_, catalog) in enumerate(
        branches,
        start=1,
    ):
        branch_id = int(catalog.sucursal_id)
        existing = (
            MarketingMonthlyInputORM.query
            .filter_by(
                month_start=month_start,
                sucursal_id=branch_id,
            )
            .first()
        )

        if existing is not None and existing.notes != marker:
            print(
                "Input manual conservado: "
                f"sucursal_id={branch_id}"
            )
            continue

        if existing is None:
            existing = MarketingMonthlyInputORM(
                month_start=month_start,
                sucursal_id=branch_id,
                investment=Decimal("0"),
                leads=0,
                notes=marker,
            )
            db.session.add(existing)

        existing.investment = Decimal(
            str(8500 + position * 1750)
        )
        existing.leads = 110 + position * 25
        existing.notes = marker

    db.session.commit()


def run_seed(month_start: date) -> None:
    delete_seed_data(month_start)

    user = resolve_user()
    branches = resolve_seed_branches(limit=3)

    print()
    print("SUCURSALES SELECCIONADAS")
    for _, catalog in branches:
        print(
            f"- {branch_label(catalog)} "
            f"(id={catalog.sucursal_id})"
        )

    visit_rows = build_visit_rows(
        branches,
        month_start,
    )
    sales_rows = build_sales_rows(
        branches,
        month_start,
    )

    visit_upload = create_upload(
        report_type_key="venta_total",
        month_start=month_start,
        user_id=int(user.id),
    )
    sales_upload = create_upload(
        report_type_key=(
            "ventas_nuevos_socios_detalle"
        ),
        month_start=month_start,
        user_id=int(user.id),
    )

    end = month_end(month_start)
    captured_at = datetime(
        end.year,
        end.month,
        end.day,
        18,
        0,
        tzinfo=timezone.utc,
    )

    visit_result = persist_venta_total_snapshot(
        warehouse_upload_id=int(visit_upload.id),
        report_type_key="venta_total",
        business_date=end,
        captured_at=captured_at,
        snapshot_kind="daily",
        parsed_snapshot={
            "rows": visit_rows,
            "row_count": len(visit_rows),
            "row_count_valid": len(visit_rows),
            "row_count_rejected": 0,
        },
        canonicality_resolver=force_canonical,
    )

    sales_result = (
        persist_ventas_nuevos_socios_detalle_snapshot(
            warehouse_upload_id=int(sales_upload.id),
            report_type_key=(
                "ventas_nuevos_socios_detalle"
            ),
            business_date=end,
            date_from=month_start,
            date_to=end,
            captured_at=captured_at,
            snapshot_kind="month_to_date",
            parsed_snapshot={
                "rows": sales_rows,
                "rejected_rows": [],
                "row_count": len(sales_rows),
                "row_count_valid": len(sales_rows),
                "row_count_rejected": 0,
                "quality_flag_counts": {},
                "metadata": {
                    "source": "local_marketing_seed",
                    "source_timezone": (
                        "America/Tijuana"
                    ),
                },
            },
            canonicality_resolver=force_canonical,
            requested_by="local-dev",
            ingestion_source=SEED_PREFIX,
        )
    )

    seed_inputs(
        branches=branches,
        month_start=month_start,
    )

    access = MarketingAccess(
        type="GLOBAL",
        is_global=True,
        branch_ids=(),
        role="ADMIN",
        can_edit_inputs=True,
    )

    month_value = month_start.strftime("%Y-%m")
    dashboard = build_marketing_dashboard(
        month=month_value,
        access=access,
    )
    detail = build_marketing_attribution_detail(
        month=month_value,
        access=access,
    )

    print()
    print("RESULTADOS DE INGESTA")
    print(
        "venta_total_snapshot_id="
        f"{visit_result['snapshot_id']}"
    )
    print(
        "ventas_snapshot_id="
        f"{sales_result['snapshot_id']}"
    )
    print(
        f"visitas_fuente={len(visit_rows)}"
    )
    print(
        f"ventas_fuente={len(sales_rows)}"
    )

    print()
    print("MARKETING LOCAL")
    print(
        "visitantes="
        f"{dashboard['summary']['visits']}"
    )
    print(
        "ventas_atribuidas="
        f"{detail['summary']['sales']}"
    )
    print(
        "ingreso_atribuido="
        f"${detail['summary']['sales_revenue']:,.2f}"
    )
    print(
        "casos_por_revisar="
        f"{detail['summary']['review_sales']}"
    )
    print(
        "integrantes_plan_familiar="
        f"{detail['summary']['family_plan_additional_members']}"
    )
    print(
        f"filas_detalle={len(detail['rows'])}"
    )

    print()
    print("DESGLOSE SEMBRADO")
    selected_ids = {
        int(catalog.sucursal_id)
        for _, catalog in branches
    }
    for branch in dashboard["branches"]:
        if branch["sucursal_id"] not in selected_ids:
            continue

        print(
            f"{branch['sucursal']} | "
            f"visitas={branch['visits']} | "
            f"ventas={branch['sales']} | "
            f"ingreso=${branch['sales_revenue']:,.2f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Puebla datos sintéticos del módulo Marketing "
            "en una base exclusivamente local."
        )
    )
    parser.add_argument(
        "--month",
        required=True,
        type=parse_month,
        help="Mes a poblar en formato YYYY-MM.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Elimina la semilla del mes y termina.",
    )
    args = parser.parse_args()

    app = create_app()

    with app.app_context():
        ensure_local_database(app)

        try:
            if args.reset:
                delete_seed_data(args.month)
                print("Reset local completado.")
                return

            run_seed(args.month)
        except Exception:
            db.session.rollback()
            raise
        finally:
            db.session.remove()


if __name__ == "__main__":
    main()
