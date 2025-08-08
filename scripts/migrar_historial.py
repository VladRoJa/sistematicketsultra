# scripts/migrar_historial.py

from app import create_app
from backend.app.extensions import db
from backend.app.models.ticket_model import Ticket
from datetime import datetime, timezone, time
import pytz

app = create_app()

def migrar_historial_tickets_a_iso():
    tz_mx = pytz.timezone("America/Tijuana")
    tickets = Ticket.query.all()
    total_actualizados = 0

    for ticket in tickets:
        historial = ticket.historial_fechas

        if not historial:
            continue

        actualizado = False
        nuevo_historial = []

        for entrada in historial:
            nueva_entrada = entrada.copy()

            for campo in ['fecha', 'fechaCambio']:
                valor = entrada.get(campo)
                if valor and isinstance(valor, str) and '/' in valor and len(valor) == 8:
                    try:
                        # Convierte de dd/mm/yy a ISO 8601 con hora 07:00
                        fecha_local = datetime.strptime(valor, "%d/%m/%y")
                        fecha_local = tz_mx.localize(datetime.combine(fecha_local.date(), time(hour=7)))
                        fecha_utc = fecha_local.astimezone(timezone.utc)
                        nueva_entrada[campo] = fecha_utc.isoformat()
                        actualizado = True
                    except Exception as e:
                        print(f"❌ Error procesando fecha '{valor}' en ticket #{ticket.id}: {e}")

            nuevo_historial.append(nueva_entrada)

        if actualizado:
            ticket.historial_fechas = nuevo_historial
            total_actualizados += 1

    if total_actualizados > 0:
        db.session.commit()
        print(f"✅ Historial actualizado en {total_actualizados} tickets.")
    else:
        print("⚠️ No se encontraron entradas para actualizar.")

if __name__ == "__main__":
    with app.app_context():
        migrar_historial_tickets_a_iso()
