from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.dialects import postgresql

from app.services.marketing_meta_dashboard_service import (
    _aggregate_campaign_investment,
    build_canonical_meta_run_statement,
    build_iventas_campaign_evidence_statement,
    read_meta_dashboard_investment_data,
    serialize_meta_investment_detail,
)


def _aggregate(insights, evidence):
    return _aggregate_campaign_investment(
        meta_sync_run_id=2,
        iventas_sync_run_id=2,
        date_from=date(2026, 8, 1),
        date_to=date(2026, 8, 17),
        insight_rows=insights,
        evidence_rows=evidence,
    )


def test_campaign_with_multiple_ads_and_leads_spends_once():
    result = _aggregate(
        [
            {"campaign_id": "c1", "ad_id": "a1", "spend": "10.25"},
            {"campaign_id": "c1", "ad_id": "a2", "spend": "4.75"},
        ],
        [
            {
                "meta_ad_id": "a1",
                "sucursal_id": 7,
                "iventas_contact_row_id": 101,
            },
            {
                "meta_ad_id": "a1",
                "sucursal_id": 7,
                "iventas_contact_row_id": 102,
            },
            {
                "meta_ad_id": "a2",
                "sucursal_id": 7,
                "iventas_contact_row_id": 101,
            },
        ],
    )

    assert result.total_meta_spend == Decimal("15.00")
    assert result.assigned_spend == Decimal("15.00")
    assert result.branch_spend == {7: Decimal("15.00")}
    assert result.campaigns_assigned == 1
    assert len(result.campaign_rows) == 1
    assert result.campaign_rows[0].meta_observed_leads == 2
    assert result.campaign_rows[0].ads_count == 2


def test_ad_without_leads_is_included_when_campaign_resolves():
    result = _aggregate(
        [
            {"campaign_id": "c1", "ad_id": "a1", "spend": "10"},
            {"campaign_id": "c1", "ad_id": "a2", "spend": "6"},
        ],
        [
            {
                "meta_ad_id": "a1",
                "sucursal_id": 3,
                "iventas_contact_row_id": 201,
            }
        ],
    )

    assert result.branch_spend == {3: Decimal("16")}
    assert result.unassigned_spend == Decimal("0")


def test_campaign_without_match_is_unassigned():
    result = _aggregate(
        [{"campaign_id": "c1", "ad_id": "a1", "spend": "9.50"}],
        [],
    )

    assert result.assigned_spend == Decimal("0")
    assert result.unassigned_spend == Decimal("9.50")
    assert result.campaigns_unassigned == 1


def test_campaign_with_two_branches_is_conflict_without_split():
    result = _aggregate(
        [{"campaign_id": "c1", "ad_id": "a1", "spend": "20"}],
        [
            {
                "meta_ad_id": "a1",
                "sucursal_id": 1,
                "iventas_contact_row_id": 301,
            },
            {
                "meta_ad_id": "a1",
                "sucursal_id": 2,
                "iventas_contact_row_id": 302,
            },
        ],
    )

    assert result.branch_spend == {}
    assert result.assigned_spend == Decimal("0")
    assert result.conflict_spend == Decimal("20")
    assert result.campaigns_conflict == 1


class _MappingsResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class _Session:
    def __init__(self, results):
        self.results = iter(results)

    def execute(self, _statement):
        return _MappingsResult(next(self.results))


def test_no_canonical_meta_returns_unavailable_without_fake_zero():
    result = read_meta_dashboard_investment_data(
        month_date=date(2026, 8, 1),
        iventas_sync_run_id=2,
        session=_Session([[]]),
    )

    assert result.available is False
    assert result.meta_sync_run_id is None
    assert result.total_meta_spend is None
    assert result.assigned_spend is None
    assert result.branch_spend == {}


def test_canonical_meta_without_iventas_does_not_fake_zero_investment():
    result = read_meta_dashboard_investment_data(
        month_date=date(2026, 8, 1),
        iventas_sync_run_id=None,
        session=_Session(
            [
                [
                    {
                        "sync_run_id": 2,
                        "date_from": date(2026, 8, 1),
                        "date_to": date(2026, 8, 17),
                    }
                ],
                [
                    {
                        "campaign_id": "c1",
                        "ad_id": "a1",
                        "spend": "125.50",
                    }
                ],
            ]
        ),
    )

    assert result.available is True
    assert result.meta_sync_run_id == 2
    assert result.iventas_sync_run_id is None
    assert result.total_meta_spend == Decimal("125.50")

    # Meta existe, pero sin iVentas no puede determinarse
    # qué inversión pertenece al funnel/sucursal.
    assert result.assigned_spend is None
    assert result.unassigned_spend is None
    assert result.conflict_spend is None
    assert result.branch_spend == {}


def test_matching_meta_and_iventas_windows_assign_investment():
    class _SessionWithMatchingIventasRun(_Session):
        def get(self, _model, run_id):
            assert run_id == 2
            return type(
                "_IventasRun",
                (),
                {
                    "date_from": date(2026, 8, 1),
                    "date_to": date(2026, 8, 17),
                },
            )()

    result = read_meta_dashboard_investment_data(
        month_date=date(2026, 8, 1),
        iventas_sync_run_id=2,
        session=_SessionWithMatchingIventasRun(
            [
                [
                    {
                        "sync_run_id": 2,
                        "date_from": date(2026, 8, 1),
                        "date_to": date(2026, 8, 17),
                    }
                ],
                [
                    {
                        "campaign_id": "c1",
                        "ad_id": "a1",
                        "spend": "125.50",
                    }
                ],
                [
                    {
                        "meta_ad_id": "a1",
                        "sucursal_id": 7,
                        "iventas_contact_row_id": 401,
                    }
                ],
            ]
        ),
    )

    assert result.available is True
    assert result.meta_sync_run_id == 2
    assert result.iventas_sync_run_id == 2
    assert result.total_meta_spend == Decimal("125.50")
    assert result.assigned_spend == Decimal("125.50")
    assert result.unassigned_spend == Decimal("0")
    assert result.conflict_spend == Decimal("0")
    assert result.branch_spend == {7: Decimal("125.50")}
    assert result.campaigns_assigned == 1


def test_meta_and_iventas_date_window_mismatch_does_not_assign_investment():
    class _SessionWithIventasRun(_Session):
        def get(self, _model, run_id):
            assert run_id == 2
            return type(
                "_IventasRun",
                (),
                {
                    "date_from": date(2026, 8, 1),
                    "date_to": date(2026, 8, 17),
                },
            )()

    result = read_meta_dashboard_investment_data(
        month_date=date(2026, 8, 1),
        iventas_sync_run_id=2,
        session=_SessionWithIventasRun(
            [
                [
                    {
                        "sync_run_id": 2,
                        "date_from": date(2026, 8, 1),
                        "date_to": date(2026, 8, 18),
                    }
                ],
                [
                    {
                        "campaign_id": "c1",
                        "ad_id": "a1",
                        "spend": "125.50",
                    }
                ],
                [
                    {
                        "meta_ad_id": "a1",
                        "sucursal_id": 7,
                    }
                ],
            ]
        ),
    )

    assert result.available is True
    assert result.meta_sync_run_id == 2
    assert result.iventas_sync_run_id == 2
    assert result.date_from == date(2026, 8, 1)
    assert result.date_to == date(2026, 8, 18)
    assert result.total_meta_spend == Decimal("125.50")

    # Ambos orígenes existen, pero sus ventanas no coinciden.
    # No debe fabricarse una inversión atribuible al funnel.
    assert result.assigned_spend is None
    assert result.unassigned_spend is None
    assert result.conflict_spend is None
    assert result.branch_spend == {}
    assert result.campaigns_total == 1
    assert result.campaigns_assigned is None
    assert result.campaigns_unassigned is None
    assert result.campaigns_conflict is None
    assert result.campaign_rows == ()


def test_canonical_meta_statement_requires_completed_canonical_period():
    statement = build_canonical_meta_run_statement(
        period_key="META-2026-08"
    )
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()

    assert "period_key = 'meta-2026-08'" in sql
    assert "status = 'completed'" in sql
    assert "is_canonical is true" in sql


def test_iventas_evidence_statement_uses_only_exact_run_and_lead_tags():
    statement = build_iventas_campaign_evidence_statement(
        iventas_sync_run_id=27,
        meta_ad_ids=("a1", "a2"),
    )
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()

    assert "marketing_iventas_contact_tags.sync_run_id = 27" in sql
    assert "marketing_iventas_contacts.sync_run_id = 27" in sql
    assert "first_message_at_utc is not null" in sql
    assert "tag_kind = 'meta_ad'" in sql
    assert "meta_ad_id is not null" in sql


def test_global_detail_rows_reconcile_all_campaign_statuses():
    result = _aggregate(
        [
            {"campaign_id": "assigned", "ad_id": "a1", "spend": "10"},
            {"campaign_id": "unassigned", "ad_id": "a2", "spend": "4"},
            {"campaign_id": "conflict", "ad_id": "a3", "spend": "6"},
        ],
        [
            {
                "meta_ad_id": "a1",
                "sucursal_id": 1,
                "iventas_contact_row_id": 1,
            },
            {
                "meta_ad_id": "a3",
                "sucursal_id": 1,
                "iventas_contact_row_id": 2,
            },
            {
                "meta_ad_id": "a3",
                "sucursal_id": 2,
                "iventas_contact_row_id": 3,
            },
        ],
    )

    detail = serialize_meta_investment_detail(
        month="2026-08",
        scope={"type": "GLOBAL", "branch_ids": [1, 2]},
        sucursal_id=None,
        meta_data=result,
        selected_branch_ids=(1, 2),
        branch_names={1: "Uno", 2: "Dos"},
        expose_global_totals=True,
    )

    spend_by_status = {
        status: sum(
            row["spend"]
            for row in detail["rows"]
            if row["assignment_status"] == status
        )
        for status in ("ASSIGNED", "UNASSIGNED", "CONFLICT")
    }
    assert detail["summary"]["card_investment"] == 10.0
    assert detail["summary"]["total_meta_spend"] == 20.0
    assert spend_by_status == {
        "ASSIGNED": 10.0,
        "UNASSIGNED": 4.0,
        "CONFLICT": 6.0,
    }


def test_restricted_detail_hides_campaigns_and_corporate_totals():
    result = _aggregate(
        [
            {"campaign_id": "branch-1", "ad_id": "a1", "spend": "10"},
            {"campaign_id": "branch-2", "ad_id": "a2", "spend": "8"},
            {"campaign_id": "unassigned", "ad_id": "a3", "spend": "4"},
        ],
        [
            {
                "meta_ad_id": "a1",
                "sucursal_id": 1,
                "iventas_contact_row_id": 1,
            },
            {
                "meta_ad_id": "a2",
                "sucursal_id": 2,
                "iventas_contact_row_id": 2,
            },
        ],
    )

    detail = serialize_meta_investment_detail(
        month="2026-08",
        scope={"type": "PRIMARY_BRANCH", "branch_ids": [1]},
        sucursal_id=None,
        meta_data=result,
        selected_branch_ids=(1,),
        branch_names={1: "Uno"},
        expose_global_totals=False,
    )

    assert [row["campaign_id"] for row in detail["rows"]] == [
        "branch-1"
    ]
    assert detail["summary"]["card_investment"] == 10.0
    assert detail["summary"]["total_meta_spend"] is None
    assert detail["summary"]["unassigned_spend"] is None
    assert detail["summary"]["conflict_spend"] is None
