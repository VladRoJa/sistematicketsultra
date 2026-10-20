"""Regresiones de fail-closed: el seed jamás debe aceptar una base productiva."""

import pytest

from scripts.seed_maintenance_closure_qa import _preflight


@pytest.fixture
def qa_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("SUITE_QA_SEED_ALLOWED", "YES_CREATE_LOCAL_SYNTHETIC_TICKETS")
    monkeypatch.setenv("SUITE_QA_TEST_PASSWORD", "only-for-synthetic-tests")
    monkeypatch.setenv(
        "SQLALCHEMY_DATABASE_URI",
        "postgresql+psycopg2://qa:qa@127.0.0.1:5432/suite_ultra_tickets_qa",
    )


def test_seed_preflight_admits_only_explicit_local_qa_database(qa_env):
    assert "/suite_ultra_tickets_qa" in _preflight()


@pytest.mark.parametrize(
    "uri",
    [
        "postgresql+psycopg2://qa:qa@127.0.0.1:5432/sistematicketsultra",
        "postgresql+psycopg2://qa:qa@db:5432/postgres",
        "postgresql+psycopg2://qa:qa@production.example.com:5432/suite_ultra_tickets_qa",
        "sqlite:///suite_ultra_tickets_qa",
    ],
)
def test_seed_rejects_non_qa_database_or_remote_host(qa_env, monkeypatch, uri):
    monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", uri)
    with pytest.raises(RuntimeError, match="Seed prohibido"):
        _preflight()


@pytest.mark.parametrize(
    "env_name,value",
    [
        ("APP_ENV", "prod"),
        ("SUITE_QA_SEED_ALLOWED", "NO"),
        ("SUITE_QA_TEST_PASSWORD", "too-short"),
    ],
)
def test_seed_rejects_missing_local_safety_conditions(qa_env, monkeypatch, env_name, value):
    monkeypatch.setenv(env_name, value)
    with pytest.raises(RuntimeError):
        _preflight()
