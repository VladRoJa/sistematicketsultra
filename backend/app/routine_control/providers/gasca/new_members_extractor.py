from __future__ import annotations

import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from app.routine_control.providers.runtime import (
    ArtifactStore,
    BrowserPhase,
    BrowserRuntime,
    ProviderArtifact,
    ProviderBrowserError,
    ProviderConfigurationError,
    ProviderExtractionResult,
    ProviderRuntimeConfig,
    provider_lock,
)

from .config import GascaProviderConfig


GASCA_PROVIDER_KEY = "gasca"
GASCA_DATASET_KEY = "new_members"
GASCA_NEW_MEMBER_HEADERS = frozenset(
    {
        "IDSocio",
        "IDFolio",
        "Sucursal",
        "Nombre",
        "ApellidoPaterno",
        "ApellidoMaterno",
        "Email",
        "FechaPago",
        "FechaCreacion",
    }
)
GASCA_CONTRACT_ERROR = "GASCA_DETAILED_REPORT_CONTRACT_UNVERIFIED"
GASCA_CONTRACT_MESSAGE = (
    "Falta comprobar la ruta, los filtros y la exportación XLSX del reporte "
    "individual de socios nuevos."
)


DownloadOperation = Callable[
    [object, object, GascaProviderConfig, date, date, Path],
    str | None,
]


def login_with_verified_gasca_selectors(page, config: GascaProviderConfig) -> None:
    """Login reutilizado del runner Gasca existente; no navega al reporte."""
    page.goto(config.login_url)
    page.get_by_label("Usuario").fill(config.user)
    page.get_by_label("Contraseña").fill(config.password)
    page.get_by_role("button", name="INICIAR SESIÓN").click()


class GascaNewMembersExtractor:
    def __init__(
        self,
        *,
        download_operation: DownloadOperation | None = None,
        runtime_factory: Callable[[ProviderRuntimeConfig], BrowserRuntime] = BrowserRuntime,
    ) -> None:
        self._download_operation = download_operation
        self._runtime_factory = runtime_factory

    @staticmethod
    def _failed(
        *,
        started: float,
        error_code: str,
        error_message: str,
        attempts: int = 0,
    ) -> ProviderExtractionResult:
        return ProviderExtractionResult(
            succeeded=False,
            artifact=None,
            attempts=attempts,
            elapsed_seconds=round(time.monotonic() - started, 3),
            error_code=error_code,
            error_message=error_message,
        )

    def extract(
        self,
        *,
        date_from: date,
        date_to: date,
        observed_at_utc: datetime,
        headless: bool | None = None,
    ) -> ProviderExtractionResult:
        started = time.monotonic()
        if date_from > date_to:
            return self._failed(
                started=started,
                error_code="INVALID_DATE_RANGE",
                error_message="date_from no puede ser posterior a date_to.",
            )
        if (
            observed_at_utc.tzinfo is None
            or observed_at_utc.utcoffset() is None
        ):
            return self._failed(
                started=started,
                error_code="INVALID_OBSERVED_AT",
                error_message="observed_at_utc debe incluir timezone.",
            )
        try:
            provider_config = GascaProviderConfig.from_env()
            runtime_config = ProviderRuntimeConfig.from_env(headless=headless)
        except ProviderConfigurationError as exc:
            return self._failed(
                started=started,
                error_code="CONFIG_INVALID",
                error_message=str(exc),
            )

        # El repositorio no contiene todavía el contrato del reporte individual.
        # Se detiene antes de crear Playwright; una operación sólo se inyecta
        # cuando ha sido comprobada o durante pruebas locales.
        if self._download_operation is None:
            return self._failed(
                started=started,
                error_code=GASCA_CONTRACT_ERROR,
                error_message=GASCA_CONTRACT_MESSAGE,
            )

        store = ArtifactStore(runtime_config.artifact_root)
        run_dir = store.create_run_directory(
            provider_key=GASCA_PROVIDER_KEY,
            dataset_key=GASCA_DATASET_KEY,
        )
        partial, final = store.prepare_download(
            run_directory=run_dir,
            source_filename="gasca-new-members.xlsx",
        )
        artifact: ProviderArtifact | None = None

        def operation(page, tracker, _attempt):
            tracker.set(BrowserPhase.LOGIN)
            source_name = self._download_operation(
                page,
                tracker,
                provider_config,
                date_from,
                date_to,
                partial,
            )
            tracker.set(BrowserPhase.VALIDATION)
            return source_name or "gasca-new-members.xlsx"

        try:
            with provider_lock(
                runtime_config.artifact_root,
                provider_key=GASCA_PROVIDER_KEY,
                dataset_key=GASCA_DATASET_KEY,
            ):
                execution = self._runtime_factory(runtime_config).run(operation)
                artifact = store.finalize_download(
                    partial_path=partial,
                    final_path=final,
                    provider_key=GASCA_PROVIDER_KEY,
                    dataset_key=GASCA_DATASET_KEY,
                    required_headers=GASCA_NEW_MEMBER_HEADERS,
                    extracted_at_utc=observed_at_utc.astimezone(timezone.utc),
                    business_date_from=date_from,
                    business_date_to=date_to,
                    source_filename=Path(str(execution.value)).name,
                    diagnostic_metadata={"report_contract": "injected_verified_operation"},
                )
            return ProviderExtractionResult(
                succeeded=True,
                artifact=artifact,
                attempts=execution.attempts,
                elapsed_seconds=execution.elapsed_seconds,
            )
        except ProviderBrowserError as exc:
            store.discard_incomplete(partial)
            return self._failed(
                started=started,
                error_code=f"GASCA_{exc.phase.value}_FAILED",
                error_message=str(exc),
                attempts=exc.attempts,
            )
        except Exception as exc:
            store.discard_incomplete(partial)
            return self._failed(
                started=started,
                error_code="GASCA_ARTIFACT_INVALID",
                error_message=type(exc).__name__,
            )

