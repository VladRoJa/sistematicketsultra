"""M1-F2: Track coverage is version-linked, exact-date and catalog-bound."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.automation_control.track_coverage_service import (
    assess_version_rows, read_track_current_catalog_coverage,
)
from app.services.automation_control.freshness_service import read_freshness

D12=date(2026,10,12)
D13=date(2026,10,13)


def _row(version, branch, day=D13, mode="official_closed_day"):
    return (version, branch, day, mode)


def test_exact_official_rows_for_current_roster():
    result=assess_version_rows(
        expected_branches={"VILLAS_DEL_REY","TEC_MXL"}, version_id=88,
        track_date=D13, mart_rows=[_row(88,"TEC_MXL"), _row(88,"VILLAS_DEL_REY")],
    )
    assert result["matches_current_catalog"] is True
    assert result["expected_branch_count"]==2
    assert result["actual_branch_count"]==2
    assert result["missing_branch_codes"]==[]
    assert result["historical_roster_verified"] is False


@pytest.mark.parametrize(("rows","missing","unexpected","duplicates","wrong_date","wrong_mode"),[
    ([_row(88,"TEC_MXL")],["VILLAS_DEL_REY"],[],[],0,0),
    ([_row(88,"TEC_MXL"),_row(88,"VILLAS_DEL_REY"),_row(88,"DEMO")],[],["DEMO"],[],0,0),
    ([_row(88,"TEC_MXL"),_row(88,"TEC_MXL"),_row(88,"VILLAS_DEL_REY")],[],[],["TEC_MXL"],0,0),
    ([_row(88,"TEC_MXL",D12),_row(88,"VILLAS_DEL_REY")],[],[],[],1,0),
    ([_row(88,"TEC_MXL",mode="manual_preview"),_row(88,"VILLAS_DEL_REY")],[],[],[],0,1),
])
def test_invalid_coverage_never_matches(rows,missing,unexpected,duplicates,wrong_date,wrong_mode):
    result=assess_version_rows(
        expected_branches={"VILLAS_DEL_REY","TEC_MXL"},version_id=88,
        track_date=D13,mart_rows=rows,
    )
    assert not result["matches_current_catalog"]
    assert result["missing_branch_codes"]==missing
    assert result["unexpected_branch_codes"]==unexpected
    assert result["duplicate_branch_codes"]==duplicates
    assert result["wrong_date_row_count"]==wrong_date
    assert result["wrong_generation_mode_row_count"]==wrong_mode


def test_empty_roster_is_not_complete():
    result=assess_version_rows(
        expected_branches=set(),version_id=88,track_date=D13,mart_rows=[],
    )
    assert not result["matches_current_catalog"]


def test_reader_selects_current_canonical_not_current_base():
    query_versions=MagicMock()
    query_versions.filter.return_value=query_versions
    query_versions.all.return_value=[
        (10,D13,"base_nocturna_canonica"),
        (11,D13,"cierre_canonico"),
        (12,D12,"base_nocturna_canonica"),
    ]
    query_mart=MagicMock()
    query_mart.filter.return_value=query_mart
    query_mart.all.return_value=[
        _row(11,"VILLAS_DEL_REY"),
        _row(11,"TEC_MXL"),
        _row(12,"TEC_MXL",D12),
    ]
    with patch("app.services.automation_control.track_coverage_service._load_active_analytical_branches",
               return_value=[SimpleNamespace(sucursal_canon="VILLAS_DEL_REY"),
                             SimpleNamespace(sucursal_canon="TEC_MXL")]), \
         patch("app.services.automation_control.track_coverage_service.db.session.query",
               side_effect=[query_versions,query_mart]):
        result=read_track_current_catalog_coverage(cutoff=D13)

    assert result["latest_selected_version_date"]=="2026-10-13"
    assert result["latest_catalog_matched_date"]=="2026-10-13"
    assert result["coverage"]["selected_version_id"]==11
    assert result["coverage"]["matches_current_catalog"] is True
    assert not result["coverage"]["historical_roster_verified"]
    assert result["ambiguous_current_version_dates"]==[]


def test_duplicate_current_canonical_version_makes_day_ambiguous():
    versions=MagicMock()
    versions.filter.return_value=versions
    versions.all.return_value=[
        (11,D13,"cierre_canonico"),(12,D13,"cierre_canonico"),
    ]
    with patch("app.services.automation_control.track_coverage_service._load_active_analytical_branches",
               return_value=[SimpleNamespace(sucursal_canon="TEC_MXL")]), \
         patch("app.services.automation_control.track_coverage_service.db.session.query",
               return_value=versions):
        result=read_track_current_catalog_coverage(cutoff=D13)
    assert result["ambiguous_current_version_dates"]==["2026-10-13"]
    assert result["latest_catalog_matched_date"] is None
    assert result["coverage"]["matches_current_catalog"] is False


def test_missing_mart_for_successful_version_is_not_a_match():
    versions=MagicMock()
    versions.filter.return_value=versions
    versions.all.return_value=[(11,D13,"base_nocturna_canonica")]
    mart=MagicMock()
    mart.filter.return_value=mart
    mart.all.return_value=[]
    with patch("app.services.automation_control.track_coverage_service._load_active_analytical_branches",
               return_value=[SimpleNamespace(sucursal_canon="TEC_MXL")]), \
         patch("app.services.automation_control.track_coverage_service.db.session.query",
               side_effect=[versions,mart]):
        result=read_track_current_catalog_coverage(cutoff=D13)
    assert not result["coverage"]["matches_current_catalog"]
    assert result["coverage"]["missing_branch_codes"]==["TEC_MXL"]


def test_m1f2_never_sets_full_complete_date_without_historical_roster():
    # The global view may show comparison with current roster but not assert
    # coverage at a past point in time.
    with patch("app.services.automation_control.freshness_service.db.session.query") as q, \
         patch("app.services.automation_control.freshness_service.read_track_current_catalog_coverage",
               return_value={
                   "latest_catalog_matched_date":"2026-10-13",
                   "ambiguous_current_version_dates":[],
                   "coverage":{
                       "matches_current_catalog":True,
                       "historical_roster_verified":False,
                   },
               }):
        empty=MagicMock()
        empty.filter.return_value=empty
        empty.all.return_value=[]
        q.return_value=empty
        result=read_freshness(
            "track.daily",scope_global_certified=True,
            track_date="2026-10-13",
            now=__import__("datetime").datetime(2026,10,14,18,
                                                tzinfo=__import__("datetime").timezone.utc),
        )
    assert result["status"]=="UNKNOWN"
    assert result["latest_complete_business_date"] is None
    assert result["expected_business_date"] is None
    assert result["latest_catalog_matched_business_date"]=="2026-10-13"
    assert result["reason_code"]=="TRACK_HISTORICAL_ROSTER_UNVERIFIED"
