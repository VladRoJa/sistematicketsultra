"""M1-F5: five-source operational deadline. No historic/catalog false green."""
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.services.automation_control.funnel_operational_sla_service import (
    SOURCE_KEYS, operational_sla_window, read_funnel_operational_sla,
)

TIJUANA = ZoneInfo("America/Tijuana")
BUSINESS_DATE = date(2026, 10, 13)
SVC = "app.services.automation_control.funnel_operational_sla_service"


def _query(rows):
    q = MagicMock()
    q.filter.return_value = q
    q.limit.return_value = q
    q.all.return_value = rows
    return q


def _read(clock, sets):
    with patch(SVC + ".db.session.query",
               side_effect=[_query(rows) for rows in sets]) as queries:
        result = read_funnel_operational_sla(
            business_date=BUSINESS_DATE, now=datetime.fromisoformat(clock),
        )
    assert queries.call_count == 5  # fixed cost; no branch N+1
    for call in queries.call_args_list:
        assert call.args  # queries must be for explicit ORM identifiers
    return result


@pytest.mark.parametrize(("instant", "status"), [
    ("2026-10-14T02:59:59-07:00", "NOT_DUE"),
    ("2026-10-14T03:00:00-07:00", "LAGGING"),
    ("2026-10-14T03:59:59-07:00", "LAGGING"),
    ("2026-10-14T04:00:00-07:00", "LATE"),
])
def test_exact_due_late_boundaries(instant, status):
    result = operational_sla_window(
        business_date=BUSINESS_DATE, now=datetime.fromisoformat(instant),
    )
    assert result["phase_if_unavailable"] == status
    assert result["due_at"] == "2026-10-14T03:00:00-07:00"
    assert result["late_at"] == "2026-10-14T04:00:00-07:00"
    assert result["policy_key"] == "FUNNEL_OPERATIONAL_D_PLUS_1_0300_0400_V1"


@pytest.mark.parametrize(("business_date", "due", "late"), [
    (date(2026, 3, 7), "2026-03-08T03:00:00-07:00", "2026-03-08T04:00:00-07:00"),
    (date(2026, 10, 31), "2026-11-01T03:00:00-08:00", "2026-11-01T04:00:00-08:00"),
    (date(2026, 12, 31), "2027-01-01T03:00:00-08:00", "2027-01-01T04:00:00-08:00"),
])
def test_dst_weekends_new_year_and_local_calendar(business_date, due, late):
    now = datetime.fromisoformat(late)
    result = operational_sla_window(business_date=business_date, now=now)
    assert result["due_at"] == due
    assert result["late_at"] == late
    assert result["applies_every_day"] is True
    assert result["phase_if_unavailable"] == "LATE"


def test_naive_clock_rejected():
    with pytest.raises(ValueError, match="timezone"):
        operational_sla_window(
            business_date=BUSINESS_DATE,
            now=datetime(2026, 10, 14, 4),
        )


@pytest.mark.parametrize(("at", "expected"), [
    ("2026-10-14T02:59:59-07:00", "NOT_DUE"),
    ("2026-10-14T03:00:00-07:00", "LAGGING"),
    ("2026-10-14T04:00:00-07:00", "LATE"),
])
def test_missing_one_of_five_sources_exposes_exact_gap(at, expected):
    rows = [[(11,)], [], [(33,)], [(44,)], [(55,)]]
    r = _read(at, rows)
    assert r["status"] == expected
    assert r["missing_sources"] == ["meta"]
    assert [x["key"] for x in r["sources"]] == list(SOURCE_KEYS)
    assert r["sources"][1]["present"] is False
    assert r["operational_not_final"] is True
    assert r["lineage_verified"] is False


def test_all_five_canonical_dates_are_available_but_cannot_prove_lineage():
    r = _read("2026-10-14T04:15:00-07:00", [[(i,)] for i in range(1, 6)])
    assert r["status"] == "UNKNOWN"
    assert r["reason_code"] == "FIVE_DATES_PRESENT_LINEAGE_UNVERIFIED"
    assert r["missing_sources"] == []
    assert not r["historical_roster_verified"]
    assert r["canonical_close_sla"] == "SEPARATE_CONDITIONAL_NOT_RATIFIED"


def test_two_canonical_candidates_are_ambiguous_not_false_green_or_red():
    r = _read(
        "2026-10-14T04:15:00-07:00",
        [[(11,), (12,)], [(22,)], [(33,)], [], [(55,)]],
    )
    assert r["status"] == "UNKNOWN"
    assert r["reason_code"] == "AMBIGUOUS_CANONICAL_SOURCE"
    assert r["sources"][0]["reason_code"] == "AMBIGUOUS_CANONICAL_DATE"


def test_pre_crm_history_does_not_query_database():
    with patch(SVC + ".db.session.query") as query:
        r = read_funnel_operational_sla(
            business_date=date(2026, 6, 30),
            now=datetime(2026, 7, 1, 20, tzinfo=timezone.utc),
        )
    query.assert_not_called()
    assert r["status"] == "UNKNOWN"
    assert r["reason_code"] == "HISTORICAL_CRM_UNAVAILABLE"


def test_source_predicates_include_canonical_and_exact_period():
    with patch(SVC + ".db.session.query", side_effect=[_query([]) for _ in range(5)]) as q:
        read_funnel_operational_sla(
            business_date=BUSINESS_DATE,
            now=datetime.fromisoformat("2026-10-14T03:30:00-07:00"),
        )
    assert q.call_count == 5
    # Semantic checks are in production source predicates, never in the
    # weaker legacy _iventas_cutoff_dates / _meta_cutoff_dates reader.
    import inspect
    from app.services.automation_control import funnel_operational_sla_service as service
    source = inspect.getsource(service._exact_current_sources)
    assert source.count("is_canonical.is_(True)") == 5
    assert "status == \"COMPLETED\"" in source
    assert "date_from == start" in source
    assert "date_to == business_date" in source
    assert ".limit(2).all()" in source
