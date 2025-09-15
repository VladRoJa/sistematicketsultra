# app/utils/notify_targets.py

from typing import Iterable, List, Optional, Set
from sqlalchemy import func
from app.models.user_model import UserORM
from app.models.ticket_model import Ticket
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

# -----------------------
# Público
# -----------------------

def build_subject(ticket: Ticket, action_bits: str) -> str:
    base = f"[Ticket #{ticket.id}]"
    dept = (ticket.departamento.nombre if ticket and ticket.departamento else "") or ""
    suc  = ticket.sucursal_id_destino if (ticket and ticket.sucursal_id_destino is not None) else ticket.sucursal_id
    extra = []
    if dept: extra.append(dept)
    if suc is not None: extra.append(f"Sucursal {suc}")
    if action_bits: extra.append(action_bits)
    return f"{base} " + " – ".join(extra)

def pick_recipients(ticket: Ticket, actor_username: str, event: str = "update") -> List[str]:
    """
    Reglas:
      - Creación por corporativo (suc 100/1000 o ADMINISTRADOR): notifica a AMBAS partes.
      - En cualquier actualización: notifica a la OTRA parte respecto al actor.
      - Siempre incluir al actor (si tiene email).
      - Siempre incluir al asignado (si existe y no es el actor).
      - Fallback a NOTIFY_DEFAULT_EMAILS si quedara vacío.
    """
    if not ticket:
        return _default_fallbacks()

    actor = _get_actor(actor_username)
    actor_email = _emails_only([actor]) if actor else []

    dept_side = _dept_admin_emails(ticket)
    branch_side = _branch_manager_emails(ticket)

    recipients: List[str] = []

    # --- Evento de creación ---
    if _norm(event) == "create":
        if actor and _is_corporativo(actor):
            # corporativo crea → ambas partes
            recipients = dept_side + branch_side
        else:
            # No corporativo crea: si actor es gerente de la sucursal → avisa al depto; si no, por defecto depto.
            # (puedes ajustar esta rama si quieres otras reglas)
            recipients = dept_side

    # --- Evento de actualización ---
    else:
        # identifica el "lado" del actor
        actor_is_dept_side = False
        if actor:
            # Es corporativo o su rol coincide con el nombre del departamento del ticket
            dept_name = (ticket.departamento.nombre if ticket and ticket.departamento else "") or ""
            actor_is_dept_side = _is_corporativo(actor) or (_norm(actor.rol) == _norm(dept_name))

        # se notifica a la otra parte
        recipients = (branch_side if actor_is_dept_side else dept_side)

    # --- Siempre CC: actor + asignado ---
    recipients = recipients + actor_email + _assignee_email(ticket, actor_username)

    # --- Fallback si queda vacío ---
    if not recipients:
        recipients = _default_fallbacks()

    # Dedupe final
    dedup, seen = [], set()
    for e in recipients:
        k = e.lower()
        if k not in seen:
            dedup.append(e)
            seen.add(k)
    return dedup
