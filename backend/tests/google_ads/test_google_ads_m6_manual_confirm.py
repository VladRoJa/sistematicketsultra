"""M6 manual confirmation HTTP, signed ticket, RAW duplicate and failure gates.

Synthetic XLSX and fake Warehouse writes only, no persistent writes.
"""
from __future__ import annotations

from contextlib import contextmanager
from io import BytesIO

import pytest
from flask import jsonify

from app.routes import google_ads_m6_continuity_routes as routes
from app.warehouse.services import google_ads_m6_manual_preview_service as preview_svc
from app.warehouse.services import google_ads_m6_manual_confirm_service as svc
from test_google_ads_m6_manual_preview import setup_client, daily_xlsx, post as preview_post

CONFIRM = "/api/integrations/google-ads/manual/confirm"


class FakeConn:
    def execute(self, *args, **kwargs):
        assert "pg_advisory_xact_lock" in str(args[0])


class FakeEngine:
    @contextmanager
    def begin(self):
        yield FakeConn()


@pytest.fixture
def setup_confirm(setup_client, monkeypatch):
    client, token, principal = setup_client
    monkeypatch.setattr(svc, "db", type("FakeDb", (), {"engine": FakeEngine()})())
    monkeypatch.setattr(
        routes, "require_warehouse_upload", lambda: None
    )
    state = {"files": {}, "writes": [], "fail_second": False}

    def existing(day):
        return [
            {"report_type_key": kind, "file_hash_sha256": row["file_hash_sha256"],
             "date_from": day, "date_to": day}
            for kind, row in state["files"].items()
        ]

    def store(**kw):
        state["writes"].append(kw)
        kind = kw["report_type_key"]
        if kind.endswith("ad_group_daily") and state["fail_second"]:
            raise RuntimeError("synthetic failure")
        from hashlib import sha256
        hash_value = sha256(kw["file_bytes"]).hexdigest()
        dup = kind in state["files"] and state["files"][kind]["file_hash_sha256"] == hash_value
        result = {
            "upload_id": len(state["files"]) + 100 if not dup
            else state["files"][kind]["upload_id"],
            "file_hash_sha256": hash_value,
            "report_type_key": kind,
            "date_from": kw["date_from"].isoformat(),
            "date_to": kw["date_to"].isoformat(),
            "upload_status": "reused_existing" if dup else "created",
        }
        state["files"][kind] = result
        return result

    monkeypatch.setattr(
        routes, "confirm_google_ads_m6_manual_pair",
        lambda **kwargs: svc.confirm_google_ads_m6_manual_pair(
            **kwargs, upload=store, existing_lookup=existing,
        ),
    )
    return client, token, principal, state


def ticket(client, token, files=None):
    r = preview_post(client, token, files=files)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["raw_confirm_ticket"]
    return r.get_json()["raw_confirm_ticket"]


def confirm(client, token, signed_ticket, files=None, extra=None):
    campaign, groups = files if files is not None else daily_xlsx()
    data = {
        "campaign": (BytesIO(campaign), "campaign.xlsx"),
        "ad_group": (BytesIO(groups), "groups.xlsx"),
        "confirmation_ticket": signed_ticket,
    }
    data.update(extra or {})
    return client.post(
        CONFIRM,
        headers={"Authorization": f"Bearer {token}"} if token else {},
        data=data,
        content_type="multipart/form-data",
    )


def test_signed_preview_can_stage_raw_only_and_replay_idempotently(setup_confirm):
    client, token, principal, state = setup_confirm
    signed = ticket(client, token)
    response = confirm(client, token, signed)
    assert response.status_code == 201, response.get_json()
    data = response.get_json()
    assert data["status"] == "RAW_PAIR_STAGED"
    assert len(data["uploads"]) == 2
    assert data["initial_m6_approval_verified"] is False
    assert data["eligible_for_structured_ingestion"] is False
    assert data["eligible_for_publication"] is False
    assert all(x["uploaded_by_user_id"] == 47 for x in state["writes"])
    assert all(x["audit_details"]["publication"] == "NOT_AUTHORIZED"
               for x in state["writes"])
    assert all("source_upload_id" not in x for x in state["writes"])
    repeat = confirm(client, token, signed)
    assert repeat.status_code == 200
    assert all(v["reused_existing"] for v in repeat.get_json()["uploads"].values())


def test_requires_preview_ticket_and_matching_bytes(setup_confirm):
    client, token, principal, state = setup_confirm
    signed = ticket(client, token)
    bad = confirm(client, token, "invalid.ticket")
    assert bad.status_code == 409
    assert bad.get_json()["code"] == "INVALID_OR_EXPIRED_CONFIRMATION"
    original, group = daily_xlsx()
    changed = confirm(client, token, signed, files=(original + b"x", group))
    assert changed.status_code == 409
    assert changed.get_json()["code"] == "CONFIRMATION_MISMATCH"
    assert state["writes"] == []


def test_without_jwt_or_current_admicorp_never_stages(setup_confirm):
    client, token, principal, state = setup_confirm
    signed = ticket(client, token)
    assert confirm(client, None, signed).status_code == 401
    principal.rol = "SISTEMAS"  # not used by DB fake; role below
    principal.role = "GERENTE"
    response = confirm(client, token, signed)
    assert response.status_code == 403
    assert state["writes"] == []


def test_rejects_non_warehouse_operator_even_if_admicorp(setup_confirm, monkeypatch):
    client, token, principal, state = setup_confirm
    signed = ticket(client, token)
    monkeypatch.setattr(
        routes, "require_warehouse_upload",
        lambda: (jsonify({"error": "Forbidden"}), 403),
    )
    assert confirm(client, token, signed).status_code == 403
    assert state["writes"] == []


def test_second_raw_failure_reports_partial_and_retry(setup_confirm):
    client, token, principal, state = setup_confirm
    signed = ticket(client, token)
    state["fail_second"] = True
    partial = confirm(client, token, signed)
    assert partial.status_code == 409
    assert partial.get_json()["status"] == "PARTIAL_RAW"
    assert len(partial.get_json()["uploads"]) == 1
    assert len(state["files"]) == 1
    state["fail_second"] = False
    retry = confirm(client, token, signed)
    assert retry.status_code == 201
    assert retry.get_json()["uploads"]["google_ads_campaign_daily"]["reused_existing"]


def test_conflicting_existing_period_rejected_before_storage(setup_confirm):
    client, token, principal, state = setup_confirm
    signed = ticket(client, token)
    state["files"]["google_ads_campaign_daily"] = {
        "upload_id": 1, "file_hash_sha256": "a" * 64,
    }
    response = confirm(client, token, signed)
    assert response.status_code == 409
    assert response.get_json()["code"] == "EXISTING_PERIOD_CONFLICT"
    assert state["writes"] == []


def test_extra_form_fields_or_missing_file_rejected(setup_confirm):
    client, token, principal, state = setup_confirm
    signed = ticket(client, token)
    assert confirm(client, token, signed, extra={"approved_by_user_id": "47"}).status_code == 400
    assert confirm(client, token, signed, extra={"approval_reference": "x"}).status_code == 400
    assert state["writes"] == []


def test_ticket_belongs_to_same_actor(setup_confirm, monkeypatch):
    client, token, principal, state = setup_confirm
    signed = ticket(client, token)
    # Direct guard verifies signed user binding independently of DB lookup.
    with client.application.app_context():
        with pytest.raises(svc.GoogleAdsM6ManualConfirmError, match="CONFIRMATION_MISMATCH"):
            svc._verify_ticket(signed, actor_id=55,
                               campaign_bytes=daily_xlsx()[0],
                               group_bytes=daily_xlsx()[1])
