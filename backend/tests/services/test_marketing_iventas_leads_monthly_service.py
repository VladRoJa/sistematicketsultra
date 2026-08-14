from datetime import date

from sqlalchemy.dialects import postgresql

from app.services.marketing_iventas_leads_service import (
    MarketingIventasLeadMetricsByBranchMonth,
    _build_lead_metrics_by_branch_month_statement,
    list_canonical_iventas_lead_metrics_by_branch_month,
)


class FakeMappings:
    def __init__(self, value):
        self.value = value

    def one(self):
        return self.value

    def all(self):
        return self.value


class FakeExecuteResult:
    def __init__(self, value):
        self.value = value

    def mappings(self):
        return FakeMappings(self.value)


class FakeSession:
    def __init__(self):
        self.executed_statements = []

    def execute(self, statement):
        self.executed_statements.append(statement)

        if len(self.executed_statements) == 1:
            return FakeExecuteResult({
                "sync_run_id": 41,
                "period_key": "IVENTAS-2026-08",
                "date_from": date(2026, 8, 1),
                "date_to": date(2026, 8, 31),
                "status": "COMPLETED",
                "is_canonical": True,
            })

        return FakeExecuteResult([
            {
                "month_start": date(2026, 8, 1),
                "sucursal_id": 2,
                "iventas_contacts": 3200,
                "iventas_contacts_with_first_message": 410,
                "meta_observed_leads": 275,
            }
        ])


def test_lists_month_metrics_without_mixing_populations():
    result = list_canonical_iventas_lead_metrics_by_branch_month(
        period_key="IVENTAS-2026-08",
        session=FakeSession(),
    )

    assert len(result) == 1

    row = result[0]

    assert isinstance(
        row,
        MarketingIventasLeadMetricsByBranchMonth,
    )
    assert row.month_start == date(2026, 8, 1)
    assert row.sucursal_id == 2
    assert row.iventas_contacts == 3200
    assert row.iventas_contacts_with_first_message == 410
    assert row.meta_observed_leads == 275

    assert (
        row.meta_observed_leads
        <= row.iventas_contacts_with_first_message
        <= row.iventas_contacts
    )



def test_month_sql_preserves_business_contract():
    statement = (
        _build_lead_metrics_by_branch_month_statement(
            41
        )
    )

    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={
                "literal_binds": True,
            },
        )
    ).lower()

    assert "date_trunc" in sql
    assert "created_date_local" in sql
    assert "sucursal_id" in sql
    assert "group by" in sql

    assert "first_message_at_utc is not null" in sql

    assert "exists" in sql
    assert "tag_kind" in sql
    assert "meta_ad" in sql

    assert "sync_run_id = 41" in sql
