#app\utils\error_handler.py

import logging
import traceback
from flask import jsonify, request
from datetime import datetime
import os

LOG_FILE = os.path.join(os.getcwd(), "logs", "errores.log")

def manejar_error(e, contexto=""):
    error_trace = traceback.format_exc()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Configurar logging (si no está ya configurado en app principal)
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.ERROR,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    # Registrar en logging con traza
    logging.exception(f"Error en {contexto} - Ruta: {request.path}")

    # En desarrollo, también mostrar en consola y retornar detalles
    if os.getenv("APP_ENV", "local"):
        print("🔴 ERROR DETECTADO")
        print(f"🕒 {timestamp}")
        print(f"📍 Contexto: {contexto}")
        print(f"📄 Ruta: {request.path}")
        print(f"🧨 Mensaje: {str(e)}")
        print(f"🧾 Traza:\n{error_trace}")

        return jsonify({
            "mensaje": "Error interno en el servidor",
            "detalle": str(e),
            "contexto": contexto,
            "ruta": request.path,
            "hora": timestamp
        }), 500

    # En producción, respuesta genérica sin detalles
    return jsonify({
        "mensaje": "Ocurrió un error interno. Por favor, inténtalo más tarde."
    }), 500
