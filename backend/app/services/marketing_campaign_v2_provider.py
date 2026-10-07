"""Provider-neutral contracts for Campaign V2 controlled submit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class CampaignProviderError(RuntimeError):
    pass


class CampaignProviderConfigurationError(CampaignProviderError):
    pass


class CampaignProviderDeterministicError(CampaignProviderError):
    def __init__(
        self,
        *,
        code: str,
        http_status: int | None,
        support_ref: str | None,
    ) -> None:
        self.code = str(code or "PROVIDER_ERROR")
        self.http_status = http_status
        self.support_ref = support_ref
        super().__init__(self.code)


class CampaignProviderAmbiguousError(CampaignProviderError):
    def __init__(
        self,
        *,
        code: str,
        http_status: int | None,
        support_ref: str | None,
    ) -> None:
        self.code = str(code or "AMBIGUOUS_PROVIDER_RESULT")
        self.http_status = http_status
        self.support_ref = support_ref
        super().__init__(self.code)


@dataclass(frozen=True)
class CampaignProviderLead:
    phone: str
    variables: tuple[str, ...]
    url_variables: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "phone": self.phone,
            "vars": list(self.variables),
        }
        if self.url_variables:
            payload["urlVars"] = list(self.url_variables)
        return payload


@dataclass(frozen=True)
class CampaignProviderDispatchBatch:
    provider: str
    campaign_name: str
    provider_channel_id: str
    template_name: str
    leads: tuple[CampaignProviderLead, ...]


@dataclass(frozen=True)
class CampaignProviderCreateResult:
    provider_campaign_id: str
    deduplicated: bool
    http_status: int
    response_metadata: dict[str, Any]


class CampaignProvider(Protocol):
    def create_campaign(
        self,
        batch: CampaignProviderDispatchBatch,
    ) -> CampaignProviderCreateResult:
        ...
