from __future__ import annotations

import importlib.util
from pathlib import Path

from app.models.marketing import MarketingCampaignV2ProviderCampaignORM


def _migration_module():
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "f3e0c3d5a6b8_add_campaign_v2_reconciliation.py"
    )
    spec = importlib.util.spec_from_file_location(
        "campaign_v2_m3_reconciliation",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_m3_reconciliation_model_has_audit_fields():
    columns = MarketingCampaignV2ProviderCampaignORM.__table__.c

    assert columns.reconciliation_resolution.nullable is True
    assert columns.reconciliation_note.nullable is True
    assert columns.reconciliation_snapshot_json.nullable is False
    assert columns.reconciled_by_user_id.nullable is True
    assert columns.reconciled_at.nullable is True


def test_m3_reconciliation_constraints_expose_safe_states():
    constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in (
            MarketingCampaignV2ProviderCampaignORM.__table__.constraints
        )
        if getattr(constraint, "name", None)
        and hasattr(constraint, "sqltext")
    }

    status = constraints[
        "ck_marketing_campaign_v2_provider_campaign_status"
    ]
    assert "RETRY_ELIGIBLE" in status

    resolution = constraints[
        "ck_mkt_v2_provider_campaign_reconciliation_resolution"
    ]
    assert "PROVIDER_CAMPAIGN_FOUND" in resolution
    assert "NOT_CREATED_CONFIRMED" in resolution

    retry = constraints[
        "ck_mkt_v2_provider_campaign_retry_eligible"
    ]
    assert "NOT_CREATED_CONFIRMED" in retry
    assert "provider_campaign_id IS NULL" in retry


def test_m3_reconciliation_migration_extends_scheduling_head():
    module = _migration_module()

    assert module.revision == "f3e0c3d5a6b8"
    assert module.down_revision == "f3d9b2c4e5f7"


def test_m3_reconciliation_postgresql_identifiers_fit_limit():
    module = _migration_module()

    names = (
        module.STATUS_CONSTRAINT,
        module.RESOLUTION_CONSTRAINT,
        module.AUDIT_CONSTRAINT,
        module.FOUND_CONSTRAINT,
        module.RETRY_CONSTRAINT,
        module.RECONCILED_BY_FK,
    )

    assert all(len(name) <= 63 for name in names)
