"""Normalización estricta de respuestas Meta Ads Insights.

Este módulo no hace HTTP ni escribe en base de datos. Recibe el
raw exacto ya capturado, valida el contrato y construye filas
estructuradas deterministas sin reinterpretar ``actions``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any


class MarketingMetaParseError(ValueError):
    """La respuesta Meta no cumple el contrato esperado."""


@dataclass(frozen=True)
class MarketingMetaRawPageResponse:
    http_status: int
    request_cursor: str | None
    raw_payload: str


@dataclass(frozen=True)
class MarketingMetaAdInsight:
    account_id: str
    account_name: str | None
    campaign_id: str
    campaign_name: str | None
    adset_id: str
    adset_name: str | None
    ad_id: str
    ad_name: str | None
    date_start: date
    date_stop: date
    spend: Decimal
    reach: int
    impressions: int
    clicks: int
    actions: tuple[dict[str, Any], ...]
    row_hash: str


@dataclass(frozen=True)
class MarketingMetaPage:
    request_cursor: str | None
    next_cursor: str | None
    has_more: bool
    http_status: int
    raw_payload: str
    insights: tuple[MarketingMetaAdInsight, ...]


def normalize_meta_account_id(value: Any) -> str:
    account_id = str(value or "").strip()
    if account_id.startswith("act_"):
        account_id = account_id[4:]

    if not account_id or not account_id.isdigit():
        raise MarketingMetaParseError(
            "account_id Meta debe ser numérico."
        )

    if len(account_id) > 64:
        raise MarketingMetaParseError(
            "account_id Meta excede 64 caracteres."
        )

    return account_id


def _required_id(row: dict[str, Any], field_name: str) -> str:
    value = str(row.get(field_name) or "").strip()
    if not value:
        raise MarketingMetaParseError(
            f"{field_name} es obligatorio en insights Meta."
        )
    if len(value) > 64:
        raise MarketingMetaParseError(
            f"{field_name} excede 64 caracteres."
        )
    return value


def _optional_name(row: dict[str, Any], field_name: str) -> str | None:
    value = str(row.get(field_name) or "").strip()
    return value or None


def _parse_date(row: dict[str, Any], field_name: str) -> date:
    raw_value = str(row.get(field_name) or "").strip()
    try:
        return date.fromisoformat(raw_value)
    except ValueError as exc:
        raise MarketingMetaParseError(
            f"{field_name} debe usar formato YYYY-MM-DD."
        ) from exc


def _parse_decimal(row: dict[str, Any], field_name: str) -> Decimal:
    if field_name not in row or row.get(field_name) in (None, ""):
        raise MarketingMetaParseError(
            f"{field_name} es obligatorio en insights Meta."
        )
    try:
        value = Decimal(str(row.get(field_name)))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise MarketingMetaParseError(
            f"{field_name} debe ser numérico."
        ) from exc

    if not value.is_finite() or value < 0:
        raise MarketingMetaParseError(
            f"{field_name} debe ser finito y no negativo."
        )

    return value


def _parse_integer(row: dict[str, Any], field_name: str) -> int:
    value = _parse_decimal(row, field_name)
    if value != value.to_integral_value():
        raise MarketingMetaParseError(
            f"{field_name} debe ser entero."
        )
    return int(value)


def _parse_actions(row: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    raw_actions = row.get("actions", [])
    if raw_actions is None:
        return ()
    if not isinstance(raw_actions, list):
        raise MarketingMetaParseError(
            "actions debe ser una lista."
        )

    actions: list[dict[str, Any]] = []
    for item in raw_actions:
        if not isinstance(item, dict):
            raise MarketingMetaParseError(
                "Cada elemento de actions debe ser un objeto."
            )
        actions.append(dict(item))

    return tuple(actions)


def _build_row_hash(values: dict[str, Any]) -> str:
    canonical = json.dumps(
        values,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def _normalize_insight(row: dict[str, Any]) -> MarketingMetaAdInsight:
    account_id = normalize_meta_account_id(
        row.get("account_id")
    )
    campaign_id = _required_id(row, "campaign_id")
    adset_id = _required_id(row, "adset_id")
    ad_id = _required_id(row, "ad_id")
    date_start = _parse_date(row, "date_start")
    date_stop = _parse_date(row, "date_stop")
    if date_start > date_stop:
        raise MarketingMetaParseError(
            "date_start no puede ser posterior a date_stop."
        )

    account_name = _optional_name(row, "account_name")
    campaign_name = _optional_name(row, "campaign_name")
    adset_name = _optional_name(row, "adset_name")
    ad_name = _optional_name(row, "ad_name")
    spend = _parse_decimal(row, "spend")
    reach = _parse_integer(row, "reach")
    impressions = _parse_integer(row, "impressions")
    clicks = _parse_integer(row, "clicks")
    actions = _parse_actions(row)

    hash_values = {
        "account_id": account_id,
        "account_name": account_name,
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "adset_id": adset_id,
        "adset_name": adset_name,
        "ad_id": ad_id,
        "ad_name": ad_name,
        "date_start": date_start.isoformat(),
        "date_stop": date_stop.isoformat(),
        "spend": str(spend),
        "reach": reach,
        "impressions": impressions,
        "clicks": clicks,
        "actions": list(actions),
    }

    return MarketingMetaAdInsight(
        account_id=account_id,
        account_name=account_name,
        campaign_id=campaign_id,
        campaign_name=campaign_name,
        adset_id=adset_id,
        adset_name=adset_name,
        ad_id=ad_id,
        ad_name=ad_name,
        date_start=date_start,
        date_stop=date_stop,
        spend=spend,
        reach=reach,
        impressions=impressions,
        clicks=clicks,
        actions=actions,
        row_hash=_build_row_hash(hash_values),
    )


def parse_meta_raw_page(
    raw_response: MarketingMetaRawPageResponse,
) -> MarketingMetaPage:
    if not isinstance(raw_response, MarketingMetaRawPageResponse):
        raise TypeError(
            "raw_response debe ser MarketingMetaRawPageResponse."
        )
    if raw_response.http_status != 200:
        raise MarketingMetaParseError(
            "Meta Ads Insights respondió un HTTP no exitoso."
        )

    try:
        payload = json.loads(raw_response.raw_payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise MarketingMetaParseError(
            "Meta Ads Insights respondió contenido no JSON."
        ) from exc

    if not isinstance(payload, dict):
        raise MarketingMetaParseError(
            "La raíz del payload Meta debe ser un objeto."
        )

    data = payload.get("data")
    if not isinstance(data, list):
        raise MarketingMetaParseError(
            "data debe ser una lista en el payload Meta."
        )

    insights: list[MarketingMetaAdInsight] = []
    for row in data:
        if not isinstance(row, dict):
            raise MarketingMetaParseError(
                "Cada insight Meta debe ser un objeto."
            )
        insights.append(_normalize_insight(row))

    next_cursor = None
    paging = payload.get("paging")
    if paging is not None:
        if not isinstance(paging, dict):
            raise MarketingMetaParseError(
                "paging debe ser un objeto."
            )
        cursors = paging.get("cursors")
        if cursors is not None and not isinstance(cursors, dict):
            raise MarketingMetaParseError(
                "paging.cursors debe ser un objeto."
            )
        if paging.get("next"):
            after = (
                cursors.get("after")
                if isinstance(cursors, dict)
                else None
            )
            if not after:
                raise MarketingMetaParseError(
                    "paging.next requiere paging.cursors.after."
                )
            next_cursor = str(after)

    return MarketingMetaPage(
        request_cursor=raw_response.request_cursor,
        next_cursor=next_cursor,
        has_more=next_cursor is not None,
        http_status=raw_response.http_status,
        raw_payload=raw_response.raw_payload,
        insights=tuple(insights),
    )
