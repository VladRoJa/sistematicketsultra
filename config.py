# C:\Users\Vladimir\Documents\Sistema tickets\config.py

# -------------------------------------------------------------------------------
# CONFIGURACIÓN GLOBAL DE LA APLICACIÓN
# -------------------------------------------------------------------------------

from datetime import timedelta
import os
from urllib.parse import quote_plus

# -------------------------------------------------------------------------------
# CLASE: Config (Configuraciones de Flask y SQLAlchemy)
# -------------------------------------------------------------------------------

class Config:
    # Seguridad
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'Sp@ces2329@'
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'tu_llave_secreta_super_segura'

    # JWT Settings
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_TOKEN_LOCATION = ['headers']
    JWT_HEADER_NAME = 'Authorization'
    JWT_HEADER_TYPE = 'Bearer'

    # Base de datos
    DB_HOST = os.environ.get('DB_HOST') or 'localhost'
    DB_USER = os.environ.get('DB_USER') or 'root'
    DB_PASSWORD = os.environ.get('DB_PASSWORD') or 'Sp@ces2329@'
    DB_NAME = os.environ.get('DB_NAME') or 'sistema_tickets'
    
    SQLALCHEMY_DATABASE_URI = (
        f"mysql://{DB_USER}:{quote_plus(DB_PASSWORD)}@{DB_HOST}/{DB_NAME}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # CORS
    CORS_ORIGINS = ["http://localhost:4200"]

    # Sesiones
    SESSION_PERMANENT = True
    SESSION_TYPE = "filesystem"
    SESSION_COOKIE_NAME = "session"
    SESSION_COOKIE_SECURE = False  # 🔥 Ponlo en True si implementas HTTPS
    SESSION_USE_SIGNER = True
    SESSION_KEY_PREFIX = "flask_session:"
    SESSION_FILE_DIR = "./flask_session"
    SESSION_FILE_THRESHOLD = 100
    SESSION_FILE_MODE = 600
    
