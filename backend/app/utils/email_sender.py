# app/utils/email_sender.py

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage


@dataclass(frozen=True, slots=True)
class EmailAttachment:
    filename: str
    content: bytes
    content_type: str


class EmailDeliveryUncertain(RuntimeError):
    """The connection failed during submission, without a definitive SMTP reply."""


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


def send_email_html(to_list, subject, html, *, attachments=(), message_id=None):
    host, port, user, pw, from_email, display_from, reply_to, security = _get_env()
    _validar_config(host, user, pw, from_email, security)

    if not to_list:
        raise RuntimeError("send_email_html llamado sin destinatarios.")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{display_from} <{from_email}>"
    msg["To"] = ", ".join(to_list)
    msg["Reply-To"] = reply_to
    if message_id:
        msg["Message-ID"] = message_id

    msg.set_content("Este correo requiere un cliente compatible con HTML.")
    msg.add_alternative(html, subtype="html")
    for attachment in attachments:
        maintype, subtype = attachment.content_type.split("/", 1)
        msg.add_attachment(
            attachment.content, maintype=maintype, subtype=subtype,
            filename=attachment.filename,
        )

    smtp_debug = _is_debug_enabled() and not attachments

    if smtp_debug:
        print(
            "[SMTP DEBUG] "
            f"host={host} port={port} user={user} "
            f"from={from_email} security={security} to={to_list}"
        )

    transport = smtplib.SMTP_SSL if security == "ssl" else smtplib.SMTP
    accepted = False
    submission_uncertain = False
    try:
        with transport(host, port, timeout=20) as s:
            if smtp_debug:
                s.set_debuglevel(1)
            s.ehlo()
            if security == "starttls":
                s.starttls()
                s.ehlo()
            s.login(user, pw)
            try:
                s.send_message(msg)
            except (smtplib.SMTPRecipientsRefused, smtplib.SMTPResponseException):
                raise
            except OSError as exc:
                if not attachments:
                    raise
                submission_uncertain = True
                raise EmailDeliveryUncertain("El servidor SMTP no confirmó la entrega.") from exc
            accepted = True
    except OSError as exc:
        if submission_uncertain:
            raise EmailDeliveryUncertain("El servidor SMTP no confirmó la entrega.") from exc
        # A failed QUIT after the server accepted DATA cannot revoke that acceptance.
        if not accepted or not attachments:
            raise
