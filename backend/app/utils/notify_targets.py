# app/utils/notify_targets.py (nuevo)
import os
from app.models.user_model import UserORM

def _email_of(username: str) -> str | None:
    if not username: return None
    u = UserORM.query.filter_by(username=username).first()
    return (getattr(u, "email", None) or "").strip() or None

def _split_csv(var: str) -> list[str]:
    return [e.strip() for e in (os.getenv(var, "") or "").split(",") if e.strip()]

def pick_recipients(ticket, actor_username: str, event: str) -> list[str]:
    """
    event: 'create' | 'update'
    - Devuelve destinatarios únicos, sin el email del actor.
    """
    base = set(_split_csv("NOTIFY_DEFAULT_EMAILS"))

    creator_email  = _email_of(ticket.username)
    assignee_email = _email_of(getattr(ticket, "asignado_a", None))

    if event == "create":
        if assignee_email:
            base.add(assignee_email)
        else:
            fallback = os.getenv("NOTIFY_FALLBACK_ASSIGNEE_EMAIL")
            if fallback: base.add(fallback)
    else:  # update
        if actor_username and actor_username == getattr(ticket, "asignado_a", None):
            if creator_email: base.add(creator_email)
        elif actor_username and actor_username == ticket.username:
            if assignee_email: base.add(assignee_email)
        else:
            if creator_email: base.add(creator_email)
            if assignee_email: base.add(assignee_email)

    # no te envíes a ti mismo
    actor_email = _email_of(actor_username)
    if actor_email in base: base.remove(actor_email)

    # filtro básico
    return [e for e in base if "@" in e]

def build_subject(ticket, prefix: str) -> str:
    desc = (ticket.descripcion or "").strip()
    if len(desc) > 70: desc = desc[:67] + "…"
    return f"[Tickets] {prefix} #{ticket.id} – {desc}"
