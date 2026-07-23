from __future__ import annotations

import os
from dataclasses import dataclass

from app.routine_control.providers.runtime import ProviderConfigurationError


@dataclass(frozen=True, slots=True)
class TrainingymProviderConfig:
    login_url: str
    user: str
    password: str

    @classmethod
    def from_env(cls) -> "TrainingymProviderConfig":
        names = (
            "TRAININGYM_LOGIN_URL",
            "TRAININGYM_USER",
            "TRAININGYM_PASS",
        )
        values = {name: (os.getenv(name) or "").strip() for name in names}
        missing = [name for name in names if not values[name]]
        if missing:
            raise ProviderConfigurationError(
                "Faltan variables de entorno: " + ", ".join(missing)
            )
        return cls(
            login_url=values["TRAININGYM_LOGIN_URL"],
            user=values["TRAININGYM_USER"],
            password=values["TRAININGYM_PASS"],
        )

