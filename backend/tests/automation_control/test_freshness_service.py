"""M1-F1: genuine business source evidence without premature green or scope leak."""
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes.automation_control_routes import automation_control_bp
from app.services.automation_control.freshness_service import (
    read_freshness, FUNNEL_SOURCE_KEYS,
)

NOW = datetime(2026, 10, 14, 18, tzinfo=timezone.utc)
D11, D12, D13 = (date(2026, 10, d) for d in (11, 12, 13))


def _source_sets():
    return [
        {D12,D13},       # iVentas
        {D12},           # Meta is a day behind other sources
        {D11,D12,D13},   # Venta Total
        {D12,D13},       # Nuevos Socios
        {D12,D13},       # KPI
    ]


def _patch_sources():
    import app.services.automation_control.freshness_service as service
    names=[
        "_iventas_cutoff_dates", "_meta_cutoff_dates", "_venta_total_cutoff_dates",
        "_new_sales_cutoff_dates", "_kpi_cutoff_dates",
    ]
    patches = [patch.object(service,name,return_value=data)
               for name,data in zip(names,_source_sets())]
    patches.append(patch.object(service,"read_marketing_sync_sla",
                    return_value={
                        "status":"UNKNOWN",
                        "reason_code":"WORKER_SCHEDULE_UNVERIFIED",
                    }))
    return patches


def test_funnel_joint_cut_never_infers_green_when_one_source_lags():
    patches=_patch_sources()
    try:
        for p in patches: p.start()
        result=read_freshness(
            "marketing.sales_funnel",scope_global_certified=True,
            month="2026-10",now=NOW,
        )
        assert len(result["sources"])==5
        assert tuple(s["key"] for s in result["sources"])==FUNNEL_SOURCE_KEYS
        assert result["latest_complete_business_date"]=="2026-10-12"
        assert result["latest_observed_business_date"]=="2026-10-13"
        assert result["status"]=="UNKNOWN"
        assert result["expected_business_date"] is None
        missing=[s for s in result["sources"] if not s["complete"]]
        assert [s["key"] for s in missing]==["meta"]
    finally:
        for p in reversed(patches): p.stop()


def test_selected_historical_cut_cannot_use_later_records():
    patches=_patch_sources()
    try:
        for p in patches: p.start()
        result=read_freshness(
            "marketing.sales_funnel",scope_global_certified=True,
            month="2026-10",cutoff_date="2026-10-12",now=NOW,
        )
        assert result["latest_observed_business_date"]=="2026-10-12"
        assert all(s["complete"] for s in result["sources"])
        assert result["status"]=="UNKNOWN"  # No ratified SLA.
    finally:
        for p in reversed(patches): p.stop()


def test_scoped_access_never_queries_or_leaks_global_dates():
    patches=_patch_sources()
    try:
        mocks = [p.start() for p in patches]
        result=read_freshness(
            "marketing.sales_funnel",scope_global_certified=False,
            month="2026-10",now=NOW,
        )
        assert result["reason_code"]=="SCOPE_NOT_CERTIFIED"
        assert result["sources"]==[]
        assert result["latest_complete_business_date"] is None
        for mock in mocks:
            mock.assert_not_called()
    finally:
        for p in reversed(patches): p.stop()


def test_track_current_success_needs_mart_and_stays_unknown():
    query_versions=MagicMock()
    query_versions.filter.return_value=query_versions
    query_versions.all.return_value=[(31,D12),(32,D13)]
    query_mart=MagicMock()
    query_mart.filter.return_value=query_mart
    query_mart.distinct.return_value=query_mart
    query_mart.all.return_value=[(31,)]
    with patch("app.services.automation_control.freshness_service.db.session.query",
               side_effect=[query_versions,query_mart]), \
         patch("app.services.automation_control.freshness_service.read_track_current_catalog_coverage",
               return_value={
                   "latest_catalog_matched_date": None,
                   "ambiguous_current_version_dates": [],
                   "coverage": None,
               }), \
         patch("app.services.automation_control.freshness_service.read_track_base_sla",
               return_value={
                   "expected_business_date": "2026-10-13",
                   "due_at": "2026-10-14T02:00:00-07:00",
                   "late_at": "2026-10-14T03:00:00-07:00",
                   "status": "UNKNOWN",
                   "reason_code": "BASE_SUCCESS_ROSTER_HISTORY_UNVERIFIED",
               }):
        result=read_freshness(
            "track.daily",scope_global_certified=True,
            track_date="2026-10-13",now=NOW,
        )
    assert result["status"]=="UNKNOWN"
    assert result["reason_code"]=="BASE_SUCCESS_ROSTER_HISTORY_UNVERIFIED"
    assert result["latest_complete_business_date"] is None
    assert result["sources"][0]["latest_complete_business_date"]=="2026-10-13"
    assert result["sources"][1]["latest_complete_business_date"]=="2026-10-12"


def test_track_scoped_never_queries_global_rows():
    with patch("app.services.automation_control.freshness_service.db.session.query") as q:
        result=read_freshness("track.daily",scope_global_certified=False,now=NOW)
    q.assert_not_called()
    assert result["sources"]==[]
    assert result["status"]=="UNKNOWN"


@pytest.mark.parametrize("kwargs",[
    {"module_key":"marketing.sales_funnel","month":"2026-99"},
    {"module_key":"marketing.sales_funnel","month":"2026-11"},
    {"module_key":"marketing.sales_funnel","month":"2026-10",
     "cutoff_date":"2026-09-30"},
    {"module_key":"marketing.sales_funnel","month":"2026-10",
     "cutoff_date":"2026-10-31"},
    {"module_key":"track.daily","track_date":"2026-10-15"},
    {"module_key":"track.daily","track_date":"not-a-date"},
    {"module_key":"unknown"},
])
def test_reject_unregistered_or_future_cutoffs(kwargs):
    with pytest.raises(ValueError):
        read_freshness(scope_global_certified=False,now=NOW,**kwargs)


@pytest.fixture
def api():
    app=Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="synthetic-jwt")
    JWTManager(app)
    app.register_blueprint(automation_control_bp,url_prefix="/api/automation-control")
    with app.app_context():
        token=create_access_token(identity="47")
    return app.test_client(), {"Authorization":"Bearer "+token}


def test_domain_auth_and_scope_guards(api):
    client,headers=api
    url="/api/automation-control/freshness?module_key=marketing.sales_funnel"
    assert client.get(url).status_code==401
    with patch("app.routes.automation_control_routes.UserORM.get_by_id",
               return_value=SimpleNamespace(username="ADMICORP",rol="ADMINISTRADOR")), \
         patch("app.routes.automation_control_routes.resolve_marketing_access"), \
         patch("app.routes.automation_control_routes.read_freshness",
               return_value={"status":"UNKNOWN"}) as read:
        response=client.get(url,headers=headers)
        assert response.status_code==200
        assert read.call_args.kwargs["scope_global_certified"] is True
        client.get(url+"&scope_mode=FILTERED",headers=headers)
        assert read.call_args.kwargs["scope_global_certified"] is False
    with patch("app.routes.automation_control_routes.UserORM.get_by_id",
               return_value=SimpleNamespace(username="manager",rol="GERENTE")), \
         patch("app.routes.automation_control_routes.resolve_marketing_access"), \
         patch("app.routes.automation_control_routes.read_freshness",
               return_value={"status":"UNKNOWN"}) as read:
        assert client.get(url,headers=headers).status_code==200
        assert read.call_args.kwargs["scope_global_certified"] is False
    with patch("app.routes.automation_control_routes.UserORM.get_by_id",
               return_value=SimpleNamespace(username="X",rol="RECEPCIONISTA")):
        assert client.get(url,headers=headers).status_code==403
        assert client.get(
            "/api/automation-control/freshness?module_key=track.daily",headers=headers,
        ).status_code==403
    assert client.get(url+"&branch_ids=1",headers=headers).status_code==400
