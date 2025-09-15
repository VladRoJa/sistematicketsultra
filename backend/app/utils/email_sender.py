# app/utils/email_sender.py
import os, smtplib
from email.message import EmailMessage

SMTP_DEBUG = os.getenv("SMTP_DEBUG", "0") == "1"

def _get_env():
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    pw   = os.getenv("SMTP_PASS")
    from_email = os.getenv("EMAIL_FROM", user)
    display_from = os.getenv("EMAIL_FROM_NAME", "Ultra Tickets")
    return host, port, user, pw, from_email, display_from

def send_email_html(to_list, subject, html):
    host, port, user, pw, from_email, display_from = _get_env()

    # 🔎 Validación explícita: si falta algo, grita fuerte
    missing = []
    if not host: missing.append("SMTP_HOST")
    if not user: missing.append("SMTP_USER")
    if not pw:   missing.append("SMTP_PASS")
    if missing:
        raise RuntimeError(
            f"Config SMTP incompleta. Faltan: {', '.join(missing)}. "
            "Verifica que el contenedor cargue .env.docker (env_file) y reinicia."
        )

    msg = EmailMessage()
    msg["Subject"]  = subject
    msg["From"]     = f"{display_from} <{from_email}>"
    msg["To"]       = ", ".join(to_list)
    msg["Reply-To"] = os.getenv("EMAIL_REPLY_TO", from_email)
    msg.set_content("Este correo requiere un cliente compatible con HTML.")
    msg.add_alternative(html, subtype="html")

    # Conexión SMTP con timeout
    with smtplib.SMTP(host, port, timeout=20) as s:
        if SMTP_DEBUG:
            s.set_debuglevel(1)  # muestra el diálogo SMTP en stdout del contenedor
            print(f"[SMTP DEBUG] host={host} port={port} user={user}")  # sin imprimir el password
        s.ehlo()
        s.starttls()
        s.ehlo()
        s.login(user, pw)
        s.send_message(msg)
