from __future__ import annotations

import importlib.util
from pathlib import Path

from app.models.marketing import MarketingCampaignV2ProviderCampaignORM


def _migration_module():
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "f3d9b2c4e5f7_add_campaign_v2_scheduling.py"
    )
    spec = importlib.util.spec_from_file_location(
        "campaign_v2_m3_scheduling",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_m3_scheduling_model_has_auditable_schedule_fields():
    columns = MarketingCampaignV2ProviderCampaignORM.__table__.c

    assert columns.scheduled_by_user_id.nullable is True
    assert columns.scheduled_timezone.nullable is True
    assert columns.scheduled_local_at.nullable is True
    assert columns.scheduled_for.nullable is True
    assert columns.provider_send_at.nullable is True


def test_m3_scheduling_status_constraint_includes_scheduled():
    constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in (
            MarketingCampaignV2ProviderCampaignORM.__table__.constraints
        )
        if getattr(constraint, "name", None)
        and hasattr(constraint, "sqltext")
    }

    assert "SCHEDULED" in constraints[
        "ck_marketing_campaign_v2_provider_campaign_status"
    ]
    assert (
        "scheduled_for IS NOT NULL"
        in constraints[
            "ck_marketing_campaign_v2_provider_campaign_schedule_complete"
        ]
    )


def test_m3_scheduling_migration_extends_channel_seed_head():
    module = _migration_module()

    assert module.revision == "f3d9b2c4e5f7"
    assert module.down_revision == "f3c8a1b2d4e6"


def test_m3_scheduling_postgresql_identifiers_fit_limit():
    module = _migration_module()

    names = (
        module.STATUS_CONSTRAINT,
        module.SCHEDULE_CONSTRAINT,
        module.SCHEDULED_INDEX,
        module.SCHEDULED_BY_FK,
    )

    assert all(len(name) <= 63 for name in names)
