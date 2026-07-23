from __future__ import annotations

import os
from dataclasses import dataclass

from app.routine_control.providers.runtime import ProviderConfigurationError


@dataclass(frozen=True, slots=True)
class GascaProviderConfig:
    login_url: str
    report_url: str
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
        return cls(
            login_url=values["DIRECCION_LOGIN_URL"],
            report_url=values["DIRECCION_REPORTE_URL"],
            user=values["DIRECCION_USER"],
            password=values["DIRECCION_PASS"],
        )

