"""seed Campaign V2 iVentas branch channel bindings

Revision ID: f3c8a1b2d4e6
Revises: a7b8c9d0e1f2
Create Date: 2026-10-08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "f3c8a1b2d4e6"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


PROVIDER = "IVENTAS"
SEED_SOURCE = "IVENTAS_OFFICIAL_BRANCH_CHANNELS_2026-10-08"

# Azahares already exists in production and is intentionally not reseeded here.
# Atención al Cliente is not a Track branch and is intentionally excluded.
# Tecnológico uses only the current iVentas channel; the old inactive channel
# 6a4553b6355c12000876bd05 must never be inserted by this migration.
CHANNEL_BINDINGS = (
    (1, "VILLAS_DEL_REY", "villas-del-rey", "6a1f4ba45586b20009719963"),
    (2, "VILLA_VERDE", "villa-verde", "6a205a8f5586b2000971b5e8"),
    (3, "INDEPENDENCIA", "independencia", "6a29c8ffe83fa20008b5a789"),
    (4, "TEC_MXL", "tecnologico-2", "6a86010a24aa9a00076c9800"),
    (5, "SEND_MXL", "sendero-mexicali", "6a29b1c12be53d00098a5f74"),
    (6, "SAN_LUIS", "san-luis-rio-colorado", "6a1f9c1655736500088a0ad1"),
    (7, "PABELLON_RTO", "pabellon-rosarito", "6a29ce18db4dac0009d16e56"),
    (8, "MISION_ENS", "mision", "6a28215127a48a00095ffe54"),
    (9, "PASEO_2000", "paseo-2000", "6a299740e83fa20008b59c9a"),
    (10, "LOMA_BONITA", "loma-bonita", "6a4ed83e24aa9a0008eb2b40"),
    (11, "SANTA_FE", "santa-fe", "6a2836effe11c3000877289c"),
    (12, "CARROUSEL_TJ", "carrousel", "6a298931ee978000082219db"),
    (13, "PAPALOTE_TJ", "papalote", "6a272e4de61c8a00084140a5"),
    (14, "SEND_CUL", "sendero-culiacan", "6a21acf127a48a00095f02cf"),
    (15, "SAN_ISIDRO_CUL", "san-isidro", "6a234a3f02ec4b00086bb453"),
    (17, "STA_CATARINA", "santa-catarina", "6a234646fe11c30008766944"),
    (18, "SEND_SALTILLO", "saltillo-sur", "6a21ca7755736500088a5652"),
    (19, "SEND_CHIH", "sendero-chihuahua", "6a21a88627a48a00095f018e"),
    (20, "PASEO_LA_PAZ", "paseo-la-paz", "6a222611e61c8a0008407c2d"),
    (21, "IXTAPALUCA", "ixtapaluca", "6a2af03a33da8500082f5262"),
    (22, "INSURGENTES", "insurgentes", "6a2aff2d555186000912586d"),
    (23, "TLALNEPANTLA", "tlalnepantla", "6a1f4d87e61c8a0008400fa7"),
    (24, "SALTILLO_VILLALTA", "villalta", "6a29cc585551860009123719"),
    (25, "METEPEC", "metepec", "6a68fb0324aa9a0008f6359d"),
    (26, "SERRANIA", "serrania", "6a28b1d755736500088b68b2"),
)


def _binding_table() -> sa.TableClause:
    return sa.table(
        "marketing_campaign_v2_channel_bindings",
        sa.column("id", sa.BigInteger()),
        sa.column("provider", sa.String(length=50)),
        sa.column("sucursal_id", sa.Integer()),
        sa.column("sucursal_canon", sa.String(length=100)),
        sa.column("provider_channel_id", sa.String(length=255)),
        sa.column("is_active", sa.Boolean()),
        sa.column("is_default", sa.Boolean()),
        sa.column("metadata_json", sa.JSON()),
    )


def _ensure_binding(
    bind,
    table: sa.TableClause,
    *,
    sucursal_id: int,
    sucursal_canon: str,
    iventas_branch: str,
    provider_channel_id: str,
) -> None:
    by_channel = bind.execute(
        sa.select(
            table.c.id,
            table.c.sucursal_id,
            table.c.sucursal_canon,
            table.c.is_active,
            table.c.is_default,
        ).where(
            table.c.provider == PROVIDER,
            table.c.provider_channel_id == provider_channel_id,
        )
    ).mappings().all()

    if by_channel:
        if len(by_channel) != 1:
            raise RuntimeError(
                f"Duplicate {PROVIDER} provider_channel_id detected: "
                f"{provider_channel_id}"
            )
        existing = by_channel[0]
        if (
            int(existing["sucursal_id"]) != sucursal_id
            or str(existing["sucursal_canon"]) != sucursal_canon
        ):
            raise RuntimeError(
                f"{PROVIDER} channel {provider_channel_id} is already bound "
                "to another branch."
            )
        return

    current_defaults = bind.execute(
        sa.select(
            table.c.id,
            table.c.provider_channel_id,
            table.c.sucursal_canon,
        ).where(
            table.c.provider == PROVIDER,
            table.c.sucursal_id == sucursal_id,
            table.c.is_active.is_(True),
            table.c.is_default.is_(True),
        )
    ).mappings().all()

    if current_defaults:
        raise RuntimeError(
            f"{PROVIDER} branch {sucursal_canon} already has an active "
            "default channel different from the official catalog."
        )

    bind.execute(
        table.insert().values(
            provider=PROVIDER,
            sucursal_id=sucursal_id,
            sucursal_canon=sucursal_canon,
            provider_channel_id=provider_channel_id,
            is_active=True,
            is_default=True,
            metadata_json={
                "iventas_branch": iventas_branch,
                "seed_source": SEED_SOURCE,
            },
        )
    )


def upgrade():
    bind = op.get_bind()
    table = _binding_table()

    for (
        sucursal_id,
        sucursal_canon,
        iventas_branch,
        provider_channel_id,
    ) in CHANNEL_BINDINGS:
        _ensure_binding(
            bind,
            table,
            sucursal_id=sucursal_id,
            sucursal_canon=sucursal_canon,
            iventas_branch=iventas_branch,
            provider_channel_id=provider_channel_id,
        )


def downgrade():
    bind = op.get_bind()
    table = _binding_table()

    for (
        sucursal_id,
        sucursal_canon,
        _iventas_branch,
        provider_channel_id,
    ) in reversed(CHANNEL_BINDINGS):
        rows = bind.execute(
            sa.select(
                table.c.id,
                table.c.metadata_json,
            ).where(
                table.c.provider == PROVIDER,
                table.c.sucursal_id == sucursal_id,
                table.c.sucursal_canon == sucursal_canon,
                table.c.provider_channel_id == provider_channel_id,
            )
        ).mappings().all()

        for row in rows:
            metadata = dict(row["metadata_json"] or {})
            if metadata.get("seed_source") != SEED_SOURCE:
                continue
            bind.execute(
                table.delete().where(table.c.id == int(row["id"]))
            )
