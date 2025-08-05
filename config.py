# config.py

from datetime import timedelta
import os
from dotenv import load_dotenv

# 🔧 Cargar el .env automáticamente desde dentro de la clase Config
class Config:
    # Forzar carga del entorno según APP_ENV
    app_env = os.getenv("APP_ENV", "local")
    env_file = ".env.local" if app_env == "local" else ".env.prod"
    load_dotenv(env_file)

    # Seguridad
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'Sp@ces2329@'
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'tu_llave_secreta_super_segura'

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
        "http://localhost:4200",                            
        "https://sistematicketsultra.onrender.com",          
        "https://sistematicketsultra-backend.onrender.com"   
    ]

    # Sesiones
    SESSION_PERMANENT = True
    SESSION_TYPE = "filesystem"
    SESSION_COOKIE_NAME = "session"
    SESSION_COOKIE_SECURE = False
    SESSION_USE_SIGNER = True
    SESSION_KEY_PREFIX = "flask_session:"
    SESSION_FILE_DIR = "./flask_session"
    SESSION_FILE_THRESHOLD = 100
    SESSION_FILE_MODE = 600

    #Cloudinary
    CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME')
    CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY')
    CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET')

