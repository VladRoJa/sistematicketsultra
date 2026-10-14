"""M6 SQL permission isolation with real PostgreSQL 16 and synthetic branches.

Only 2 synthetic branches are inserted to measure SQL scope filtering; the
separate authenticated-approval test proves all 26 are inserted on approval.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.google_ads_daily import GoogleAdsDailyMetricORM
from app.models.google_ads_ad_group_daily import GoogleAdsAdGroupDailyMetricORM
from app.models.google_ads_m6_continuity import (
    GoogleAdsBranchApprovalVersionORM, GoogleAdsBranchApprovedIdentityORM,
)
from app.models.sucursal_model import Sucursal
from app.models.warehouse import TrackBranchCatalogORM
from app.services import marketing_google_ads_m6_attribution_service as reader
from app.services.marketing_access import MarketingAccess
from app.warehouse.services.google_ads_m5_identity_seed_service import (
    _load as load_manifest,
)
from test_google_ads_m6_continuity_postgres import _test_engine


@pytest.fixture()
def m6_pg(monkeypatch):
    engine = _test_engine()
    meta = sa.MetaData()
    users = sa.Table("users", meta, sa.Column("id", sa.Integer, primary_key=True))
    uploads = sa.Table(
        "warehouse_uploads", meta, sa.Column("id", sa.Integer, primary_key=True),
    )
    models = (
        Sucursal.__table__, TrackBranchCatalogORM.__table__,
        GoogleAdsDailyMetricORM.__table__, GoogleAdsAdGroupDailyMetricORM.__table__,
        GoogleAdsBranchApprovalVersionORM.__table__,
        GoogleAdsBranchApprovedIdentityORM.__table__,
    )
    tables = {model.name: model.to_metadata(meta) for model in models}
    manifest = load_manifest()
    mapped = {int(row[5]): row for row in manifest["rows"]}
    ids = (1, 2)
    try:
        with engine.begin() as conn:
            for table in (*tables.values(), users, uploads):
                assert not sa.inspect(conn).has_table(table.name), table.name
            meta.create_all(conn)
            conn.execute(users.insert(), [{"id": 47}])
            conn.execute(uploads.insert(), [
                {"id": 21499}, {"id": 21604}, {"id": 21605},
            ])
            for branch_id in ids:
                m = mapped[branch_id]
                conn.execute(tables["sucursales"].insert(), {
                    "sucursal_id": branch_id, "serie": str(branch_id),
                    "sucursal": f"Lab {branch_id}", "estado": "BC",
                    "operational_status": "ACTIVA", "municipio": "LAB",
                    "direccion": "Synthetic",
                })
                conn.execute(tables["track_branch_catalog"].insert(), {
                    "sucursal_canon": m[4], "sucursal_id": branch_id,
                    "track_label": f"LAB {branch_id}", "display_order": branch_id,
                    "is_track_active": True,
                })
            version_id = conn.execute(
                tables["google_ads_branch_approval_versions"].insert().returning(
                    tables["google_ads_branch_approval_versions"].c.id,
                ), {
                    "customer_id": reader.CUSTOMER_ID,
                    "approval_reference": reader.M6_REFERENCE,
                    "source_approval_reference": reader.M5_REFERENCE,
                    "valid_from": reader.START, "valid_to": None,
                    "source_campaign_upload_id": 21604,
                    "source_ad_group_upload_id": 21605,
                    "approved_by_user_id": 47,
                    "approved_on": date(2026, 10, 14),
                },
            ).scalar_one()
            conn.execute(tables["google_ads_branch_approved_identities"].insert(), [
                {
                    "approval_version_id": version_id,
                    "campaign_key": mapped[i][2],
                    "ad_group_key": mapped[i][3],
                    "sucursal_canon": mapped[i][4],
                }
                for i in ids
            ])
            rows = []
            for branch_id in ids:
                m = mapped[branch_id]
                for day in range(9, 13):
                    rows.append({
                        "customer_id": reader.CUSTOMER_ID,
                        "campaign_id": None, "ad_group_id": None,
                        "campaign_key": m[2], "ad_group_key": m[3],
                        "campaign_name": m[0], "ad_group_name": m[1],
                        "report_date": date(2026, 10, day),
                        "currency_code": "MXN", "cost": Decimal(str(branch_id * 5)),
                        "clicks": branch_id * 2, "impressions": branch_id * 20,
                        "conversions": Decimal("1"),
                        "free_pass_conversions": Decimal("0.5"),
                        "web_purchase_conversions": Decimal("0.25"),
                        "conversion_value": Decimal("0"),
                        "source_kind": "WAREHOUSE_XLSX",
                        "source_upload_id": 21605,
                    })
            conn.execute(tables["google_ads_ad_group_daily_metrics"].insert(), rows)
            statements = []
            def capture(_conn, _cursor, sql, parameters, _context, _many):
                if sql.lstrip().lower().startswith("select"):
                    statements.append((sql, parameters))
            sa.event.listen(engine, "before_cursor_execute", capture)
            with Session(bind=conn) as session:
                monkeypatch.setattr(reader, "db", SimpleNamespace(session=session))
                monkeypatch.setattr(
                    reader, "load_visible_marketing_branches",
                    lambda access: ([], access.visible_branch_ids(ids), {}),
                )
                yield conn, tables, statements, mapped
            sa.event.remove(engine, "before_cursor_execute", capture)
            meta.drop_all(conn)
    finally:
        engine.dispose()


def _access(branch_ids):
    return MarketingAccess(
        type="PRIMARY_BRANCH" if len(branch_ids) == 1 else "ASSIGNED_BRANCHES",
        is_global=False, branch_ids=tuple(branch_ids),
        role="GERENTE" if len(branch_ids) == 1 else "GERENTE_REGIONAL",
        can_edit_inputs=False,
    )


def _read(ids):
    return reader.read_google_ads_m6_branch_attribution(
        month_start=date(2026, 10, 1),
        cutoff_date=date(2026, 10, 12),
        access=_access(ids),
    )


def _assert_sql_scoped(statements, allowed):
    assert statements
    assert not any(
        "google_ads_daily_metrics" in sql for sql, _ in statements
    ), "A branch-limited user queried the global Google Ads account ledger."
    fact_queries = [
        (sql, parameters) for sql, parameters in statements
        if "google_ads_ad_group_daily_metrics" in sql
    ]
    assert fact_queries
    for sql, parameters in fact_queries:
        normalized = " ".join(sql.lower().split())
        assert "track_branch_catalog.sucursal_id in (" in normalized
        assert {
            int(value) for key, value in parameters.items()
            if key.startswith("sucursal_id_") and isinstance(value, int)
        } == set(allowed)


def test_pg16_gerente_and_regional_only_see_authorized_branch(m6_pg):
    _conn, _tables, statements, _mapped = m6_pg
    gerente = _read((1,))
    assert gerente["status"] == "partial"
    assert gerente["covered_days"] == 4
    assert gerente["scope_attributed_cost"] == 20.0
    assert [r["sucursal_id"] for r in gerente["rows"]] == [1]
    assert "account_cost_observed" not in gerente
    _assert_sql_scoped(statements, (1,))

    statements.clear()
    regional = _read((1, 2))
    assert regional["scope_attributed_cost"] == 60.0
    assert [r["sucursal_id"] for r in regional["rows"]] == [1, 2]
    assert "unassigned_cost_observed" not in regional
    _assert_sql_scoped(statements, (1, 2))


def test_pg16_missing_branch_day_fails_closed_without_account_query(m6_pg):
    conn, tables, statements, mapped = m6_pg
    conn.execute(sa.delete(tables["google_ads_ad_group_daily_metrics"]).where(
        tables["google_ads_ad_group_daily_metrics"].c.ad_group_key == mapped[2][3],
        tables["google_ads_ad_group_daily_metrics"].c.report_date == date(2026, 10, 12),
    ))
    assert _read((1,))["status"] == "partial"
    regional = _read((1, 2))
    assert regional["status"] == "requires_review"
    assert regional["rows"] == []
    assert regional["scope_attributed_cost"] is None
    assert not any("google_ads_daily_metrics" in sql for sql, _ in statements)
