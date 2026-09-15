from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
JOB = ROOT / "app" / "warehouse" / "jobs" / "reactivation_outcomes_daily_job.py"
SCHEDULER = ROOT / "app" / "warehouse" / "scheduler" / "reports_scheduler_worker.py"
ROUTES = ROOT / "app" / "routes" / "marketing_reactivation_outcome_routes.py"


def test_daily_job_only_requests_campaigns_with_open_outcomes_and_registered_sends():
    source = JOB.read_text(encoding="utf-8")

    assert "MarketingReactivationCampaignBranchSendORM" in source
    assert 'MarketingReactivationCampaignORM.status.in_(("EXPORTED", "SENT"))' in source
    assert "MarketingReactivationCampaignRecipientOutcomeORM.id.is_(None)" in source
    assert "OUTCOME_PENDING" in source
    assert "OUTCOME_REVIEW" in source
    assert "campaign_ids=campaign_ids" in source


def test_scheduler_runs_outcomes_after_sources_at_0915_and_retries_when_source_missing():
    source = SCHEDULER.read_text(encoding="utf-8")

    assert 'job_key = "reactivation_outcomes_daily"' in source
    assert 'default_hour=9' in source
    assert 'default_minute=15' in source
    assert 'reason="reactivation_sources_not_ready"' in source
    assert source.index("_run_reactivation_sources_if_due(now)") < source.index(
        "_run_reactivation_outcomes_if_due(now)"
    )
    assert "db.session.remove()" in source


def test_outcome_api_exposes_summary_detail_and_scoped_manual_reconciliation():
    source = ROUTES.read_text(encoding="utf-8")

    assert '@marketing_reactivation_outcome_bp.get("/reactivation/outcomes/summary")' in source
    assert '"/reactivation/outcomes/campaigns/<int:campaign_id>"' in source
    assert '@marketing_reactivation_outcome_bp.post("/reactivation/outcomes/run")' in source
    assert "resolve_marketing_access" in source
    assert "not access.can_edit_inputs or not access.is_global" in source
    assert "La campaña no contiene destinatarios dentro del alcance del usuario." in source
    assert "_reopen_closed_outcomes_for_reconciliation" in source
    assert "OUTCOME_WINDOW_CLOSED" in source
    assert "OUTCOME_PENDING" in source
