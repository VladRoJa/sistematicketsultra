# backend\app\config.py

from datetime import timedelta
import os

from dotenv import load_dotenv


# Cargar .env automáticamente según APP_ENV
APP_ENV = os.getenv("APP_ENV", "local")
ENV_FILE = ".env.local" if APP_ENV == "local" else ".env.docker"
load_dotenv(ENV_FILE)


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"❌ La variable de entorno {name} no está definida. Deteniendo la app."
        )
    return value


class Config:
    # Seguridad
    SECRET_KEY = _require_env("SECRET_KEY")
    JWT_SECRET_KEY = _require_env("JWT_SECRET_KEY")

    # JWT
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=45)
    JWT_TOKEN_LOCATION = ["headers"]
    JWT_HEADER_NAME = "Authorization"
    JWT_HEADER_TYPE = "Bearer"
    JWT_VERIFY_EXPIRATION = True

    # Base de datos
    SQLALCHEMY_DATABASE_URI = os.getenv("SQLALCHEMY_DATABASE_URI")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

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
    SESSION_COOKIE_SECURE = APP_ENV == "prod"
    SESSION_USE_SIGNER = True
    SESSION_KEY_PREFIX = "flask_session:"
    SESSION_FILE_DIR = "./flask_session"
    SESSION_FILE_THRESHOLD = 100
    SESSION_FILE_MODE = 0o600

    # Storage / Subida de archivos
    STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local")
    LOCAL_UPLOAD_DIR = os.getenv(
        "LOCAL_UPLOAD_DIR",
        "/home/adminrdp/sistematicketsultra/uploads/reportes",
    )
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://184.107.165.75")
    UPLOADS_PUBLIC_PATH = os.getenv("UPLOADS_PUBLIC_PATH", "/uploads/reportes")
    MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))

    # ──────────────────────────────────────
    # Warehouse / Gasca runtime config
    # ──────────────────────────────────────

    # Estrategia por defecto: single_report interno
    WAREHOUSE_GASCA_SCRIPT_STRATEGY = os.getenv(
        "WAREHOUSE_GASCA_SCRIPT_STRATEGY",
        "single_report",
    )

    # Legacy main runner (se conserva por compatibilidad/fallback)
    WAREHOUSE_GASCA_LEGACY_MAIN_MODULE = os.getenv(
        "WAREHOUSE_GASCA_LEGACY_MAIN_MODULE",
        "scripts.gasca_legacy_main",
    )
    WAREHOUSE_GASCA_LEGACY_MAIN_ENTRYPOINT = os.getenv(
        "WAREHOUSE_GASCA_LEGACY_MAIN_ENTRYPOINT",
        "main",
    )

    # Resolución de artifacts por carpeta/prefijo
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
        "kpi_ventas_nuevos_socios": os.getenv(
            "WAREHOUSE_GASCA_KPI_VENTAS_NUEVOS_OUTPUT_DIR",
            "data/kpi_ventas_nuevos_socios",
        ),
        "corte_caja": os.getenv(
            "WAREHOUSE_GASCA_CORTE_CAJA_OUTPUT_DIR",
            "data/corte_caja",
        ),
        "cargos_recurrentes": os.getenv(
            "WAREHOUSE_GASCA_CARGOS_RECURRENTES_OUTPUT_DIR",
            "data/cargos_recurrentes",
        ),
        "venta_total": os.getenv(
            "WAREHOUSE_GASCA_VENTA_TOTAL_OUTPUT_DIR",
            "data/venta_total",
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
        "kpi_ventas_nuevos_socios": os.getenv(
            "WAREHOUSE_GASCA_KPI_VENTAS_NUEVOS_FILENAME_PREFIX",
            "kpi_ventas_nuevos_socios_",
        ),
        "corte_caja": os.getenv(
            "WAREHOUSE_GASCA_CORTE_CAJA_FILENAME_PREFIX",
            "corte_caja",
        ),
        "cargos_recurrentes": os.getenv(
            "WAREHOUSE_GASCA_CARGOS_RECURRENTES_FILENAME_PREFIX",
            "cargos_recurrentes",
        ),
        "venta_total": os.getenv(
            "WAREHOUSE_GASCA_VENTA_TOTAL_FILENAME_PREFIX",
            "venta_total",
        ),
    }

    # Upload documental existente de Warehouse F1
    WAREHOUSE_EXISTING_UPLOAD_SERVICE_MODULE = os.getenv(
        "WAREHOUSE_EXISTING_UPLOAD_SERVICE_MODULE",
        "",
    )
    WAREHOUSE_EXISTING_UPLOAD_SERVICE_ENTRYPOINT = os.getenv(
        "WAREHOUSE_EXISTING_UPLOAD_SERVICE_ENTRYPOINT",
        "",
    )

    WAREHOUSE_INTERNAL_SYSTEM_USER_ID = int(
        os.getenv("WAREHOUSE_INTERNAL_SYSTEM_USER_ID", "0")
    )