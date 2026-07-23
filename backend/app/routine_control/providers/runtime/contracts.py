from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


DEFAULT_ARTIFACT_ROOT = Path("/app/runtime/routine-control/artifacts")
DEFAULT_TIMEOUT_MS = 60_000
DEFAULT_MAX_ATTEMPTS = 2


class ProviderConfigurationError(ValueError):
    """Configuración inválida sin incluir valores sensibles."""


def _optional_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ProviderConfigurationError(f"{name} debe ser booleano.")


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ProviderConfigurationError(f"{name} debe ser entero.") from exc
    if value < minimum or value > maximum:
        raise ProviderConfigurationError(
            f"{name} debe estar entre {minimum} y {maximum}."
        )
    return value


@dataclass(frozen=True, slots=True)
class ProviderRuntimeConfig:
    artifact_root: Path
    headless: bool
    timeout_ms: int
    max_attempts: int

    @classmethod
    def from_env(cls, *, headless: bool | None = None) -> "ProviderRuntimeConfig":
        configured_root = os.getenv("ROUTINE_CONTROL_ARTIFACT_DIR")
        artifact_root = Path(configured_root) if configured_root else DEFAULT_ARTIFACT_ROOT
        configured_headless = _optional_bool(
            "ROUTINE_CONTROL_PROVIDER_HEADLESS",
            True,
        )
        return cls(
            artifact_root=artifact_root,
            headless=configured_headless if headless is None else bool(headless),
            timeout_ms=_bounded_int(
                "ROUTINE_CONTROL_PROVIDER_TIMEOUT_MS",
                DEFAULT_TIMEOUT_MS,
                1_000,
                300_000,
            ),
            max_attempts=_bounded_int(
                "ROUTINE_CONTROL_PROVIDER_MAX_ATTEMPTS",
                DEFAULT_MAX_ATTEMPTS,
                1,
                5,
            ),
        )


def _immutable_metadata(values: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(values or {}))


@dataclass(frozen=True, slots=True)
class ProviderArtifact:
    provider_key: str
    dataset_key: str
    local_path: Path
    sha256: str
    size_bytes: int
    extracted_at_utc: datetime
    business_date_from: date
    business_date_to: date
    source_filename: str
    diagnostic_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "diagnostic_metadata",
            _immutable_metadata(self.diagnostic_metadata),
        )


@dataclass(frozen=True, slots=True)
class ProviderExtractionResult:
    succeeded: bool
    artifact: ProviderArtifact | None
    attempts: int
    elapsed_seconds: float
    error_code: str | None = None
    error_message: str | None = None
    diagnostic_artifact: str | None = None

