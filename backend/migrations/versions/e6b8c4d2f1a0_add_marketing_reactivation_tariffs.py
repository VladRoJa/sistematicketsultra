"""add marketing reactivation tariffs

Revision ID: e6b8c4d2f1a0
Revises: d9f4b2c7e1a6
Create Date: 2026-09-03
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unicodedata

from alembic import op
import sqlalchemy as sa


revision = "e6b8c4d2f1a0"
down_revision = "d9f4b2c7e1a6"
branch_labels = None
depends_on = None


_EXPECTED_TARIFF_COUNT = 161
_EXPECTED_CANONICAL_SEED_SHA256 = (
    "20766ed709508b78979a235bad94b429cc9398d80e2b1b6c2702e26e28b8ba2f"
)
_VALID_REACTIVATION_GROUPS = {
    "REACTIVATE",
    "DOMICILIATED_FLOW",
    "EXCLUDE",
    "REVIEW",
}
_SEED_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "reference"
    / "reactivacion_tarifas_edmundo_seed.json"
)


def _normalize_tariff_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().upper()
    return re.sub(r"\s+", " ", normalized)


def _load_seed_rows() -> list[dict[str, object]]:
    document = json.loads(_SEED_PATH.read_text(encoding="utf-8"))
    tariffs = document.get("tariffs")
    source = document.get("source") or {}
    groups = document.get("groups") or {}
    if not isinstance(tariffs, list) or len(tariffs) != _EXPECTED_TARIFF_COUNT:
        raise RuntimeError(
            "Reactivation tariff seed must contain exactly "
            f"{_EXPECTED_TARIFF_COUNT} tariffs"
        )
    if source.get("distinct_tariffs") != _EXPECTED_TARIFF_COUNT:
        raise RuntimeError("Reactivation tariff seed metadata count is invalid")
    if source.get("conflicts") != 0:
        raise RuntimeError("Reactivation tariff seed contains classification conflicts")

    source_name = str(source.get("name") or "").strip()
    if not source_name:
        raise RuntimeError("Reactivation tariff seed source is required")

    canonical_tariffs = sorted(
        [
            {
                "tarifa_raw": tariff.get("tarifa_raw"),
                "categoria_tarifa": tariff.get("categoria_tarifa"),
                "reactivation_group": tariff.get("reactivation_group"),
            }
            for tariff in tariffs
        ],
        key=lambda tariff: str(tariff["tarifa_raw"]),
    )
    canonical_payload = json.dumps(
        {"source": source_name, "tariffs": canonical_tariffs},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if (
        hashlib.sha256(canonical_payload).hexdigest()
        != _EXPECTED_CANONICAL_SEED_SHA256
    ):
        raise RuntimeError("Reactivation tariff seed does not match the approved data")

    category_groups: dict[str, str] = {}
    for group, categories in groups.items():
        if group not in _VALID_REACTIVATION_GROUPS or not isinstance(
            categories, list
        ):
            raise RuntimeError("Reactivation tariff seed groups are invalid")
        for category in categories:
            category_name = str(category).strip()
            if category_name in category_groups:
                raise RuntimeError(
                    "Reactivation tariff category belongs to multiple groups: "
                    f"{category_name!r}"
                )
            category_groups[category_name] = group

    rows: list[dict[str, object]] = []
    seen_keys: set[str] = set()
    for tariff in tariffs:
        tarifa_raw = str(tariff.get("tarifa_raw") or "")
        tarifa_key = _normalize_tariff_key(tarifa_raw)
        categoria_tarifa = str(tariff.get("categoria_tarifa") or "").strip()
        reactivation_group = str(tariff.get("reactivation_group") or "").strip()
        if not tarifa_key or not categoria_tarifa:
            raise RuntimeError("Reactivation tariff seed contains an empty value")
        if reactivation_group not in _VALID_REACTIVATION_GROUPS:
            raise RuntimeError(
                f"Invalid reactivation group for tariff {tarifa_raw!r}: "
                f"{reactivation_group!r}"
            )
        if tarifa_key in seen_keys:
            raise RuntimeError(
                f"Duplicate normalized reactivation tariff key: {tarifa_key!r}"
            )
        seen_keys.add(tarifa_key)
        rows.append(
            {
                "tarifa_key": tarifa_key,
                "tarifa_raw": tarifa_raw,
                "categoria_tarifa": categoria_tarifa,
                "reactivation_group": reactivation_group,
                "is_active": True,
                "source": source_name,
            }
        )
    return sorted(rows, key=lambda row: str(row["tarifa_key"]))


def upgrade():
    op.create_table(
        "marketing_reactivation_tariffs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tarifa_key", sa.String(length=255), nullable=False),
        sa.Column("tarifa_raw", sa.String(length=255), nullable=False),
        sa.Column("categoria_tarifa", sa.String(length=100), nullable=False),
        sa.Column("reactivation_group", sa.String(length=30), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "reactivation_group IN "
            "('REACTIVATE', 'DOMICILIATED_FLOW', 'EXCLUDE', 'REVIEW')",
            name="ck_marketing_reactivation_tariffs_group",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_marketing_reactivation_tariffs",
        ),
        sa.UniqueConstraint(
            "tarifa_key",
            name="uq_marketing_reactivation_tariffs_tarifa_key",
        ),
    )
    op.create_index(
        "ix_marketing_reactivation_tariffs_active_group",
        "marketing_reactivation_tariffs",
        ["is_active", "reactivation_group"],
        unique=False,
    )

    tariff_table = sa.table(
        "marketing_reactivation_tariffs",
        sa.column("tarifa_key", sa.String(length=255)),
        sa.column("tarifa_raw", sa.String(length=255)),
        sa.column("categoria_tarifa", sa.String(length=100)),
        sa.column("reactivation_group", sa.String(length=30)),
        sa.column("is_active", sa.Boolean()),
        sa.column("source", sa.String(length=255)),
    )
    op.bulk_insert(tariff_table, _load_seed_rows())


def downgrade():
    op.drop_index(
        "ix_marketing_reactivation_tariffs_active_group",
        table_name="marketing_reactivation_tariffs",
    )
    op.drop_table("marketing_reactivation_tariffs")
