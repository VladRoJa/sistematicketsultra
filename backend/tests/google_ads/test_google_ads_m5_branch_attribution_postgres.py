"""M5-CORE: real PostgreSQL 16 isolation tests for scoped SQL queries.

Three *synthetic* branches with approved keys from the versioned manifest.
No production connection, mutations to existing Suite tables, or Funnel API.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import os
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.google_ads_daily import GoogleAdsDailyMetricORM
from app.models.google_ads_ad_group_daily import GoogleAdsAdGroupDailyMetricORM
from app.models.google_ads_branch_identity_mapping import (
    GoogleAdsBranchIdentityMappingORM,
)
from app.models.sucursal_model import Sucursal
from app.models.warehouse import TrackBranchCatalogORM
from app.services.marketing_access import MarketingAccess
from app.services import marketing_google_ads_branch_attribution_service as reader
from app.warehouse.services.google_ads_m5_identity_seed_service import (
    _load as load_approved_manifest,
)

TEST_URL = os.environ.get("GOOGLE_ADS_M5_TEST_POSTGRES_URL")
FIRST_DAY = date(2026, 10, 1)
SECOND_DAY = date(2026, 10, 2)
MODEL_TABLES = (
    Sucursal.__table__,
    TrackBranchCatalogORM.__table__,
    GoogleAdsBranchIdentityMappingORM.__table__,
    GoogleAdsAdGroupDailyMetricORM.__table__,
    GoogleAdsDailyMetricORM.__table__,
)


def _engine():
    if not TEST_URL:
        pytest.skip("Requiere PostgreSQL 16 aislado para M5")
    url = sa.engine.make_url(TEST_URL)
    if (
        url.get_backend_name() != "postgresql"
        or url.host not in ("localhost", "127.0.0.1")
        or url.database != "google_ads_m5_test"
        or url.username != "google_ads_m5_ci"
    ):
        pytest.fail("BD fuera del laboratorio M5 prohibida")
    return sa.create_engine(TEST_URL, future=True)


@pytest.fixture()
def real_pg(monkeypatch):
    """Create only the minimum authentic ORM tables in a rolled-back PG txn."""
    engine = _engine()
    meta = sa.MetaData()
    upload = sa.Table(
        "warehouse_uploads", meta,
        sa.Column("id", sa.Integer, primary_key=True),
    )
    tables = {model.name: model.to_metadata(meta) for model in MODEL_TABLES}
    manifest = load_approved_manifest()
    approved = {int(r[5]): r for r in manifest["rows"]}
    ids = (1, 2, 3)
    assert set(ids) <= set(approved)

    try:
        with engine.begin() as connection:
            meta.create_all(connection)
            connection.execute(upload.insert(), {"id": 21499})
            for branch_id in ids:
                approved_row = approved[branch_id]
                connection.execute(tables["sucursales"].insert(), {
                    "sucursal_id": branch_id,
                    "serie": str(branch_id),
                    "sucursal": f"Synthetic {branch_id}",
                    "estado": "BC",
                    "operational_status": "ACTIVA",
                    "municipio": "LAB",
                    "direccion": "Synthetic data only",
                })
                connection.execute(tables["track_branch_catalog"].insert(), {
                    "sucursal_canon": approved_row[4],
                    "sucursal_id": branch_id,
                    "track_label": f"LAB {branch_id}",
                    "display_order": branch_id,
                    "is_track_active": True,
                })
                connection.execute(
                    tables["google_ads_branch_identity_mappings"].insert(), {
                        "customer_id": reader.CUSTOMER_ID,
                        "campaign_key": approved_row[2],
                        "ad_group_key": approved_row[3],
                        "sucursal_canon": approved_row[4],
                        "source_upload_id": 21499,
                        "valid_from": date(2026, 9, 24),
                        "valid_to": date(2026, 10, 8),
                        "approval_status": reader.APPROVAL_STATUS,
                        "approval_reference": reader.APPROVAL_REFERENCE,
                        "approved_on": date(2026, 10, 12),
                    },
                )
                for day in (FIRST_DAY, SECOND_DAY):
                    connection.execute(
                        tables["google_ads_ad_group_daily_metrics"].insert(), {
                            "customer_id": reader.CUSTOMER_ID,
                            "campaign_key": approved_row[2],
                            "ad_group_key": approved_row[3],
                            "campaign_name": approved_row[0],
                            "ad_group_name": approved_row[1],
                            "report_date": day,
                            "currency_code": "MXN",
                            "cost": Decimal(str(branch_id * 5)),
                            "impressions": branch_id * 20,
                            "clicks": branch_id * 2,
                            "conversions": Decimal("1"),
                            "free_pass_conversions": Decimal("0.5"),
                            "web_purchase_conversions": Decimal("0.25"),
                            "conversion_value": Decimal("0"),
                            "source_kind": "WAREHOUSE_XLSX",
                            "source_upload_id": 21499,
                            "created_at": datetime.now(timezone.utc),
                        },
                    )

            statements = []

            def track_select(conn, cursor, statement, parameters, context, many):
                if statement.lstrip().lower().startswith("select"):
                    statements.append((statement, parameters))

            sa.event.listen(engine, "before_cursor_execute", track_select)
            with Session(bind=connection) as session:
                monkeypatch.setattr(
                    reader, "db", SimpleNamespace(session=session),
                )
                # Faithful scope mechanism, without Flask request context.
                monkeypatch.setattr(
                    reader, "load_visible_marketing_branches",
                    lambda access: (
                        [],
                        access.visible_branch_ids(ids),
                        {},
                    ),
                )
                yield connection, tables, statements
            sa.event.remove(engine, "before_cursor_execute", track_select)
            meta.drop_all(connection)
    finally:
        engine.dispose()


def _access(role, branch_ids):
    return MarketingAccess(
        type="PRIMARY_BRANCH" if role == "GERENTE" else "ASSIGNED_BRANCHES",
        is_global=False,
        branch_ids=tuple(branch_ids),
        role=role,
        can_edit_inputs=False,
    )


def _read(role, ids):
    return reader.read_google_ads_branch_attribution(
        month_start=FIRST_DAY, cutoff_date=SECOND_DAY,
        access=_access(role, ids),
    )


def _assert_scoped_sql(statements, allowed):
    """Inspect the SQL *sent to PostgreSQL*; no account-wide scans."""
    assert statements, "No hubo consultas SQL"
    assert not any(
        "google_ads_daily_metrics" in sql
        for sql, _ in statements
    ), "El ledger global no puede consultarse con acceso restringido"
    mappings = [
        (sql, params) for sql, params in statements
        if "google_ads_branch_identity_mappings" in sql
    ]
    assert len(mappings) >= 2
    for sql, params in mappings:
        normalized = " ".join(sql.lower().split())
        assert "track_branch_catalog.sucursal_id in (" in normalized
        assert isinstance(params, dict)
        branch_parameters = {
            int(v) for k, v in params.items()
            if k.startswith("sucursal_id_") and isinstance(v, int)
        }
        assert branch_parameters == set(allowed), (
            "SQL filtró sucursales distintas de las autorizadas: "
            f"{branch_parameters} vs {set(allowed)}"
        )


def test_pg16_primary_and_regional_read_only_scopes(real_pg):
    _connection, _tables, statements = real_pg

    primary = _read("GERENTE", (1,))
    assert primary["status"] == "complete"
    assert primary["scope_attributed_cost"] == 10.0
    assert [r["sucursal_id"] for r in primary["rows"]] == [1]
    assert "account_cost_observed" not in primary
    _assert_scoped_sql(statements, (1,))

    statements.clear()
    regional = _read("GERENTE_REGIONAL", (1, 2))
    assert regional["status"] == "complete"
    assert regional["scope_attributed_cost"] == 30.0
    assert [r["sucursal_id"] for r in regional["rows"]] == [1, 2]
    assert "unassigned_cost_observed" not in regional
    _assert_scoped_sql(statements, (1, 2))

    statements.clear()
    third = _read("GERENTE", (3,))
    assert third["status"] == "complete"
    assert third["scope_attributed_cost"] == 30.0
    assert [r["sucursal_id"] for r in third["rows"]] == [3]
    _assert_scoped_sql(statements, (3,))

    assert all(
        result["account_reconciled"] is not True
        for result in (primary, regional, third)
        if "account_reconciled" in result
    )


def test_pg16_missing_regional_day_fails_closed_without_global_query(real_pg):
    conn, tables, statements = real_pg
    facts = tables["google_ads_ad_group_daily_metrics"]
    manifest = load_approved_manifest()
    second_key = next(r[3] for r in manifest["rows"] if r[5] == 2)
    conn.execute(
        sa.delete(facts).where(
            facts.c.ad_group_key == second_key,
            facts.c.report_date == SECOND_DAY,
        )
    )
    # Club 1 remains valid. Regional cannot present an incomplete sum.
    primary = _read("GERENTE", (1,))
    assert primary["status"] == "complete"
    regional = _read("GERENTE_REGIONAL", (1, 2))
    assert regional["status"] == "requires_review"
    assert regional["scope_attributed_cost"] is None
    assert regional["rows"] == []
    assert not any(
        "google_ads_daily_metrics" in sql for sql, _ in statements
    )


def test_pg16_foreign_branch_not_in_scope_never_reaches_result(real_pg):
    _connection, _tables, statements = real_pg
    res = _read("GERENTE_REGIONAL", (1, 9999))
    assert res["status"] == "complete"
    assert [r["sucursal_id"] for r in res["rows"]] == [1]
    assert res["scope_attributed_cost"] == 10.0
    _assert_scoped_sql(statements, (1,))
