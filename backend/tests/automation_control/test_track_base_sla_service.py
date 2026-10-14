"""M1-F3: business-ratified Track nightly base SLA, without false-green."""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.services.automation_control.freshness_service import read_freshness
from app.services.automation_control.track_base_sla_service import (
    base_sla_window, read_track_base_sla,
)

TZ = ZoneInfo("America/Tijuana")
D = date(2026, 10, 13)


@pytest.mark.parametrize(("local_time","expected"), [
    ("2026-10-14T01:59:59-07:00", "NOT_DUE"),
    ("2026-10-14T02:00:00-07:00", "LAGGING"),
    ("2026-10-14T02:59:59-07:00", "LAGGING"),
    ("2026-10-14T03:00:00-07:00", "LATE"),
    ("2026-10-14T23:59:59-07:00", "LATE"),
])
def test_exact_2am_3am_boundaries(local_time, expected):
    result=base_sla_window(
        business_date=D, now=datetime.fromisoformat(local_time),
    )
    assert result["phase_if_unavailable"] == expected
    assert result["due_at"] == "2026-10-14T02:00:00-07:00"
    assert result["late_at"] == "2026-10-14T03:00:00-07:00"
    assert result["expected_business_date"] == "2026-10-13"
    assert result["applies_every_day"] is True


@pytest.mark.parametrize(("day","due"),[
    (date(2026,10,16),"2026-10-17T02:00:00-07:00"), # Saturday
    (date(2026,10,17),"2026-10-18T02:00:00-07:00"), # Sunday
    (date(2026,10,18),"2026-10-19T02:00:00-07:00"), # Monday
    (date(2026,12,31),"2027-01-01T02:00:00-08:00"), # Year rollover
])
def test_weekends_year_rollover_and_tijuana_zone(day,due):
    x=base_sla_window(business_date=day,now=datetime(2026,10,14,18,tzinfo=timezone.utc))
    assert x["due_at"]==due


def test_spring_forward_missing_two_am_has_no_phantom_grace_hour():
    day=date(2026,3,7)
    before=base_sla_window(business_date=day,
                           now=datetime(2026,3,8,9,59,59,tzinfo=timezone.utc))
    at=base_sla_window(business_date=day,
                       now=datetime(2026,3,8,10,0,0,tzinfo=timezone.utc))
    assert before["phase_if_unavailable"] == "NOT_DUE"
    assert at["phase_if_unavailable"] == "LATE"
    assert at["due_at"] == "2026-03-08T03:00:00-07:00"
    assert at["late_at"] == at["due_at"]


def test_fall_back_uses_correct_standard_time_offset():
    x=base_sla_window(business_date=date(2026,10,31),
                      now=datetime(2026,11,1,9,59,tzinfo=timezone.utc))
    assert x["due_at"]=="2026-11-01T02:00:00-08:00"
    assert x["phase_if_unavailable"] == "NOT_DUE"
    y=base_sla_window(business_date=date(2026,10,31),
                      now=datetime(2026,11,1,10,0,tzinfo=timezone.utc))
    assert y["phase_if_unavailable"]=="LAGGING"


def test_naive_time_is_rejected():
    with pytest.raises(ValueError):
        base_sla_window(business_date=D,now=datetime(2026,10,14,3))


def _version_query(rows):
    q=MagicMock()
    q.filter.return_value=q
    q.all.return_value=rows
    return q


@pytest.mark.parametrize(("version_rows","time","status","reason"), [
    ([], "2026-10-14T01:59:59-07:00", "NOT_DUE", "NO_CURRENT_BASE"),
    ([], "2026-10-14T02:00:00-07:00", "LAGGING", "NO_CURRENT_BASE"),
    ([], "2026-10-14T03:00:00-07:00", "LATE", "NO_CURRENT_BASE"),
    ([(8, "failed")], "2026-10-14T02:59:59-07:00", "LAGGING", "BASE_CURRENT_NOT_SUCCESS"),
    ([(8, "running")], "2026-10-14T03:00:00-07:00", "LATE", "BASE_CURRENT_NOT_SUCCESS"),
    ([(8, "success"), (9, "success")], "2026-10-14T04:00:00-07:00",
     "UNKNOWN", "AMBIGUOUS_CURRENT_BASE"),
])
def test_no_current_success_yields_ratified_phase(version_rows,time,status,reason):
    with patch("app.services.automation_control.track_base_sla_service.db.session.query",
               return_value=_version_query(version_rows)):
        data=read_track_base_sla(business_date=D,now=datetime.fromisoformat(time))
    assert data["status"]==status
    assert data["reason_code"]==reason
    assert data["historical_roster_verified"] is False
    assert data["canonical_close_sla"]=="SEPARATE_CONDITIONAL_NOT_RATIFIED"
    assert data["base_current_catalog_coverage"] is None


@pytest.mark.parametrize(("mart_rows","matches"),[
    ([(44,"TEC_MXL",D,"official_closed_day"),
      (44,"VILLAS_DEL_REY",D,"official_closed_day")], True),
    ([(44,"TEC_MXL",D,"official_closed_day")], False),
])
def test_success_base_never_green_without_historical_roster(mart_rows,matches):
    version_query=_version_query([(44,"success")])
    mart_query=_version_query(mart_rows)
    branches=[SimpleNamespace(sucursal_canon="TEC_MXL"),
              SimpleNamespace(sucursal_canon="VILLAS_DEL_REY")]
    with patch("app.services.automation_control.track_base_sla_service.db.session.query",
               side_effect=[version_query,mart_query]), \
         patch("app.services.automation_control.track_base_sla_service._load_active_analytical_branches",
               return_value=branches):
        result=read_track_base_sla(
            business_date=D,now=datetime.fromisoformat("2026-10-14T05:00:00-07:00"),
        )
    assert result["base_current_catalog_coverage"]["matches_current_catalog"]==matches
    assert result["status"]=="UNKNOWN"
    assert result["reason_code"]=="BASE_SUCCESS_ROSTER_HISTORY_UNVERIFIED"
    assert result["base_version_id"]==44
    assert result["historical_roster_verified"] is False


def test_successful_base_before_deadline_is_not_due_not_green():
    with patch("app.services.automation_control.track_base_sla_service.db.session.query",
               side_effect=[
                   _version_query([(44, "success")]),
                   _version_query([(44,"TEC_MXL",D,"official_closed_day")]),
               ]), \
         patch("app.services.automation_control.track_base_sla_service._load_active_analytical_branches",
               return_value=[SimpleNamespace(sucursal_canon="TEC_MXL")]):
        value=read_track_base_sla(
            business_date=D,now=datetime.fromisoformat("2026-10-14T01:30:00-07:00"),
        )
    assert value["status"] == "NOT_DUE"
    assert value["historical_roster_verified"] is False


def test_default_track_business_date_is_yesterday_not_today():
    # Does not consult global source tables for a restricted role.
    with patch("app.services.automation_control.freshness_service._track_evidence") as reader:
        with patch("app.services.automation_control.freshness_service.read_track_base_sla"):
            read_freshness("track.daily",scope_global_certified=True,
                           now=datetime(2026,10,14,18,tzinfo=timezone.utc))
            assert reader.call_args.kwargs["cutoff"] == D
            read_freshness("track.daily",scope_global_certified=True,
                           track_date="2026-10-14",
                           now=datetime(2026,10,14,18,tzinfo=timezone.utc))
            assert reader.call_args.kwargs["cutoff"] == date(2026,10,14)


def test_scoped_view_never_computes_private_sla_or_global_versions():
    with patch("app.services.automation_control.freshness_service._track_evidence") as evidence, \
         patch("app.services.automation_control.track_base_sla_service.db.session.query") as query:
        result=read_freshness("track.daily",scope_global_certified=False,
            now=datetime(2026,10,14,18,tzinfo=timezone.utc))
    evidence.assert_not_called()
    query.assert_not_called()
    assert result["status"]=="UNKNOWN"
    assert result["expected_business_date"] is None
    assert result["due_at"] is None


def test_no_success_base_can_be_late_with_only_a_canonical_close_present():
    # A canonical close (or preview) never replaces evidence of current base.
    versions=_version_query([])
    with patch("app.services.automation_control.track_base_sla_service.db.session.query",
               return_value=versions):
        result=read_track_base_sla(
            business_date=D,
            now=datetime.fromisoformat("2026-10-14T03:01:00-07:00"),
        )
    assert result["status"]=="LATE"
    assert result["base_version_id"] is None
