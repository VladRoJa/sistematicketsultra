"""Real PG16 M6 13-Oct regional privacy after RAW -> ingest -> publish.

HTTP CRUD and FS/DB provenance are real; only the external marketing
permission resolver and synthetic M5 baseline manifest are injected.
No production credentials, no actual publication, no mutation of live data.
"""
from __future__ import annotations

from datetime import date
import sqlalchemy as sa
import pytest

from app.extensions import db
from app.models.sucursal_model import Sucursal
from app.services import marketing_google_ads_m6_daily_attribution_service as reader
from app.services.marketing_access import MarketingAccess
from app.warehouse.services import google_ads_m6_manual_preview_service as preview_svc
from test_google_ads_m6_manual_raw_postgres import real_warehouse
from test_google_ads_m6_manual_structured_postgres import lab, _ingest
from test_google_ads_m6_manual_publication_postgres import (
    publication_lab, _publish,
)

DAY = date(2026, 10, 13)


def _access(branch_ids):
    return MarketingAccess(
        type="PRIMARY_BRANCH" if len(branch_ids) == 1 else "ASSIGNED_BRANCHES",
        is_global=False, branch_ids=tuple(branch_ids),
        role="GERENTE" if len(branch_ids) == 1 else "GERENTE_REGIONAL",
        can_edit_inputs=False,
    )


@pytest.fixture
def daily_pg(publication_lab, monkeypatch):
    client, token, other, engine, campaign_id, group_id = publication_lab
    # Structured fixture originally needs only a minimal catalog for 26
    # provisional identity strings. Enrich THAT isolated table in-place so
    # the actual ORM regional SQL joins/catalog permissions can be exercised.
    with engine.begin() as conn:
        assert not sa.inspect(conn).has_table("sucursales")
        Sucursal.__table__.create(conn)
        conn.execute(sa.text("""
            ALTER TABLE track_branch_catalog
            ADD COLUMN sucursal_id INTEGER,
            ADD COLUMN track_label TEXT,
            ADD COLUMN display_order INTEGER,
            ADD COLUMN is_track_active BOOLEAN,
            ADD COLUMN notes TEXT
        """))
        conn.execute(Sucursal.__table__.insert(), [
            {
                "sucursal_id": idx, "serie": str(idx),
                "sucursal": f"Lab Regional {idx}", "estado": "LAB",
                "operational_status": "ACTIVA", "municipio": "LAB",
                "direccion": "CI only",
            }
            for idx in (1, 2)
        ])
        conn.execute(sa.text("""
            UPDATE track_branch_catalog
            SET sucursal_id = :id, track_label = :label,
                display_order = :id, is_track_active = true
            WHERE sucursal_canon = :branch
        """), [
            {"id": idx, "label": f"Lab {idx}", "branch": f"LAB_BRANCH_{idx-1}"}
            for idx in (1, 2)
        ])
    monkeypatch.setattr(reader, "_load_m5", preview_svc._load_m5)
    monkeypatch.setattr(
        reader, "load_visible_marketing_branches",
        lambda access: ([], access.visible_branch_ids((1, 2)), {}),
    )
    monkeypatch.setenv("GOOGLE_ADS_M6_STRUCTURED_INGESTION_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_ADS_M6_DAILY_PUBLICATION_ENABLED", "true")

    stage = _ingest(client, token, campaign_id, group_id)
    assert stage.status_code == 201, stage.get_json()
    pub = _publish(client, token, campaign_id, group_id)
    assert pub.status_code == 201, pub.get_json()
    statements = []
    def record_sql(_conn, _cursor, statement, parameters, _context, _many):
        if statement.lstrip().lower().startswith("select"):
            statements.append((statement, parameters))
    app_engine = db.engine
    sa.event.listen(app_engine, "before_cursor_execute", record_sql)
    try:
        yield engine, group_id, statements
    finally:
        sa.event.remove(app_engine, "before_cursor_execute", record_sql)
        db.session.remove()
        with engine.begin() as conn:
            Sucursal.__table__.drop(conn)


def _read(branch_ids):
    return reader.read_google_ads_m6_daily_branch_attribution(
        month_start=date(2026, 10, 1),
        cutoff_date=DAY, access=_access(branch_ids),
    )


def _assert_scope_sql(statements, ids, upload_id):
    facts = [(sql, params) for sql, params in statements
             if "google_ads_ad_group_daily_metrics" in sql]
    assert facts, "The real group-fact SQL query must execute"
    for sql, params in facts:
        normalized = " ".join(sql.lower().split())
        assert "track_branch_catalog.sucursal_id in (" in normalized
        assert "google_ads_ad_group_daily_metrics.source_upload_id in (" in normalized
        branch_params = {
            int(v) for k, v in params.items()
            if k.startswith("sucursal_id_") and isinstance(v, int)
        }
        assert branch_params == set(ids)
        assert upload_id in set(params.values())
    assert not any("google_ads_daily_metrics" in sql for sql, _ in statements), (
        "A scoped user must not query the global campaign ledger"
    )


def test_real_pg16_published_day_isolated_by_gerente_and_regional(
    daily_pg, monkeypatch,
):
    engine, group_id, statements = daily_pg
    monkeypatch.setattr(
        reader, "_global_day_cost",
        lambda *a, **kw: pytest.fail("Restricted user queried account spend"),
    )
    gerente = _read((1,))
    assert gerente["status"] == "partial"
    assert gerente["covered_days"] == 1
    assert gerente["observed_from"] == gerente["observed_to"] == DAY.isoformat()
    assert [r["sucursal_id"] for r in gerente["rows"]] == [1]
    assert gerente["scope_attributed_cost"] is not None
    assert all(key not in gerente for key in (
        "account_cost_observed", "unassigned_cost_observed", "account_reconciled",
    ))
    _assert_scope_sql(statements, (1,), group_id)

    statements.clear()
    regional = _read((1, 2))
    assert regional["status"] == "partial"
    assert [r["sucursal_id"] for r in regional["rows"]] == [1, 2]
    assert regional["scope_attributed_cost"] >= gerente["scope_attributed_cost"]
    assert regional["covered_days"] == 1
    assert all(key not in regional for key in (
        "account_cost_observed", "unassigned_cost_observed", "account_reconciled",
    ))
    _assert_scope_sql(statements, (1, 2), group_id)

    statements.clear()
    no_access = _read((99,))
    assert no_access["status"] == "scope_unavailable"
    assert no_access["scope_attributed_cost"] is None
    assert not statements


def test_real_pg16_archived_canonical_raw_fails_closed(daily_pg):
    engine, group_id, statements = daily_pg
    with engine.begin() as conn:
        conn.execute(sa.text("""
            UPDATE warehouse_uploads SET status = 'ARCHIVED' WHERE id = :id
        """), {"id": group_id})
    invalid = _read((1,))
    assert invalid["status"] == "requires_review"
    assert invalid["rows"] == []
    assert invalid["scope_attributed_cost"] is None
    assert not any("google_ads_daily_metrics" in sql for sql, _ in statements)
