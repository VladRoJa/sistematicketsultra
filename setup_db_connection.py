# C:\Users\Vladimir\Documents\Sistema tickets\setup_db_connection.py

# -------------------------------------------------------------------------------
# CONEXIÓN DIRECTA A BASE DE DATOS para scripts de inicialización
# -------------------------------------------------------------------------------

import mysql.connector
from config import Config

def get_setup_db_connection():
    """🔹 Devuelve una conexión directa (pura) a la base de datos."""
    return mysql.connector.connect(
        host=Config.DB_HOST,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        database=Config.DB_NAME
    )
