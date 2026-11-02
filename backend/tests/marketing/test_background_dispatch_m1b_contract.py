"""Issue #1129 M1b: syntactic, policy and fail-closed contract smoke checks.

Does not contact iVentas, create jobs or require a database.
These are NOT a substitute for Flask/JWT and PostgreSQL 16 integration gates.
"""
import ast
from pathlib import Path
import re
import pytest

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "app/services/marketing_campaign_v2_background_job_service.py"
ROUTES = ROOT / "app/routes/marketing_campaign_v2_routes.py"
CONFIG = ROOT / "app/config.py"


def _service_ast():
    return ast.parse(SERVICE.read_text(encoding="utf-8"))


def test_service_compiles_and_never_imports_provider():
    tree = _service_ast()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            assert "iventas" not in ast.unparse(node).lower()
    source = SERVICE.read_text(encoding="utf-8")
    assert "IVentasBroadcastProvider" not in source
    assert "execute_governed_child(" not in source
    assert "create_campaign(" not in source


def test_service_keeps_safe_public_operations():
    tree = _service_ast()
    names = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    assert {"enqueue_background_job", "get_background_job",
            "list_background_jobs", "stop_background_job", "_snapshot"} <= names
    source = SERVICE.read_text(encoding="utf-8")
    assert "acquire_campaign_v2_contact_gate(session)" in source
    assert "_locked_review(" in source
    assert "_check_child_identities(" in source
    assert 'session.add(Event(job_id=job.id, event_no=1, event_kind="ENQUEUED"' in source
    assert 'session.commit()' in source
    assert '"REVIEW_REQUIRED"' in source


def test_flags_default_off_until_worker_is_integrated():
    config = CONFIG.read_text(encoding="utf-8")
    routes = ROUTES.read_text(encoding="utf-8")
    assert 'os.getenv("CAMPAIGN_V2_BACKGROUND_DISPATCH_WORKER_READY", "false")' in config
    assert 'os.getenv("CAMPAIGN_V2_BACKGROUND_DISPATCH_ENABLED", "false")' in config
    fn = routes[routes.index("def _background_dispatch_enabled():"):
                routes.index("@marketing_campaign_v2_bp.post(\"/campaigns-v2/<int:campaign_id>/dispatch/jobs\")")]
    assert all(flag in fn for flag in (
        "CAMPAIGN_V2_BACKGROUND_DISPATCH_ENABLED",
        "CAMPAIGN_V2_BACKGROUND_DISPATCH_WORKER_READY",
        "CAMPAIGN_V2_PROVIDER_SEND_ENABLED",
        "CAMPAIGN_V2_GOVERNED_DISPATCH_ENABLED",
    ))


def test_four_routes_are_jwt_protected_and_do_not_send():
    source = ROUTES.read_text(encoding="utf-8")
    for fn in (
        "campaign_v2_background_enqueue_endpoint",
        "campaign_v2_background_get_endpoint",
        "campaign_v2_background_mine_endpoint",
        "campaign_v2_background_stop_endpoint",
    ):
        assert re.search(r"@jwt_required\(\)\s+def " + fn + r"\(", source)
    segment = source[source.index("def _background_dispatch_enabled():"):
                     source.index('@marketing_campaign_v2_bp.post("/campaigns-v2/qa-manual/preview")')]
    assert "IVentasBroadcastProvider(" not in segment
    assert "execute_governed_child(" not in segment
    assert 'password = payload.pop("operator_password", None)' in segment
    assert "_valid_governed_dispatch_password(user, password)" in segment
    assert "_require_campaign_v2_send(access)" in segment
    assert 'return _error(str(exc), 423)' in segment


def test_queries_use_server_identity_not_caller_supplied_actor():
    source = ROUTES.read_text(encoding="utf-8")
    seg = source[source.index("def _background_dispatch_enabled():"):
                 source.index('@marketing_campaign_v2_bp.post("/campaigns-v2/qa-manual/preview")')]
    assert '"actor_user_id"' not in seg.split("_parse_payload({", 1)[1].split("})", 1)[0]
    assert "actor_user_id=int(user.id)" in seg
    assert "operator_user_id=int(user.id)" in seg
    service = SERVICE.read_text(encoding="utf-8")
    assert "Job.operator_user_id == actor_user_id" in service
    assert "Job.operator_user_id == operator_user_id" in service


def test_no_secret_storage_or_auto_resume():
    source = SERVICE.read_text(encoding="utf-8")
    assert 'may_auto_retry": False' in source
    assert 'may_auto_resume": False' in source
    assert 'delivery_confirmed": False' in source
    assert "operator_password" not in source
    assert "JWT_TOKEN" not in source


def test_repo_m1a_migration_and_model_are_already_registered():
    model = ROOT / "app/models/marketing_campaign_v2_background_job.py"
    migration = ROOT / "migrations/versions/n26c10202626_campaign_v2_background_jobs.py"
    assert model.is_file() and migration.is_file()
    assert 'down_revision = "v2e4b1102826"' in migration.read_text()
    assert "uq_mkt_v2_bg_jobs_campaign_active" in model.read_text()


def test_worker_ready_requires_explicit_environment_opt_in(monkeypatch):
    """Evaluate the real Config expression without importing app secrets or services."""
    import os

    tree = ast.parse(CONFIG.read_text(encoding="utf-8"))
    config_class = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Config"
    )
    assignment = next(
        node for node in config_class.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name)
                and target.id == "CAMPAIGN_V2_BACKGROUND_DISPATCH_WORKER_READY"
                for target in node.targets)
    )
    code = compile(ast.Expression(assignment.value), str(CONFIG), "eval")
    flag = "CAMPAIGN_V2_BACKGROUND_DISPATCH_WORKER_READY"

    monkeypatch.delenv(flag, raising=False)
    assert eval(code, {"os": os}) is False
    for value in ("false", "1", "yes", "", "TRUE-ish"):
        monkeypatch.setenv(flag, value)
        assert eval(code, {"os": os}) is False
    for value in ("true", "TRUE", " True "):
        monkeypatch.setenv(flag, value)
        assert eval(code, {"os": os}) is True
