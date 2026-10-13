"""M6 schema contract: no implicit approval and no M5 historical mutation."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models.google_ads_m6_continuity import (
    GoogleAdsBranchApprovalVersionORM,
    GoogleAdsBranchApprovedIdentityORM,
)


def _constraints(table):
    return {constraint.name for constraint in table.constraints}


def _foreign_keys(table):
    return {
        (key.parent.name, key.target_fullname, key.ondelete)
        for key in table.foreign_keys
    }


def test_approval_version_persists_explicit_actor_and_original_evidence():
    table = GoogleAdsBranchApprovalVersionORM.__table__
    assert table.name == "google_ads_branch_approval_versions"
    for key in (
        "customer_id", "approval_reference", "source_approval_reference",
        "valid_from", "valid_to", "source_campaign_upload_id",
        "source_ad_group_upload_id", "approved_by_user_id", "approved_on",
    ):
        assert key in table.c
    assert table.c.approved_by_user_id.nullable is False
    assert table.c.valid_to.nullable is True  # ongoing validity until explicitly superseded
    assert (
        "approved_by_user_id", "users.id", "RESTRICT"
    ) in _foreign_keys(table)
    assert (
        "source_campaign_upload_id", "warehouse_uploads.id", "RESTRICT"
    ) in _foreign_keys(table)
    assert (
        "source_ad_group_upload_id", "warehouse_uploads.id", "RESTRICT"
    ) in _foreign_keys(table)
    assert "uq_ga_m6_approval_reference" in _constraints(table)
    assert "uq_ga_m6_approval_start" in _constraints(table)
    assert "ck_ga_m6_approval_dates" in _constraints(table)
    assert "ck_ga_m6_distinct_sources" in _constraints(table)


def test_approved_identities_are_versioned_not_bound_to_each_daily_upload():
    table = GoogleAdsBranchApprovedIdentityORM.__table__
    assert table.name == "google_ads_branch_approved_identities"
    assert "source_upload_id" not in table.c
    assert "source_campaign_upload_id" not in table.c
    assert "source_ad_group_upload_id" not in table.c
    assert (
        "approval_version_id", "google_ads_branch_approval_versions.id", "RESTRICT"
    ) in _foreign_keys(table)
    assert (
        "sucursal_canon", "track_branch_catalog.sucursal_canon", "RESTRICT"
    ) in _foreign_keys(table)
    assert "uq_ga_m6_version_identity" in _constraints(table)
    assert "ck_ga_m6_campaign_key" in _constraints(table)
    assert "ck_ga_m6_ad_group_key" in _constraints(table)


def test_schema_is_valid_postgresql_and_preserves_m5_name():
    versions = GoogleAdsBranchApprovalVersionORM.__table__
    identities = GoogleAdsBranchApprovedIdentityORM.__table__
    assert versions.name != "google_ads_branch_identity_mappings"
    assert identities.name != "google_ads_branch_identity_mappings"
    for table in (versions, identities):
        ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
        assert "CREATE TABLE" in ddl
        assert "CHECK" in ddl
        assert "FOREIGN KEY" in ddl


def test_alembic_revision_has_no_seed_and_protects_rollback():
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/b3e7c2d9a104_google_ads_m6_branch_continuity.py"
    )
    spec = importlib.util.spec_from_file_location("google_ads_m6_revision", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    assert module.revision == "b3e7c2d9a104"
    assert module.down_revision == "e4b856c9170d"
    source = path.read_text(encoding="utf-8")
    assert "op.create_table(" in source
    assert "op.execute(" not in source
    assert "op.alter_column(" not in source
    assert "op.drop_constraint(" not in source
    assert "if count:" in source
    assert "raise RuntimeError(" in source
