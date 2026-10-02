from datetime import date, datetime, timezone
import inspect
from types import SimpleNamespace

import pytest

from app.models.marketing import MarketingCampaignV2ORM
from app.services import marketing_campaign_v2_audience_service as audience
from app.services import marketing_campaign_v2_creation_service as creation
from app.services import marketing_campaign_v2_funnel_source_service as funnel_source


NOW = datetime(2026, 10, 2, 18, 0, tzinfo=timezone.utc)
ACCESS = SimpleNamespace(is_global=False, branch_ids=(1,))


class _Query:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, *_args):
        return self

    def all(self):
        return list(self.rows)


class _Session:
    def __init__(self, active_phones):
        self.active_phones = list(active_phones)
        self.added = []
        self.query_count = 0
        self.flushes = 0
        self.commits = 0
        self.rollbacks = 0
    def query(self, *_args):
        self.query_count += 1
        return _Query(self.active_phones)

    def add(self, value):
        self.added.append(value)

    def flush(self):
        self.flushes += 1
        for value in self.added:
            if isinstance(value, MarketingCampaignV2ORM) and value.id is None:
                value.id = 220

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _lead(phone, contact_id, *, branch_id=1, bought=False):
    return {
        "phone_mx10": phone,
        "contact_id": contact_id,
        "name": None,
        "sucursal_id": branch_id,
        "channel": "WhatsApp",
        "source_date": "2026-09-15",
        "origin": "iVentas / Meta Ads",
        "bought": bought,
    }


def _portfolio(state):
    return {
        "funnel_month": "2026-09",
        "funnel_cutoff_date": "2026-09-30",
        "iventas_sync_run_id": state["iventas_sync_run_id"],
        "scope": {"type": "PRIMARY_BRANCH", "branch_ids": [1]},
        "rows": [
            _lead("6862000002", "B-active"),
            _lead("6862000003", "C-history"),
            _lead("6862000004", "D-eligible-1"),
            _lead("526862000004", "D-eligible-2"),
            _lead("6862000005", "E-outside", branch_id=2),
        ],
        "buyer_excluded": [
            _lead("6862000001", "A-buyer", bought=True),
        ],
    }


def _snapshot(state):
    return SimpleNamespace(
        id=state["active_snapshot_id"],
        cutoff_date=date(2026, 9, 30),
        snapshot_kind="daily",
        captured_at=datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc),
    )


def _history(**kwargs):
    rows = []
    for phone in kwargs["phones"]:
        viewed = phone == "6862000003"
        rows.append(
            {
                "normalized_phone": f"mx10:{phone}",
                "last_observed_at": "2026-09-30T18:00:00+00:00",
                "ever_observed": {
                    "delivery_buckets": ["VIEWED"] if viewed else [],
                    "outcomes": [],
                    "button_interacted": False,
                },
            }
        )
    return {"rows": rows}


def _install(monkeypatch, state):
    calls = {"portfolio": 0, "history": 0}

    def portfolio(**_kwargs):
        calls["portfolio"] += 1
        return _portfolio(state)

    def history(**kwargs):
        calls["history"] += 1
        return _history(**kwargs)
    monkeypatch.setattr(
        funnel_source,
        "build_marketing_funnel_portfolio_at_cutoff",
        portfolio,
    )
    monkeypatch.setattr(
        funnel_source,
        "marketing_branch_keys_by_sucursal_ids",
        lambda **_kwargs: {1: "BRANCH A", 2: "BRANCH B"},
    )
    monkeypatch.setattr(
        funnel_source.activos_resolver,
        "resolve_latest_canonical_socios_activos_snapshot",
        lambda **_kwargs: _snapshot(state),
    )
    monkeypatch.setattr(audience, "get_provider_history_for_phones", history)
    return calls


def _audience_kwargs(session):
    return {
        "source": "FUNNEL_PORTFOLIO",
        "audience_families": None,
        "allowed_sucursal_keys": ("BRANCH A",),
        "funnel_month": "2026-09",
        "funnel_cutoff_date": "2026-09-30",
        "marketing_access": ACCESS,
        "history_exclusion": {"delivery_buckets": ["VIEWED"]},
        "session": session,
    }


def test_phase2b_funnel_acceptance_preview_detail_and_freeze(monkeypatch):
    state = {"iventas_sync_run_id": 77, "active_snapshot_id": 900}
    calls = _install(monkeypatch, state)
    session = _Session([("526862000002",)])

    preview = creation.build_campaign_v2_freeze_preview(
        **_audience_kwargs(session)
    )

    assert preview["funnel_candidate_count"] == 5
    assert preview["funnel_buyer_excluded_count"] == 1
    assert preview["active_member_suppression_count"] == 1
    assert preview["scoped_count"] == 3
    assert preview["before_history_filter_count"] == 2
    assert preview["history_excluded_count"] == 1
    assert preview["after_history_filter_count"] == 1
    assert preview["duplicate_count"] == 1
    assert preview["unique_recipient_count"] == 1

    for bucket, phone in (
        ("FUNNEL_BUYER_EXCLUDED", "6862000001"),
        ("ACTIVE_MEMBER_SUPPRESSION", "6862000002"),
        ("HISTORY_EXCLUDED", "6862000003"),
        ("RECIPIENTS", "6862000004"),
    ):
        detail = audience.build_campaign_v2_audience_preview_detail(
            bucket=bucket,
            page=1,
            page_size=50,
            **_audience_kwargs(session),
        )
        assert detail["total"] == 1
        assert detail["rows"][0]["phone_mx10"] == phone

    frozen = creation.freeze_campaign_v2(
        name="Funnel 2B acceptance",
        purpose="NEW_SALE",
        expected_preview_fingerprint=preview["preview_fingerprint"],
        created_by_user_id=7,
        now=NOW,
        **_audience_kwargs(session),
    )

    assert frozen["recipient_count"] == 1
    campaign = session.added[0]
    assert len(campaign.recipients) == 1
    recipient = campaign.recipients[0]
    assert recipient.phone_mx10 == "6862000004"
    assert recipient.source == "FUNNEL_PORTFOLIO"
    assert recipient.member_id is None
    assert recipient.member_pin is None
    assert recipient.member_name is None
    assert recipient.tarifa_raw is None
    assert recipient.categoria_tarifa is None
    assert recipient.audience_family is None
    assert len(recipient.evidence_rows) == 2
    assert {
        evidence.phone_raw for evidence in recipient.evidence_rows
    } == {"6862000004", "526862000004"}

    frozen_metadata = campaign.audience_definition_json["source_metadata"]
    assert frozen_metadata["iventas_sync_run_id"] == 77
    assert frozen_metadata["active_members_snapshot_id"] == 900
    assert calls["portfolio"] >= 6
    assert calls["history"] >= 6
    assert session.commits == 1


def test_phase2b_funnel_drift_causes_preview_mismatch(monkeypatch):
    state = {"iventas_sync_run_id": 77, "active_snapshot_id": 900}
    _install(monkeypatch, state)
    session = _Session([("6862000002",)])

    preview = creation.build_campaign_v2_freeze_preview(
        **_audience_kwargs(session)
    )
    state["active_snapshot_id"] = 901

    with pytest.raises(creation.MarketingCampaignV2PreviewMismatchError):
        creation.freeze_campaign_v2(
            name="Funnel drift",
            purpose="NEW_SALE",
            expected_preview_fingerprint=preview["preview_fingerprint"],
            created_by_user_id=7,
            now=NOW,
            **_audience_kwargs(session),
        )

    assert session.added == []
    assert session.commits == 0


def test_phase2b_funnel_acceptance_has_no_forbidden_side_effects():
    adapter_source = inspect.getsource(funnel_source)
    creation_source = inspect.getsource(creation)

    forbidden_broadcast_path = "/v2/" + "broadcast"

    assert "provider" not in adapter_source.lower()
    assert forbidden_broadcast_path not in adapter_source
    assert forbidden_broadcast_path not in creation_source
    assert ".add(" not in adapter_source
    assert ".commit(" not in adapter_source
