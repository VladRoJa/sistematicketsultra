# app/utils/email_sender.py

import os, smtplib
from email.message import EmailMessage

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USER)

def send_email_html(to_list, subject, html):
    
    DISPLAY_FROM = os.getenv("EMAIL_FROM_NAME", "Ultra Tickets")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{DISPLAY_FROM} <{EMAIL_FROM}>"
    msg["To"] = ", ".join(to_list)
    msg["Reply-To"] = os.getenv("EMAIL_REPLY_TO", EMAIL_FROM)
    msg.set_content("Este correo requiere un cliente compatible con HTML.")
    msg.add_alternative(html, subtype="html")

    # timeout para no colgar el request si el SMTP no responde
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
        s.ehlo()
        s.starttls()
        s.ehlo()
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)
