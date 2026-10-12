"""Approve Google Ads group-name aliases against 26 active Suite branches.

Revision ID: b14d9e2c6f80
Revises: a12b3c4d5e6f
Create Date: 2026-10-12

Only prepares a controlled catalog. DOES NOT attribute spend, mutate facts,
or connect to Funnel. The names alone are NOT a sufficient production join:
subsequent attribution must bind Google customer + campaign + group IDs/keys.
"""
from __future__ import annotations

import re

from alembic import op
import sqlalchemy as sa


revision = "b14d9e2c6f80"
down_revision = "a12b3c4d5e6f"
branch_labels = None
depends_on = None

FAMILY = "google_ads_family"
SOURCE_FAMILY_CHECK_NAME = "ck_track_branch_aliases_source_family"
# Approved database state immediately before M4, established by iVentas.
SOURCE_FAMILIES_BEFORE = (
    "manual_targets",
    "gasca_family",
    "domiciliados_total",
    "domiciliados_recep",
    "venta_tienda",
    "totalpass_family",
    "wellhub_family",
    "iventas_family",
)
SOURCE_FAMILIES_AFTER = (*SOURCE_FAMILIES_BEFORE, FAMILY)
NOTES = (
    "Google Ads grupos-día: catálogo aprobado 2026-10-12; "
    "requiere validar customer_id, campaign_key y ad_group_key "
    "antes de atribuir. Sin asignación automática a Funnel."
)

# Exact names from 2026-09-24..2026-10-08 group-day XLSX.
# Includes explicitly approved Paseo Villalta and Sendero Sur Saltillo.
# EGADE (preapertura) and Marca (nacional) intentionally excluded.
APPROVED_ALIASES = (
    ("Villas del Rey", "VILLAS_DEL_REY", 1),
    ("Villa Verde", "VILLA_VERDE", 2),
    ("Independencia", "INDEPENDENCIA", 3),
    ("TEC", "TEC_MXL", 4),
    ("Sendero Mexicali", "SEND_MXL", 5),
    ("San Luis Río Colorado", "SAN_LUIS", 6),
    ("Pabellón Rosarito", "PABELLON_RTO", 7),
    ("Misión Ensenada", "MISION_ENS", 8),
    ("Paseo 2000", "PASEO_2000", 9),
    ("Loma Bonita", "LOMA_BONITA", 10),
    ("Santa Fe", "SANTA_FE", 11),
    ("Carrousel", "CARROUSEL_TJ", 12),
    ("Papalote", "PAPALOTE_TJ", 13),
    ("Sendero Culiacán", "SEND_CUL", 14),
    ("San Isidro", "SAN_ISIDRO_CUL", 15),
    ("Azahares", "AZAHARES_CUL", 16),
    ("Santa Catarina", "STA_CATARINA", 17),
    ("Sendero Sur Saltillo", "SEND_SALTILLO", 18),
    ("Sendero Chihuahua", "SEND_CHIH", 19),
    ("La Paz", "PASEO_LA_PAZ", 20),
    ("Sendero Ixtapaluca", "IXTAPALUCA", 21),
    ("Insurgentes Sur", "INSURGENTES", 22),
    ("Tlalnepantla", "TLALNEPANTLA", 23),
    ("Paseo Villalta", "SALTILLO_VILLALTA", 24),
    ("Metepec", "METEPEC", 25),
    ("Serranía", "SERRANIA", 26),
)


def _source_families_in_database(bind) -> set[str]:
    definition = bind.execute(
        sa.text(
            """
            SELECT pg_get_constraintdef(c.oid, true)
            FROM pg_constraint c
            WHERE c.conrelid = 'track_branch_aliases'::regclass
              AND c.contype = 'c'
              AND c.conname = :name
            """
        ),
        {"name": SOURCE_FAMILY_CHECK_NAME},
    ).scalar_one_or_none()
    if not definition:
        raise RuntimeError("Falta el CHECK de source_family de Track.")
    # PostgreSQL renders IN clauses as ANY(ARRAY['x'::text, ...]).
    return set(re.findall(r"'([^']+)'", definition))


def _assert_source_family_domain(bind, expected: tuple[str, ...]) -> None:
    observed = _source_families_in_database(bind)
    if observed != set(expected):
        raise RuntimeError(
            "Dominio CHECK source_family inesperado: "
            f"actual={sorted(observed)!r}, esperado={sorted(expected)!r}."
        )


def _replace_check_domain(
    bind, *, before: tuple[str, ...], after: tuple[str, ...],
) -> None:
    _assert_source_family_domain(bind, before)
    op.drop_constraint(
        SOURCE_FAMILY_CHECK_NAME, "track_branch_aliases", type_="check",
    )
    allowed = ", ".join(f"'{family}'" for family in after)
    op.create_check_constraint(
        SOURCE_FAMILY_CHECK_NAME, "track_branch_aliases",
        f"source_family IN ({allowed})",
    )
    _assert_source_family_domain(bind, after)


def _validate_manifest() -> None:
    names = [raw.strip().casefold() for raw, _, _ in APPROVED_ALIASES]
    canons = [canon for _, canon, _ in APPROVED_ALIASES]
    ids = [branch_id for _, _, branch_id in APPROVED_ALIASES]
    if (
        len(APPROVED_ALIASES) != 26
        or len(set(names)) != 26
        or len(set(canons)) != 26
        or set(ids) != set(range(1, 27))
        or {"marca", "egade", "grupo de anuncios 1"} & set(names)
    ):
        raise RuntimeError("Manifiesto Google Ads: identidad duplicada o no autorizada.")


def _validate_real_branches(bind) -> None:
    wanted = {canon: branch_id for _, canon, branch_id in APPROVED_ALIASES}
    rows = bind.execute(
        sa.text(
            """
            SELECT t.sucursal_canon, t.sucursal_id,
                   t.is_track_active, s.operational_status
            FROM track_branch_catalog t
            LEFT JOIN sucursales s ON s.sucursal_id = t.sucursal_id
            WHERE t.sucursal_canon = ANY(:canons)
            """
        ),
        {"canons": list(wanted)},
    ).mappings().all()
    actual = {row["sucursal_canon"]: row for row in rows}
    if len(actual) != 26:
        raise RuntimeError("Faltan sucursales canónicas para Google Ads.")
    for canon, expected_id in wanted.items():
        row = actual[canon]
        if (
            row["sucursal_id"] != expected_id
            or row["is_track_active"] is not True
            or row["operational_status"] != "ACTIVA"
        ):
            raise RuntimeError(
                f"Sucursal no elegible para Google Ads: {canon} "
                f"(ID esperado {expected_id})."
            )


def _check_existing_aliases(bind) -> None:
    existing = bind.execute(
        sa.text(
            """
            SELECT raw_branch_name, sucursal_canon, is_active
            FROM track_branch_aliases WHERE source_family = :family
            """
        ),
        {"family": FAMILY},
    ).mappings().all()
    wanted = {raw.casefold(): canon for raw, canon, _ in APPROVED_ALIASES}
    for row in existing:
        normalized = row["raw_branch_name"].strip().casefold()
        if (
            normalized not in wanted
            or wanted[normalized] != row["sucursal_canon"]
            or row["is_active"] is not True
            or row["raw_branch_name"] not in {
                raw for raw, _, _ in APPROVED_ALIASES
            }
        ):
            raise RuntimeError(
                "Alias google_ads_family ajeno o conflictivo: "
                f"{row['raw_branch_name']!r}."
            )


def upgrade():
    _validate_manifest()
    bind = op.get_bind()
    _validate_real_branches(bind)
    _check_existing_aliases(bind)
    actual_domain = _source_families_in_database(bind)
    if actual_domain == set(SOURCE_FAMILIES_BEFORE):
        _replace_check_domain(
            bind, before=SOURCE_FAMILIES_BEFORE,
            after=SOURCE_FAMILIES_AFTER,
        )
    else:
        # Fail closed on an unexpected constraint, including one missing M4.
        _assert_source_family_domain(bind, SOURCE_FAMILIES_AFTER)

    sql = sa.text(
        """
        INSERT INTO track_branch_aliases
            (source_family, raw_branch_name, sucursal_canon, is_active, notes)
        VALUES (:family, :raw_name, :canon, true, :notes)
        ON CONFLICT (source_family, raw_branch_name) DO NOTHING
        """
    )
    bind.execute(
        sql,
        [
            {
                "family": FAMILY, "raw_name": raw, "canon": canon,
                "notes": NOTES,
            }
            for raw, canon, _ in APPROVED_ALIASES
        ],
    )
    _check_existing_aliases(bind)
    count = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM track_branch_aliases "
            "WHERE source_family = :family AND is_active = true"
        ),
        {"family": FAMILY},
    ).scalar_one()
    if count != 26:
        raise RuntimeError("El catálogo Google Ads no quedó en 26 alias activos.")


def downgrade():
    bind = op.get_bind()
    _assert_source_family_domain(bind, SOURCE_FAMILIES_AFTER)
    # A downgrade must not silently remove independently changed mappings.
    rows = bind.execute(
        sa.text(
            "SELECT raw_branch_name, notes "
            "FROM track_branch_aliases WHERE source_family = :family"
        ),
        {"family": FAMILY},
    ).mappings().all()
    expected_names = {raw for raw, _, _ in APPROVED_ALIASES}
    if (
        len(rows) != 26
        or {r["raw_branch_name"] for r in rows} != expected_names
        or any(r["notes"] != NOTES for r in rows)
    ):
        raise RuntimeError(
            "No es seguro revertir Google Ads M4: el catálogo fue modificado."
        )
    bind.execute(
        sa.text(
            "DELETE FROM track_branch_aliases "
            "WHERE source_family = :family AND notes = :notes"
        ),
        {"family": FAMILY, "notes": NOTES},
    )
    remaining = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM track_branch_aliases "
            "WHERE source_family = :family"
        ),
        {"family": FAMILY},
    ).scalar_one()
    if remaining:
        raise RuntimeError("Persisten alias Google Ads después del downgrade.")
    _replace_check_domain(
        bind, before=SOURCE_FAMILIES_AFTER, after=SOURCE_FAMILIES_BEFORE,
    )
