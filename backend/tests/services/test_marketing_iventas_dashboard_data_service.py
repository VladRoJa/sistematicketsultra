from datetime import date
from types import SimpleNamespace

from sqlalchemy.exc import NoResultFound

from app.services.marketing_iventas_dashboard_data_service import (
    read_iventas_dashboard_month_data,
)


class FakeMappings:
    def one(self):
        raise NoResultFound()


class FakeExecuteResult:
    def mappings(self):
        return FakeMappings()


class FakeSession:
    def __init__(self):
        self.executed_statements = []

    def execute(self, statement):
        self.executed_statements.append(statement)
        return FakeExecuteResult()


def test_reports_month_as_unavailable_when_no_canonical_snapshot_exists():
    session = FakeSession()

    result = read_iventas_dashboard_month_data(
        month_date=date(2026, 8, 1),
        today=date(2026, 8, 13),
        session=session,
    )

    assert result.available is False
    assert result.period_key == "IVENTAS-2026-08"
    assert result.sync_run_id is None
    assert result.metrics is None

    assert len(session.executed_statements) == 1


class FakeAvailableMappings:
    def __init__(self, value):
        self.value = value

    def one(self):
        return self.value

    def all(self):
        return self.value


class FakeAvailableExecuteResult:
    def __init__(self, value):
        self.value = value

    def mappings(self):
        return FakeAvailableMappings(self.value)


class FakeAvailableSession:
    def __init__(self):
        self.executed_statements = []
        self.responses = [
            {
                "sync_run_id": 41,
                "period_key": "IVENTAS-2026-08",
                "date_from": date(2026, 8, 1),
                "date_to": date(2026, 8, 13),
                "status": "COMPLETED",
                "is_canonical": True,
            },
            {
                "iventas_contacts": 5887,
                "iventas_contacts_with_first_message": 508,
                "meta_observed_leads": 288,
            },
            [
                {
                    "month_start": date(2026, 8, 1),
                    "sucursal_id": 2,
                    "iventas_contacts": 2442,
                    "iventas_contacts_with_first_message": 52,
                    "meta_observed_leads": 19,
                },
                {
                    "month_start": date(2026, 8, 1),
                    "sucursal_id": 23,
                    "iventas_contacts": 43,
                    "iventas_contacts_with_first_message": 43,
                    "meta_observed_leads": 39,
                },
            ],
        ]

    def execute(self, statement):
        self.executed_statements.append(statement)
        value = self.responses.pop(0)
        return FakeAvailableExecuteResult(value)

    def get(self, model, object_id):
        assert object_id == 41

        return SimpleNamespace(
            id=41,
            period_key="IVENTAS-2026-08",
            date_from=date(2026, 8, 1),
            date_to=date(2026, 8, 13),
            status="COMPLETED",
            is_canonical=True,
        )


def test_returns_canonical_month_metrics_when_snapshot_exists():
    session = FakeAvailableSession()

    result = read_iventas_dashboard_month_data(
        month_date=date(2026, 8, 1),
        today=date(2026, 8, 13),
        session=session,
    )

    assert result.available is True
    assert result.period_key == "IVENTAS-2026-08"
    assert result.sync_run_id == 41

    assert result.metrics is not None
    assert result.metrics.iventas_contacts == 5887
    assert (
        result.metrics.iventas_contacts_with_first_message
        == 508
    )
    assert result.metrics.meta_observed_leads == 288

    assert result.branch_metrics is not None
    assert len(result.branch_metrics) == 2

    villa_verde = result.branch_metrics[0]
    assert villa_verde.sync_run_id == 41
    assert villa_verde.sucursal_id == 2
    assert villa_verde.iventas_contacts == 2442
    assert villa_verde.iventas_contacts_with_first_message == 52
    assert villa_verde.meta_observed_leads == 19

    assert len(session.executed_statements) == 3


class FakeChangingCanonicalSession:
    def __init__(self):
        self.executed_statements = []
        self.responses = [
            {
                "sync_run_id": 41,
                "period_key": "IVENTAS-2026-08",
                "date_from": date(2026, 8, 1),
                "date_to": date(2026, 8, 13),
                "status": "COMPLETED",
                "is_canonical": True,
            },
            {
                "iventas_contacts": 5887,
                "iventas_contacts_with_first_message": 508,
                "meta_observed_leads": 288,
            },
            [
                {
                    "month_start": date(2026, 8, 1),
                    "sucursal_id": 2,
                    "iventas_contacts": 2500,
                    "iventas_contacts_with_first_message": 60,
                    "meta_observed_leads": 22,
                },
            ],
        ]

    def execute(self, statement):
        self.executed_statements.append(statement)
        value = self.responses.pop(0)
        return FakeAvailableExecuteResult(value)

    def get(self, model, object_id):
        assert object_id == 41

        return SimpleNamespace(
            id=41,
            period_key="IVENTAS-2026-08",
            date_from=date(2026, 8, 1),
            date_to=date(2026, 8, 13),
            status="COMPLETED",
            is_canonical=True,
        )


def test_never_mixes_metrics_from_different_canonical_runs():
    result = read_iventas_dashboard_month_data(
        month_date=date(2026, 8, 1),
        today=date(2026, 8, 13),
        session=FakeChangingCanonicalSession(),
    )

    assert result.branch_metrics is not None
    assert all(
        row.sync_run_id == result.sync_run_id
        for row in result.branch_metrics
    )

def test_reports_actual_canonical_snapshot_range_not_theoretical_today():
    session = FakeAvailableSession()

    result = read_iventas_dashboard_month_data(
        month_date=date(2026, 8, 1),
        today=date(2026, 8, 14),
        session=session,
    )

    assert result.available is True
    assert result.period_key == "IVENTAS-2026-08"

    # El periodo teórico llega al 14,
    # pero el snapshot canónico disponible llega al 13.
    assert result.date_from == date(2026, 8, 1)
    assert result.date_to == date(2026, 8, 13)

    assert result.sync_run_id == 41
