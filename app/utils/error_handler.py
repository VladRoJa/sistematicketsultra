#C:\Users\Vladimir\Documents\Sistema tickets\app\utils\error_handler.py

import traceback
from flask import jsonify, request
from datetime import datetime
import os

LOG_FILE = os.path.join(os.getcwd(), "logs", "errores.log")

def manejar_error(e, contexto=""):
    error_trace = traceback.format_exc()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 🖨 Consola en desarrollo
    print("🔴 ERROR DETECTADO")
    print(f"🕒 {timestamp}")
    print(f"📍 Contexto: {contexto}")
    print(f"📄 Ruta: {request.path}")
    print(f"🧨 Mensaje: {str(e)}")
    print(f"🧾 Traza:\n{error_trace}")

    # 📁 Guardar en archivo logs/errores.log
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n[{timestamp}] ERROR en {contexto} - {request.path}\n")
            f.write(f"Mensaje: {str(e)}\n")
            f.write(f"Traza:\n{error_trace}\n")
    except Exception as log_err:
        print(f"⚠️ Error al escribir log: {log_err}")

    # 🧃 Respuesta JSON genérica para el frontend
    return jsonify({
        "mensaje": "Error interno en el servidor",
        "detalle": str(e),
        "contexto": contexto,
        "ruta": request.path,
        "hora": timestamp
    }), 500
