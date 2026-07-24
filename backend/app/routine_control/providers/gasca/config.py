from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.routine_control.providers.runtime import ProviderConfigurationError


_DEFAULT_KPI_URL = "https://ultragimnasios.com/Modulo/Kpis/Index"


@dataclass(frozen=True, slots=True)
class GascaProviderConfig:
    login_url: str
    report_url: str
    kpi_url: str
    user: str
    password: str

    @classmethod
    def from_env(cls) -> "GascaProviderConfig":
        names = (
            "DIRECCION_LOGIN_URL",
            "DIRECCION_REPORTE_URL",
            "DIRECCION_USER",
            "DIRECCION_PASS",
        )
        values = {name: (os.getenv(name) or "").strip() for name in names}
        missing = [name for name in names if not values[name]]
        if missing:
            raise ProviderConfigurationError(
                "Faltan variables de entorno: " + ", ".join(missing)
            )
        kpi_url = (
            (os.getenv("KPI_DESEMPENO_URL") or "").strip()
            or _DEFAULT_KPI_URL
        )
        try:
            parsed_kpi_url = urlsplit(kpi_url)
        except ValueError as exc:
            raise ProviderConfigurationError(
                "KPI_DESEMPENO_URL no contiene una URL válida."
            ) from exc
        if parsed_kpi_url.scheme.casefold() != "https":
            raise ProviderConfigurationError(
                "KPI_DESEMPENO_URL debe usar HTTPS."
            )
        if not parsed_kpi_url.hostname:
            raise ProviderConfigurationError(
                "KPI_DESEMPENO_URL debe incluir hostname."
            )
        if not parsed_kpi_url.path or parsed_kpi_url.path == "/":
            raise ProviderConfigurationError(
                "KPI_DESEMPENO_URL debe incluir un path."
            )
        return cls(
            login_url=values["DIRECCION_LOGIN_URL"],
            report_url=values["DIRECCION_REPORTE_URL"],
            kpi_url=kpi_url,
            user=values["DIRECCION_USER"],
            password=values["DIRECCION_PASS"],
        )

