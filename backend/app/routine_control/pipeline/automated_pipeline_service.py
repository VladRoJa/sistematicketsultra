from __future__ import annotations

import time
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Protocol

from app.routine_control.pipeline.manual_pipeline_service import (
    run_manual_routine_control_pipeline,
)
from app.routine_control.providers.gasca import (
    GascaNewMembersExtractor,
    GascaProviderConfig,
)
from app.routine_control.providers.runtime import (
    ProviderArtifact,
    ProviderConfigurationError,
    ProviderExtractionResult,
    ProviderRuntimeConfig,
    provider_lock,
)
from app.routine_control.providers.trainingym import TrainingymProviderConfig


class ProviderExtractor(Protocol):
    def extract(
        self,
        *,
        date_from: date,
        date_to: date,
        observed_at_utc: datetime,
        headless: bool | None,
    ) -> ProviderExtractionResult: ...


class _UnavailableTrainingymExtractor:
    def extract(
        self,
        *,
        date_from: date,
        date_to: date,
        observed_at_utc: datetime,
        headless: bool | None,
    ) -> ProviderExtractionResult:
        del date_from, date_to, observed_at_utc, headless
        return ProviderExtractionResult(
            succeeded=False,
            artifact=None,
            attempts=0,
            elapsed_seconds=0.0,
            error_code="TRAININGYM_WORKOUT_CONTRACT_UNVERIFIED",
            error_message=(
                "Faltan URL Workout, filtros, centro y exportación comprobados."
            ),
        )


def _artifact_summary(artifact: ProviderArtifact | None) -> dict[str, object] | None:
    if artifact is None:
        return None
    return {
        "business_date_from": artifact.business_date_from.isoformat(),
        "business_date_to": artifact.business_date_to.isoformat(),
        "dataset_key": artifact.dataset_key,
        "provider_key": artifact.provider_key,
        "sha256": artifact.sha256[:12],
        "size_bytes": artifact.size_bytes,
    }


def _extraction_summary(result: ProviderExtractionResult | None) -> dict[str, object] | None:
    if result is None:
        return None
    return {
        "artifact": _artifact_summary(result.artifact),
        "attempts": result.attempts,
        "diagnostic_artifact": (
            Path(result.diagnostic_artifact).name
            if result.diagnostic_artifact
            else None
        ),
        "elapsed_seconds": result.elapsed_seconds,
        "error_code": result.error_code,
        "succeeded": result.succeeded,
    }


@dataclass(frozen=True, slots=True)
class AutomatedRoutineControlPipelineResult:
    status: str
    succeeded: bool
    gasca: ProviderExtractionResult | None
    trainingym: ProviderExtractionResult | None
    manual_pipeline: Any | None
    elapsed_seconds: float
    error_code: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, object]:
        manual = None
        if self.manual_pipeline is not None:
            manual = (
                self.manual_pipeline.to_dict()
                if hasattr(self.manual_pipeline, "to_dict")
                else {"succeeded": bool(getattr(self.manual_pipeline, "succeeded", False))}
            )
        return {
            "elapsed_seconds": self.elapsed_seconds,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "gasca": _extraction_summary(self.gasca),
            "manual_pipeline": manual,
            "status": self.status,
            "succeeded": self.succeeded,
            "trainingym": _extraction_summary(self.trainingym),
        }


def _result(
    *,
    started: float,
    status: str,
    gasca: ProviderExtractionResult | None = None,
    trainingym: ProviderExtractionResult | None = None,
    manual_pipeline: Any | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> AutomatedRoutineControlPipelineResult:
    return AutomatedRoutineControlPipelineResult(
        status=status,
        succeeded=status == "SUCCESS",
        gasca=gasca,
        trainingym=trainingym,
        manual_pipeline=manual_pipeline,
        elapsed_seconds=round(time.monotonic() - started, 3),
        error_code=error_code,
        error_message=error_message,
    )


def run_automated_routine_control_pipeline(
    *,
    date_from: date,
    date_to: date,
    observed_at_utc: datetime,
    headless: bool | None = None,
    gasca_extractor: ProviderExtractor | None = None,
    trainingym_extractor: ProviderExtractor | None = None,
    manual_pipeline: Callable[..., Any] = run_manual_routine_control_pipeline,
    lock_factory: Callable[..., AbstractContextManager[None]] = provider_lock,
) -> AutomatedRoutineControlPipelineResult:
    started = time.monotonic()
    if date_from > date_to:
        return _result(
            started=started,
            status="FAILED",
            error_code="INVALID_DATE_RANGE",
            error_message="date_from no puede ser posterior a date_to.",
        )
    if observed_at_utc.tzinfo is None or observed_at_utc.utcoffset() is None:
        return _result(
            started=started,
            status="FAILED",
            error_code="INVALID_OBSERVED_AT",
            error_message="observed_at_utc debe incluir timezone.",
        )
    try:
        # Se valida todo antes del lock y antes de que cualquier extractor abra Playwright.
        GascaProviderConfig.from_env()
        TrainingymProviderConfig.from_env()
        runtime_config = ProviderRuntimeConfig.from_env(headless=headless)
    except ProviderConfigurationError as exc:
        return _result(
            started=started,
            status="FAILED",
            error_code="CONFIG_INVALID",
            error_message=str(exc),
        )

    gasca_provider = gasca_extractor or GascaNewMembersExtractor()
    trainingym_provider = trainingym_extractor or _UnavailableTrainingymExtractor()
    try:
        with lock_factory(
            runtime_config.artifact_root,
            provider_key="routine_control",
            dataset_key="automated_pipeline",
        ):
            gasca_result = gasca_provider.extract(
                date_from=date_from,
                date_to=date_to,
                observed_at_utc=observed_at_utc,
                headless=headless,
            )
            if not gasca_result.succeeded or gasca_result.artifact is None:
                return _result(
                    started=started,
                    status="FAILED",
                    gasca=gasca_result,
                    error_code=gasca_result.error_code or "GASCA_EXTRACTION_FAILED",
                    error_message="La extracción Gasca no produjo un artifact válido.",
                )

            trainingym_result = trainingym_provider.extract(
                date_from=date_from,
                date_to=date_to,
                observed_at_utc=observed_at_utc,
                headless=headless,
            )
            if (
                not trainingym_result.succeeded
                or trainingym_result.artifact is None
            ):
                return _result(
                    started=started,
                    status="PARTIAL",
                    gasca=gasca_result,
                    trainingym=trainingym_result,
                    error_code=(
                        trainingym_result.error_code
                        or "TRAININGYM_EXTRACTION_FAILED"
                    ),
                    error_message=(
                        "Gasca se conservó, pero Trainingym no produjo un artifact válido."
                    ),
                )

            manual_result = manual_pipeline(
                gasca_xlsx=gasca_result.artifact.local_path,
                trainingym_xlsx=trainingym_result.artifact.local_path,
                observed_at_utc=observed_at_utc,
                requested_by="automated_provider_cli",
            )
            if not bool(getattr(manual_result, "succeeded", False)):
                return _result(
                    started=started,
                    status="FAILED",
                    gasca=gasca_result,
                    trainingym=trainingym_result,
                    manual_pipeline=manual_result,
                    error_code="MANUAL_PIPELINE_FAILED",
                    error_message="El pipeline manual reportó un fallo.",
                )
            return _result(
                started=started,
                status="SUCCESS",
                gasca=gasca_result,
                trainingym=trainingym_result,
                manual_pipeline=manual_result,
            )
    except Exception as exc:
        return _result(
            started=started,
            status="FAILED",
            error_code="AUTOMATED_PIPELINE_FAILED",
            error_message=type(exc).__name__,
        )

