"""add marketing campaign v2 tariff catalog

Revision ID: c3a7e1f5b9d2
Revises: e2c4a6b8d0f1
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import unicodedata
from typing import Any

from alembic import op
import sqlalchemy as sa


revision = "c3a7e1f5b9d2"
down_revision = "e2c4a6b8d0f1"
branch_labels = None
depends_on = None


_EXPECTED_TARIFF_COUNT = 166
_EXPECTED_SNAPSHOT_SHA256 = (
    "00b9475ea8bdfbaf3c9d1d3571d630035ff315ab8cd374fb0339e18589162bae"
)
_EXPECTED_FAMILY_COUNTS = {
    "DOMICILIADO": 102,
    "TRIMESTRAL": 21,
    "CONVENIO": 12,
    "SEMESTRE": 10,
    "OUT_OF_SEGMENT": 10,
    "ESTUDIANTE": 6,
    "MES": 5,
}
_VALID_AUDIENCE_FAMILIES = frozenset(_EXPECTED_FAMILY_COUNTS)
_SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "reference"
    / "marketing_campaign_v2_tariffs_2026-09-30.json"
)


def _normalize_tariff_key(value: Any) -> str | None:
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKC", str(value)).strip().upper()
    normalized = " ".join(normalized.split())
    return normalized or None


def _load_snapshot_rows() -> list[dict[str, str]]:
    payload = _SNAPSHOT_PATH.read_bytes()
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if actual_sha256 != _EXPECTED_SNAPSHOT_SHA256:
        raise RuntimeError(
            "Campaign V2 tariff snapshot SHA-256 mismatch: "
            f"expected {_EXPECTED_SNAPSHOT_SHA256}, got {actual_sha256}"
        )

    document = json.loads(payload.decode("utf-8"))
    if document.get("schema_version") != 1:
        raise RuntimeError("Campaign V2 tariff snapshot schema_version must be 1")
    if document.get("catalog_key") != "marketing_campaign_v2_tariffs":
        raise RuntimeError("Campaign V2 tariff snapshot catalog_key is invalid")
    if document.get("artifact_policy") != "immutable":
        raise RuntimeError("Campaign V2 tariff snapshot must be immutable")
    if document.get("approved_on") != "2026-09-30":
        raise RuntimeError("Campaign V2 tariff snapshot approved_on is invalid")
    if document.get("row_count") != _EXPECTED_TARIFF_COUNT:
        raise RuntimeError("Campaign V2 tariff snapshot metadata count is invalid")

    tariffs = document.get("tariffs")
    if not isinstance(tariffs, list) or len(tariffs) != _EXPECTED_TARIFF_COUNT:
        raise RuntimeError(
            "Campaign V2 tariff snapshot must contain exactly "
            f"{_EXPECTED_TARIFF_COUNT} tariffs"
        )

    rows: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    family_counts: Counter[str] = Counter()

    for tariff in tariffs:
        if not isinstance(tariff, dict):
            raise RuntimeError("Campaign V2 tariff snapshot row must be an object")

        tarifa_raw = str(tariff.get("tarifa_raw") or "")
        tarifa_key = _normalize_tariff_key(tarifa_raw)
        categoria_tarifa = str(tariff.get("categoria_tarifa") or "").strip()
        audience_family = str(tariff.get("audience_family") or "").strip()

        if not tarifa_key or not categoria_tarifa:
            raise RuntimeError("Campaign V2 tariff snapshot contains an empty value")
        if audience_family not in _VALID_AUDIENCE_FAMILIES:
            raise RuntimeError(
                f"Invalid Campaign V2 audience_family for {tarifa_raw!r}: "
                f"{audience_family!r}"
            )
        if tarifa_key in seen_keys:
            raise RuntimeError(
                f"Duplicate normalized Campaign V2 tariff key: {tarifa_key!r}"
            )

        seen_keys.add(tarifa_key)
        family_counts[audience_family] += 1
        rows.append(
            {
                "tarifa_key": tarifa_key,
                "tarifa_raw": tarifa_raw,
                "categoria_tarifa": categoria_tarifa,
                "audience_family": audience_family,
            }
        )

    if dict(family_counts) != _EXPECTED_FAMILY_COUNTS:
        raise RuntimeError(
            "Campaign V2 tariff snapshot audience_family distribution is invalid: "
            f"{dict(family_counts)!r}"
        )

    return sorted(rows, key=lambda row: row["tarifa_key"])


def upgrade():
    op.create_table(
        "marketing_campaign_v2_tariffs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tarifa_key", sa.String(length=255), nullable=False),
        sa.Column("tarifa_raw", sa.String(length=255), nullable=False),
        sa.Column("categoria_tarifa", sa.String(length=100), nullable=False),
        sa.Column("audience_family", sa.String(length=30), nullable=False),
        sa.CheckConstraint(
            "audience_family IN ("
            "'DOMICILIADO', "
            "'TRIMESTRAL', "
            "'CONVENIO', "
            "'SEMESTRE', "
            "'ESTUDIANTE', "
            "'MES', "
            "'OUT_OF_SEGMENT'"
            ")",
            name="ck_marketing_campaign_v2_tariffs_audience_family",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_marketing_campaign_v2_tariffs",
        ),
        sa.UniqueConstraint(
            "tarifa_key",
            name="uq_marketing_campaign_v2_tariffs_tarifa_key",
        ),
    )
    op.create_index(
        "ix_marketing_campaign_v2_tariffs_audience_family",
        "marketing_campaign_v2_tariffs",
        ["audience_family"],
        unique=False,
    )

    tariff_table = sa.table(
        "marketing_campaign_v2_tariffs",
        sa.column("tarifa_key", sa.String(length=255)),
        sa.column("tarifa_raw", sa.String(length=255)),
        sa.column("categoria_tarifa", sa.String(length=100)),
        sa.column("audience_family", sa.String(length=30)),
    )
    op.bulk_insert(tariff_table, _load_snapshot_rows())


def downgrade():
    op.drop_index(
        "ix_marketing_campaign_v2_tariffs_audience_family",
        table_name="marketing_campaign_v2_tariffs",
    )
    op.drop_table("marketing_campaign_v2_tariffs")
