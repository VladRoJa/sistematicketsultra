from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa


def _load_migration():
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "f3c8a1b2d4e6_seed_campaign_v2_iventas_channels.py"
    )
    spec = importlib.util.spec_from_file_location(
        "campaign_v2_m3_channel_seed",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _channel_table(metadata):
    return sa.Table(
        "marketing_campaign_v2_channel_bindings",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("sucursal_id", sa.Integer(), nullable=False),
        sa.Column("sucursal_canon", sa.String(100), nullable=False),
        sa.Column("provider_channel_id", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
    )


def test_m3_channel_seed_catalog_is_exact_and_safe():
    module = _load_migration()

    assert module.revision == "f3c8a1b2d4e6"
    assert module.down_revision == "a7b8c9d0e1f2"
    assert len(module.CHANNEL_BINDINGS) == 25

    sucursal_ids = {row[0] for row in module.CHANNEL_BINDINGS}
    canons = {row[1] for row in module.CHANNEL_BINDINGS}
    branches = {row[2] for row in module.CHANNEL_BINDINGS}
    channels = {row[3] for row in module.CHANNEL_BINDINGS}

    assert len(sucursal_ids) == 25
    assert len(canons) == 25
    assert len(channels) == 25
    assert 16 not in sucursal_ids
    assert "AZAHARES_CUL" not in canons
    assert "atencion-al-cliente" not in branches
    assert "6a7e23bf24aa9a00076c8b3c" not in channels

    tech = [row for row in module.CHANNEL_BINDINGS if row[1] == "TEC_MXL"]
    assert tech == [
        (
            4,
            "TEC_MXL",
            "tecnologico-2",
            "6a86010a24aa9a00076c9800",
        )
    ]
    assert "6a4553b6355c12000876bd05" not in channels


def test_m3_channel_seed_upgrade_is_idempotent(monkeypatch):
    module = _load_migration()
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    table = _channel_table(metadata)
    metadata.create_all(engine)

    with engine.begin() as connection:
        monkeypatch.setattr(module.op, "get_bind", lambda: connection)

        module.upgrade()
        module.upgrade()

        rows = connection.execute(
            sa.select(table).order_by(table.c.sucursal_id)
        ).mappings().all()

        assert len(rows) == 25
        assert all(row["provider"] == "IVENTAS" for row in rows)
        assert all(row["is_active"] is True for row in rows)
        assert all(row["is_default"] is True for row in rows)
        assert all(
            row["metadata_json"]["seed_source"] == module.SEED_SOURCE
            for row in rows
        )

    engine.dispose()


def test_m3_channel_seed_rejects_existing_conflicting_default():
    module = _load_migration()
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    table = _channel_table(metadata)
    metadata.create_all(engine)

    tech = next(
        row for row in module.CHANNEL_BINDINGS if row[1] == "TEC_MXL"
    )

    with engine.begin() as connection:
        connection.execute(
            table.insert().values(
                provider="IVENTAS",
                sucursal_id=4,
                sucursal_canon="TEC_MXL",
                provider_channel_id="different-current-channel",
                is_active=True,
                is_default=True,
                metadata_json={},
            )
        )

        with pytest.raises(RuntimeError, match="already has an active default"):
            module._ensure_binding(
                connection,
                module._binding_table(),
                sucursal_id=tech[0],
                sucursal_canon=tech[1],
                iventas_branch=tech[2],
                provider_channel_id=tech[3],
            )

        channels = connection.execute(
            sa.select(table.c.provider_channel_id)
        ).scalars().all()
        assert channels == ["different-current-channel"]

    engine.dispose()


def test_m3_channel_seed_downgrade_only_removes_seeded_rows(monkeypatch):
    module = _load_migration()
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    table = _channel_table(metadata)
    metadata.create_all(engine)

    with engine.begin() as connection:
        monkeypatch.setattr(module.op, "get_bind", lambda: connection)
        module.upgrade()

        connection.execute(
            table.insert().values(
                provider="IVENTAS",
                sucursal_id=16,
                sucursal_canon="AZAHARES_CUL",
                provider_channel_id="6a2201f802ec4b00086b8bb2",
                is_active=True,
                is_default=True,
                metadata_json={"source": "existing-production-binding"},
            )
        )

        module.downgrade()

        remaining = connection.execute(
            sa.select(table)
        ).mappings().all()

        assert len(remaining) == 1
        assert remaining[0]["sucursal_canon"] == "AZAHARES_CUL"
        assert (
            remaining[0]["provider_channel_id"]
            == "6a2201f802ec4b00086b8bb2"
        )

    engine.dispose()
