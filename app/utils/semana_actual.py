#app\utils\semana_actual.py

from datetime import date

def get_semana_actual(fecha=None):
    """
    Devuelve 1 o 2 según la semana par o non desde una fecha base (lunes 2024-01-01)
    """
    base = date(2024, 1, 8)  # Cambia a tu semana base real
    if not fecha:
        fecha = date.today()
    semanas_transcurridas = ((fecha - base).days // 7)
    return 1 if semanas_transcurridas % 2 == 0 else 2
