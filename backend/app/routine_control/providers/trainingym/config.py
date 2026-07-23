from __future__ import annotations

import os
from dataclasses import dataclass

from app.routine_control.providers.runtime import ProviderConfigurationError


@dataclass(frozen=True, slots=True)
class TrainingymProviderConfig:
    login_url: str
    user: str
    password: str
    center_name: str | None

    @classmethod
    def from_env(
        cls,
        *,
        require_center: bool = False,
    ) -> "TrainingymProviderConfig":
        names = [
            "TRAININGYM_LOGIN_URL",
            "TRAININGYM_USER",
            "TRAININGYM_PASS",
        ]
        if require_center:
            names.append("TRAININGYM_CENTER_NAME")
        values = {name: (os.getenv(name) or "").strip() for name in names}
        missing = [name for name in names if not values[name]]
        if missing:
            raise ProviderConfigurationError(
                "Faltan variables de entorno: " + ", ".join(missing)
            )
        center_name = (os.getenv("TRAININGYM_CENTER_NAME") or "").strip() or None
        normalized_center = " ".join((center_name or "").split()).casefold()
        if "la viga" in normalized_center:
            raise ProviderConfigurationError(
                "TRAININGYM_CENTER_NAME refiere a una sucursal dada de baja."
            )
        return cls(
            login_url=values["TRAININGYM_LOGIN_URL"],
            user=values["TRAININGYM_USER"],
            password=values["TRAININGYM_PASS"],
            center_name=center_name,
        )
