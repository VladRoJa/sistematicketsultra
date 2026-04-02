# backend\app\config.py

from datetime import timedelta
import os
from dotenv import load_dotenv

# Cargar .env automáticamente según APP_ENV
app_env = os.getenv("APP_ENV", "local")

# 👇 ANTES usabas ".env.prod". Debe apuntar a .env.docker en no-local:
env_file = ".env.local" if app_env == "local" else ".env.docker"

load_dotenv(env_file)
print(f" APP_ENV={app_env} | .env cargado: {env_file}")

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

    print(" URI en config.py:", SQLALCHEMY_DATABASE_URI)

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
        "http://184.107.165.75:80",
        "http://192.168.100.53:4200",
        
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
    
    
    # ------- Storage / Subida de archivos -------
    STORAGE_BACKEND     = os.getenv('STORAGE_BACKEND', 'local')
    LOCAL_UPLOAD_DIR    = os.getenv('LOCAL_UPLOAD_DIR', '/home/adminrdp/sistematicketsultra/uploads/reportes')
    PUBLIC_BASE_URL     = os.getenv('PUBLIC_BASE_URL', 'http://184.107.165.75')
    UPLOADS_PUBLIC_PATH = os.getenv('UPLOADS_PUBLIC_PATH', '/uploads/reportes')
    MAX_UPLOAD_SIZE_MB  = int(os.getenv('MAX_UPLOAD_SIZE_MB', '10'))

    # ──────────────────────────────────────
    # Warehouse / Gasca runtime config
    # ──────────────────────────────────────

    # Estrategia actual: integrar el script legado multi-reporte sin reescribirlo todavía.
    WAREHOUSE_GASCA_SCRIPT_STRATEGY = os.getenv(
        "WAREHOUSE_GASCA_SCRIPT_STRATEGY",
        "single_report",
    )

    # Main legado de Gasca
    # AJUSTA estos 2 valores en .env.local o aquí mismo cuando confirmes la ruta real del script.
    WAREHOUSE_GASCA_LEGACY_MAIN_MODULE = os.getenv(
        "WAREHOUSE_GASCA_LEGACY_MAIN_MODULE",
        "",
    )
    WAREHOUSE_GASCA_LEGACY_MAIN_ENTRYPOINT = os.getenv(
        "WAREHOUSE_GASCA_LEGACY_MAIN_ENTRYPOINT",
        "main",
    )

    # Bridge de archivos generados por el script legado
    WAREHOUSE_GASCA_SCRIPT_RECENT_FILE_LOOKBACK_SECONDS = int(
        os.getenv("WAREHOUSE_GASCA_SCRIPT_RECENT_FILE_LOOKBACK_SECONDS", "3600")
    )

    WAREHOUSE_GASCA_SCRIPT_OUTPUT_DIRS = {
        "reporte_direccion": os.getenv(
            "WAREHOUSE_GASCA_REPORTE_DIRECCION_OUTPUT_DIR",
            "data/direccion_ingresos",
        ),
        "kpi_desempeno": os.getenv(
            "WAREHOUSE_GASCA_KPI_DESEMPENO_OUTPUT_DIR",
            "data/kpi_desempeno",
        ),
        "kpi_ventas_nuevos": os.getenv(
            "WAREHOUSE_GASCA_KPI_VENTAS_NUEVOS_OUTPUT_DIR",
            "data/kpi_ventas_nuevos_socios",
        ),
    }

    WAREHOUSE_GASCA_SCRIPT_FILENAME_PREFIXES = {
        "reporte_direccion": os.getenv(
            "WAREHOUSE_GASCA_REPORTE_DIRECCION_FILENAME_PREFIX",
            "ingresos_",
        ),
        "kpi_desempeno": os.getenv(
            "WAREHOUSE_GASCA_KPI_DESEMPENO_FILENAME_PREFIX",
            "kpi_desempeno_",
        ),
        "kpi_ventas_nuevos": os.getenv(
            "WAREHOUSE_GASCA_KPI_VENTAS_NUEVOS_FILENAME_PREFIX",
            "kpi_ventas_nuevos_socios_",
        ),
    }

    # Upload documental existente de Warehouse F1
    # Déjalos vacíos por ahora si aún no amarramos el servicio real.
    WAREHOUSE_EXISTING_UPLOAD_SERVICE_MODULE = os.getenv(
        "WAREHOUSE_EXISTING_UPLOAD_SERVICE_MODULE",
        "",
    )
    WAREHOUSE_EXISTING_UPLOAD_SERVICE_ENTRYPOINT = os.getenv(
        "WAREHOUSE_EXISTING_UPLOAD_SERVICE_ENTRYPOINT",
        "",
    )

    # ──────────────────────────────────────
    # Warehouse / Gasca legacy runner
    # ──────────────────────────────────────
    WAREHOUSE_GASCA_SCRIPT_STRATEGY = os.getenv(
        "WAREHOUSE_GASCA_SCRIPT_STRATEGY",
        "single_report",
    )

    WAREHOUSE_GASCA_LEGACY_MAIN_MODULE = os.getenv(
        "WAREHOUSE_GASCA_LEGACY_MAIN_MODULE",
        "scripts.gasca_legacy_main",
    )
    WAREHOUSE_GASCA_LEGACY_MAIN_ENTRYPOINT = os.getenv(
        "WAREHOUSE_GASCA_LEGACY_MAIN_ENTRYPOINT",
        "main",
    )

    WAREHOUSE_GASCA_SCRIPT_RECENT_FILE_LOOKBACK_SECONDS = int(
        os.getenv("WAREHOUSE_GASCA_SCRIPT_RECENT_FILE_LOOKBACK_SECONDS", "3600")
    )

    WAREHOUSE_GASCA_SCRIPT_OUTPUT_DIRS = {
        "reporte_direccion": os.getenv(
            "WAREHOUSE_GASCA_REPORTE_DIRECCION_OUTPUT_DIR",
            "data/direccion_ingresos",
        ),
        "kpi_desempeno": os.getenv(
            "WAREHOUSE_GASCA_KPI_DESEMPENO_OUTPUT_DIR",
            "data/kpi_desempeno",
        ),
        "kpi_ventas_nuevos": os.getenv(
            "WAREHOUSE_GASCA_KPI_VENTAS_NUEVOS_OUTPUT_DIR",
            "data/kpi_ventas_nuevos_socios",
        ),
    }

    WAREHOUSE_GASCA_SCRIPT_FILENAME_PREFIXES = {
        "reporte_direccion": os.getenv(
            "WAREHOUSE_GASCA_REPORTE_DIRECCION_FILENAME_PREFIX",
            "ingresos_",
        ),
        "kpi_desempeno": os.getenv(
            "WAREHOUSE_GASCA_KPI_DESEMPENO_FILENAME_PREFIX",
            "kpi_desempeno_",
        ),
        "kpi_ventas_nuevos": os.getenv(
            "WAREHOUSE_GASCA_KPI_VENTAS_NUEVOS_FILENAME_PREFIX",
            "kpi_ventas_nuevos_socios_",
        ),
    }
    
    WAREHOUSE_INTERNAL_SYSTEM_USER_ID = int(
        os.getenv("WAREHOUSE_INTERNAL_SYSTEM_USER_ID", "0")
    )