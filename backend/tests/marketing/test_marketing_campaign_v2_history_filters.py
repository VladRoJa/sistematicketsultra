from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.marketing import MarketingCampaignV2ORM
from app.services import marketing_campaign_v2_audience_service as audience
from app.services import marketing_campaign_v2_creation_service as creation


CUTOFF = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def _candidate(row_id: int, phone: str):
    return audience.MarketingCampaignV2AudienceCandidate(
        source=audience.SOURCE_EXPIRED_MEMBERS,
        source_ref_type="SOCIOS_VENCIDOS_CARTERA",
        source_ref_id=row_id,
        phone_raw=phone,
        phone_mx10=phone,
        member_pin=f"PIN-{row_id}",
        member_name=f"Socio {row_id}",
        sucursal="BRANCH A",
        sucursal_key="BRANCH A",
        tarifa_raw="DOM",
        tarifa_key="DOM",
        categoria_tarifa="Domiciliado",
        audience_family="DOMICILIADO",
        fecha_vencimiento=date(2026, 8, 15),
        current_status=audience.current_status.STATUS_NOT_FOUND,
    )


def _install_source(monkeypatch, candidates):
    result = audience._SourceLoadResult(
        universe_count=len(candidates),
        scoped_count=len(candidates),
        candidates=tuple(candidates),
        current_status_blocked=(),
        current_status_counts={},
        metadata={"fixture": True},
    )
    monkeypatch.setattr(
        audience,
        "_load_expired_source",
        lambda **kwargs: result,
    )
    monkeypatch.setattr(
        audience,
        "_read_v2_tariff_catalog",
        lambda **kwargs: {
            "DOM": ("Domiciliado", "DOMICILIADO"),
        },
    )


def _history_row(
    phone,
    *,
    buckets=(),
    outcomes=(),
    button=False,
    first=None,
    last=None,
):
    return {
        "normalized_phone": f"mx10:{phone}",
        "campaign_count": 1 if (buckets or outcomes or button) else 0,
        "first_observed_at": (
            first.isoformat()
            if first is not None
            else (CUTOFF.isoformat() if (buckets or outcomes or button) else None)
        ),
        "last_observed_at": (
            last.isoformat()
            if last is not None
            else (CUTOFF.isoformat() if (buckets or outcomes or button) else None)
        ),
        "ever_observed": {
            "outcomes": list(outcomes),
            "delivery_buckets": list(buckets),
            "button_interacted": button,
            "button_labels": ["INFO"] if button else [],
        },
        "latest_by_campaign": [],
    }


def _install_history(monkeypatch, rows, calls=None):
    def lookup(**kwargs):
        if calls is not None:
            calls.append(kwargs)
        return {
            "observed_before": (
                kwargs.get("observed_before").isoformat()
                if kwargs.get("observed_before") is not None
                else None
            ),
            "observed_after": (
                kwargs.get("observed_after").isoformat()
                if kwargs.get("observed_after") is not None
                else None
            ),
            "phone_count": len(kwargs["phones"]),
            "rows": rows,
        }

    monkeypatch.setattr(
        audience,
        "get_provider_history_for_phones",
        lookup,
    )


def _preview(monkeypatch, candidates, *, rule=None, scope=None):
    _install_source(monkeypatch, candidates)
    return audience.build_campaign_v2_audience_preview(
        source="EXPIRED_MEMBERS",
        audience_families=["DOMICILIADO"],
        allowed_sucursal_keys=scope,
        expiration_date_from="2026-08-01",
        expiration_date_to="2026-08-31",
        history_exclusion=rule,
        session=object(),
    )


def test_without_history_filter_is_backward_compatible_and_skips_history(monkeypatch):
    calls = []
    _install_source(monkeypatch, [_candidate(1, "6861000001")])
    monkeypatch.setattr(
        audience,
        "get_provider_history_for_phones",
        lambda **kwargs: calls.append(kwargs),
    )

    preview = audience.build_campaign_v2_audience_preview(
        source="EXPIRED_MEMBERS",
        audience_families=["DOMICILIADO"],
        allowed_sucursal_keys=None,
        expiration_date_from="2026-08-01",
        expiration_date_to="2026-08-31",
        session=object(),
    )

    assert preview["unique_recipient_count"] == 1
    assert "history_exclusion" not in preview["filters"]
    assert "history_evaluation" not in preview["source_metadata"]
    assert "history_excluded_count" not in preview
    assert calls == []


@pytest.mark.parametrize(
    ("rule", "row"),
    [
        (
            {"delivery_buckets": ["VIEWED"]},
            _history_row("6861000001", buckets=["VIEWED"], outcomes=["SUCCESSFUL"]),
        ),
        (
            {"delivery_buckets": ["DELIVERED"]},
            _history_row("6861000001", buckets=["DELIVERED"], outcomes=["SUCCESSFUL"]),
        ),
        (
            {"delivery_buckets": ["SENT"]},
            _history_row("6861000001", buckets=["SENT"], outcomes=["SUCCESSFUL"]),
        ),
        (
            {"outcomes": ["FAILED"]},
            _history_row("6861000001", outcomes=["FAILED"]),
        ),
        (
            {"button_interacted": True},
            _history_row("6861000001", outcomes=["SUCCESSFUL"], button=True),
        ),
    ],
)
def test_each_supported_history_condition_excludes(monkeypatch, rule, row):
    _install_history(monkeypatch, [row])

    preview = _preview(
        monkeypatch,
        [_candidate(1, "6861000001"), _candidate(2, "6861000002")],
        rule=rule,
    )

    assert preview["before_history_filter_count"] == 2
    assert preview["history_excluded_count"] == 1
    assert preview["after_history_filter_count"] == 1
    assert preview["unique_recipient_count"] == 1


def test_viewed_does_not_imply_delivered(monkeypatch):
    _install_history(
        monkeypatch,
        [
            _history_row(
                "6861000001",
                buckets=["VIEWED"],
                outcomes=["SUCCESSFUL"],
            )
        ],
    )

    preview = _preview(
        monkeypatch,
        [_candidate(1, "6861000001")],
        rule={"delivery_buckets": ["DELIVERED"]},
    )

    assert preview["history_excluded_count"] == 0
    assert preview["unique_recipient_count"] == 1


def test_unknown_or_nonexistent_history_semantics_are_rejected():
    with pytest.raises(
        audience.MarketingCampaignV2AudienceValidationError,
        match="no permitidos",
    ):
        audience._normalize_history_exclusion({"responded": True})


def test_multiple_rules_are_or_and_reason_counts_are_non_exclusive(monkeypatch):
    _install_history(
        monkeypatch,
        [
            _history_row(
                "6861000001",
                buckets=["VIEWED"],
                outcomes=["FAILED"],
            ),
            _history_row(
                "6861000002",
                outcomes=["SUCCESSFUL"],
                button=True,
            ),
            _history_row("6861000003"),
        ],
    )
    rule = {
        "delivery_buckets": ["VIEWED"],
        "outcomes": ["FAILED"],
        "button_interacted": True,
    }

    preview = _preview(
        monkeypatch,
        [
            _candidate(1, "6861000001"),
            _candidate(2, "6861000002"),
            _candidate(3, "6861000003"),
        ],
        rule=rule,
    )

    assert preview["history_excluded_count"] == 2
    assert preview["after_history_filter_count"] == 1
    assert preview["excluded_by_delivery_bucket"] == {"VIEWED": 1}
    assert preview["excluded_by_outcome"] == {"FAILED": 1}
    assert preview["excluded_by_button_interaction"] == 1
    assert (
        sum(preview["excluded_by_delivery_bucket"].values())
        + sum(preview["excluded_by_outcome"].values())
        + preview["excluded_by_button_interaction"]
        == 3
    )


def test_lookback_uses_backend_cutoff_and_inclusive_window(monkeypatch):
    calls = []
    _install_source(
        monkeypatch,
        [
            _candidate(1, "6861000001"),
            _candidate(2, "6861000002"),
        ],
    )

    anchor_rows = [
        _history_row(
            "6861000001",
            buckets=["VIEWED"],
            last=CUTOFF - timedelta(days=100),
        ),
        _history_row(
            "6861000002",
            buckets=["VIEWED"],
            last=CUTOFF,
        ),
    ]
    window_rows = [
        _history_row("6861000001"),
        _history_row(
            "6861000002",
            buckets=["VIEWED"],
            first=CUTOFF - timedelta(days=90),
            last=CUTOFF,
        ),
    ]

    def lookup(**kwargs):
        calls.append(kwargs)
        rows = window_rows if kwargs.get("observed_after") is not None else anchor_rows
        return {
            "observed_before": None,
            "observed_after": None,
            "phone_count": 2,
            "rows": rows,
        }

    monkeypatch.setattr(audience, "get_provider_history_for_phones", lookup)

    preview = audience.build_campaign_v2_audience_preview(
        source="EXPIRED_MEMBERS",
        audience_families=["DOMICILIADO"],
        allowed_sucursal_keys=None,
        expiration_date_from="2026-08-01",
        expiration_date_to="2026-08-31",
        history_exclusion={
            "delivery_buckets": ["VIEWED"],
            "lookback_days": 90,
        },
        session=object(),
    )

    assert len(calls) == 2
    assert calls[0].get("observed_before") is None
    assert calls[0]["max_phones"] is None
    assert calls[1]["observed_before"] == CUTOFF
    assert calls[1]["observed_after"] == CUTOFF - timedelta(days=90)
    assert preview["history_excluded_count"] == 1
    assert preview["source_metadata"]["history_evaluation"] == {
        "observed_before": CUTOFF.isoformat(),
        "observed_after": (CUTOFF - timedelta(days=90)).isoformat(),
    }


def test_scope_is_forwarded_to_history_and_candidate_without_history_remains(monkeypatch):
    calls = []
    _install_history(
        monkeypatch,
        [_history_row("6861000001")],
        calls=calls,
    )

    preview = _preview(
        monkeypatch,
        [_candidate(1, "6861000001")],
        rule={"delivery_buckets": ["VIEWED"]},
        scope=("BRANCH A",),
    )

    assert preview["history_excluded_count"] == 0
    assert preview["unique_recipient_count"] == 1
    assert calls[0]["allowed_sucursal_keys"] == ("BRANCH A",)


def test_provider_unmatched_history_phone_can_exclude_same_normalized_candidate(monkeypatch):
    _install_history(
        monkeypatch,
        [_history_row("6861000001", buckets=["VIEWED"])],
    )
    preview = _preview(
        monkeypatch,
        [_candidate(1, "6861000001")],
        rule={"delivery_buckets": ["VIEWED"]},
    )
    assert preview["history_excluded_count"] == 1
    assert preview["unique_recipient_count"] == 0


def test_preview_detail_history_excluded_has_canonical_reasons(monkeypatch):
    _install_source(monkeypatch, [_candidate(1, "6861000001")])
    _install_history(
        monkeypatch,
        [
            _history_row(
                "6861000001",
                buckets=["VIEWED"],
                outcomes=["FAILED"],
                button=True,
            )
        ],
    )

    detail = audience.build_campaign_v2_audience_preview_detail(
        source="EXPIRED_MEMBERS",
        audience_families=["DOMICILIADO"],
        allowed_sucursal_keys=None,
        expiration_date_from="2026-08-01",
        expiration_date_to="2026-08-31",
        history_exclusion={
            "delivery_buckets": ["VIEWED"],
            "outcomes": ["FAILED"],
            "button_interacted": True,
        },
        bucket="HISTORY_EXCLUDED",
        page=1,
        page_size=50,
        session=object(),
    )

    assert detail["total"] == 1
    assert detail["rows"][0]["phone_mx10"] == "6861000001"
    assert detail["rows"][0]["history_exclusion_reasons"] == [
        "HISTORY_BUTTON_INTERACTION",
        "HISTORY_DELIVERY_VIEWED",
        "HISTORY_OUTCOME_FAILED",
    ]


class WriteSession:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, value):
        self.added.append(value)

    def flush(self):
        for value in self.added:
            if isinstance(value, MarketingCampaignV2ORM) and value.id is None:
                value.id = 901

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


def test_freeze_persists_rule_and_effective_cutoff(monkeypatch):
    candidates = [
        _candidate(1, "6861000001"),
        _candidate(2, "6861000002"),
    ]
    _install_source(monkeypatch, candidates)
    _install_history(
        monkeypatch,
        [
            _history_row("6861000001", buckets=["VIEWED"]),
            _history_row("6861000002"),
        ],
    )
    rule = {
        "delivery_buckets": ["VIEWED"],
        "outcomes": [],
        "button_interacted": False,
        "lookback_days": None,
    }

    preview = creation.build_campaign_v2_freeze_preview(
        source="EXPIRED_MEMBERS",
        audience_families=["DOMICILIADO"],
        allowed_sucursal_keys=None,
        expiration_date_from="2026-08-01",
        expiration_date_to="2026-08-31",
        history_exclusion=rule,
        session=object(),
    )

    session = WriteSession()
    created = creation.freeze_campaign_v2(
        name="History Filter",
        purpose="REACTIVATION",
        source="EXPIRED_MEMBERS",
        audience_families=["DOMICILIADO"],
        allowed_sucursal_keys=None,
        expiration_date_from="2026-08-01",
        expiration_date_to="2026-08-31",
        history_exclusion=rule,
        expected_preview_fingerprint=preview["preview_fingerprint"],
        created_by_user_id=7,
        session=session,
        now=CUTOFF,
    )

    campaign = session.added[0]
    assert created["recipient_count"] == 1
    assert campaign.audience_definition_json["filters"]["history_exclusion"] == rule
    assert campaign.audience_definition_json["source_metadata"]["history_evaluation"] == {
        "observed_before": CUTOFF.isoformat(),
        "observed_after": None,
    }


def test_new_history_between_preview_and_freeze_causes_fingerprint_mismatch(monkeypatch):
    candidates = [_candidate(1, "6861000001")]
    _install_source(monkeypatch, candidates)
    cutoff = {"value": CUTOFF}

    def lookup(**kwargs):
        return {
            "observed_before": None,
            "observed_after": None,
            "phone_count": 1,
            "rows": [
                _history_row(
                    "6861000001",
                    outcomes=["SUCCESSFUL"],
                    last=cutoff["value"],
                )
            ],
        }

    monkeypatch.setattr(audience, "get_provider_history_for_phones", lookup)
    rule = {"outcomes": ["FAILED"]}

    preview = creation.build_campaign_v2_freeze_preview(
        source="EXPIRED_MEMBERS",
        audience_families=["DOMICILIADO"],
        allowed_sucursal_keys=None,
        expiration_date_from="2026-08-01",
        expiration_date_to="2026-08-31",
        history_exclusion=rule,
        session=object(),
    )

    cutoff["value"] = CUTOFF + timedelta(minutes=5)

    with pytest.raises(creation.MarketingCampaignV2PreviewMismatchError):
        creation.freeze_campaign_v2(
            name="Drift",
            purpose="REACTIVATION",
            source="EXPIRED_MEMBERS",
            audience_families=["DOMICILIADO"],
            allowed_sucursal_keys=None,
            expiration_date_from="2026-08-01",
            expiration_date_to="2026-08-31",
            history_exclusion=rule,
            expected_preview_fingerprint=preview["preview_fingerprint"],
            created_by_user_id=7,
            session=WriteSession(),
            now=CUTOFF,
        )


def test_large_audience_uses_single_bulk_history_call_without_lookback(monkeypatch):
    candidates = [
        _candidate(index, f"686{index:07d}")
        for index in range(1, 2001)
    ]
    _install_source(monkeypatch, candidates)
    calls = []

    def lookup(**kwargs):
        calls.append(kwargs)
        return {
            "observed_before": None,
            "observed_after": None,
            "phone_count": len(kwargs["phones"]),
            "rows": [
                _history_row(phone)
                for phone in kwargs["phones"]
            ],
        }

    monkeypatch.setattr(audience, "get_provider_history_for_phones", lookup)

    preview = audience.build_campaign_v2_audience_preview(
        source="EXPIRED_MEMBERS",
        audience_families=["DOMICILIADO"],
        allowed_sucursal_keys=None,
        expiration_date_from="2026-08-01",
        expiration_date_to="2026-08-31",
        history_exclusion={"delivery_buckets": ["VIEWED"]},
        session=object(),
    )

    assert preview["unique_recipient_count"] == 2000
    assert len(calls) == 1
    assert len(calls[0]["phones"]) == 2000
    assert calls[0]["max_phones"] is None
