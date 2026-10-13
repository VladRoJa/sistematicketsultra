"""Pruebas del catálogo M1-A: metadatos, consistencia y no-false-green."""
from dataclasses import FrozenInstanceError

import pytest

from app.services.automation_control import job_catalog as catalog


def test_catalog_is_consistent_and_unique():
    catalog.validate_catalog()
    jobs = catalog.get_job_catalog()
    datasets = catalog.get_dataset_catalog()
    assert len(jobs) == 18
    assert len(datasets) == 2
    assert len({job.key for job in jobs}) == len(jobs)


def test_catalog_has_distinct_worker_and_job_identity():
    jobs = catalog.get_job_catalog()
    assert {job.worker_key for job in jobs} == {
        "marketing-scheduler",
        "track-scheduler",
        "reports-scheduler",
        "routine-control-scheduler",
        "ticket-attachment-cleanup",
    }
    assert len([job for job in jobs if job.worker_key == "marketing-scheduler"]) == 3
    assert len([job for job in jobs if job.worker_key == "track-scheduler"]) == 7


def test_catalog_never_implies_live_status_or_manual_permission():
    for job in catalog.get_job_catalog():
        assert job.manual_run_supported is False
        assert job.priority_policy in {
            "SECONDARY_TRACK_WINDOW", "TRACK_PRIMARY",
            "NIGHTLY_TRACK_WINDOW", "DEFER_WHEN_TRACK_ACTIVE",
        }
        assert job.timezone == "America/Tijuana"
        assert job.schedule_kind
        assert job.schedule_reference

    assert next(
        job for job in catalog.get_job_catalog()
        if job.key == "marketing.campaign_v2_provider_stats"
    ).enabled_default is False


def test_funnel_requires_exact_five_sources_and_no_google_ads():
    funnel = next(
        dataset for dataset in catalog.get_dataset_catalog()
        if dataset.key == "marketing.sales_funnel"
    )
    assert {source.key for source in funnel.sources} == {
        "iventas",
        "meta",
        "venta_total",
        "ventas_nuevos_socios",
        "kpi_desempeno",
    }
    assert funnel.completion_contract == "INTERSECTION_OF_REQUIRED_SOURCE_DATES"
    assert funnel.cutoff_reader.endswith(".list_available_funnel_cutoffs")
    assert funnel.expected_cutoff_policy is None


def test_funnel_sources_preserve_existing_persistence_filters():
    funnel = next(
        dataset for dataset in catalog.get_dataset_catalog()
        if dataset.key == "marketing.sales_funnel"
    )
    sources = {source.key: source for source in funnel.sources}

    assert sources["iventas"].producing_job_key == "marketing.iventas_sync"
    assert sources["meta"].producing_job_key == "marketing.meta_sync"
    assert sources["iventas"].business_date_column == "date_to"
    assert sources["meta"].business_date_column == "date_to"
    assert "COMPLETED" in sources["iventas"].selection_contract
    assert "COMPLETED" in sources["meta"].selection_contract
    for name in ("venta_total", "ventas_nuevos_socios", "kpi_desempeno"):
        assert sources[name].producing_job_key is None
        assert "is_canonical" in sources[name].selection_contract


def test_track_cutoff_is_explicitly_unverified():
    track = next(
        dataset for dataset in catalog.get_dataset_catalog()
        if dataset.key == "track.daily"
    )
    assert {source.evidence_table for source in track.sources} == {
        "track_daily_versions",
        "track_daily_mart",
    }
    assert track.cutoff_reader is None
    assert track.expected_cutoff_policy is None
    assert track.completion_contract == "TRACK_VERSION_AND_MART_RECONCILIATION_PENDING"


def test_conditional_jobs_are_not_presented_as_fixed_daily_runs():
    by_key = {job.key: job for job in catalog.get_job_catalog()}
    assert by_key["track.base_nocturna_retry"].schedule_kind == "CONDITIONAL_DAILY_TIME"
    assert by_key["track.request_cierre_canonico"].schedule_kind == "CONDITIONAL"
    assert by_key["track.pending_manual_canonical_close"].schedule_kind == "PENDING_REQUEST"
    assert by_key["track.agregadoras_consolidado_export"].schedule_kind == "INTERVAL_CHECK"
    assert by_key["track.warehouse_retention"].dataset_keys == ()


def test_catalog_objects_are_immutable():
    job = catalog.get_job_catalog()[0]
    with pytest.raises(FrozenInstanceError):
        job.key = "forbidden"


def test_validation_rejects_duplicate_jobs(monkeypatch):
    jobs = catalog.get_job_catalog()
    monkeypatch.setattr(catalog, "_JOBS", jobs + (jobs[0],))
    with pytest.raises(ValueError, match="job_key duplicado"):
        catalog.validate_catalog()


def test_validation_rejects_unknown_dataset(monkeypatch):
    jobs = catalog.get_job_catalog()
    invalid = catalog.JobSpec(
        key="test.unknown_dataset",
        worker_key="test",
        domain="test",
        label="Invalid",
        schedule_kind="CONDITIONAL",
        schedule_reference="N/A",
        schedule_env_keys=(),
        evidence_tables=(),
        priority_policy="TRACK_PRIMARY",
        dataset_keys=("missing.dataset",),
    )
    monkeypatch.setattr(catalog, "_JOBS", jobs + (invalid,))
    with pytest.raises(ValueError, match="dataset desconocido"):
        catalog.validate_catalog()
