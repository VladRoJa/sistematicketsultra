from __future__ import annotations

from dataclasses import dataclass

import pytest
import requests

from app.integrations.iventas.broadcast_provider import IVentasBroadcastProvider
from app.services.marketing_campaign_v2_provider import (
    CampaignProviderAmbiguousError,
    CampaignProviderConfigurationError,
    CampaignProviderDeterministicError,
    CampaignProviderDispatchBatch,
    CampaignProviderLead,
)


@dataclass
class _Response:
    status_code: int
    payload: object = None
    json_error: bool = False

    def json(self):
        if self.json_error:
            raise ValueError("bad json")
        return self.payload


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError("unexpected extra POST")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _batch():
    return CampaignProviderDispatchBatch(
        provider="IVENTAS",
        campaign_name="QA M2 · TEC_MXL",
        provider_channel_id="6a21ca7755736500088a5652",
        template_name="reactivacion_v1",
        leads=(
            CampaignProviderLead(
                phone="526861000001",
                variables=("ANA", "2026-10-31"),
            ),
            CampaignProviderLead(
                phone="526861000002",
                variables=("JUAN", "2026-10-31"),
            ),
        ),
    )


def _provider(responses):
    session = _Session(responses)
    provider = IVentasBroadcastProvider(
        api_key="ivk_live_test_secret",
        base_url="https://provider.test",
        session=session,
    )
    return provider, session


def test_create_campaign_posts_exact_immediate_payload_once():
    provider, session = _provider([
        _Response(200, {"campaign": "provider-123"}),
    ])

    result = provider.create_campaign(_batch())

    assert result.provider_campaign_id == "provider-123"
    assert result.deduplicated is False
    assert len(session.calls) == 1
    url, kwargs = session.calls[0]
    assert url == "https://provider.test/v2/broadcast"
    assert kwargs["json"] == {
        "templateName": "reactivacion_v1",
        "leads": [
            {
                "phone": "526861000001",
                "vars": ["ANA", "2026-10-31"],
            },
            {
                "phone": "526861000002",
                "vars": ["JUAN", "2026-10-31"],
            },
        ],
        "channelId": "6a21ca7755736500088a5652",
        "name": "QA M2 · TEC_MXL",
    }
    assert "sendAt" not in kwargs["json"]
    assert "token" not in kwargs["json"]
    assert kwargs["headers"]["Authorization"] == "Bearer ivk_live_test_secret"
    assert kwargs["timeout"] == (10.0, 30.0)


def test_success_deduplicated_requires_campaign_id():
    provider, _ = _provider([
        _Response(
            200,
            {"campaign": "provider-123", "deduplicated": True},
        ),
    ])

    result = provider.create_campaign(_batch())

    assert result.provider_campaign_id == "provider-123"
    assert result.deduplicated is True
    assert result.response_metadata == {
        "campaign": "provider-123",
        "deduplicated": True,
    }


@pytest.mark.parametrize(
    ("status", "payload", "expected_code"),
    [
        (400, {"error": "INVALID_CHANNEL_TOKEN", "supportRef": "ref-1"}, "INVALID_CHANNEL_TOKEN"),
        (400, {"error": "MISSING_CHANNEL", "supportRef": "ref-2"}, "MISSING_CHANNEL"),
        (400, {"error": "TEMPLATE_NOT_FOUND", "supportRef": "ref-3"}, "TEMPLATE_NOT_FOUND"),
        (403, {"error": "FORBIDDEN"}, "FORBIDDEN"),
    ],
)
def test_known_4xx_are_deterministic_without_retry(status, payload, expected_code):
    provider, session = _provider([
        _Response(status, payload),
        _Response(200, {"campaign": "must-not-run"}),
    ])

    with pytest.raises(CampaignProviderDeterministicError) as captured:
        provider.create_campaign(_batch())

    assert captured.value.code == expected_code
    assert len(session.calls) == 1


@pytest.mark.parametrize(
    ("response", "expected_code"),
    [
        (
            _Response(
                409,
                {
                    "error": "DUPLICATE_BROADCAST_IN_PROGRESS",
                    "supportRef": "ref-409",
                },
            ),
            "DUPLICATE_BROADCAST_IN_PROGRESS",
        ),
        (
            _Response(
                500,
                {
                    "userMessage": "ERROR_SENDING_TEMPLATE_WITH_VARIABLES",
                    "supportRef": "ref-500",
                },
            ),
            "ERROR_SENDING_TEMPLATE_WITH_VARIABLES",
        ),
        (
            _Response(200, json_error=True),
            "INVALID_SUCCESS_JSON",
        ),
        (
            _Response(200, {"deduplicated": False}),
            "MISSING_CAMPAIGN_ID",
        ),
    ],
)
def test_ambiguous_results_never_retry(response, expected_code):
    provider, session = _provider([
        response,
        _Response(200, {"campaign": "must-not-run"}),
    ])

    with pytest.raises(CampaignProviderAmbiguousError) as captured:
        provider.create_campaign(_batch())

    assert captured.value.code == expected_code
    assert len(session.calls) == 1


def test_transport_timeout_is_ambiguous_and_not_retried():
    provider, session = _provider([
        requests.Timeout("timeout"),
        _Response(200, {"campaign": "must-not-run"}),
    ])

    with pytest.raises(CampaignProviderAmbiguousError) as captured:
        provider.create_campaign(_batch())

    assert captured.value.code == "TRANSPORT_TIMEOUT"
    assert len(session.calls) == 1


def test_support_ref_is_sanitized():
    provider, _ = _provider([
        _Response(
            400,
            {
                "error": "TEMPLATE_NOT_FOUND",
                "supportRef": "ivk_live_test_secret-sensitive",
            },
        ),
    ])

    with pytest.raises(CampaignProviderDeterministicError) as captured:
        provider.create_campaign(_batch())

    assert captured.value.support_ref == "<redacted>-sensitive"


def test_legacy_static_token_is_rejected():
    with pytest.raises(
        CampaignProviderConfigurationError,
        match="integration key",
    ):
        IVentasBroadcastProvider(api_key="legacy-static-token")
