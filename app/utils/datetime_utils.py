# app/utils/datetime_utils.py

from datetime import datetime
import pytz

TZ = pytz.timezone('America/Tijuana')

def format_datetime_short(fecha):
    if not fecha:
        return "N/A"
    local = fecha.astimezone(TZ)
    return local.strftime('%d/%m/%Y %I:%M %p')

def format_datetime_long(fecha):
    if not fecha:
        return "N/A"
    local = fecha.astimezone(TZ)
    return local.strftime('%d/%m/%Y %I:%M %p')
