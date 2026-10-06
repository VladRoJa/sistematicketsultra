from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.marketing import MarketingCampaignV2ORM
from app.services import marketing_campaign_v2_audience_service as audience
from app.services import marketing_campaign_v2_creation_service as creation
from app.services import marketing_campaign_v2_provider_history_service as provider_history


@pytest.fixture(autouse=True)
def _empty_blacklist(monkeypatch):
    monkeypatch.setattr(audience, "get_blacklisted_phones", lambda **_kwargs: set())


CUTOFF = datetime(2026, 10, 2, 18, 0, tzinfo=timezone.utc)


def _candidate(phone: str, row_id: int):
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


def _history_row(
    phone: str,
    *,
    buckets=(),
    outcomes=(),
    button=False,
    last=CUTOFF,
):
    has_history = bool(buckets or outcomes or button)
    return {
        "normalized_phone": f"mx10:{phone}",
        "campaign_count": 1 if has_history else 0,
        "first_observed_at": last.isoformat() if has_history else None,
        "last_observed_at": last.isoformat() if has_history else None,
        "ever_observed": {
            "outcomes": list(outcomes),
            "delivery_buckets": list(buckets),
            "button_interacted": button,
            "button_labels": ["CTA"] if button else [],
        },
        "latest_by_campaign": [],
    }


def _abcd_rows():
    return [
        _history_row("6861000001", buckets=["VIEWED"]),
        _history_row("6861000002", button=True),
        _history_row("6861000003", buckets=["VIEWED"], button=True),
        _history_row("6861000004"),
    ]


def _abcd_candidates():
    return tuple(
        _candidate(f"686100000{index}", index)
        for index in range(1, 5)
    )


def _install_rows(monkeypatch, rows, calls=None):
    def lookup(**kwargs):
        if calls is not None:
            calls.append(kwargs)
        return {
            "observed_before": None,
            "observed_after": None,
            "phone_count": len(kwargs["phones"]),
            "rows": rows,
        }

    monkeypatch.setattr(
        audience,
        "get_provider_history_for_phones",
        lookup,
    )


def _rule(mode: str, match: str, **overrides):
    value = {
        "mode": mode,
        "match": match,
        "delivery_buckets": ["VIEWED"],
        "outcomes": [],
        "button_interacted": True,
        "lookback_days": None,
    }
    value.update(overrides)
    return audience._normalize_historical_targeting(value)


@pytest.mark.parametrize(
    ("mode", "match", "expected"),
    [
        ("INCLUDE", "ALL", {"6861000003"}),
        (
            "INCLUDE",
            "ANY",
            {"6861000001", "6861000002", "6861000003"},
        ),
        (
            "EXCLUDE",
            "ALL",
            {"6861000001", "6861000002", "6861000004"},
        ),
        ("EXCLUDE", "ANY", {"6861000004"}),
    ],
)
def test_historical_targeting_mode_match_matrix(
    monkeypatch,
    mode,
    match,
    expected,
):
    _install_rows(monkeypatch, _abcd_rows())

    remaining, decisions, diagnostics, _evaluation = (
        audience._evaluate_historical_targeting(
            candidates=_abcd_candidates(),
            rule=_rule(mode, match),
            allowed_sucursal_keys=("BRANCH A",),
            session=object(),
            legacy=False,
        )
    )

    assert {row.phone_mx10 for row in remaining} == expected
    assert diagnostics["before_history_filter_count"] == 4
    assert diagnostics["history_included_count"] == len(expected)
    assert diagnostics["history_excluded_count"] == 4 - len(expected)
    assert diagnostics["after_history_filter_count"] == len(expected)
    assert len(decisions) == 4


def test_no_history_naturally_fails_match(monkeypatch):
    _install_rows(monkeypatch, [_history_row("6861000004")])
    candidate = (_candidate("6861000004", 4),)

    included, include_decisions, include_diag, _ = (
        audience._evaluate_historical_targeting(
            candidates=candidate,
            rule=_rule("INCLUDE", "ANY"),
            allowed_sucursal_keys=None,
            session=object(),
            legacy=False,
        )
    )
    excluded, exclude_decisions, exclude_diag, _ = (
        audience._evaluate_historical_targeting(
            candidates=candidate,
            rule=_rule("EXCLUDE", "ANY"),
            allowed_sucursal_keys=None,
            session=object(),
            legacy=False,
        )
    )

    assert included == ()
    assert include_decisions[0].matched is False
    assert include_decisions[0].decision == "EXCLUDED"
    assert include_diag["history_not_matched_count"] == 1

    assert [row.phone_mx10 for row in excluded] == ["6861000004"]
    assert exclude_decisions[0].matched is False
    assert exclude_decisions[0].decision == "INCLUDED"
    assert exclude_diag["history_not_matched_count"] == 1


def test_mixed_atomic_conditions_require_every_selected_condition_for_all(
    monkeypatch,
):
    rows = [
        _history_row(
            "6861000001",
            buckets=["DELIVERED", "VIEWED"],
            outcomes=["SUCCESSFUL"],
            button=True,
        ),
        _history_row(
            "6861000002",
            buckets=["DELIVERED", "VIEWED"],
            outcomes=["FAILED"],
            button=True,
        ),
    ]
    _install_rows(monkeypatch, rows)
    candidates = (
        _candidate("6861000001", 1),
        _candidate("6861000002", 2),
    )
    rule = _rule(
        "INCLUDE",
        "ALL",
        delivery_buckets=["DELIVERED", "VIEWED"],
        outcomes=["SUCCESSFUL"],
        button_interacted=True,
    )

    remaining, _decisions, diagnostics, _ = (
        audience._evaluate_historical_targeting(
            candidates=candidates,
            rule=rule,
            allowed_sucursal_keys=None,
            session=object(),
            legacy=False,
        )
    )

    assert [row.phone_mx10 for row in remaining] == ["6861000001"]
    assert diagnostics["history_matched_count"] == 1
    assert diagnostics["matched_by_delivery_bucket"] == {
        "DELIVERED": 1,
        "VIEWED": 1,
    }
    assert diagnostics["matched_by_outcome"] == {"SUCCESSFUL": 1}
    assert diagnostics["matched_by_button_interaction"] == 1


def test_cross_campaign_ever_observed_satisfies_all(monkeypatch):
    phone = "6861000003"
    campaign_a = SimpleNamespace(id=11)
    campaign_b = SimpleNamespace(id=22)
    snapshot_a = SimpleNamespace(
        id=101,
        fetched_at=CUTOFF - timedelta(hours=1),
        provider="IVENTAS",
        provider_campaign_id="campaign-a",
    )
    snapshot_b = SimpleNamespace(
        id=102,
        fetched_at=CUTOFF,
        provider="IVENTAS",
        provider_campaign_id="campaign-b",
    )
    observation_a = SimpleNamespace(
        outcome="SUCCESSFUL",
        delivery_bucket="VIEWED",
        button_labels_json=[],
    )
    observation_b = SimpleNamespace(
        outcome="SUCCESSFUL",
        delivery_bucket="SENT",
        button_labels_json=["CTA"],
    )

    history = provider_history._serialize_history(
        provider_history._build_history(
            normalized_phone=f"mx10:{phone}",
            rows=[
                (observation_a, snapshot_a, campaign_a),
                (observation_b, snapshot_b, campaign_b),
            ],
        )
    )
    assert history["campaign_count"] == 2
    assert "VIEWED" in history["ever_observed"]["delivery_buckets"]
    assert history["ever_observed"]["button_interacted"] is True

    _install_rows(monkeypatch, [history])
    remaining, decisions, diagnostics, _ = (
        audience._evaluate_historical_targeting(
            candidates=(_candidate(phone, 3),),
            rule=_rule("INCLUDE", "ALL"),
            allowed_sucursal_keys=None,
            session=object(),
            legacy=False,
        )
    )

    assert [row.phone_mx10 for row in remaining] == [phone]
    assert decisions[0].matched is True
    assert diagnostics["history_matched_count"] == 1
def test_lookback_preserves_m14_backend_authoritative_anchor(monkeypatch):
    calls = []
    candidates = (
        _candidate("6861000001", 1),
        _candidate("6861000002", 2),
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
            last=CUTOFF,
        ),
    ]

    def lookup(**kwargs):
        calls.append(kwargs)
        return {
            "rows": (
                window_rows
                if kwargs.get("observed_after") is not None
                else anchor_rows
            )
        }

    monkeypatch.setattr(
        audience,
        "get_provider_history_for_phones",
        lookup,
    )

    remaining, _decisions, _diagnostics, evaluation = (
        audience._evaluate_historical_targeting(
            candidates=candidates,
            rule=_rule(
                "INCLUDE",
                "ANY",
                button_interacted=False,
                lookback_days=90,
            ),
            allowed_sucursal_keys=("BRANCH A",),
            session=object(),
            legacy=False,
        )
    )

    assert len(calls) == 2
    assert calls[0].get("observed_before") is None
    assert calls[0]["allowed_sucursal_keys"] == ("BRANCH A",)
    assert calls[1]["observed_before"] == CUTOFF
    assert calls[1]["observed_after"] == CUTOFF - timedelta(days=90)
    assert evaluation == {
        "observed_before": CUTOFF.isoformat(),
        "observed_after": (CUTOFF - timedelta(days=90)).isoformat(),
    }
    assert [row.phone_mx10 for row in remaining] == ["6861000002"]


@pytest.mark.parametrize(
    "payload,match",
    [
        (
            {
                "mode": "MAYBE",
                "match": "ANY",
                "delivery_buckets": ["VIEWED"],
            },
            "mode",
        ),
        (
            {
                "mode": "INCLUDE",
                "match": "SOME",
                "delivery_buckets": ["VIEWED"],
            },
            "match",
        ),
        (
            {
                "mode": "INCLUDE",
                "match": "ALL",
                "delivery_buckets": [],
                "outcomes": [],
                "button_interacted": False,
            },
            "condición efectiva",
        ),
        (
            {
                "mode": "INCLUDE",
                "match": "ALL",
                "delivery_buckets": ["VIEWED"],
                "lookback_days": 0,
            },
            "entero positivo",
        ),
    ],
)
def test_new_rule_validation(payload, match):
    with pytest.raises(
        audience.MarketingCampaignV2AudienceValidationError,
        match=match,
    ):
        audience._normalize_historical_targeting(payload)


def test_legacy_resolves_to_exclude_any_without_changing_frozen_shape():
    legacy = {
        "delivery_buckets": ["VIEWED"],
        "outcomes": ["FAILED"],
        "button_interacted": True,
        "lookback_days": 30,
    }
    resolved = audience._resolve_historical_targeting_input(
        history_exclusion=legacy,
        historical_targeting=None,
    )

    assert resolved.legacy is True
    assert resolved.rule == {
        "mode": "EXCLUDE",
        "match": "ANY",
        **legacy,
    }
    assert resolved.filter_key == "history_exclusion"
    assert resolved.filter_value == legacy


def test_direct_core_rejects_legacy_and_new_together():
    with pytest.raises(
        audience.MarketingCampaignV2AudienceValidationError,
        match="no pueden enviarse juntos",
    ):
        audience._resolve_historical_targeting_input(
            history_exclusion={"delivery_buckets": ["VIEWED"]},
            historical_targeting={
                "mode": "INCLUDE",
                "match": "ANY",
                "delivery_buckets": ["VIEWED"],
            },
        )


def _source_result(candidates):
    return audience._SourceLoadResult(
        universe_count=len(candidates),
        scoped_count=len(candidates),
        candidates=tuple(candidates),
        current_status_blocked=(),
        current_status_counts={},
        metadata={"fixture": True},
    )


def _install_expired_source(monkeypatch, candidates):
    monkeypatch.setattr(
        audience,
        "_load_expired_source",
        lambda **_kwargs: _source_result(candidates),
    )
    monkeypatch.setattr(
        audience,
        "_read_v2_tariff_catalog",
        lambda **_kwargs: {
            "DOM": ("Domiciliado", "DOMICILIADO"),
        },
    )


def _targeting(mode="EXCLUDE", match="ANY"):
    return {
        "mode": mode,
        "match": match,
        "delivery_buckets": ["VIEWED"],
        "outcomes": [],
        "button_interacted": False,
        "lookback_days": None,
    }


def test_no_rule_skips_m13(monkeypatch):
    _install_expired_source(
        monkeypatch,
        [_candidate("6861000001", 1)],
    )
    calls = []
    monkeypatch.setattr(
        audience,
        "get_provider_history_for_phones",
        lambda **kwargs: calls.append(kwargs),
    )

    preview = audience.build_campaign_v2_audience_preview(
        source="EXPIRED_MEMBERS",
        audience_families=["DOMICILIADO"],
        allowed_sucursal_keys=("BRANCH A",),
        expiration_date_from="2026-08-01",
        expiration_date_to="2026-08-31",
        session=object(),
    )

    assert preview["unique_recipient_count"] == 1
    assert calls == []
    assert "historical_targeting" not in preview["filters"]
    assert "history_exclusion" not in preview["filters"]


def test_new_preview_persists_canonical_filter_and_neutral_diagnostics(
    monkeypatch,
):
    _install_expired_source(
        monkeypatch,
        [
            _candidate("6861000001", 1),
            _candidate("6861000002", 2),
        ],
    )
    _install_rows(
        monkeypatch,
        [
            _history_row("6861000001", buckets=["VIEWED"]),
            _history_row("6861000002"),
        ],
    )

    preview = creation.build_campaign_v2_freeze_preview(
        source="EXPIRED_MEMBERS",
        audience_families=["DOMICILIADO"],
        allowed_sucursal_keys=("BRANCH A",),
        expiration_date_from="2026-08-01",
        expiration_date_to="2026-08-31",
        historical_targeting=_targeting(),
        session=object(),
    )

    assert preview["filters"]["historical_targeting"] == _targeting()
    assert "history_exclusion" not in preview["filters"]
    assert preview["history_matched_count"] == 1
    assert preview["history_not_matched_count"] == 1
    assert preview["history_included_count"] == 1
    assert preview["history_excluded_count"] == 1
    assert preview["matched_by_delivery_bucket"] == {"VIEWED": 1}
    assert preview["unique_recipient_count"] == 1
    assert preview["source_metadata"]["history_evaluation"] == {
        "observed_before": CUTOFF.isoformat(),
        "observed_after": None,
    }


class _WriteSession:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, value):
        self.added.append(value)

    def flush(self):
        for value in self.added:
            if isinstance(value, MarketingCampaignV2ORM) and value.id is None:
                value.id = 777

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


def test_new_freeze_is_stable_and_persists_new_filter(monkeypatch):
    candidates = [
        _candidate("6861000001", 1),
        _candidate("6861000002", 2),
    ]
    _install_expired_source(monkeypatch, candidates)
    _install_rows(
        monkeypatch,
        [
            _history_row("6861000001", buckets=["VIEWED"]),
            _history_row("6861000002"),
        ],
    )

    kwargs = {
        "source": "EXPIRED_MEMBERS",
        "audience_families": ["DOMICILIADO"],
        "allowed_sucursal_keys": ("BRANCH A",),
        "expiration_date_from": "2026-08-01",
        "expiration_date_to": "2026-08-31",
        "historical_targeting": _targeting(),
    }
    first = creation.build_campaign_v2_freeze_preview(
        **kwargs,
        session=object(),
    )
    second = creation.build_campaign_v2_freeze_preview(
        **kwargs,
        session=object(),
    )
    assert first["preview_fingerprint"] == second["preview_fingerprint"]

    session = _WriteSession()
    frozen = creation.freeze_campaign_v2(
        name="Historical targeting",
        purpose="REACTIVATION",
        expected_preview_fingerprint=first["preview_fingerprint"],
        created_by_user_id=7,
        now=CUTOFF,
        session=session,
        **kwargs,
    )

    assert frozen["recipient_count"] == 1
    campaign = session.added[0]
    assert campaign.audience_definition_json["filters"][
        "historical_targeting"
    ] == _targeting()
    assert "history_exclusion" not in campaign.audience_definition_json["filters"]
    assert campaign.audience_definition_json["source_metadata"][
        "history_evaluation"
    ] == {
        "observed_before": CUTOFF.isoformat(),
        "observed_after": None,
    }


def test_history_cutoff_drift_causes_preview_mismatch(monkeypatch):
    _install_expired_source(
        monkeypatch,
        [_candidate("6861000001", 1)],
    )
    observed = {"at": CUTOFF}

    def lookup(**kwargs):
        return {
            "rows": [
                _history_row(
                    "6861000001",
                    buckets=["VIEWED"],
                    last=observed["at"],
                )
            ]
        }

    monkeypatch.setattr(
        audience,
        "get_provider_history_for_phones",
        lookup,
    )
    kwargs = {
        "source": "EXPIRED_MEMBERS",
        "audience_families": ["DOMICILIADO"],
        "allowed_sucursal_keys": ("BRANCH A",),
        "expiration_date_from": "2026-08-01",
        "expiration_date_to": "2026-08-31",
        "historical_targeting": _targeting(
            mode="INCLUDE",
            match="ANY",
        ),
    }

    preview = creation.build_campaign_v2_freeze_preview(
        **kwargs,
        session=object(),
    )
    observed["at"] = CUTOFF + timedelta(minutes=5)

    session = _WriteSession()
    with pytest.raises(
        creation.MarketingCampaignV2PreviewMismatchError
    ):
        creation.freeze_campaign_v2(
            name="Drift",
            purpose="REACTIVATION",
            expected_preview_fingerprint=preview["preview_fingerprint"],
            created_by_user_id=7,
            now=CUTOFF,
            session=session,
            **kwargs,
        )

    assert session.added == []
    assert session.commits == 0


def test_active_members_uses_same_historical_targeting_evaluator(monkeypatch):
    active = replace(
        _candidate("6861000001", 1),
        source=audience.SOURCE_ACTIVE_MEMBERS,
        source_ref_type="SOCIOS_ACTIVOS_SNAPSHOT_ROW",
        source_snapshot_id=91,
        current_status=None,
    )
    monkeypatch.setattr(
        audience,
        "_load_active_source",
        lambda **_kwargs: _source_result([active]),
    )
    monkeypatch.setattr(
        audience,
        "_read_v2_tariff_catalog",
        lambda **_kwargs: {
            "DOM": ("Domiciliado", "DOMICILIADO"),
        },
    )
    _install_rows(
        monkeypatch,
        [_history_row("6861000001", buckets=["VIEWED"])],
    )

    preview = audience.build_campaign_v2_audience_preview(
        source="ACTIVE_MEMBERS",
        audience_families=["DOMICILIADO"],
        allowed_sucursal_keys=("BRANCH A",),
        historical_targeting=_targeting(
            mode="INCLUDE",
            match="ANY",
        ),
        session=object(),
    )

    assert preview["unique_recipient_count"] == 1
    assert preview["history_matched_count"] == 1
    assert preview["history_included_count"] == 1
    assert "historical_targeting" in preview["filters"]


def test_historical_targeting_core_reads_m13_only():
    import inspect

    source = inspect.getsource(audience._evaluate_historical_targeting)
    assert "get_provider_history_for_phones" in source
    assert "provider_stats" not in source
    assert "requests." not in source
    assert "http" not in source.lower()
