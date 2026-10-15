"""M6 candidate HTTP: explicit non-publishing ingest and READ ONLY diff, PG16."""

from pathlib import Path
import importlib.util
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations

from test_google_ads_m6_correction_candidate_stage_pg_e2e import (
    candidate_lab, REASON, _counts,
)
from test_google_ads_m6_manual_structured_postgres import lab
from test_google_ads_m6_manual_raw_postgres import real_warehouse

@pytest.fixture
def case_review_schema(candidate_lab):
    """Full Alembic schema for case GET, isolated from earlier staging fixtures."""
    client, actor, other, engine, camp, group = candidate_lab
    migrations = []
    for revision in (
        "ac42e8b9d510_google_ads_m6_correction_review.py",
        "c5e7a2d93f10_google_ads_m6_correction_promotions.py",
    ):
        path = Path(__file__).resolve().parents[2] / "migrations/versions" / revision
        spec = importlib.util.spec_from_file_location("candidate_detail_" + revision, path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        migrations.append(module)
    with engine.begin() as conn:
        for mod in migrations:
            mod.op = Operations(MigrationContext.configure(conn))
            mod.upgrade()
    try:
        yield candidate_lab
    finally:
        with engine.begin() as conn:
            for mod in reversed(migrations):
                mod.op = Operations(MigrationContext.configure(conn))
                mod.downgrade()


STAGE = "/api/integrations/google-ads/corrections/candidates/ingest"
GET = "/api/integrations/google-ads/corrections/candidates/"


def _post(client, token, camp, group, *, confirmation="INGESTAR_CORRECCION_M6_SIN_PUBLICAR"):
    return client.post(
        STAGE,
        json={
            "campaign_upload_id": camp, "ad_group_upload_id": group,
            "revision": 1, "expected_publication_id": None,
            "reason": REASON, "confirmation": confirmation,
        },
        headers={"Authorization": "Bearer " + token} if token else {},
    )


def test_candidate_route_safe_write_and_readonly_comparison(case_review_schema):
    client, actor, other, engine, camp, group = case_review_schema
    assert _counts(engine) == (0, 0, 0, 0, 0, 0, 0)
    resp = _post(client, actor, camp, group)
    assert resp.status_code == 201, resp.get_json()
    assert resp.json["status"] == "CANDIDATE_STAGED"
    assert not resp.json["eligible_for_publication"]
    cid = resp.json["case_id"]
    snapshot = _counts(engine)
    assert snapshot == (1, 27, 43, 0, 0, 0, 2)
    view = client.get(GET + str(cid), headers={"Authorization": "Bearer " + actor})
    assert view.status_code == 200, view.get_json()
    body = view.get_json()
    assert body["candidate_account_cost_mxn"] is not None
    assert body["previous_account_cost_mxn"] is None
    assert body["status"] == "REQUIRES_BASELINE_EVIDENCE_REVIEW"
    assert len(body["branch_costs_mxn"]) == 26
    assert body["approved"] is False
    assert body["eligible_for_publication"] is False
    assert _counts(engine) == snapshot
    again = _post(client, actor, camp, group)
    assert again.status_code == 200, again.get_json()
    assert again.json["status"] == "ALREADY_STAGED"
    assert _counts(engine) == snapshot


def test_candidate_route_jwt_permissions_confirmation_and_missing_case(candidate_lab):
    client, actor, other, engine, camp, group = candidate_lab
    assert _post(client, None, camp, group).status_code == 401
    assert _post(client, other, camp, group).status_code == 403
    assert _post(client, actor, camp, group, confirmation="WRONG").status_code == 400
    assert client.get(GET + "99999",
                      headers={"Authorization": "Bearer " + actor}).status_code == 404
    assert client.get(GET + "1").status_code == 401
    assert client.get(GET + "1",
                      headers={"Authorization": "Bearer " + other}).status_code == 403
    assert _counts(engine) == (0, 0, 0, 0, 0, 0, 0)
