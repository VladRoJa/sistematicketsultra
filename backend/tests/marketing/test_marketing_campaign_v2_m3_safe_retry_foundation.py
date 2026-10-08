from __future__ import annotations

import importlib.util
from pathlib import Path

from app.models.marketing import MarketingCampaignV2ProviderCampaignORM


def _migration_module():
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "f3f1d4e6a7c9_add_campaign_v2_safe_retry.py"
    )
    spec = importlib.util.spec_from_file_location(
        "campaign_v2_m3_safe_retry",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_m3_safe_retry_model_has_audit_fields():
    columns = MarketingCampaignV2ProviderCampaignORM.__table__.c

    assert columns.retry_attempt_count.nullable is False
    assert columns.retry_last_attempt_at.nullable is True
    assert columns.retry_next_allowed_at.nullable is True
    assert columns.retry_last_by_user_id.nullable is True
    assert columns.retry_history_json.nullable is False


def test_m3_safe_retry_constraints_expose_limit_and_terminal_state():
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
    assert "RETRY_EXHAUSTED" in status

    attempts = constraints[
        "ck_mkt_v2_provider_campaign_retry_attempts"
    ]
    assert "retry_attempt_count <= 3" in attempts

    eligible = constraints[
        "ck_mkt_v2_provider_campaign_retry_eligible"
    ]
    assert "retry_attempt_count < 3" in eligible

    exhausted = constraints[
        "ck_mkt_v2_provider_campaign_retry_exhausted"
    ]
    assert "retry_attempt_count >= 3" in exhausted


def test_m3_safe_retry_migration_extends_reconciliation_head():
    module = _migration_module()

    assert module.revision == "f3f1d4e6a7c9"
    assert module.down_revision == "f3e0c3d5a6b8"


def test_m3_safe_retry_postgresql_identifiers_fit_limit():
    module = _migration_module()

    names = (
        module.STATUS_CONSTRAINT,
        module.RETRY_ELIGIBLE_CONSTRAINT,
        module.RETRY_EXHAUSTED_CONSTRAINT,
        module.RETRY_ATTEMPTS_CONSTRAINT,
        module.RETRY_LAST_USER_FK,
        module.RETRY_NEXT_INDEX,
    )

    assert all(len(name) <= 63 for name in names)
