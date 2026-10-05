from app.services import marketing_campaign_v2_audience_service as audience


def _candidate(phone: str):
    return audience.MarketingCampaignV2AudienceCandidate(
        source=audience.SOURCE_FUNNEL_PORTFOLIO,
        source_ref_type="FUNNEL_CONTACT",
        source_ref_id=None,
        phone_raw=phone,
        phone_mx10=phone,
    )


def test_current_iventas_status_filter_keeps_viewed_without_campaign_history(monkeypatch):
    rows = (
        _candidate("6861111111"),
        _candidate("6862222222"),
        _candidate("6863333333"),
    )

    monkeypatch.setattr(
        audience,
        "get_latest_iventas_status_by_phone",
        lambda **_kwargs: {
            "sync_run_id": 77,
            "period_key": "2026-10",
            "date_from": "2026-10-01",
            "date_to": "2026-10-05",
            "finished_at": "2026-10-05T20:00:00+00:00",
            "statuses": {
                "6861111111": "VIEWED",
                "6862222222": "DELIVERED",
                "6863333333": None,
            },
        },
    )

    kept, metadata = audience._filter_by_iventas_current_status(
        candidates=rows,
        selected_statuses=("VIEWED",),
        session=object(),
    )

    assert [row.phone_mx10 for row in kept] == ["6861111111"]
    assert metadata["sync_run_id"] == 77
    assert metadata["before_phone_count"] == 3
    assert metadata["matched_phone_count"] == 1
    assert metadata["status_counts"]["VIEWED"] == 1
    assert metadata["status_counts"]["DELIVERED"] == 1
    assert metadata["status_counts"]["NO_DATA"] == 1


def test_current_iventas_status_filter_supports_no_data(monkeypatch):
    rows = (
        _candidate("6861111111"),
        _candidate("6862222222"),
    )

    monkeypatch.setattr(
        audience,
        "get_latest_iventas_status_by_phone",
        lambda **_kwargs: {
            "sync_run_id": 78,
            "period_key": "2026-10",
            "date_from": "2026-10-01",
            "date_to": "2026-10-05",
            "finished_at": "2026-10-05T20:00:00+00:00",
            "statuses": {
                "6861111111": "FAILED",
                "6862222222": None,
            },
        },
    )

    kept, _metadata = audience._filter_by_iventas_current_status(
        candidates=rows,
        selected_statuses=("NO_DATA",),
        session=object(),
    )

    assert [row.phone_mx10 for row in kept] == ["6862222222"]


def test_current_iventas_status_filter_rejects_unknown_status():
    try:
        audience._normalize_iventas_current_statuses(["READ"])
    except audience.MarketingCampaignV2AudienceValidationError as exc:
        assert "READ" in str(exc)
    else:
        raise AssertionError("Expected unsupported iVentas status to be rejected")
