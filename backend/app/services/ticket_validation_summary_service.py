#   backend\app\services\ticket_validation_summary_service.py


from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from app.models.ticket_model import Ticket
from app.utils.ticket_filters import filtrar_tickets_por_usuario


TicketValidationSeverity = Literal["none", "normal", "warning", "critical"]

TICKET_STATUS_POR_VALIDAR = "por_validar"
WARNING_HOURS = 48
CRITICAL_HOURS = 72


@dataclass(frozen=True)
class TicketValidationSummary:
    total_por_validar: int
    mayores_48h: int
    mayores_72h: int
    severity: TicketValidationSeverity

    def to_dict(self) -> dict:
        return {
            "total_por_validar": self.total_por_validar,
            "mayores_48h": self.mayores_48h,
            "mayores_72h": self.mayores_72h,
            "severity": self.severity,
        }


def get_ticket_validation_summary_for_user(
    user,
    *,
    now_utc: datetime | None = None,
) -> TicketValidationSummary:
    """
    Devuelve el resumen operativo de tickets en estado por_validar
    visibles para el usuario recibido.

    Reglas:
    - Solo aplica para usuarios que pueden validar cierres.
    - Reutiliza filtrar_tickets_por_usuario(user) para no duplicar permisos.
    - Usa Ticket.fecha_finalizado como fecha de entrada a por_validar.
    - 48h+ => warning.
    - 72h+ => critical.
    """
    if not _can_receive_ticket_validation_alert(user):
        return build_ticket_validation_summary(
            total_por_validar=0,
            mayores_48h=0,
            mayores_72h=0,
        )

    now = _ensure_utc(now_utc or datetime.now(timezone.utc))

    warning_cutoff = now - timedelta(hours=WARNING_HOURS)
    critical_cutoff = now - timedelta(hours=CRITICAL_HOURS)

    base_query = filtrar_tickets_por_usuario(user).filter(
        Ticket.estado == TICKET_STATUS_POR_VALIDAR
    )

    total_por_validar = base_query.order_by(None).count()

    mayores_48h = (
        base_query.filter(
            Ticket.fecha_finalizado.isnot(None),
            Ticket.fecha_finalizado <= warning_cutoff,
        )
        .order_by(None)
        .count()
    )

    mayores_72h = (
        base_query.filter(
            Ticket.fecha_finalizado.isnot(None),
            Ticket.fecha_finalizado <= critical_cutoff,
        )
        .order_by(None)
        .count()
    )

    return build_ticket_validation_summary(
        total_por_validar=total_por_validar,
        mayores_48h=mayores_48h,
        mayores_72h=mayores_72h,
    )


def build_ticket_validation_summary(
    *,
    total_por_validar: int,
    mayores_48h: int = 0,
    mayores_72h: int = 0,
) -> TicketValidationSummary:
    """
    Construye el resumen operativo de tickets en estado Por validar.

    Esta función no consulta base de datos. Solo normaliza conteos y calcula severidad.
    """
    safe_total = max(int(total_por_validar or 0), 0)
    safe_48h = max(int(mayores_48h or 0), 0)
    safe_72h = max(int(mayores_72h or 0), 0)

    return TicketValidationSummary(
        total_por_validar=safe_total,
        mayores_48h=safe_48h,
        mayores_72h=safe_72h,
        severity=resolve_ticket_validation_severity(
            total_por_validar=safe_total,
            mayores_48h=safe_48h,
            mayores_72h=safe_72h,
        ),
    )


def resolve_ticket_validation_severity(
    *,
    total_por_validar: int,
    mayores_48h: int,
    mayores_72h: int,
) -> TicketValidationSeverity:
    if total_por_validar <= 0:
        return "none"

    if mayores_72h > 0:
        return "critical"

    if mayores_48h > 0:
        return "warning"

    return "normal"


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)

def _can_receive_ticket_validation_alert(user) -> bool:
    rol = (getattr(user, "rol", "") or "").strip().upper()

    return rol in {
        "ADMIN",
        "ADMINISTRADOR",
        "SUPER_ADMIN",
        "GERENTE",
    }