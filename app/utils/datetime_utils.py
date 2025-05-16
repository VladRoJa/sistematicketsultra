# app/utils/datetime_utils.py

from datetime import datetime
import pytz

TZ = pytz.timezone("America/Tijuana")

def format_datetime(dt: datetime | None) -> str:
    """Devuelve la fecha en formato 'DD/MM/YYYY hh:mm AM/PM' en zona Tijuana"""
    if not dt:
        return "N/A"
    local_dt = dt.astimezone(TZ)
    return local_dt.strftime('%d/%m/%Y %I:%M %p')

def format_datetime_iso(dt: datetime | None) -> str:
    """Devuelve fecha como string ISO (para base de datos o depuración)"""
    if not dt:
        return "N/A"
    return dt.astimezone(TZ).isoformat()
