# backend/app/utils/pm_legacy_transition.py

from __future__ import annotations

import os

from flask import current_app


FLAG_NAME = "TICKETS_PREVENTIVE_V1_ENABLED"


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value

    normalized = str(value or "").strip().lower()
    return normalized in {
        "1",
        "true",
        "yes",
        "si",
        "sí",
        "on",
        "enabled",
    }


def tickets_preventive_v1_enabled() -> bool:
    configured = current_app.config.get(FLAG_NAME)

    if configured is None:
        configured = os.getenv(FLAG_NAME, "false")

    return _as_bool(configured)


def legacy_operational_block():
    if not tickets_preventive_v1_enabled():
        return None

    return (
        {
            "error": "Legacy PM Read Only",
            "detail": (
                "La operación preventiva oficial ya vive en Tickets. "
                "El PM legacy permanece disponible únicamente como histórico."
            ),
            "replacement": {
                "programming": "/api/tickets/preventive-planning/batches",
                "my_program": "/api/tickets/preventive-planning/my-program",
                "dashboard": (
                    "/api/tickets/preventive-planning/dashboard/weekly"
                ),
            },
        },
        409,
    )


def transition_state_payload() -> dict:
    enabled = tickets_preventive_v1_enabled()

    return {
        "tickets_preventive_v1_enabled": enabled,
        "source_of_truth": "TICKETS" if enabled else "PM_LEGACY",
        "legacy": {
            "operational_writes_enabled": not enabled,
            "derived_schedule_enabled": not enabled,
            "history_readable": True,
            "legacy_validation_allowed": True,
        },
        "replacement": {
            "programming_route": "/main/programacion-preventiva",
            "technician_route": "/main/mi-programa",
            "dashboard_route": "/main/panel-mantenimiento",
            "legacy_history_route": "/pm/consulta-historial",
        },
    }
