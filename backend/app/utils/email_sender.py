# app/utils/email_sender.py

import os
import smtplib
from email.message import EmailMessage


def _is_debug_enabled() -> bool:
    return os.getenv("SMTP_DEBUG", "0").strip() == "1"


def _get_env():
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    pw = os.getenv("SMTP_PASS")

    from_email = os.getenv("EMAIL_FROM", user)
    display_from = os.getenv("EMAIL_FROM_NAME", "Ultra Tickets")
    reply_to = os.getenv("EMAIL_REPLY_TO", from_email)

    # Valores permitidos:
    # - starttls: puerto 587 normalmente
    # - ssl: puerto 465 normalmente
    # - none: sin cifrado, solo si el proveedor lo pide explícitamente
    security = os.getenv("SMTP_SECURITY", "starttls").strip().lower()

    return host, port, user, pw, from_email, display_from, reply_to, security


def _validar_config(host, user, pw, from_email, security):
    missing = []

    if not host:
        missing.append("SMTP_HOST")
    if not user:
        missing.append("SMTP_USER")
    if not pw:
        missing.append("SMTP_PASS")
    if not from_email:
        missing.append("EMAIL_FROM")

    if missing:
        raise RuntimeError(
            f"Config SMTP incompleta. Faltan: {', '.join(missing)}. "
            "Verifica que el contenedor cargue .env.docker y reinicia backend."
        )

    if security not in {"starttls", "ssl", "none"}:
        raise RuntimeError(
            "SMTP_SECURITY inválido. Usa uno de estos valores: starttls, ssl, none."
        )


def send_email_html(to_list, subject, html):
    host, port, user, pw, from_email, display_from, reply_to, security = _get_env()
    _validar_config(host, user, pw, from_email, security)

    if not to_list:
        raise RuntimeError("send_email_html llamado sin destinatarios.")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{display_from} <{from_email}>"
    msg["To"] = ", ".join(to_list)
    msg["Reply-To"] = reply_to

    msg.set_content("Este correo requiere un cliente compatible con HTML.")
    msg.add_alternative(html, subtype="html")

    smtp_debug = _is_debug_enabled()

    if smtp_debug:
        print(
            "[SMTP DEBUG] "
            f"host={host} port={port} user={user} "
            f"from={from_email} security={security} to={to_list}"
        )

    # Puerto 465 / SSL directo
    if security == "ssl":
        with smtplib.SMTP_SSL(host, port, timeout=20) as s:
            if smtp_debug:
                s.set_debuglevel(1)

            s.ehlo()
            s.login(user, pw)
            s.send_message(msg)

        return

    # Puerto 587 / STARTTLS o sin cifrado
    with smtplib.SMTP(host, port, timeout=20) as s:
        if smtp_debug:
            s.set_debuglevel(1)

        s.ehlo()

        if security == "starttls":
            s.starttls()
            s.ehlo()

        s.login(user, pw)
        s.send_message(msg)
        