# app/utils/notify_targets.py

from typing import Iterable, List, Optional, Set
from sqlalchemy import func
from app.models.user_model import UserORM
from app.models.ticket_model import Ticket
from app.models.sucursal_model import Sucursal
import os

# -----------------------
# Helpers
# -----------------------

def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()

def _is_corporativo(user: UserORM) -> bool:
    try:
        return (user.rol or "").upper() == "ADMINISTRADOR" or int(user.sucursal_id) in (100, 1000)
    except Exception:
        return False

def _emails_only(rows: Iterable[UserORM]) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    for u in rows or []:
        e = (u.email or "").strip()
        if e and "@" in e and e.lower() not in seen:
            out.append(e)
            seen.add(e.lower())
    return out

def _get_actor(username: str) -> Optional[UserORM]:
    if not username:
        return None
    return UserORM.query.filter(func.lower(UserORM.username) == username.lower()).first()

def _assignee_email(ticket: Ticket, actor_username: str) -> List[str]:
    if not ticket or not ticket.asignado_a:
        return []
    if ticket.asignado_a and ticket.asignado_a.lower() == (actor_username or "").lower():
        return []
    u = UserORM.query.filter(func.lower(UserORM.username) == ticket.asignado_a.lower()).first()
    return _emails_only([u]) if u else []

def _creator_email(ticket: Ticket) -> List[str]:
    """
    Correo del usuario que creó el ticket.
    El ticket guarda username, así que buscamos al usuario por username.
    """
    if not ticket or not ticket.username:
        return []

    u = UserORM.query.filter(
        func.lower(UserORM.username) == ticket.username.lower()
    ).first()

    return _emails_only([u]) if u else []


def _dedupe_emails(emails: Iterable[str]) -> List[str]:
    """
    Deduplicación centralizada para evitar mandar el mismo correo varias veces.
    """
    dedup: List[str] = []
    seen: Set[str] = set()

    for e in emails or []:
        email = (e or "").strip()
        key = email.lower()

        if email and "@" in email and key not in seen:
            dedup.append(email)
            seen.add(key)

    return dedup


def _all_involved_emails(ticket: Ticket, actor_username: str) -> List[str]:
    """
    Destinatarios para eventos de cierre/finalización.

    Incluye:
    - jefes del departamento
    - gerente(s) de la sucursal destino
    - creador del ticket
    - actor que ejecutó la acción
    - asignado, si existe
    """
    actor = _get_actor(actor_username)
    actor_email = _emails_only([actor]) if actor else []

    recipients = (
        _dept_admin_emails(ticket)
        + _branch_manager_emails(ticket)
        + _creator_email(ticket)
        + actor_email
        + _assignee_email(ticket, actor_username)
    )

    return _dedupe_emails(recipients)

def _dept_admin_emails(ticket: Ticket) -> List[str]:
    """
    Jefes de departamento corporativos (sucursal_id == 100) cuyo rol coincide con el nombre del departamento.
    Si tu esquema fuera distinto, ajusta este filtro.
    """
    dept_name = (ticket.departamento.nombre if ticket and ticket.departamento else "") or ""
    if not dept_name:
        return []
    q = (
        UserORM.query
        .filter(UserORM.sucursal_id == 100)
        .filter(func.lower(UserORM.rol) == func.lower(dept_name))
    )
    return _emails_only(q.all())

def _branch_manager_emails(ticket: Ticket) -> List[str]:
    """
    Gerente(s) de la sucursal destino (o la de creación si no hubiera destino).
    """
    suc_id = ticket.sucursal_id_destino if (ticket and ticket.sucursal_id_destino is not None) else ticket.sucursal_id
    if suc_id is None:
        return []
    q = (
        UserORM.query
        .filter(UserORM.sucursal_id == suc_id)
        .filter(func.lower(UserORM.rol) == "gerente")
    )
    return _emails_only(q.all())

def _default_fallbacks() -> List[str]:
    raw = os.getenv("NOTIFY_DEFAULT_EMAILS", "")
    # admite coma o espacio
    parts = [p.strip() for p in raw.replace(";", ",").replace(" ", ",").split(",") if p.strip()]
    # dedupe + sanity
    out, seen = [], set()
    for e in parts:
        if "@" in e and e.lower() not in seen:
            out.append(e)
            seen.add(e.lower())
    return out

def _sucursal_nombre_by_id(suc_id: Optional[int]) -> Optional[str]:
    """Devuelve el nombre legible de la sucursal o None si no existe."""
    try:
        if suc_id is None:
            return None
        s = Sucursal.query.filter_by(sucursal_id=int(suc_id)).first()
        return (s.sucursal or "").strip() if s else None
    except Exception:
        return None

# -----------------------
# Público
# -----------------------

def build_subject(ticket: Ticket, action_bits: str) -> str:
    base = f"[Ticket #{ticket.id}]"
    dept = (ticket.departamento.nombre if ticket and ticket.departamento else "") or ""
    suc_id = ticket.sucursal_id_destino if (ticket and ticket.sucursal_id_destino is not None) else ticket.sucursal_id

    extra = []
    if dept:
        extra.append(dept)

    # 👇 usa nombre de sucursal si existe; si no, cae a ID
    suc_nombre = _sucursal_nombre_by_id(suc_id)
    if suc_nombre:
        extra.append(f"Sucursal {suc_nombre}")
    elif suc_id is not None:
        extra.append(f"Sucursal {suc_id}")

    if action_bits:
        extra.append(action_bits)

    return f"{base} " + " – ".join(extra)

def pick_recipients(ticket: Ticket, actor_username: str, event: str = "update") -> List[str]:
    """
    Reglas:
      - Creación por corporativo: notifica a ambas partes.
      - Creación por sucursal: notifica al departamento.
      - Actualización normal: notifica a la otra parte respecto al actor.
      - Cierre/finalización: notifica a todos los involucrados.
      - Siempre incluir actor + asignado en updates normales.
      - Fallback a NOTIFY_DEFAULT_EMAILS si quedara vacío.
    """
    if not ticket:
        return _default_fallbacks()

    event_norm = _norm(event)

    closure_events = {
        "closure_requested",
        "closure_accepted",
        "closure_rejected",
        "finalized",
        "manager_finalized",
    }

    # Eventos de cierre/finalización: avisar a todos los involucrados.
    if event_norm in closure_events:
        recipients = _all_involved_emails(ticket, actor_username)

        if not recipients:
            recipients = _default_fallbacks()

        return _dedupe_emails(recipients)

    actor = _get_actor(actor_username)
    actor_email = _emails_only([actor]) if actor else []

    dept_side = _dept_admin_emails(ticket)
    branch_side = _branch_manager_emails(ticket)

    recipients: List[str] = []

    # --- Evento de creación ---
    if event_norm == "create":
        if actor and _is_corporativo(actor):
            # Corporativo crea → ambas partes
            recipients = dept_side + branch_side
        else:
            # Sucursal/gerente/usuario crea → avisa al departamento
            recipients = dept_side

    # --- Evento de actualización normal ---
    else:
        actor_is_dept_side = False

        if actor:
            dept_name = (ticket.departamento.nombre if ticket and ticket.departamento else "") or ""
            actor_is_dept_side = _is_corporativo(actor) or (_norm(actor.rol) == _norm(dept_name))

        # Se notifica a la otra parte
        recipients = branch_side if actor_is_dept_side else dept_side

    # Siempre CC: actor + asignado
    recipients = recipients + actor_email + _assignee_email(ticket, actor_username)

    if not recipients:
        recipients = _default_fallbacks()

    return _dedupe_emails(recipients)