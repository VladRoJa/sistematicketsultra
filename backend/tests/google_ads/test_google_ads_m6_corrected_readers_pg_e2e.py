"""C4 PG16: corrected canonical source selection and scoped privacy tests."""
from __future__ import annotations

from datetime import date
import json
from decimal import Decimal
import sqlalchemy as sa
import pytest

from app.extensions import db
from app.models.sucursal_model import Sucursal
from app.models.google_ads_daily import GoogleAdsDailyMetricORM
from app.services import (
    marketing_google_ads_m6_daily_attribution_service as daily,
    marketing_google_ads_funnel_service as global_reader,
)
from app.services.marketing_access import MarketingAccess
from app.warehouse.services import google_ads_m6_manual_preview_service as preview
from test_google_ads_m6_correction_promotion_pg_e2e import (
    promotion_lab, _promote,
)
from test_google_ads_m6_correction_decision_pg_e2e import (
    reviewer_lab, _stage, _review,
)
from test_google_ads_m6_correction_candidate_stage_pg_e2e import (
    candidate_lab, _stage as stage_revision,
)
from test_google_ads_m6_manual_structured_postgres import lab
from test_google_ads_m6_manual_raw_postgres import real_warehouse

DAY = date(2026, 10, 13)


@pytest.fixture
def readers_pg(promotion_lab, monkeypatch):
    client, actor, reviewer, engine, campaign, group = promotion_lab
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
        conn.execute(Sucursal.__table__.insert(), [{
            "sucursal_id": i + 1, "serie": str(i+1),
            "sucursal": f"Lab {i+1}", "estado": "LAB",
            "operational_status": "ACTIVA",
            "municipio": "LAB", "direccion": "Synthetic CI",
        } for i in range(26)])
        conn.execute(sa.text("""
            UPDATE track_branch_catalog
            SET sucursal_id = :id, track_label = :label,
                display_order = :id, is_track_active = true
            WHERE sucursal_canon = :branch
        """), [{
            "id": i + 1, "label": f"Lab {i+1}",
            "branch": f"LAB_BRANCH_{i}",
        } for i in range(26)])
    monkeypatch.setattr(daily, "_load_m5", preview._load_m5)
    monkeypatch.setattr(
        daily, "load_visible_marketing_branches",
        lambda access: (
            [], tuple(range(1, 27)) if access.is_global
            else access.visible_branch_ids(tuple(range(1, 27))), {},
        ),
    )
    monkeypatch.setenv(daily.CORRECTION_READER_FLAG, "true")
    try:
        yield client, actor, reviewer, engine, campaign, group
    finally:
        db.session.remove()
        with engine.begin() as conn:
            Sucursal.__table__.drop(conn)


def _access(*, ids=(), global_=False):
    return MarketingAccess(
        type="GLOBAL" if global_ else (
            "PRIMARY_BRANCH" if len(ids) == 1 else "ASSIGNED_BRANCHES"),
        is_global=global_, branch_ids=tuple(ids),
        role="ADMINISTRADOR" if global_ else (
            "GERENTE" if len(ids) == 1 else "GERENTE_REGIONAL"),
        can_edit_inputs=False,
    )


def _daily(ids=(), global_=False):
    return daily.read_google_ads_m6_daily_branch_attribution(
        month_start=date(2026, 10, 1),
        cutoff_date=DAY,
        access=_access(ids=ids, global_=global_),
    )


def _global():
    return global_reader.read_google_ads_funnel_investment(
        month_start=date(2026, 10, 1), cutoff_date=DAY, is_global=True,
    )


def _publish_correction(client, actor, reviewer, campaign, group):
    cid = _stage(client, actor, campaign, group)
    reviewed = _review(client, reviewer, cid)
    assert reviewed.status_code == 201, reviewed.get_json()
    posted = _promote(client, actor, cid, reviewed.json)
    assert posted.status_code == 201, posted.get_json()
    return posted.json


def test_canonical_correction_reads_27_campaigns_once_and_only_scoped_groups(
    readers_pg, monkeypatch,
):
    client, actor, reviewer, engine, campaign, group = readers_pg
    published = _publish_correction(client, actor, reviewer, campaign, group)
    expected = float(Decimal(published["account_cost_mxn"]))
    selected = []
    def observe(conn, cursor, sql, params, ctx, multi):
        if sql.lstrip().lower().startswith("select"):
            selected.append((sql.lower(), params))
    with client.application.app_context():
        app_engine = db.engine
        sa.event.listen(app_engine, "before_cursor_execute", observe)
        try:
            gerente = _daily((1,))
        finally:
            sa.event.remove(app_engine, "before_cursor_execute", observe)
    assert gerente["status"] == "partial", gerente
    assert gerente["covered_days"] == 1
    assert [row["sucursal_id"] for row in gerente["rows"]] == [1]
    assert gerente["scope_attributed_cost"] > 0
    assert not {"account_cost_observed", "unassigned_cost_observed"} & gerente.keys()
    group_queries = [(sql, params) for sql, params in selected
                     if "google_ads_m6_correction_group_facts" in sql]
    assert group_queries
    for sql, params in group_queries:
        assert "track_branch_catalog.sucursal_id in (" in sql
        assert "google_ads_m6_correction_group_facts.case_id in (" in sql
        scoped = {int(v) for k, v in params.items()
                  if k.startswith("sucursal_id_") and isinstance(v, int)}
        assert scoped == {1}
    assert not any("google_ads_m6_correction_campaign_facts" in sql
                   or "google_ads_daily_metrics" in sql
                   for sql, _ in selected)
    regional = _daily((1, 2))
    assert [row["sucursal_id"] for row in regional["rows"]] == [1, 2]
    assert regional["scope_attributed_cost"] >= gerente["scope_attributed_cost"]
    assert _daily((99,))["status"] == "scope_unavailable"
    company = _daily(global_=True)
    assert company["status"] == "partial", company
    assert company["account_reconciled"] is True
    assert company["account_cost_observed"] == pytest.approx(expected)
    assert company["scope_attributed_cost"] <= expected
    account = _global()
    assert account["status"] == "partial", account
    assert account["amount"] == pytest.approx(expected)
    assert account["covered_days"] == 1
    assert account["clicks"] > 0
    assert global_reader.read_google_ads_funnel_investment(
        month_start=date(2026, 10, 1), cutoff_date=DAY, is_global=False,
    )["amount"] is None


def test_corrected_canonical_ignores_original_global_campaign_spend(readers_pg):
    client, actor, reviewer, engine, campaign, group = readers_pg
    published = _publish_correction(client, actor, reviewer, campaign, group)
    with engine.begin() as conn:
        # Fake a previously imported/now-superseded 27-campaign ledger.
        # It must not leak into a canonical corrected revision.
        data = [{
            "customer_id": daily.CUSTOMER_ID, "campaign_id": None,
            "campaign_key": "name:" + format(i, "064x"),
            "campaign_name": f"Previous campaign {i}",
            "report_date": DAY, "currency_code": "MXN",
            "cost": Decimal("999.00"), "clicks": 1, "impressions": 10,
            "conversions": Decimal("0"), "conversion_value": Decimal("0"),
            "source_kind": "WAREHOUSE_XLSX", "source_upload_id": 990101,
        } for i in range(1, 28)]
        conn.execute(GoogleAdsDailyMetricORM.__table__.insert(), data)
    account = _global()
    assert account["amount"] == pytest.approx(
        float(Decimal(published["account_cost_mxn"]))
    ), account
    assert account["covered_days"] == 1


def test_corrected_reader_fails_closed_for_archived_or_tampered_raw(readers_pg):
    client, actor, reviewer, engine, campaign, group = readers_pg
    _publish_correction(client, actor, reviewer, campaign, group)
    with engine.begin() as conn:
        conn.execute(sa.text("""
            UPDATE warehouse_uploads SET status = 'ARCHIVED'
            WHERE id = :id
        """), {"id": group})
    assert _daily((1,))["status"] == "requires_review"
    assert _global()["amount"] is None


def test_corrected_reader_rejects_invalid_promotion_link(readers_pg):
    client, actor, reviewer, engine, campaign, group = readers_pg
    _publish_correction(client, actor, reviewer, campaign, group)
    with engine.begin() as conn:
        conn.execute(sa.text("""
            UPDATE google_ads_m6_correction_promotions
            SET snapshot_sha256 = :bad
        """), {"bad": "0" * 64})
    assert _daily((1,))["status"] == "requires_review"
    assert _global()["status"] == "requires_review"


def test_revision_two_replaces_account_and_branch_read_without_old_double_count(readers_pg):
    """Full SQL regression: historical canonical r1 superseded by approved r2."""
    client, actor, reviewer, engine, camp, group = readers_pg
    publication = __import__(
        "app.models.google_ads_m6_daily_publication",
        fromlist=["GoogleAdsM6DailyPublicationORM"],
    ).GoogleAdsM6DailyPublicationORM
    with engine.begin() as conn:
        prior = conn.execute(
            publication.__table__.insert().returning(publication.id), {
                "customer_id": daily.CUSTOMER_ID,
                "business_date": DAY, "revision": 1,
                "campaign_upload_id": 990101,
                "ad_group_upload_id": 990102,
                "approval_version_id": 1,
                "campaign_sha256": "f" * 64,
                "ad_group_sha256": "e" * 64,
                "is_canonical": True, "published_by_user_id": 47,
                "published_on": date(2026, 10, 14),
            },
        ).scalar_one()
        # This is the historical 27-row global account ledger, not active r2.
        conn.execute(GoogleAdsDailyMetricORM.__table__.insert(), [{
            "customer_id": daily.CUSTOMER_ID,
            "campaign_id": None,
            "campaign_key": "name:" + format(i, "064x"),
            "campaign_name": f"Prior campaign {i}",
            "report_date": DAY, "currency_code": "MXN",
            "cost": Decimal("999.00"),
            "clicks": 1, "impressions": 10,
            "conversions": Decimal("0"), "conversion_value": Decimal("0"),
            "source_kind": "WAREHOUSE_XLSX", "source_upload_id": 990101,
        } for i in range(1, 28)])
        conn.execute(sa.text("""
            UPDATE warehouse_audit_logs
               SET details = details::jsonb || CAST(:extra AS jsonb)
             WHERE action = 'UPLOAD'
               AND upload_id IN (:camp, :grp)
        """), {
            "extra": json.dumps({
                "intended_revision": 2,
                "expected_publication_id": prior,
            }),
            "camp": camp, "grp": group,
        })
    staged = stage_revision(client, actor, camp, group,
                            revision=2, expected=prior)
    assert staged.status_code == 201, staged.get_json()
    case_id = staged.json["case_id"]
    reviewed = _review(client, reviewer, case_id)
    assert reviewed.status_code == 201, reviewed.get_json()
    promoted = _promote(client, actor, case_id, reviewed.json,
                        revision=2, prior=prior)
    assert promoted.status_code == 201, promoted.get_json()
    new_cost = float(Decimal(promoted.json["account_cost_mxn"]))
    assert new_cost < 27000  # prior ledger intentionally costs 26,973 MXN
    from_company = _global()
    assert from_company["status"] == "partial", from_company
    assert from_company["amount"] == pytest.approx(new_cost), from_company
    assert from_company["covered_days"] == 1
    scoped = _daily((1,))
    assert scoped["status"] == "partial", scoped
    assert [r["sucursal_id"] for r in scoped["rows"]] == [1]
    global_daily = _daily(global_=True)
    assert global_daily["status"] == "partial", global_daily
    assert global_daily["account_cost_observed"] == pytest.approx(new_cost)
    assert global_daily["scope_attributed_cost"] <= new_cost
    with engine.connect() as conn:
        versions = conn.execute(sa.text("""
            SELECT revision, is_canonical
            FROM google_ads_m6_daily_publications
            WHERE business_date = :day ORDER BY revision
        """), {"day": DAY}).all()
    assert versions == [(1, False), (2, True)]

def test_global_correction_uses_read_only_snapshot_without_row_locks(readers_pg):
    """Funnel GET may validate hashes, but cannot acquire approval write locks."""
    client, actor, reviewer, engine, camp, group = readers_pg
    promoted = _publish_correction(client, actor, reviewer, camp, group)
    commands = []
    with client.application.app_context():
        app_engine = db.engine
        def record(_conn, _cursor, sql, params, _context, _multi):
            normalized = " ".join(sql.lower().split())
            if ("google_ads_m6_correction_" in normalized
                    or "set transaction" in normalized):
                commands.append(normalized)
        sa.event.listen(app_engine, "before_cursor_execute", record)
        try:
            account = _global()
        finally:
            sa.event.remove(app_engine, "before_cursor_execute", record)
    assert account["amount"] == pytest.approx(
        float(Decimal(promoted["account_cost_mxn"]))
    )
    assert any("set transaction isolation level repeatable read, read only"
               in line for line in commands)
    assert not any("for update" in line or "for share" in line
                   for line in commands)



def test_review_comparison_uses_immediately_previous_corrected_canonical(readers_pg):
    """Revision 2 candidate must compare against published correction r1,
    never a stale normal campaign ledger for the same day.
    """
    client, actor, reviewer, engine, camp, group = readers_pg
    promoted = _publish_correction(client, actor, reviewer, camp, group)
    previous = promoted["publication_id"]
    base_amount = Decimal(promoted["account_cost_mxn"])
    next_id = None
    try:
        with engine.begin() as conn:
            original_case = conn.execute(sa.text("""
                SELECT case_id FROM google_ads_m6_correction_promotions
                WHERE publication_id = :pub
            """), {"pub": previous}).scalar_one()
            # Read-only comparison fixture: clone facts for a hypothetical
            # next revision; do not use a staging endpoint or republish.
            next_id = conn.execute(sa.text("""
                INSERT INTO google_ads_m6_correction_cases (
                    customer_id, business_date, revision,
                    expected_publication_id, campaign_upload_id,
                    ad_group_upload_id, approval_version_id,
                    campaign_sha256, ad_group_sha256,
                    requested_by_user_id, reason
                )
                SELECT customer_id, business_date, 2,
                       :previous, campaign_upload_id, ad_group_upload_id,
                       approval_version_id, campaign_sha256, ad_group_sha256,
                       requested_by_user_id,
                       'Synthetic comparison of next version to prior correction'
                  FROM google_ads_m6_correction_cases WHERE id = :src
                RETURNING id
            """), {"src": original_case, "previous": previous}).scalar_one()
            conn.execute(sa.text("""
                INSERT INTO google_ads_m6_correction_campaign_facts (
                    case_id, campaign_key, campaign_name, currency_code,
                    cost, impressions, clicks, conversions, conversion_value
                )
                SELECT :new, campaign_key, campaign_name, currency_code,
                       cost, impressions, clicks, conversions, conversion_value
                FROM google_ads_m6_correction_campaign_facts WHERE case_id = :src
            """), {"new": next_id, "src": original_case})
            conn.execute(sa.text("""
                INSERT INTO google_ads_m6_correction_group_facts (
                    case_id, campaign_key, ad_group_key, campaign_name,
                    ad_group_name, currency_code, cost,
                    impressions, clicks, conversions,
                    free_pass_conversions, web_purchase_conversions, conversion_value
                )
                SELECT :new, campaign_key, ad_group_key, campaign_name,
                       ad_group_name, currency_code, cost,
                       impressions, clicks, conversions,
                       free_pass_conversions, web_purchase_conversions, conversion_value
                FROM google_ads_m6_correction_group_facts WHERE case_id = :src
            """), {"new": next_id, "src": original_case})
            conn.execute(sa.text("""
                UPDATE google_ads_m6_correction_campaign_facts
                   SET cost = cost + 10
                 WHERE id = (
                    SELECT MIN(id) FROM google_ads_m6_correction_campaign_facts
                    WHERE case_id = :id
                 )
            """), {"id": next_id})
            conn.execute(sa.text("""
                UPDATE google_ads_m6_correction_group_facts
                   SET cost = cost + 10
                 WHERE id = (
                    SELECT MIN(id) FROM google_ads_m6_correction_group_facts
                    WHERE case_id = :id
                 )
            """), {"id": next_id})
        inspected = client.get(
            "/api/integrations/google-ads/corrections/candidates/" + str(next_id),
            headers={"Authorization": "Bearer " + actor},
        )
        assert inspected.status_code == 200, inspected.get_json()
        assert Decimal(inspected.json["previous_account_cost_mxn"]) == base_amount
        assert Decimal(inspected.json["candidate_account_cost_mxn"]) == base_amount + 10
        assert Decimal(inspected.json["delta_account_cost_mxn"]) == Decimal("10")
        assert inspected.json["expected_publication_id"] == previous
        assert inspected.json["status"] == "REQUIRES_INDEPENDENT_REVIEW"
    finally:
        if next_id is not None:
            db.session.remove()
            with engine.begin() as conn:
                conn.execute(sa.text("""
                    DELETE FROM google_ads_m6_correction_group_facts
                    WHERE case_id = :id
                """), {"id": next_id})
                conn.execute(sa.text("""
                    DELETE FROM google_ads_m6_correction_campaign_facts
                    WHERE case_id = :id
                """), {"id": next_id})
                conn.execute(sa.text("""
                    DELETE FROM google_ads_m6_correction_cases
                    WHERE id = :id
                """), {"id": next_id})
