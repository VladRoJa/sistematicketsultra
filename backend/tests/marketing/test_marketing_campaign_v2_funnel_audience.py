from types import SimpleNamespace

import pytest

from app.services import marketing_campaign_v2_audience_service as audience
from app.services import marketing_campaign_v2_funnel_source_service as funnel_source


@pytest.fixture(autouse=True)
def _empty_blacklist(monkeypatch):
    monkeypatch.setattr(audience, "get_blacklisted_phones", lambda **_kwargs: set())


ACCESS = SimpleNamespace(is_global=False, branch_ids=(1,))


def _row(phone, contact_id, *, branch_id=1, key="BRANCH A"):
    return funnel_source.MarketingCampaignV2FunnelCandidate(
        phone_raw=phone,
        phone_mx10=phone,
        contact_id=contact_id,
        sucursal_id=branch_id,
        sucursal_key=key,
        channel="WhatsApp",
        source_date="2026-09-15",
        origin="iVentas / Meta Ads",
        source_reference=(
            f"{branch_id}:{contact_id}" if branch_id is not None else contact_id
        ),
    )


def _result():
    first = _row("6861000001", "a1")
    duplicate = _row("6861000001", "a2")
    history = _row("6861000002", "history")
    invalid = _row(None, "invalid")
    suppressed = _row("6861000003", "active")
    buyer = _row("6861000004", "buyer")
    return funnel_source.MarketingCampaignV2FunnelSourceResult(
        funnel_month="2026-09",
        funnel_cutoff_date="2026-09-30",
        universe_count=6,
        scoped_count=3,
        funnel_candidates=(
            first,
            duplicate,
            history,
            invalid,
            suppressed,
        ),
        buyer_excluded=(buyer,),
        invalid_phone=(invalid,),
        active_member_suppressed=(suppressed,),
        candidates=(first, duplicate, history),
        metadata={
            "funnel_month": "2026-09",
            "funnel_cutoff_date": "2026-09-30",
            "iventas_sync_run_id": 77,
            "active_members_snapshot_id": 900,
            "active_members_cutoff_date": "2026-09-30",
        },
    )


def _install(monkeypatch):
    monkeypatch.setattr(
        audience.funnel_source,
        "load_campaign_v2_funnel_source",
        lambda **_kwargs: _result(),
    )

    calls = []

    def history(**kwargs):
        calls.append(kwargs)
        return {
            "rows": [
                {
                    "normalized_phone": "mx10:6861000001",
                    "last_observed_at": "2026-09-29T18:00:00+00:00",
                    "ever_observed": {
                        "delivery_buckets": [],
                        "outcomes": [],
                        "button_interacted": False,
                    },
                },
                {
                    "normalized_phone": "mx10:6861000002",
                    "last_observed_at": "2026-09-30T18:00:00+00:00",
                    "ever_observed": {
                        "delivery_buckets": ["VIEWED"],
                        "outcomes": [],
                        "button_interacted": False,
                    },
                },
            ]
        }

    monkeypatch.setattr(audience, "get_provider_history_for_phones", history)
    monkeypatch.setattr(
        audience,
        "_read_v2_tariff_catalog",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("Funnel no debe clasificar tarifas.")
        ),
    )
    return calls


def _kwargs():
    return {
        "source": "FUNNEL_PORTFOLIO",
        "audience_families": None,
        "allowed_sucursal_keys": ("BRANCH A",),
        "funnel_month": "2026-09",
        "funnel_cutoff_date": "2026-09-30",
        "marketing_access": ACCESS,
        "history_exclusion": {"delivery_buckets": ["VIEWED"]},
        "session": object(),
    }


def test_funnel_preview_runs_common_history_then_dedupe(monkeypatch):
    history_calls = _install(monkeypatch)

    preview = audience.build_campaign_v2_audience_preview(**_kwargs())

    assert preview["source"] == "FUNNEL_PORTFOLIO"
    assert preview["funnel_candidate_count"] == 5
    assert preview["funnel_buyer_excluded_count"] == 1
    assert preview["active_member_suppression_count"] == 1
    assert preview["invalid_phone_count"] == 1
    assert preview["scoped_count"] == 3
    assert preview["before_history_filter_count"] == 2
    assert preview["history_excluded_count"] == 1
    assert preview["after_history_filter_count"] == 1
    assert preview["duplicate_count"] == 1
    assert preview["unique_recipient_count"] == 1
    assert preview["family_counts"] == {
        family: 0 for family in audience.ALL_AUDIENCE_FAMILIES
    }
    assert preview["source_metadata"]["iventas_sync_run_id"] == 77
    assert preview["source_metadata"]["active_members_snapshot_id"] == 900
    assert len(history_calls) == 1
    assert set(history_calls[0]["phones"]) == {
        "6861000001",
        "6861000002",
    }


@pytest.mark.parametrize(
    ("bucket", "expected_total"),
    [
        ("FUNNEL_BUYER_EXCLUDED", 1),
        ("ACTIVE_MEMBER_SUPPRESSION", 1),
        ("HISTORY_EXCLUDED", 1),
        ("RECIPIENTS", 1),
    ],
)
def test_funnel_preview_detail_buckets(monkeypatch, bucket, expected_total):
    _install(monkeypatch)
    detail = audience.build_campaign_v2_audience_preview_detail(
        bucket=bucket,
        page=1,
        page_size=50,
        **_kwargs(),
    )

    assert detail["bucket"] == bucket
    assert detail["total"] == expected_total
    assert len(detail["rows"]) == expected_total


def test_funnel_recipient_is_phone_only_and_has_no_tariff_family(monkeypatch):
    _install(monkeypatch)
    detail = audience.build_campaign_v2_audience_preview_detail(
        bucket="RECIPIENTS",
        **_kwargs(),
    )
    recipient = detail["rows"][0]

    assert recipient["source"] == "FUNNEL_PORTFOLIO"
    assert recipient["phone_mx10"] == "6861000001"
    assert recipient["member_id"] is None
    assert recipient["member_pin"] is None
    assert recipient["member_name"] is None
    assert recipient["tarifa_raw"] is None
    assert recipient["tarifa_key"] is None
    assert recipient["categoria_tarifa"] is None
    assert recipient["audience_family"] is None
    assert recipient["inclusion_reason"] == "FUNNEL_PORTFOLIO_ELIGIBLE"


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"audience_families": ["DOMICILIADO"]}, "audience_families no aplica"),
        ({"expiration_date_from": "2026-09-01"}, "vencimiento no aplican"),
        ({"funnel_month": None}, "funnel_month es obligatorio"),
        ({"funnel_cutoff_date": None}, "funnel_cutoff_date es obligatorio"),
    ],
)
def test_funnel_rejects_non_applicable_or_missing_filters(monkeypatch, kwargs, match):
    _install(monkeypatch)
    payload = _kwargs()
    payload.pop("history_exclusion", None)
    payload.update(kwargs)

    with pytest.raises(
        audience.MarketingCampaignV2AudienceValidationError,
        match=match,
    ):
        audience.build_campaign_v2_audience_preview(**payload)


def test_funnel_family_bucket_is_not_applicable(monkeypatch):
    _install(monkeypatch)
    with pytest.raises(
        audience.MarketingCampaignV2AudienceValidationError,
        match="no aplica",
    ):
        audience.build_campaign_v2_audience_preview_detail(
            bucket="FAMILY",
            audience_family="DOMICILIADO",
            **_kwargs(),
        )


def test_supported_sources_contains_funnel_portfolio():
    assert audience.SOURCE_FUNNEL_PORTFOLIO in audience.SUPPORTED_SOURCES


def test_funnel_canonical_historical_targeting_uses_common_evaluator(monkeypatch):
    history_calls = _install(monkeypatch)
    payload = _kwargs()
    payload.pop("history_exclusion")
    payload["historical_targeting"] = {
        "mode": "INCLUDE",
        "match": "ANY",
        "delivery_buckets": ["VIEWED"],
        "outcomes": [],
        "button_interacted": False,
        "lookback_days": None,
    }

    preview = audience.build_campaign_v2_audience_preview(**payload)

    assert preview["active_member_suppression_count"] == 1
    assert preview["before_history_filter_count"] == 2
    assert preview["history_matched_count"] == 1
    assert preview["history_not_matched_count"] == 1
    assert preview["history_included_count"] == 1
    assert preview["history_excluded_count"] == 1
    assert preview["unique_recipient_count"] == 1
    assert preview["filters"]["historical_targeting"]["mode"] == "INCLUDE"
    assert len(history_calls) == 1
    assert set(history_calls[0]["phones"]) == {
        "6861000001",
        "6861000002",
    }

    detail = audience.build_campaign_v2_audience_preview_detail(
        bucket="RECIPIENTS",
        page=1,
        page_size=50,
        **payload,
    )
    assert detail["rows"][0]["phone_mx10"] == "6861000002"


def test_funnel_history_decision_buckets_never_restore_active_suppression(monkeypatch):
    history_calls = _install(monkeypatch)
    payload = _kwargs()
    payload.pop("history_exclusion")
    payload["historical_targeting"] = {
        "mode": "INCLUDE",
        "match": "ANY",
        "delivery_buckets": ["VIEWED"],
        "outcomes": [],
        "button_interacted": False,
        "lookback_days": None,
    }

    included = audience.build_campaign_v2_audience_preview_detail(
        bucket="HISTORY_INCLUDED",
        page=1,
        page_size=50,
        **payload,
    )
    excluded = audience.build_campaign_v2_audience_preview_detail(
        bucket="HISTORY_EXCLUDED",
        page=1,
        page_size=50,
        **payload,
    )
    recipients = audience.build_campaign_v2_audience_preview_detail(
        bucket="RECIPIENTS",
        page=1,
        page_size=50,
        **payload,
    )

    assert [row["phone_mx10"] for row in included["rows"]] == [
        "6861000002"
    ]
    assert included["rows"][0]["history_matched"] is True
    assert included["rows"][0]["history_decision"] == "INCLUDED"
    assert included["rows"][0]["history_reasons"] == [
        "HISTORY_DELIVERY_VIEWED"
    ]

    assert [row["phone_mx10"] for row in excluded["rows"]] == [
        "6861000001"
    ]
    assert excluded["rows"][0]["history_matched"] is False
    assert excluded["rows"][0]["history_decision"] == "EXCLUDED"
    assert excluded["rows"][0]["history_reasons"] == []

    assert [row["phone_mx10"] for row in recipients["rows"]] == [
        "6861000002"
    ]
    observed_phones = {
        phone
        for call in history_calls
        for phone in call["phones"]
    }
    assert "6861000003" not in observed_phones
