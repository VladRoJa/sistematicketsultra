from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.services.marketing_iventas_leads_service import (
    MarketingIventasCanonicalRunRequiredError,
    MarketingIventasLeadMetrics,
    MarketingIventasLeadMetricsByBranchDate,
    _build_lead_metrics_by_branch_date_statement,
    _build_lead_metrics_statement,
    list_canonical_iventas_lead_metrics_by_branch_date,
    read_canonical_iventas_lead_metrics,
)


class FakeMappings:
    def __init__(self, row):
        self.row = row

    def one(self):
        return self.row


class FakeExecuteResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return FakeMappings(self.row)


class FakeSession:
    def __init__(
        self,
        *,
        canonical_run=None,
        metrics_row=None,
    ):
        self.canonical_run = canonical_run
        self.metrics_row = metrics_row
        self.executed_statements = []

    def execute(self, statement):
        self.executed_statements.append(statement)

        if len(self.executed_statements) == 1:
            return FakeExecuteResult(
                self.canonical_run
            )

        return FakeExecuteResult(
            self.metrics_row
        )


def _canonical_run():
    return {
        "sync_run_id": 41,
        "period_key": "IVENTAS-2026-08-11",
        "date_from": date(2026, 8, 11),
        "date_to": date(2026, 8, 11),
        "status": "COMPLETED",
        "is_canonical": True,
    }


def _metrics_row():
    return {
        "iventas_contacts": 5887,
        "iventas_contacts_with_first_message": 508,
        "meta_observed_leads": 288,
    }


def test_reads_three_separate_business_populations():
    session = FakeSession(
        canonical_run=_canonical_run(),
        metrics_row=_metrics_row(),
    )

    result = read_canonical_iventas_lead_metrics(
        period_key="IVENTAS-2026-08-11",
        session=session,
    )

    assert isinstance(
        result,
        MarketingIventasLeadMetrics,
    )

    assert result.sync_run_id == 41
    assert result.period_key == "IVENTAS-2026-08-11"

    assert result.iventas_contacts == 5887

    assert (
        result.iventas_contacts_with_first_message
        == 508
    )

    assert result.meta_observed_leads == 288


def test_meta_observed_lead_never_defaults_to_all_contacts():
    session = FakeSession(
        canonical_run=_canonical_run(),
        metrics_row={
            "iventas_contacts": 2442,
            "iventas_contacts_with_first_message": 52,
            "meta_observed_leads": 19,
        },
    )

    result = read_canonical_iventas_lead_metrics(
        period_key="IVENTAS-2026-08-11",
        session=session,
    )

    assert result.iventas_contacts == 2442
    assert result.meta_observed_leads == 19

    assert (
        result.meta_observed_leads
        < result.iventas_contacts
    )


def test_requires_canonical_snapshot():
    session = FakeSession(
        canonical_run=None,
        metrics_row=None,
    )

    with pytest.raises(
        MarketingIventasCanonicalRunRequiredError,
        match="canónico",
    ):
        read_canonical_iventas_lead_metrics(
            period_key="IVENTAS-2026-08-11",
            session=session,
        )

    assert len(
        session.executed_statements
    ) == 1


@pytest.mark.parametrize(
    "period_key",
    [
        "",
        "   ",
        None,
    ],
)
def test_period_key_is_required(period_key):
    with pytest.raises(
        ValueError,
        match="period_key",
    ):
        read_canonical_iventas_lead_metrics(
            period_key=period_key,
            session=FakeSession(),
        )


def test_metrics_cannot_violate_population_cardinality():
    session = FakeSession(
        canonical_run=_canonical_run(),
        metrics_row={
            "iventas_contacts": 100,
            "iventas_contacts_with_first_message": 80,
            "meta_observed_leads": 101,
        },
    )

    with pytest.raises(
        ValueError,
        match="meta_observed_leads",
    ):
        read_canonical_iventas_lead_metrics(
            period_key="IVENTAS-2026-08-11",
            session=session,
        )


def test_meta_observed_leads_cannot_exceed_first_message_contacts():
    session = FakeSession(
        canonical_run=_canonical_run(),
        metrics_row={
            "iventas_contacts": 100,
            "iventas_contacts_with_first_message": 20,
            "meta_observed_leads": 21,
        },
    )

    with pytest.raises(
        ValueError,
        match="meta_observed_leads",
    ):
        read_canonical_iventas_lead_metrics(
            period_key="IVENTAS-2026-08-11",
            session=session,
        )


def test_meta_observed_lead_sql_contract():
    statement = _build_lead_metrics_statement(
        41
    )

    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={
                "literal_binds": True,
            },
        )
    ).lower()

    # Un contacto con N tags META sigue siendo 1 lead.
    assert "count(distinct" in sql
    assert "marketing_iventas_contacts.id" in sql

    # Debe existir evidencia de interacción.
    assert "first_message_at_utc is not null" in sql

    # Debe existir relación META_AD observada.
    assert "tag_kind" in sql
    assert "'meta_ad'" in sql

    # Todo debe quedar acotado al mismo snapshot/run.
    assert "sync_run_id = 41" in sql


class FakeBranchDateScalars:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeBranchDateResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return FakeBranchDateScalars(
            self.rows
        )


class FakeBranchDateSession(FakeSession):
    def __init__(
        self,
        *,
        canonical_run=None,
        branch_rows=None,
    ):
        super().__init__(
            canonical_run=canonical_run,
            metrics_row=None,
        )
        self.branch_rows = branch_rows or []

    def execute(self, statement):
        self.executed_statements.append(statement)

        if len(self.executed_statements) == 1:
            return FakeExecuteResult(
                self.canonical_run
            )

        return FakeBranchDateResult(
            self.branch_rows
        )


def test_lists_metrics_by_business_date_and_branch():
    session = FakeBranchDateSession(
        canonical_run=_canonical_run(),
        branch_rows=[
            {
                "lead_date": date(2026, 8, 11),
                "sucursal_id": 2,
                "iventas_contacts": 2442,
                "iventas_contacts_with_first_message": 52,
                "meta_observed_leads": 19,
            },
            {
                "lead_date": date(2026, 8, 11),
                "sucursal_id": 15,
                "iventas_contacts": 917,
                "iventas_contacts_with_first_message": 40,
                "meta_observed_leads": 10,
            },
        ],
    )

    result = (
        list_canonical_iventas_lead_metrics_by_branch_date(
            period_key="IVENTAS-2026-08-11",
            session=session,
        )
    )

    assert len(result) == 2

    villa_verde = result[0]

    assert isinstance(
        villa_verde,
        MarketingIventasLeadMetricsByBranchDate,
    )

    assert villa_verde.lead_date == date(
        2026,
        8,
        11,
    )
    assert villa_verde.sucursal_id == 2
    assert villa_verde.iventas_contacts == 2442
    assert (
        villa_verde
        .iventas_contacts_with_first_message
        == 52
    )
    assert villa_verde.meta_observed_leads == 19


def test_branch_date_metrics_preserve_population_order():
    session = FakeBranchDateSession(
        canonical_run=_canonical_run(),
        branch_rows=[
            {
                "lead_date": date(2026, 8, 11),
                "sucursal_id": 2,
                "iventas_contacts": 100,
                "iventas_contacts_with_first_message": 20,
                "meta_observed_leads": 7,
            },
        ],
    )

    result = (
        list_canonical_iventas_lead_metrics_by_branch_date(
            period_key="IVENTAS-2026-08-11",
            session=session,
        )
    )

    row = result[0]

    assert (
        row.meta_observed_leads
        <= row.iventas_contacts_with_first_message
        <= row.iventas_contacts
    )


def test_branch_date_metrics_require_canonical_run():
    session = FakeBranchDateSession(
        canonical_run=None,
    )

    with pytest.raises(
        MarketingIventasCanonicalRunRequiredError,
        match="canónico",
    ):
        list_canonical_iventas_lead_metrics_by_branch_date(
            period_key="IVENTAS-2026-08-11",
            session=session,
        )

    assert len(
        session.executed_statements
    ) == 1


def test_branch_date_sql_preserves_lead_business_contract():
    statement = (
        _build_lead_metrics_by_branch_date_statement(
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

    # Fecha de negocio del lead observado.
    assert "created_date_local" in sql

    # La métrica debe poder cortarse por sucursal.
    assert "sucursal_id" in sql
    assert "group by" in sql

    # Debe existir interacción real.
    assert "first_message_at_utc is not null" in sql

    # Debe existir una relación META_AD observada.
    assert "meta_ad" in sql
    assert "tag_kind" in sql

    # La relación con tags debe resolverse como existencia,
    # no mediante un JOIN que multiplique contactos.
    assert "exists" in sql

    # Debe quedar aislado al snapshot solicitado.
    assert "sync_run_id = 41" in sql
