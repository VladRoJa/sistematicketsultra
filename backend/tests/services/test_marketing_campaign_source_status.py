from datetime import date, datetime, timezone
from types import SimpleNamespace as NS

from app.models import MarketingIventasSyncRunORM
from app.models.warehouse import SociosActivosSnapshotORM, SociosVencidosSnapshotORM
from app.services.marketing_campaign_source_status_service import read_campaign_source_status


NOW = datetime(2026, 9, 9, 5, 0, tzinfo=timezone.utc)  # Sep 8, 22:00 in Tijuana


class Query:
    def __init__(self, result):
        self.result = result

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def first(self):
        return self.result


class Session:
    def __init__(self, rows):
        self.rows = rows

    def query(self, model):
        return Query(self.rows.get(model))


def test_campaign_source_status_uses_real_cutoff_fields_and_tijuana_date():
    session = Session({
        SociosActivosSnapshotORM: NS(cutoff_date=date(2026, 9, 8)),
        SociosVencidosSnapshotORM: NS(date_to=date(2026, 9, 7)),
        MarketingIventasSyncRunORM: NS(date_to=date(2026, 9, 5)),
    })

    result = read_campaign_source_status(session=session, now=NOW)

    assert result == {
        "business_date": "2026-09-08",
        "sources": {
            "activos": {"cutoff_date": "2026-09-08", "age_days": 0, "status": "CURRENT"},
            "vencidos": {"cutoff_date": "2026-09-07", "age_days": 1, "status": "RECENT"},
            "iventas": {"cutoff_date": "2026-09-05", "age_days": 3, "status": "STALE"},
        },
    }


def test_campaign_source_status_marks_missing_sources_unavailable():
    session = Session({
        SociosActivosSnapshotORM: None,
        SociosVencidosSnapshotORM: None,
        MarketingIventasSyncRunORM: None,
    })

    result = read_campaign_source_status(session=session, now=NOW)

    assert result["sources"] == {
        "activos": {"cutoff_date": None, "age_days": None, "status": "UNAVAILABLE"},
        "vencidos": {"cutoff_date": None, "age_days": None, "status": "UNAVAILABLE"},
        "iventas": {"cutoff_date": None, "age_days": None, "status": "UNAVAILABLE"},
    }
