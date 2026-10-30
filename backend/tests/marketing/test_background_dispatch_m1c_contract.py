"""Issue #1129 M1c: fail-closed worker/guard source contract.

No network, credentials or production database. Full PostgreSQL 16 and
Flask/JWT integration tests remain a mandatory independent gate.
"""
import ast
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "app/services/marketing_campaign_v2_background_worker_service.py"
RUNNER = ROOT / "app/services/marketing_campaign_v2_background_worker.py"
D2C = ROOT / "app/services/marketing_campaign_v2_governed_dispatch_service.py"
CONFIG = ROOT / "app/config.py"


def _src(path):
    source = path.read_text(encoding="utf-8")
    ast.parse(source)
    return source


def test_no_worker_side_effect_from_import():
    tree = ast.parse(_src(RUNNER))
    calls = [node for node in tree.body if isinstance(node, ast.Expr)
             and isinstance(node.value, ast.Call)]
    assert not calls
    assert 'if __name__ == "__main__":' in _src(RUNNER)


def test_gunicorn_never_starts_background_worker():
    source = _src(RUNNER)
    assert "app = create_app()" in source
    assert "run_loop(app=app" in source
    assert "def main()" in source
    assert "import signal" in source


def test_worker_requires_all_four_flags():
    source = _src(WORKER)
    assert all(flag in source for flag in (
        "CAMPAIGN_V2_BACKGROUND_DISPATCH_ENABLED",
        "CAMPAIGN_V2_BACKGROUND_DISPATCH_WORKER_READY",
        "CAMPAIGN_V2_GOVERNED_DISPATCH_ENABLED",
        "CAMPAIGN_V2_PROVIDER_SEND_ENABLED",
    ))
    assert 'os.getenv("CAMPAIGN_V2_BACKGROUND_DISPATCH_WORKER_READY", "false")' in _src(CONFIG)


def test_worker_claims_queued_once_and_expired_never_reclaimed():
    source = _src(WORKER)
    assert "with_for_update(skip_locked=True)" in source
    assert 'Job.status == "QUEUED"' in source
    assert "def expire_stale_running(" in source
    assert 'job.status = "REVIEW_REQUIRED"' in source
    assert "def _fail_closed(" in source
    assert 'session.commit()' in source


def test_d2c_remains_only_provider_call_and_claim_persists_before_it():
    source = _src(D2C)
    assert "background_claim: BackgroundDispatchClaim | None = None" in source
    guard_index = source.index("_guard_background_execution(", source.index("def execute_governed_child("))
    durable_index = source.index('row.status = "SUBMITTING"', guard_index)
    commit_index = source.index("active.commit()", durable_index)
    post_index = source.index("outcome = provider.create_campaign(dispatch)", commit_index)
    assert guard_index < durable_index < commit_index < post_index


def test_manual_dispatch_is_blocked_even_if_feature_disabled():
    source = _src(D2C)
    guard = source[source.index("def _guard_background_execution("):source.index("def _utc(now:")]
    assert "if claim is None:" in guard
    assert "if job is not None:" in guard
    assert "REVIEW_REQUIRED" in guard
    assert "background_claim" in source
    assert "worker_claim_generation" in guard
    assert "resolve_marketing_access(user)" in guard


def test_stop_before_claim_requires_recheck_no_provider_attempt():
    source = _src(WORKER)
    d2c = _src(D2C)
    assert "BackgroundDispatchStoppedBeforeClaim" in source
    assert "BackgroundDispatchStoppedBeforeClaim" in d2c
    assert 'child.status == "READY"' in source
    assert "child.submit_started_at is None" in source
    assert "child.provider_campaign_id is None" in source


def test_worker_does_not_store_credentials_or_retry():
    source = _src(WORKER)
    assert "operator_password" not in source
    assert "jwt_required" not in source
    assert "requests.post(" not in source
    assert "retry" not in source.lower().replace("auto-retry", "")
    assert "provider_factory()" in source


def test_worker_revalidates_actor_on_every_child():
    source = _src(WORKER)
    assert "resolve_marketing_access(user)" in source
    assert "_actor(session, int(job.operator_user_id))" in source
    assert "_actor(session, int(job.operator_user_id))" in source[source.index("def _prepare("):]
    assert "can_send_campaigns" in source


def test_graceful_shutdown_quarantines_without_sending_another_child():
    worker = _src(WORKER)
    runner = _src(RUNNER)
    assert 'should_terminate is not None and should_terminate()' in worker
    assert '"WORKER_SHUTDOWN"' in worker
    assert 'should_terminate=lambda: STOP' in runner

def test_compose_background_worker_is_opt_in_and_send_disabled():
    """Worker is not part of the default or scheduler Compose deployments."""
    compose = (ROOT.parent / "docker-compose.yml").read_text(encoding="utf-8")
    assert compose.count("\n  campaign-v2-dispatch-worker:\n") == 1
    service = compose.split("\n  campaign-v2-dispatch-worker:\n", 1)[1].split(
        "\n  frontend:\n", 1
    )[0]
    assert "profiles:\n      - campaign-dispatch" in service
    assert "command: python -m app.services.marketing_campaign_v2_background_worker" in service
    assert 'CAMPAIGN_V2_BACKGROUND_DISPATCH_ENABLED: "false"' in service
    assert 'CAMPAIGN_V2_PROVIDER_SEND_ENABLED: "false"' in service
    assert 'CAMPAIGN_V2_GOVERNED_DISPATCH_ENABLED: "false"' in service
    assert "stop_grace_period: 90s" in service
    assert "ports:" not in service
    # Even manually enabling a Compose profile must not bypass the app gate.
    assert 'os.getenv("CAMPAIGN_V2_BACKGROUND_DISPATCH_WORKER_READY", "false")' in _src(CONFIG)
