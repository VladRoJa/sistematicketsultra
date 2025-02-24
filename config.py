#config.py

from datetime import timedelta
import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'Sp@ces2329@'
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    DB_HOST = os.environ.get('DB_HOST') or 'localhost'
    DB_USER = os.environ.get('DB_USER') or 'root'
    DB_PASSWORD = os.environ.get('DB_PASSWORD') or 'Sp@ces2329@'
    DB_NAME = os.environ.get('DB_NAME') or 'sistema_tickets'
    
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'tu_llave_secreta_super_segura'
    JWT_TOKEN_LOCATION = ['headers']  # 🔥 Indicar que el token está en los headers
    JWT_HEADER_NAME = 'Authorization'  # 🔥 Asegurar que el nombre del encabezado es correcto
    JWT_HEADER_TYPE = 'Bearer'  # 🔥 Debe ser "Bearer"
    
    # Construye la URI de la base de datos para SQLAlchemy
    SQLALCHEMY_DATABASE_URI = f'mysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    CORS_ORIGINS = ["http://localhost:4200"]
    
    SESSION_PERMANENT = True
    SESSION_TYPE = "filesystem"
    SESSION_COOKIE_NAME = "session"
    SESSION_COOKIE_SECURE = False  # Si usas HTTPS, ponlo en True
    SESSION_USE_SIGNER = True
    SESSION_KEY_PREFIX = "flask_session:"
    SESSION_FILE_DIR = "./flask_session"
    SESSION_FILE_THRESHOLD = 100
    SESSION_FILE_MODE = 600
