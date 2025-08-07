# config.py

from datetime import timedelta
import os
from dotenv import load_dotenv

# Cargar .env automáticamente según APP_ENV
app_env = os.getenv("APP_ENV", "local")
env_file = ".env.local" if app_env == "local" else ".env.prod"
load_dotenv(env_file)

# 🚨 Validar claves secretas obligatorias
SECRET_KEY = os.environ.get('SECRET_KEY')
JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY')
if not SECRET_KEY:
    raise RuntimeError("❌ La variable de entorno SECRET_KEY no está definida. Deteniendo la app.")
if not JWT_SECRET_KEY:
    raise RuntimeError("❌ La variable de entorno JWT_SECRET_KEY no está definida. Deteniendo la app.")

class Config:
    # Seguridad
    SECRET_KEY = SECRET_KEY
    JWT_SECRET_KEY = JWT_SECRET_KEY

    # JWT Settings
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=45)
    JWT_TOKEN_LOCATION = ['headers']
    JWT_HEADER_NAME = 'Authorization'
    JWT_HEADER_TYPE = 'Bearer' 
    JWT_VERIFY_EXPIRATION = True

    # Base de datos
    SQLALCHEMY_DATABASE_URI = os.getenv('SQLALCHEMY_DATABASE_URI')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    print("🔧 URI en config.py:", SQLALCHEMY_DATABASE_URI)

    # CORS
    CORS_ORIGINS = [
        "http://localhost",
        "http://localhost:80",
        "http://localhost:4200",
        "http://127.0.0.1",
        "http://127.0.0.1:80",
        "http://127.0.0.1:4200",
        "https://sistematicketsultra.onrender.com",
        "https://sistematicketsultra-backend.onrender.com",
        "http://184.107.165.75",
        "http://184.107.165.75:80"
        
    ]


    # Sesiones
    SESSION_PERMANENT = True
    SESSION_TYPE = "filesystem" 
    SESSION_COOKIE_NAME = "session"
    SESSION_COOKIE_SECURE = (app_env == "prod")  # True solo en prod, False en local
    SESSION_USE_SIGNER = True
    SESSION_KEY_PREFIX = "flask_session:"
    SESSION_FILE_DIR = "./flask_session"
    SESSION_FILE_THRESHOLD = 100
    SESSION_FILE_MODE = 600

    # Cloudinary
    CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME')
    CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY')
    CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET')


    # Sesiones
    SESSION_PERMANENT = True
    SESSION_TYPE = "filesystem" 
    SESSION_COOKIE_NAME = "session"
    SESSION_COOKIE_SECURE = (app_env == "prod")  # True solo en prod, False en local
    SESSION_USE_SIGNER = True
    SESSION_KEY_PREFIX = "flask_session:"
    SESSION_FILE_DIR = "./flask_session"
    SESSION_FILE_THRESHOLD = 100
    SESSION_FILE_MODE = 600

    # Cloudinary
    CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME')
    CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY')
    CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET')
