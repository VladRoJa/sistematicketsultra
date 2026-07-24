from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.routine_control.providers.runtime import ProviderConfigurationError


class TrainingymWorkoutConfigurationError(ProviderConfigurationError):
    pass


@dataclass(frozen=True, slots=True)
class TrainingymProviderConfig:
    login_url: str
    user: str
    password: str
    center_name: str | None
    workout_url: str | None

    @classmethod
    def from_env(
        cls,
        *,
        require_center: bool = False,
        require_workout: bool = False,
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
        workout_url = (os.getenv("TRAININGYM_WORKOUT_URL") or "").strip() or None
        if require_workout and not workout_url:
            raise TrainingymWorkoutConfigurationError(
                "Falta la variable de entorno: TRAININGYM_WORKOUT_URL"
            )
        if workout_url:
            login = urlsplit(values["TRAININGYM_LOGIN_URL"])
            workout = urlsplit(workout_url)
            if workout.scheme.casefold() != "https":
                raise TrainingymWorkoutConfigurationError(
                    "TRAININGYM_WORKOUT_URL debe usar HTTPS."
                )
            if not workout.hostname or (
                (login.hostname or "").casefold()
                != workout.hostname.casefold()
            ):
                raise TrainingymWorkoutConfigurationError(
                    "TRAININGYM_WORKOUT_URL debe usar el mismo hostname "
                    "que TRAININGYM_LOGIN_URL."
                )
            if not workout.path or workout.path == "/":
                raise TrainingymWorkoutConfigurationError(
                    "TRAININGYM_WORKOUT_URL debe incluir un path."
                )
            if workout.fragment:
                raise TrainingymWorkoutConfigurationError(
                    "TRAININGYM_WORKOUT_URL no admite fragmentos."
                )
        return cls(
            login_url=values["TRAININGYM_LOGIN_URL"],
            user=values["TRAININGYM_USER"],
            password=values["TRAININGYM_PASS"],
            center_name=center_name,
            workout_url=workout_url,
        )
